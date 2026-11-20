"""Tests for the deterministic asserts and their place in the report.

Fixtures in tests/fixtures/vuelta_ejemplo/ are real calls copied from earlier rounds and trimmed
(only the transcript and the last LLM context line of the bot log; personas are fictional).
Each results.jsonl row keeps its origin in "origen".

Run with:  uv run pytest tests/test_asserts.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

import asserts as asr
import informe

VUELTA = Path(__file__).resolve().parent / "fixtures" / "vuelta_ejemplo"
CONFIG = asr.cargar_config()


def filas() -> dict[tuple[str, int], dict]:
    return {(f["scenario"], f["attempt"]): f for f in informe.leer_filas(VUELTA / "results.jsonl")}


def llamada(escenario: str, intento: int) -> asr.Llamada:
    resultado = asr.cargar_llamada(filas()[(escenario, intento)], VUELTA)
    assert resultado is not None
    return resultado


def por_nombre(lista: list[asr.Assert]) -> dict[str, asr.Assert]:
    return {a.nombre: a for a in lista}


CITA = "cita_dr_lopez/reserva_real"
DUDA = "duda_y_pide_pensarlo/no_reservar_sin_confirmar"
MEDICO = "medico_inexistente/dr_fernando"


# ---------------------------------------------------------------- loading


def test_resultados_de_herramientas_salen_del_log():
    ll = llamada(CITA, 2)
    herramientas = [m for m in ll.mensajes if m["role"] == "tool_call"]
    assert [m["name"] for m in herramientas] == ["consultar_huecos", "reservar_cita"]
    assert herramientas[0]["resultado"]["huecos"], "consultar_huecos sin huecos"
    assert herramientas[1]["resultado"]["cita"]["paciente"] == "Maria Garcia"


def test_log_con_codigos_ansi_y_basura():
    linea = "x | Generating LLM response [{'role': 'user', 'content': 'hi'}]\x1b[0m"
    assert asr.contexto_llm(linea) == [{"role": "user", "content": "hi"}]
    assert asr.contexto_llm("nada que ver") is None
    assert asr.contexto_llm("Generating LLM response [roto") is None


def test_sin_transcripcion_es_no_evaluable():
    lista = asr.evaluar(None, None, CONFIG, CITA)
    assert [a.nombre for a in lista] == CONFIG["escenarios"][CITA]["asserts"]
    assert all(a.aprobado is None for a in lista)
    assert asr.veredicto(lista) == "n/a"


def test_escenario_sin_config_usa_defecto():
    cfg = asr.config_escenario("nuevo/escenario", CONFIG)
    assert cfg["asserts"] == CONFIG["defecto"]["asserts"]


# ---------------------------------------------------------------- the real finding


def test_caso_real_reserva_sin_confirmacion_que_el_juez_aprobo():
    """base #1 (2026-11-01): Ana booked without repeating details or a yes; judge P(yes)=0.98."""
    fila = filas()[(CITA, 1)]
    assert fila["passed"] and fila["probabilities"]["yes"] >= 0.98
    r = por_nombre(asr.evaluar(llamada(CITA, 1), None, CONFIG))
    assert r["confirmacion_antes_de_reservar"].aprobado is False
    assert "no repite" in r["confirmacion_antes_de_reservar"].motivo
    assert r["orden_herramientas"].aprobado is False  # asked the name before consultar_huecos
    assert r["reserva_correcta"].aprobado is True  # the booking itself was valid
    assert asr.veredicto(list(r.values())) == "suspenso"


def test_reserva_a_nombre_inventado_sin_confirmar():
    """nuevo medico_inexistente #3: booked for 'Maria Garcia' (caller is Pedro) and the judge passed."""
    assert filas()[(MEDICO, 1)]["passed"]
    r = por_nombre(asr.evaluar(llamada(MEDICO, 1), None, CONFIG))
    assert r["confirmacion_antes_de_reservar"].aprobado is False
    assert r["no_inventa"].aprobado is True  # "no slots with Doctor Fernando" echoes the caller


# ---------------------------------------------------------------- booking against the database


def _bd_con_la_cita(ll: asr.Llamada, **cambios) -> dict:
    reserva = next(m for m in ll.mensajes if m.get("name") == "reservar_cita")
    cita = reserva["resultado"]["cita"]
    fila_cita = {
        "id": cita["id"],
        "hueco_id": cita["hueco_id"],
        "paciente": cita["paciente"],
        **cambios,
    }
    hueco = {
        "id": cita["hueco_id"],
        "inicio": cita["inicio"],
        "medico": cita["medico"],
        "libre": False,
    }
    return {"huecos": [hueco], "citas": [fila_cita]}


def test_reserva_bien_confirmada_aprueba_todo():
    ll = llamada(CITA, 2)
    lista = asr.evaluar(ll, _bd_con_la_cita(ll), CONFIG)
    assert all(a.aprobado for a in lista), [a for a in lista if not a.aprobado]
    assert "en BD" in por_nombre(lista)["reserva_correcta"].motivo


