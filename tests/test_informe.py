"""Tests for the eval round report.

Run with:  uv run pytest tests/test_informe.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

from informe import agregar, clasificar, codigo_salida, intentos_repetidos


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


# ---------------------------------------------------------------- nonexistent tool

ERROR_FILE = (
    "Error during completion: tool call validation failed: "
    "attempted to call tool 'file' which was not in request.tools"
)


def test_herramienta_inexistente_de_ana_es_suspenso():
    # The refusal is in the bot log: Ana's own LLM asked for the tool
    log = f"GroqLLMService#0 error: {ERROR_FILE}"
    veredicto, causa = clasificar(fila(error=ERROR_FILE, ended_by="error"), log)
    assert veredicto == "suspenso" and "Ana" in causa and "file" in causa


def test_herramienta_inexistente_de_ana_sin_error_en_la_fila():
    # The harness may not report it; the bot log alone is enough
    log = f"... {ERROR_FILE} ..."
    assert clasificar(fila(), log)[0] == "suspenso"


def test_herramienta_inexistente_de_la_persona_es_infra():
    # Only the harness saw it (as in base-2026-11-20-b #2): the simulated patient's LLM
    veredicto, causa = clasificar(fila(error=ERROR_FILE, ended_by="error"), "bot log sin error")
    assert veredicto == "infra" and "persona" in causa and "file" in causa


# ---------------------------------------------------------------- bench round layout

import json

from informe import analizar, filas_de_vuelta


def _trabajo(raiz: Path, nombre: str, filas: list[dict] | None, bot_log: str = "") -> Path:
    d = raiz / nombre
    (d / "logs").mkdir(parents=True)
    (d / "bot.log").write_text(bot_log, encoding="utf-8")
    if filas is not None:
        lineas = []
        for f in filas:
            f = {**f, "artifacts": {"log": str(d / "logs" / "x__y.log")}}
            lineas.append(json.dumps(f))
        (d / "results.jsonl").write_text("\n".join(lineas), encoding="utf-8")
    return d


def test_vuelta_de_la_cola_toma_la_ultima_ejecucion(tmp_path):
    _trabajo(tmp_path, "a__001__e1", [fila(scenario="a/x", error="judge call failed")])
    _trabajo(tmp_path, "a__001__e2", [fila(scenario="a/x", passed=True)])
    _trabajo(tmp_path, "a__002__e1", None)  # harness died, nothing written
    filas, reintentos = filas_de_vuelta(tmp_path)
    assert reintentos == 1
    assert [f.get("passed") for f, _ in filas] == [True, None]
    assert filas[1][0]["error"] == "sin results.jsonl"


def test_vuelta_de_la_cola_lee_bot_log_del_trabajo(tmp_path):
    # API down: the marker is only in <job>/bot.log, not next to the transcript
    _trabajo(
        tmp_path, "a__001__e1", [fila(scenario="a/x")], bot_log='{"error": "agenda_no_disponible"}'
    )
    detalle, _ = analizar(tmp_path, con_asserts=False)
    assert detalle[0]["veredicto"] == "infra" and "API" in detalle[0]["causa"]
