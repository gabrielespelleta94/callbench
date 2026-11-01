"""Clinic API tests against a real Postgres. Run with:  uv run pytest"""

import asyncio

import httpx

from tests.conftest import SEMILLA


def test_salud(cliente):
    assert cliente.get("/salud").json() == {"estado": "ok"}


def test_solo_lista_huecos_libres(cliente):
    ids = [h["id"] for h in cliente.get("/huecos").json()]
    assert ids == [1, 2, 4]
    assert len(SEMILLA) == 4  # slot 3 is seeded as taken


def test_reservar_devuelve_201_y_ocupa_el_hueco(cliente):
    r = cliente.post("/citas", json={"hueco_id": 1, "paciente": "John Smith"})
    assert r.status_code == 201
    assert r.json()["medico"] == "Dr. Lopez"
    assert 1 not in [h["id"] for h in cliente.get("/huecos").json()]
    # The appointment is stored and can be read back
    assert cliente.get(f"/citas/{r.json()['id']}").json()["paciente"] == "John Smith"


def test_doble_reserva_devuelve_409(cliente):
    cliente.post("/citas", json={"hueco_id": 2, "paciente": "John Smith"})
    r = cliente.post("/citas", json={"hueco_id": 2, "paciente": "Mary Jones"})
    assert r.status_code == 409
    assert r.json()["detail"] == "El hueco ya está ocupado"


def test_hueco_inexistente_devuelve_404(cliente):
    r = cliente.post("/citas", json={"hueco_id": 99, "paciente": "John Smith"})
    assert r.status_code == 404
    assert r.json()["detail"] == "El hueco no existe"


def test_datos_invalidos_devuelven_422(cliente):
    # Missing patient: Pydantic rejects it before reaching crear_cita
    assert cliente.post("/citas", json={"hueco_id": 1}).status_code == 422


def test_reservas_simultaneas_del_mismo_hueco(app_con_bd):
    """Two simultaneous requests for the same slot: one wins (201), the other loses (409)."""

    async def reservar_a_la_vez():
        transporte = httpx.ASGITransport(app=app_con_bd)
        async with httpx.AsyncClient(transport=transporte, base_url="http://test") as c:
            return await asyncio.gather(
                c.post("/citas", json={"hueco_id": 1, "paciente": "John Smith"}),
                c.post("/citas", json={"hueco_id": 1, "paciente": "Mary Jones"}),
            )

    respuestas = asyncio.run(reservar_a_la_vez())
    assert sorted(r.status_code for r in respuestas) == [201, 409]