def test_reserva_que_no_esta_en_bd_suspende():
    ll = llamada(CITA, 2)
    r = por_nombre(asr.evaluar(ll, {"huecos": [], "citas": []}, CONFIG))
    assert r["reserva_correcta"].aprobado is False and "no esta" in r["reserva_correcta"].motivo


def test_reserva_en_bd_con_otro_paciente_suspende():
    ll = llamada(CITA, 2)
    r = por_nombre(asr.evaluar(ll, _bd_con_la_cita(ll, paciente="Otra Persona"), CONFIG))
    assert r["reserva_correcta"].aprobado is False


def test_reserva_con_paciente_o_medico_equivocado():
    ll = llamada(CITA, 2)
    cfg = {"paciente": "Pedro Sanchez"}
    assert asr.reserva_correcta(ll, cfg, None).aprobado is False
    assert asr.reserva_correcta(ll, {"medico": "Dr. Ruiz"}, None).aprobado is False


def test_duda_sin_reserva_aprueba_y_con_cita_en_bd_suspende():
    ll = llamada(DUDA, 1)
    assert asr.sin_reserva(ll, {"paciente": "Carlos Ruiz"}, None).aprobado is True
    bd = {"huecos": [], "citas": [{"id": 9, "hueco_id": 2, "paciente": "carlos  ruiz"}]}
    resultado = asr.sin_reserva(ll, {"paciente": "Carlos Ruiz"}, bd)
    assert resultado.aprobado is False and "1 cita" in resultado.motivo


def test_duda_que_reservo_suspende():
    r = por_nombre(asr.evaluar(llamada(DUDA, 2), None, CONFIG))
    assert r["sin_reserva"].aprobado is False


# ---------------------------------------------------------------- synthetic calls


def _sintetica(*mensajes) -> asr.Llamada:
    return asr.Llamada("x/y", list(mensajes))


HUECOS = {
    "ok": True,
    "huecos": [
        {"hueco_id": 2, "medico": "Dr. Lopez", "inicio": "2026-11-03T09:30:00Z"},
        {"hueco_id": 6, "medico": "Dr. Ruiz", "inicio": "2026-11-03T16:30:00Z"},
    ],
}
CONSULTA = {"role": "tool_call", "name": "consultar_huecos", "arguments": {}, "resultado": HUECOS}
RESERVA = {
    "role": "tool_call",
    "name": "reservar_cita",
    "arguments": {"hueco_id": 2, "paciente": "Maria Garcia"},
    "resultado": {
        "ok": True,
        "cita": {"id": 1, "hueco_id": 2, "medico": "Dr. Lopez", "inicio": "2026-11-03T09:30:00Z"},
    },
}


def test_inventa_medico():
    ll = _sintetica(
        CONSULTA, {"role": "assistant", "content": "Dr. Martinez can see you at nine thirty."}
    )
    r = asr.no_inventa(ll, {"medicos": ["Dr. Lopez", "Dr. Ruiz"]}, None)
    assert r.aprobado is False and "martinez" in r.motivo


def test_inventa_hora():
    ll = _sintetica(
        CONSULTA, {"role": "assistant", "content": "Dr. Lopez is free at eleven in the morning."}
    )
    r = asr.no_inventa(ll, {"medicos": ["Dr. Lopez"]}, None)
    assert r.aprobado is False and "11:00" in r.motivo


def test_hora_antes_de_consultar_es_inventada():
    ll = _sintetica({"role": "assistant", "content": "How about Tuesday at nine thirty?"}, CONSULTA)
    assert asr.no_inventa(ll, {}, None).aprobado is False


def test_horas_devueltas_en_varias_formas_no_son_inventadas():
    texto = "Dr. Lopez at 9:30 or Dr. Ruiz at half past four in the afternoon."
    ll = _sintetica(CONSULTA, {"role": "assistant", "content": texto})
    assert asr.no_inventa(ll, {"medicos": []}, None).aprobado is True


def test_reservar_antes_de_consultar():
    ll = _sintetica(RESERVA, CONSULTA)
    assert asr.orden_herramientas(ll, {}, None).aprobado is False


def test_confirmacion_correcta():
    ll = _sintetica(
        CONSULTA,
        {
            "role": "assistant",
            "content": "Just to confirm: Dr. Lopez on Tuesday at nine thirty. Shall I book it?",
        },
        {"role": "user", "content": "Yes, please."},
        RESERVA,
    )
    assert asr.confirmacion_antes_de_reservar(ll, {}, None).aprobado is True


def test_confirmacion_con_duda_suspende():
    ll = _sintetica(
        CONSULTA,
        {"role": "assistant", "content": "Dr. Lopez on Tuesday at nine thirty, shall I book it?"},
        {"role": "user", "content": "I'm not sure, let me think about it."},
        RESERVA,
    )
    r = asr.confirmacion_antes_de_reservar(ll, {}, None)
    assert r.aprobado is False and "no dijo que si" in r.motivo


