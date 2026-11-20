"""Job queue tests against the real Postgres (test database). No bot and no Groq:
the scenario runner is replaced by a function that returns canned results.

Run with:  uv run pytest tests/test_cola.py
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import text

from bench import cola, worker
from bench.cola import Resultado

RAIZ = Path(__file__).resolve().parent.parent

# Real results.jsonl records (trimmed) as pipecat.evals writes them
FILA_APROBADA = {
    "scenario": "cita_dr_lopez/reserva_real", "kind": "simulation", "attempt": 1,
    "passed": True, "succeeded": True, "error": None, "confidence": 0.98,
    "ended_by": "end_call", "duration_ms": 30000,
    "messages": [{"role": "assistant", "content": "Hi, Sunrise Family Clinic."}],
}
FILA_SUSPENSA = {**FILA_APROBADA, "passed": False, "succeeded": False, "confidence": 0.9}
FILA_JUEZ_CAIDO = {
    **FILA_APROBADA, "passed": False, "succeeded": False,
    "error": "judge call failed: 429 rate limit",
}


def aprobado(t):
    return [worker.resultado_de_fila(FILA_APROBADA)]


def suspenso(t):
    return [worker.resultado_de_fila(FILA_SUSPENSA)]


def infra(t):
    return [worker.resultado_de_fila(FILA_JUEZ_CAIDO)]


@pytest.fixture
def motor(url_test):
    m = cola.motor(url_test)
    with m.begin() as con:
        con.execute(text("TRUNCATE llamadas, trabajos, vueltas, versiones RESTART IDENTITY"))
    yield m
    m.dispose()


def vuelta(motor, escenarios=("a", "b"), repeticiones=2, nombre="v") -> int:
    with motor.begin() as con:
        version = cola.obtener_version(con, "test", "abc123", {"stt": "x"})
        return cola.crear_vuelta(con, nombre, version, list(escenarios), repeticiones)


def trabajo(motor, id_: int) -> dict:
    with motor.connect() as con:
        return dict(con.execute(text("SELECT * FROM trabajos WHERE id = :i"), {"i": id_}).mappings().one())


def llamadas(motor) -> list[dict]:
    with motor.connect() as con:
        return [dict(f) for f in con.execute(text("SELECT * FROM llamadas ORDER BY id")).mappings()]


# --- versions and rounds


def test_la_version_se_reutiliza_si_coinciden_etiqueta_commit_y_config(motor):
    with motor.begin() as con:
        a = cola.obtener_version(con, "v1", "sha", {"stt": "deepgram", "tts": "x"})
        b = cola.obtener_version(con, "v1", "sha", {"tts": "x", "stt": "deepgram"})
        c = cola.obtener_version(con, "v1", "sha", {"stt": "elevenlabs", "tts": "x"})
    assert a == b != c


def test_la_vuelta_crea_un_trabajo_por_escenario_e_intento_y_primero_los_intentos_1(motor):
    vuelta(motor, escenarios=("a", "b"), repeticiones=3)
    orden = []
    while (t := cola.tomar(motor, "w")) is not None:
        orden.append((t.escenario, t.intento))
    assert orden == [("a", 1), ("b", 1), ("a", 2), ("b", 2), ("a", 3), ("b", 3)]


def test_no_se_puede_repetir_el_nombre_de_una_vuelta(motor):
    vuelta(motor, nombre="dup")
    with pytest.raises(Exception, match="unique|duplicate|duplicada"):
        vuelta(motor, nombre="dup")


# --- claiming: SKIP LOCKED and leases


def test_skip_locked_salta_la_fila_bloqueada_por_otra_transaccion(motor):
    vuelta(motor, escenarios=("a",), repeticiones=2)
    with motor.connect() as otra:
        tx = otra.begin()
        otra.execute(text("SELECT id FROM trabajos WHERE id = 1 FOR UPDATE"))
        t = cola.tomar(motor, "w")  # does not wait for the lock, takes the next one
        tx.rollback()
    assert t is not None and t.id == 2


def test_varios_workers_a_la_vez_nunca_toman_el_mismo_trabajo(motor):
    vuelta(motor, escenarios=[f"e{i}" for i in range(10)], repeticiones=2)
    tomados: list[int] = []
    cerrojo = threading.Lock()

    def worker_(n):
        while (t := cola.tomar(motor, f"w{n}")) is not None:
            with cerrojo:
                tomados.append(t.id)

    hilos = [threading.Thread(target=worker_, args=(n,)) for n in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(tomados) == list(range(1, 21))


def test_un_lease_vivo_no_se_puede_tomar_y_uno_caducado_si(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    t1 = cola.tomar(motor, "w1", lease_s=1)
    assert cola.tomar(motor, "w2") is None
    time.sleep(1.2)
    t2 = cola.tomar(motor, "w2")
    assert t2.id == t1.id and t2.intentos == 2


def test_renovar_el_lease_lo_mantiene_y_falla_si_ya_no_es_tuyo(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    t = cola.tomar(motor, "w1", lease_s=1)
    time.sleep(0.6)
    assert cola.renovar_lease(motor, t.id, "w1", lease_s=1)
    time.sleep(0.6)
    assert cola.tomar(motor, "w2") is None  # renewed: still alive
    time.sleep(0.6)
    assert cola.tomar(motor, "w2") is not None
    assert not cola.renovar_lease(motor, t.id, "w1")


def test_el_worker_que_perdio_el_lease_no_escribe_su_resultado(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    lento = cola.tomar(motor, "lento", lease_s=0.5)
    time.sleep(0.7)
    rapido = cola.tomar(motor, "rapido")
    assert cola.terminar(motor, lento, "lento", aprobado(lento)) is None
    assert llamadas(motor) == []
    assert cola.terminar(motor, rapido, "rapido", aprobado(rapido)) == "hecho"
    assert [ll["ejecucion"] for ll in llamadas(motor)] == [2]


# --- results and retries


def test_aprobado_y_suspenso_terminan_el_trabajo_sin_reintento(motor):
    vuelta(motor, escenarios=("a", "b"), repeticiones=1)
    assert worker.procesar_uno(motor, "w", aprobado)
    assert worker.procesar_uno(motor, "w", suspenso)
    assert worker.procesar_uno(motor, "w", aprobado) is None  # queue empty
    assert [trabajo(motor, i)["estado"] for i in (1, 2)] == ["hecho", "hecho"]
    filas = llamadas(motor)
    assert [(f["veredicto"], f["aprobado_juez"]) for f in filas] == [
        ("aprobado", True),
        ("suspenso", False),
    ]
    assert filas[0]["confianza_juez"] == 0.98
    assert filas[0]["resultado"]["scenario"] == "cita_dr_lopez/reserva_real"
    assert filas[0]["transcripcion"][0]["role"] == "assistant"
    assert filas[0]["aprobado_asserts"] is None  # filled by the asserts (F4b)


def test_infra_se_reintenta_con_backoff_y_falla_al_tercer_intento(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    worker.procesar_uno(motor, "w", infra, backoff_s=60)
    t = trabajo(motor, 1)
    assert (t["estado"], t["intentos"], t["worker"]) == ("pendiente", 1, None)
    assert "juez" in t["error"]
    assert worker.procesar_uno(motor, "w", aprobado) is None  # waiting for its backoff

    with motor.begin() as con:  # skip the wait
        con.execute(text("UPDATE trabajos SET disponible_en = now()"))
    worker.procesar_uno(motor, "w", infra, backoff_s=0)
    worker.procesar_uno(motor, "w", infra, backoff_s=0)
    t = trabajo(motor, 1)
    assert (t["estado"], t["intentos"]) == ("fallido", 3)
    assert t["terminado_en"] is not None
    assert [f["ejecucion"] for f in llamadas(motor)] == [1, 2, 3]
    assert {f["aprobado_juez"] for f in llamadas(motor)} == {None}


def test_el_backoff_se_duplica_en_cada_reintento(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    esperas = []
    for _ in range(2):
        worker.procesar_uno(motor, "w", infra, backoff_s=100)
        with motor.begin() as con:
            esperas.append(
                con.execute(
                    text("SELECT extract(epoch FROM disponible_en - now()) FROM trabajos")
                ).scalar_one()
            )
            con.execute(text("UPDATE trabajos SET disponible_en = now()"))
    assert 95 < esperas[0] <= 100 and 195 < esperas[1] <= 200


def test_infra_y_luego_aprobado_cuenta_como_hecho(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    worker.procesar_uno(motor, "w", infra, backoff_s=0)
    worker.procesar_uno(motor, "w", aprobado, backoff_s=0)
    assert trabajo(motor, 1)["estado"] == "hecho"
    assert [f["veredicto"] for f in llamadas(motor)] == ["infra", "aprobado"]


def test_si_el_ejecutor_revienta_es_infra(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)

    def revienta(t):
        raise ConnectionError("bot caido")

    worker.procesar_uno(motor, "w", revienta, backoff_s=0)
    t = trabajo(motor, 1)
    assert t["estado"] == "pendiente" and "ConnectionError" in t["error"]


def test_sin_resultados_es_infra(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    worker.procesar_uno(motor, "w", lambda t: [], backoff_s=0)
    assert trabajo(motor, 1)["error"] == "sin resultados"


def test_un_lease_caducado_sin_intentos_restantes_pasa_a_fallido(motor):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    with motor.begin() as con:
        con.execute(
            text(
                "UPDATE trabajos SET estado = 'en_curso', intentos = 3, worker = 'muerto', "
                "lease_hasta = now() - interval '1 second'"
            )
        )
    assert worker.procesar_uno(motor, "w", aprobado) is None
    t = trabajo(motor, 1)
    assert t["estado"] == "fallido" and "lease caducado" in t["error"]


def test_el_bucle_vacia_la_cola_esperando_los_backoffs(motor):
    vuelta(motor, escenarios=("a", "b"), repeticiones=2)
    veces = {"n": 0}

    def a_veces_falla(t):
        veces["n"] += 1
        return infra(t) if veces["n"] == 1 else aprobado(t)

    hechos = worker.bucle(motor, "w", a_veces_falla, backoff_s=0.2, pausa_s=0.1)
    assert hechos == 5  # 4 jobs + 1 retry
    assert cola.quedan(motor) == 0


# --- classification of real pipecat.evals records (reuses evals/informe.py)


@pytest.mark.parametrize(
    ("fila", "veredicto", "juez"),
    [
        (FILA_APROBADA, "aprobado", True),
        (FILA_SUSPENSA, "suspenso", False),
        (FILA_JUEZ_CAIDO, "infra", None),
        ({"scenario": "s", "passed": False, "error": "error: ProcessLookupError"}, "infra", None),
        ({"scenario": "s", "kind": "script", "passed": True, "turns": [{"turn_index": 0}]}, "aprobado", True),
    ],
)
def test_clasificacion_de_filas(fila, veredicto, juez):
    r = worker.resultado_de_fila(fila)
    assert (r.veredicto, r.aprobado_juez) == (veredicto, juez)


def test_suspenso_con_la_api_caida_en_el_log_es_infra(tmp_path):
    log = tmp_path / "logs" / "x.log"
    log.parent.mkdir()
    log.write_text('tool result {"error": "agenda_no_disponible"}', encoding="utf-8")
    fila = {**FILA_SUSPENSA, "artifacts": {"log": str(log)}}
    assert worker.resultado_de_fila(fila, tmp_path).veredicto == "infra"


# --- chaos: a worker process dies mid-job


def test_chaos_el_worker_muere_el_lease_caduca_y_otro_lo_recoge(motor, url_test):
    vuelta(motor, escenarios=("a",), repeticiones=1)
    proc = subprocess.Popen(
        [sys.executable, str(RAIZ / "tests" / "worker_que_muere.py"), url_test, "victima", "1.5"],
        cwd=RAIZ,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdout.readline().startswith("TOMADO")
        # The heartbeat keeps the lease alive past its initial 1.5 s while the worker lives
        time.sleep(2.5)
        assert trabajo(motor, 1)["worker"] == "victima"
        assert cola.tomar(motor, "rescate") is None
    finally:
        proc.kill()  # no cleanup: the job stays 'en_curso' with a lease nobody renews
        proc.wait()
    assert trabajo(motor, 1)["estado"] == "en_curso"

    limite = time.monotonic() + 5
    while (t := worker.procesar_uno(motor, "rescate", aprobado)) is None:
        assert time.monotonic() < limite, "the lease never expired"
        time.sleep(0.2)
    fin = trabajo(motor, 1)
    assert (fin["estado"], fin["intentos"], fin["worker"]) == ("hecho", 2, "rescate")
    assert [(f["ejecucion"], f["veredicto"]) for f in llamadas(motor)] == [(2, "aprobado")]


def test_resultado_es_inmutable():
    with pytest.raises(AttributeError):
        Resultado("a", "aprobado", None, {}).veredicto = "x"
