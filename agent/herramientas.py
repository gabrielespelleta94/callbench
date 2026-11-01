"""Agent tools: look up slots and book appointments through the clinic API.

The HTTP logic lives in plain functions (they take the httpx client and return a
dict); the Pipecat handlers only call them. Nothing raises exceptions into the pipeline.
"""

import os
from datetime import datetime

import httpx
from loguru import logger

from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

TIMEOUT_SEGUNDOS = 5.0
MAX_HUECOS = 6  # few slots: the LLM reads them out loud

ESQUEMA_CONSULTAR = FunctionSchema(
    name="consultar_huecos",
    description="List the free appointment slots. Optionally filter by doctor and/or by date.",
    properties={
        "medico": {"type": "string", "description": "Doctor name, e.g. 'Dr. Lopez'. Optional."},
        "fecha": {"type": "string", "description": "Date as YYYY-MM-DD. Optional."},
    },
    required=[],
)

ESQUEMA_RESERVAR = FunctionSchema(
    name="reservar_cita",
    description=(
        "Book an appointment in a slot returned by consultar_huecos. "
        "Needs the patient's full name."
    ),
    properties={
        "hueco_id": {"type": "integer", "description": "Slot id from consultar_huecos."},
        "paciente": {"type": "string", "description": "Patient's full name."},
        "motivo": {"type": "string", "description": "Reason for the visit. Optional."},
    },
    required=["hueco_id", "paciente"],
)

AGENDA_NO_DISPONIBLE = {
    "ok": False,
    "error": "agenda_no_disponible",
    "mensaje": "The scheduling system is not available right now. Apologise and offer to try again.",
}


def url_base() -> str:
    return os.getenv("CLINICA_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=url_base(), timeout=TIMEOUT_SEGUNDOS)


def _dia_legible(inicio: str) -> str:
    try:
        return datetime.fromisoformat(inicio).strftime("%A %B %d at %H:%M")
    except ValueError:
        return inicio


async def buscar_huecos(
    cliente: httpx.AsyncClient, medico: str | None = None, fecha: str | None = None
) -> dict:
    """Fetch the free slots and filter them client-side by doctor and date."""
    try:
        resp = await cliente.get("/huecos", params={"solo_libres": "true"})
        resp.raise_for_status()
        huecos = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"consultar_huecos falló: {exc!r}")
        return AGENDA_NO_DISPONIBLE

    if medico:
        huecos = [h for h in huecos if medico.strip().lower() in h["medico"].lower()]
    if fecha:
        huecos = [h for h in huecos if h["inicio"].startswith(fecha.strip())]
    huecos = sorted(huecos, key=lambda h: h["inicio"])[:MAX_HUECOS]

    if not huecos:
        return {"ok": True, "huecos": [], "mensaje": "No free slots match that request."}
    return {
        "ok": True,
        "huecos": [
            {
                "hueco_id": h["id"],
                "medico": h["medico"],
                "inicio": h["inicio"],
                "cuando": _dia_legible(h["inicio"]),
            }
            for h in huecos
        ],
    }


async def crear_cita(
    cliente: httpx.AsyncClient, hueco_id: int, paciente: str, motivo: str | None = None
) -> dict:
    """Book the appointment and translate HTTP errors into something the LLM can say."""
    cuerpo = {"hueco_id": hueco_id, "paciente": paciente}
    if motivo:
        cuerpo["motivo"] = motivo
    try:
        resp = await cliente.post("/citas", json=cuerpo)
    except httpx.HTTPError as exc:
        logger.warning(f"reservar_cita falló: {exc!r}")
        return AGENDA_NO_DISPONIBLE

    if resp.status_code == 201:
        try:
            return {"ok": True, "cita": resp.json()}
        except ValueError:
            return AGENDA_NO_DISPONIBLE
    if resp.status_code == 404:
        return {"ok": False, "error": "hueco_no_existe",
                "mensaje": "That slot does not exist. Check the available slots again."}
    if resp.status_code == 409:
        return {"ok": False, "error": "hueco_ocupado",
                "mensaje": "That slot was just taken. Offer another slot."}
    if resp.status_code == 422:
        return {"ok": False, "error": "datos_invalidos",
                "mensaje": "The data is not valid. Ask the caller for their full name again."}
    logger.warning(f"reservar_cita: estado inesperado {resp.status_code}")
    return AGENDA_NO_DISPONIBLE


# Pipecat handlers: open the client, call the logic and return the result to the LLM
async def handler_consultar_huecos(params: FunctionCallParams):
    try:
        args = params.arguments
        async with _cliente() as cliente:
            resultado = await buscar_huecos(cliente, args.get("medico"), args.get("fecha"))
    except Exception as exc:  # never break the pipeline
        logger.exception(exc)
        resultado = AGENDA_NO_DISPONIBLE
    await params.result_callback(resultado)


async def handler_reservar_cita(params: FunctionCallParams):
    try:
        args = params.arguments
        async with _cliente() as cliente:
            resultado = await crear_cita(
                cliente, int(args["hueco_id"]), str(args["paciente"]), args.get("motivo")
            )
    except Exception as exc:
        logger.exception(exc)
        resultado = AGENDA_NO_DISPONIBLE
    await params.result_callback(resultado)


def registrar_herramientas(llm) -> ToolsSchema:
    """Register the handlers on the LLM and return the schema for the context."""
    llm.register_function("consultar_huecos", handler_consultar_huecos)
    llm.register_function("reservar_cita", handler_reservar_cita)
    return ToolsSchema(standard_tools=[ESQUEMA_CONSULTAR, ESQUEMA_RESERVAR])
