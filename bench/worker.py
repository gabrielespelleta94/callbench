"""Queue worker: `uv run python -m bench.worker --puerto 7970 --api-url http://127.0.0.1:8000`.

Loop: take a job (FOR UPDATE SKIP LOCKED + lease), start a fresh bot on this worker's
port, run the scenario against it (bench.ejecutar), classify each result with
evals/informe.py and store it. Infrastructure failures go back to the queue with a
backoff (at most 3 executions); agent failures are final. While a scenario runs, a
thread renews the lease; if the worker dies, the lease expires and another worker
takes the job.

Run one worker per port. Two workers are the useful maximum: Groq rate-limits the judge.
"""

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path

from loguru import logger
from sqlalchemy.engine import Engine

from bench import cola
from bench.cola import Resultado, Trabajo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from evals.informe import _leer_log, clasificar, leer_filas  # noqa: E402

DIR_RUNS = RAIZ / "evals" / "runs"
ARRANQUE_BOT_S = 60
TIMEOUT_ESCENARIO_S = 15 * 60

Ejecutor = Callable[[Trabajo], list[Resultado]]


def resultado_de_fila(fila: dict, dir_logs: Path | None = None) -> Resultado:
    """Classify a results.jsonl record the same way evals/informe.py does."""
    # The bot log decides who asked for a nonexistent tool and whether the API was down
    texto_log = _leer_log(fila, dir_logs) if dir_logs is not None else None
    veredicto, causa = clasificar(fila, texto_log)
    # The judge's own verdict: a simulation's `succeeded`; a scripted scenario has no
    # separate one (its `passed` already mixes judge evals and event checks)
    juez = fila.get("succeeded", fila.get("passed")) if veredicto != "infra" else None
    return Resultado(
        escenario=fila.get("scenario", "?"),
        veredicto=veredicto,
        causa=causa,
        fila=fila,
        aprobado_juez=juez,
        confianza_juez=fila.get("confidence"),
        transcripcion=fila.get("messages") or fila.get("turns") or None,
        duracion_ms=fila.get("duration_ms"),
    )