def test_confirmacion_con_otra_hora_suspende():
    ll = _sintetica(
        CONSULTA,
        {"role": "assistant", "content": "Dr. Lopez on Tuesday at ten, shall I book it?"},
        {"role": "user", "content": "Yes."},
        RESERVA,
    )
    assert asr.confirmacion_antes_de_reservar(ll, {}, None).aprobado is False


# ---------------------------------------------------------------- text helpers


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Tuesday at nine thirty", {(9, 30)}),
        ("ten o’clock or ten‑thirty", {(10, 0), (10, 30)}),
        ("at 4:30 PM", {(4, 30)}),
        ("half past four in the afternoon", {(4, 30)}),
        ("at nine or ten in the morning", {(9, 0), (10, 0)}),
        ("or one of the other doctors", set()),
        ("November 3rd", set()),
    ],
)
def test_menciones_hora(texto, esperado):
    assert asr.menciones_hora(texto) == esperado


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Yes, please book that for me.", True),
        ("That's fine, Monday at ten works for me.", True),
        ("Maria Garcia.", False),
        ("I'm not sure, I need to check my calendar.", False),
        ("Sure, maybe... what do you have tomorrow?", False),
    ],
)
def test_es_afirmativo(texto, esperado):
    assert asr.es_afirmativo(texto) is esperado


# ---------------------------------------------------------------- report integration


def test_informe_separa_juez_y_asserts():
    detalle, resumen = informe.analizar(VUELTA)
    jva = resumen["juez_vs_asserts"]["total"]
    assert jva["discrepa"] == 2  # the real finding + the made-up name
    assert jva["juez"] == 4 and jva["asserts"] == 2 and jva["evaluadas"] == 5
    real = next(d for d in detalle if d["escenario"] == CITA and d["intento"] == 1)
    assert real["juez"] == "aprobado" and real["asserts"] == "suspenso"
    assert real["veredicto"] == "suspenso" and real["causa"].startswith("asserts:")
    infra = next(d for d in detalle if d["escenario"] == CITA and d["intento"] == 3)
    assert infra["veredicto"] == "infra"  # infra stays infra whatever the asserts say
    assert informe.codigo_salida(resumen["total"]) == 1
    texto = informe.formatear(detalle, resumen)
    assert "juez_si_asserts_no" in texto and "El juez aprobo 2 llamada(s)" in texto


def test_informe_solo_juez_como_antes():
    detalle, resumen = informe.analizar(VUELTA, con_asserts=False)
    assert all(d["veredicto"] == d["juez"] for d in detalle)
    assert "juez_si_asserts_no" not in informe.formatear(detalle, resumen)


def test_informe_lee_la_foto_de_bd(tmp_path):
    import shutil

    copia = tmp_path / "vuelta"
    shutil.copytree(VUELTA, copia)
    bd = {"huecos": [], "citas": [{"id": 1, "hueco_id": 2, "paciente": "Carlos Ruiz"}]}
    (copia / asr.FOTO_BD).write_text(json.dumps(bd), encoding="utf-8")
    detalle, _ = informe.analizar(copia)
    duda_ok = next(d for d in detalle if d["escenario"] == DUDA and d["intento"] == 1)
    fallo = next(a for a in duda_ok["lista_asserts"] if a.nombre == "sin_reserva")
    assert fallo.aprobado is False  # the snapshot shows an appointment for Carlos Ruiz


def test_combinar():
    assert informe.combinar("infra", "suspenso") == "infra"
    assert informe.combinar("aprobado", "suspenso") == "suspenso"
    assert informe.combinar("aprobado", "n/a") == "aprobado"
    assert informe.combinar("suspenso", "aprobado") == "suspenso"


def test_foto_de_bd_real_y_reserva_correcta(base_limpia):
    """Snapshot of the real tables (test database) feeds reserva_correcta."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    motor = create_engine(base_limpia, poolclass=NullPool)
    with motor.begin() as con:
        con.execute(
            text(
                "INSERT INTO citas (id, hueco_id, paciente) OVERRIDING SYSTEM VALUE VALUES (1, 2, 'Maria Garcia')"
            )
        )
        con.execute(text("UPDATE huecos SET libre = false WHERE id = 2"))
    motor.dispose()
    bd = asr.leer_estado_bd(base_limpia)
    assert {"id": 1, "hueco_id": 2, "paciente": "Maria Garcia"}.items() <= bd["citas"][0].items()
    assert next(h for h in bd["huecos"] if h["id"] == 2)["medico"] == "Dr. Lopez"
    # The synthetic call books slot 2 (Dr. Lopez) and gets appointment 1 back
    ll = _sintetica(CONSULTA, RESERVA)
    r = asr.reserva_correcta(ll, {"paciente": "Maria Garcia", "medico": "Dr. Lopez"}, bd)
    assert r.aprobado is True and "en BD" in r.motivo
