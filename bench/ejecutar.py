"""`pipecat eval run` plus a results.jsonl record: what the worker runs in a subprocess.

    python -m bench.ejecutar evals/cita_dr_lopez.yaml --bot-url ws://localhost:7970/ws \
        --logs-dir <dir> --results <dir>/results.jsonl --intento 2

`evals/lanzar.py run` (pipecat's `run` command) only prints the outcome; the structured
record exists only in `suite`, which spawns its own bots. This module runs the same
code as `run` (`_build_scenario_runs` + `_execute_scenario`) and then appends the same
record `suite` writes (`_append_result`), so evals/informe.py classifies it unchanged.
These are private pipecat helpers: the version is pinned in uv.lock.
"""

import argparse
import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Scenario YAMLs reference `factory: evals.servicios_groq.juez`
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402
from pipecat.cli.commands.eval import (  # noqa: E402
    _build_scenario_runs,
    _execute_scenario,
    _expand_scenario_paths,
)
from pipecat.evals.session import EvalSessionParams  # noqa: E402
from pipecat.evals.suite import _append_result  # noqa: E402


async def ejecutar(
    escenarios: list[Path], bot_url: str, logs_dir: Path, results: Path, intento: int, timeout_s: int
) -> int:
    runs = _build_scenario_runs(_expand_scenario_paths(escenarios), bot_url)
    params = EvalSessionParams(default_timeout_ms=timeout_s * 1000)
    logs_dir.mkdir(parents=True, exist_ok=True)
    results.parent.mkdir(parents=True, exist_ok=True)
    fallos = 0
    for run in runs:
        run.attempt = intento
        if run.status != "done":  # a file that failed to load is already done, with its error
            await _execute_scenario(
                run,
                audio=False,
                record_dir=str(logs_dir),
                params=params,
                logs_dir=str(logs_dir),
                debug=False,
                verbose=False,
            )
        _append_result(results, run, run.stem, logs_dir, None)
        fallos += not (run.result is not None and run.result.passed and not run.error)
    return 1 if fallos else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("escenarios", nargs="+", type=Path)
    p.add_argument("--bot-url", required=True)
    p.add_argument("--logs-dir", type=Path, required=True)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--intento", type=int, default=1)
    p.add_argument("--timeout", type=int, default=60, help="per-expectation timeout (s)")
    a = p.parse_args(argv)
    load_dotenv(RAIZ / ".env")  # judge and persona read GROQ_API_KEY
    return asyncio.run(
        ejecutar(a.escenarios, a.bot_url, a.logs_dir, a.results, a.intento, a.timeout)
    )


if __name__ == "__main__":
    sys.exit(main())
