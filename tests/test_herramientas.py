"""Tests for the agent tools using httpx.MockTransport.

Run with:  uv run pytest tests/test_herramientas.py
"""

import asyncio

import httpx

from agent.herramientas import buscar_huecos, crear_cita

HUECOS = [
    {"id": 1, "inicio": "2026-11-02T09:00:00", "medico": "Dr. Lopez", "libre": True},
    {"id": 2, "inicio": "2026-11-03T10:30:00", "medico": "Dr. Ruiz", "libre": True},
    {"id": 3, "inicio": "2026-11-03T11:00:00", "medico": "Dr. Lopez", "libre": True},
]


async def ejecutar(handler, funcion, *args):
    transporte = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://api", transport=transporte) as c:
        return await funcion(c, *args)


def test_filtra_por_medico():
    r = asyncio.run(ejecutar(lambda req: httpx.Response(200, json=HUECOS), buscar_huecos, "ruiz"))
    assert r["ok"] and [h["hueco_id"] for h in r["huecos"]] == [2]


def test_filtra_por_medico_con_titulo_largo():
    # The model sometimes says "Doctor Lopez" instead of "Dr. Lopez"
    r = asyncio.run(
        ejecutar(lambda req: httpx.Response(200, json=HUECOS), buscar_huecos, "Doctor Lopez")
    )
    assert [h["hueco_id"] for h in r["huecos"]] == [1, 3]


def test_filtra_por_fecha():
    r = asyncio.run(
        ejecutar(lambda req: httpx.Response(200, json=HUECOS), buscar_huecos, None, "2026-11-03")
    )
    assert [h["hueco_id"] for h in r["huecos"]] == [2, 3]


def test_reserva_correcta():
    def handler(req):
        assert req.url.path == "/citas"
        return httpx.Response(201, json={"id": 9, "hueco_id": 1, "paciente": "Ana Gil"})

    r = asyncio.run(ejecutar(handler, crear_cita, 1, "Ana Gil", "revision"))
    assert r["ok"] and r["cita"]["id"] == 9


def test_conflicto_hueco_ocupado():
    r = asyncio.run(
        ejecutar(
            lambda req: httpx.Response(409, json={"detail": "El hueco ya está ocupado"}),
            crear_cita, 1, "Ana Gil", None,
        )
    )
    assert r["ok"] is False and r["error"] == "hueco_ocupado"


def test_api_caida():
    def caida(req):
        raise httpx.ConnectError("sin conexión")

    assert asyncio.run(ejecutar(caida, buscar_huecos))["error"] == "agenda_no_disponible"
    assert asyncio.run(ejecutar(caida, crear_cita, 1, "Ana Gil"))["error"] == "agenda_no_disponible"


# ---------------------------------------------------------------- confirmation guard

from agent import herramientas
from agent.confirmacion import ERROR, check_confirmation

HUECOS_TOOL = {
    "role": "tool",
    "tool_call_id": "c1",
    "content": '{"ok": true, "huecos": [{"hueco_id": 8, "medico": "Dr. Lopez", '
    '"inicio": "2026-11-24T09:30:00Z", "cuando": "Tuesday November 24 at 09:30"}]}',
}
LEIDA = "Dr. Lopez on Tuesday at nine thirty for Maria Garcia. Shall I book it?"


def conversacion(ana: str = LEIDA, paciente: str = "Yes, that's right.") -> list[dict]:
    return [
        {"role": "system", "content": "You are Ana."},
        {"role": "user", "content": "I need to see Dr. Lopez."},
        {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "consultar_huecos"}}]},
        HUECOS_TOOL,
        {"role": "assistant", "content": ana},
        {"role": "user", "content": paciente},
        {"role": "assistant", "content": "Great, booking it now."},  # same response as the call
    ]


def args(**extra) -> dict:
    base = {"hueco_id": 8, "paciente": "Maria Garcia", "confirmado_por_paciente": True,
            "frase_del_paciente": "Yes, that's right"}
    return {**base, **extra}


def test_guarda_deja_reservar_con_si_tras_leer_los_datos():
    assert check_confirmation(args(), conversacion()) is None


def test_guarda_exige_la_marca_de_confirmacion():
    r = check_confirmation(args(confirmado_por_paciente=False), conversacion())
    assert r["ok"] is False and r["error"] == ERROR


def test_guarda_rechaza_una_frase_que_el_paciente_no_dijo():
    # The model claims a yes that is not in the caller's last turn
    r = check_confirmation(args(frase_del_paciente="Yes, book it"), conversacion())
    assert r["error"] == ERROR and "did not say" in r["mensaje"]


def test_guarda_rechaza_si_el_paciente_duda():
    r = check_confirmation(
        args(frase_del_paciente="ok"), conversacion(paciente="Ok, but wait, let me think about it.")
    )
    assert r["error"] == ERROR and "clear yes" in r["mensaje"]


def test_guarda_rechaza_si_ana_no_repite_medico_y_hora():
    r = check_confirmation(args(), conversacion(ana="Can I have your full name, please?"))
    assert r["error"] == ERROR and "the doctor and the time" in r["mensaje"]


def test_guarda_no_vale_un_si_anterior_a_la_lectura():
    # "Yes" to the slot earlier, then the name; the last turn is the name, not a yes
    r = check_confirmation(
        args(frase_del_paciente="Maria Garcia"),
        conversacion(ana="And your full name?", paciente="Maria Garcia."),
    )
    assert r["error"] == ERROR


def test_guarda_acepta_hora_en_cifras():
    ana = "Dr. Lopez, Tuesday at 9:30, for Maria Garcia. Is that correct?"
    assert check_confirmation(args(), conversacion(ana=ana)) is None


class _Contexto:
    def __init__(self, mensajes):
        self.mensajes = mensajes

    def get_messages(self):
        return self.mensajes


class _Params:
    def __init__(self, arguments, mensajes):
        self.arguments = arguments
        self.context = _Contexto(mensajes)
        self.resultado = None

    async def result_callback(self, resultado):
        self.resultado = resultado


def test_handler_no_llama_a_la_api_si_la_guarda_rechaza(monkeypatch):
    llamadas = []
    monkeypatch.setattr(herramientas, "crear_cita", lambda *a, **k: llamadas.append(a))
    p = _Params(args(confirmado_por_paciente=False), conversacion())
    asyncio.run(herramientas.handler_reservar_cita(p))
    assert p.resultado["error"] == ERROR and llamadas == []


def test_handler_reserva_si_la_guarda_deja(monkeypatch):
    async def crear(cliente, hueco_id, paciente, motivo=None):
        return {"ok": True, "cita": {"id": 1, "hueco_id": hueco_id, "paciente": paciente}}

    monkeypatch.setattr(herramientas, "crear_cita", crear)
    p = _Params(args(), conversacion())
    asyncio.run(herramientas.handler_reservar_cita(p))
    assert p.resultado["ok"] is True and p.resultado["cita"]["hueco_id"] == 8
