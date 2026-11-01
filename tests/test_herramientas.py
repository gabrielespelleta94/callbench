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