def _puerto_abierto(puerto: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _parar(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


class EjecutorBot:
    """Runs a job for real: fresh bot on `puerto`, scenario via bench.ejecutar."""

    def __init__(self, puerto: int, api_url: str):
        self.puerto = puerto
        self.api_url = api_url

    def __call__(self, t: Trabajo) -> list[Resultado]:
        directorio = DIR_RUNS / t.vuelta / f"{t.escenario}__{t.intento:03d}__e{t.intentos}"
        directorio.mkdir(parents=True, exist_ok=True)
        results = directorio / "results.jsonl"
        results.unlink(missing_ok=True)
        if _puerto_abierto(self.puerto):
            return [Resultado(t.escenario, "infra", f"puerto {self.puerto} ocupado", {})]

        # Metrics (agent/metricas.py) inside the job directory, so each call keeps its own
        # latency and cost (bench/resultados.py reads <job>/metrics/*.jsonl)
        entorno = {
            **os.environ,
            "CLINICA_API_URL": self.api_url,
            "CALLBENCH_METRICS_DIR": str(directorio / "metrics"),
        }
        with open(directorio / "bot.log", "wb") as log_bot:
            bot = subprocess.Popen(
                [sys.executable, str(RAIZ / "agent" / "bot.py"), "--port", str(self.puerto)],
                cwd=RAIZ,
                env=entorno,
                stdout=log_bot,
                stderr=subprocess.STDOUT,
            )
        try:
            limite = time.monotonic() + ARRANQUE_BOT_S
            while not _puerto_abierto(self.puerto):
                if bot.poll() is not None or time.monotonic() > limite:
                    return [Resultado(t.escenario, "infra", "el bot no arranco", {})]
                time.sleep(0.5)
            with open(directorio / "ejecutar.log", "wb") as log_eval:
                proc = subprocess.run(
                    [
                        sys.executable, "-m", "bench.ejecutar",
                        str(RAIZ / "evals" / f"{t.escenario}.yaml"),
                        "--bot-url", f"ws://localhost:{self.puerto}/ws",
                        "--logs-dir", str(directorio / "logs"),
                        "--results", str(results),
                        "--intento", str(t.intento),
                    ],
                    cwd=RAIZ,
                    env=entorno,
                    stdout=log_eval,
                    stderr=subprocess.STDOUT,
                    timeout=TIMEOUT_ESCENARIO_S,
                )
        except subprocess.TimeoutExpired:
            return [Resultado(t.escenario, "infra", "escenario sin terminar (timeout)", {})]
        finally:
            _parar(bot)
        if not results.exists():
            causa = f"bench.ejecutar sin resultados (salida {proc.returncode})"
            return [Resultado(t.escenario, "infra", causa, {})]
        return [resultado_de_fila(f, directorio) for f in leer_filas(results)]


class _Renovador:
    """Background thread that renews the lease every lease/3 seconds."""

    def __init__(self, motor: Engine, t: Trabajo, worker: str, lease_s: float):
        self.args = (motor, t.id, worker, lease_s)
        self.parar = threading.Event()
        self.hilo = threading.Thread(target=self._bucle, daemon=True)

    def _bucle(self) -> None:
        while not self.parar.wait(self.args[3] / 3):
            try:
                if not cola.renovar_lease(*self.args):
                    logger.warning(f"lease perdido del trabajo {self.args[1]}")
                    return
            except Exception as e:  # noqa: BLE001 - a DB blip must not kill the run
                logger.warning(f"no se pudo renovar el lease: {e}")

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *exc):
        self.parar.set()
        self.hilo.join()


def procesar_uno(
    motor: Engine,
    worker: str,
    ejecutor: Ejecutor,
    lease_s: float = cola.LEASE_S,
    max_intentos: int = cola.MAX_INTENTOS,
    backoff_s: float = cola.BACKOFF_S,
) -> Trabajo | None:
    """Take one job, run it and store the result. None if no job was runnable."""
    cola.recoger_caducados(motor, max_intentos)
    t = cola.tomar(motor, worker, lease_s, max_intentos)
    if t is None:
        return None
    logger.info(f"[{worker}] {t.vuelta} {t.escenario} #{t.intento} (ejecucion {t.intentos})")
    with _Renovador(motor, t, worker, lease_s):
        try:
            resultados = ejecutor(t)
        except Exception as e:  # noqa: BLE001 - any crash of the harness is infrastructure
            resultados = [Resultado(t.escenario, "infra", f"error: {type(e).__name__}: {e}", {})]
    estado = cola.terminar(motor, t, worker, resultados, max_intentos, backoff_s)
    veredictos = ", ".join(r.veredicto for r in resultados)
    logger.info(f"[{worker}] trabajo {t.id}: {veredictos} -> {estado or 'descartado (lease perdido)'}")
    return t


def bucle(
    motor: Engine,
    worker: str,
    ejecutor: Ejecutor,
    *,
    esperar: bool = False,
    pausa_s: float = 5.0,
    **opciones,
) -> int:
    """Process jobs until the queue is empty (or forever with `esperar`). Returns the count."""
    hechos = 0
    while True:
        if procesar_uno(motor, worker, ejecutor, **opciones):
            hechos += 1
            continue
        if not esperar and cola.quedan(motor) == 0:
            return hechos
        time.sleep(pausa_s)  # jobs waiting for their backoff, or held by other workers


def api_viva(api_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{api_url}/salud", timeout=5) as r:
            return r.status == 200
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--puerto", type=int, default=7970, help="bot port (one per worker)")
    p.add_argument(
        "--api-url", default=os.getenv("CLINICA_API_URL", "http://127.0.0.1:8000").rstrip("/")
    )
    p.add_argument("--lease", type=float, default=cola.LEASE_S, help="lease seconds")
    p.add_argument("--esperar", action="store_true", help="keep polling when the queue is empty")
    p.add_argument("--nombre", default=None, help="worker id (default host-pid-random)")
    a = p.parse_args(argv)
    if not api_viva(a.api_url):
        print(f"La API de la clinica no responde en {a.api_url}/salud: arrancala antes.")
        return 2
    worker = a.nombre or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:4]}"
    hechos = bucle(
        cola.motor(), worker, EjecutorBot(a.puerto, a.api_url), esperar=a.esperar, lease_s=a.lease
    )
    print(f"{worker}: {hechos} trabajos procesados; cola vacia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
