"""Tests for the eval round report.

Run with:  uv run pytest tests/test_informe.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

from informe import agregar, clasificar, codigo_salida, intentos_repetidos  # noqa: E402


def fila(**campos):
    base = {"scenario": "a/b", "passed": False, "error": None, "ended_by": "end_call"}
    return {**base, **campos}


def test_aprobado():
    assert clasificar(fila(passed=True)) == ("aprobado", None)


def test_juez_caido_en_error():
    veredicto, causa = clasificar(fila(error="judge call failed", ended_by="silence"))
    assert veredicto == "infra" and "juez" in causa


def test_juez_caido_en_failures():
    f = fila(failures=[{"kind": "judge_no", "reason": "judge said no: judge call failed"}])
    assert clasificar(f)[0] == "infra"


def test_groq_rechaza_herramienta():
    f = fila(error="Error during completion: tool call validation failed", ended_by="error")
    veredicto, causa = clasificar(f)
    assert veredicto == "infra" and "herramienta" in causa


def test_proceso_muerto():
    veredicto, causa = clasificar(fila(error="error: ProcessLookupError: ", ended_by="error"))
    assert veredicto == "infra" and "proceso" in causa


def test_api_caida_solo_con_log():
    log = "{'role': 'tool', 'content': '{\"ok\": false, \"error\": \"agenda_no_disponible\"}'}"
    assert clasificar(fila())[0] == "suspenso"
    veredicto, causa = clasificar(fila(), log)
    assert veredicto == "infra" and "agenda_no_disponible" in causa


def test_log_sin_marca_no_cambia_el_suspenso():
    assert clasificar(fila(), "todo normal")[0] == "suspenso"


def test_suspenso_normal_del_juez():
    f = fila(failures=[{"kind": "judge_no", "reason": "judge said no: no confirmo"}])
    assert clasificar(f) == ("suspenso", "judge said no: no confirmo")


def test_error_desconocido_es_infra_truncado():
    veredicto, causa = clasificar(fila(error="boom " * 100))
    assert veredicto == "infra" and causa.startswith("error: boom") and len(causa) < 100


def test_agregacion_con_tasa_sobre_validos():
    r = agregar([("x", "aprobado"), ("x", "aprobado"), ("x", "suspenso"), ("y", "infra")])
    assert r["escenarios"]["x"] == {"aprobado": 2, "suspenso": 1, "infra": 0}
    assert r["total"] == {"aprobado": 2, "suspenso": 1, "infra": 1}
    assert abs(r["tasa"] - 2 / 3) < 1e-9


def test_agregacion_sin_validos():
    assert agregar([("x", "infra")])["tasa"] is None


def test_codigos_de_salida():
    assert codigo_salida({"aprobado": 3, "suspenso": 0, "infra": 0}) == 0
    assert codigo_salida({"aprobado": 3, "suspenso": 1, "infra": 2}) == 1
    assert codigo_salida({"aprobado": 3, "suspenso": 0, "infra": 2}) == 2


def test_detecta_nombre_de_vuelta_reutilizado():
    uno = {"escenario": "a", "intento": 1}
    assert intentos_repetidos([uno, {"escenario": "a", "intento": 2}]) is False
    assert intentos_repetidos([uno, dict(uno)]) is True
