"""Queue a round: `uv run python -m bench.encolar -n base-texto -e v1 -r 10 [--reiniciar] [escenarios...]`.

Creates (or reuses) the version (label + git commit + STT/LLM/TTS config) and a round
with one job per scenario x attempt. Without scenarios it takes the suite's list from
evals/suite.yaml. Then start one or two workers: `uv run python -m bench.worker`.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

from bench import cola

RAIZ = Path(__file__).resolve().parent.parent
DIR_EVALS = RAIZ / "evals"


def escenarios_de_la_suite() -> list[str]:
    manifiesto = yaml.safe_load((DIR_EVALS / "suite.yaml").read_text(encoding="utf-8"))
    return [e for entrada in manifiesto["suite"] for e in entrada["scenarios"]]


def git_sha() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=RAIZ, capture_output=True, text=True, check=True,
        ).stdout.strip()
        sucio = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=RAIZ, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"
    return sha + ("-dirty" if sucio else "")


def config_actual() -> dict:
    """The STT/LLM/TTS combination the bot will run with (bot.py defaults unless overridden)."""
    return {
        "stt": os.getenv("CALLBENCH_STT", "deepgram"),
        "llm": os.getenv("CALLBENCH_LLM", "groq:openai/gpt-oss-120b"),
        "tts": os.getenv("CALLBENCH_TTS", "deepgram:aura-2-thalia-en"),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("escenarios", nargs="*", help="names in evals/ (default: the suite's list)")
    p.add_argument("-n", "--nombre", required=True, help="round name (unique)")
    p.add_argument("-e", "--etiqueta", required=True, help="agent version label")
    p.add_argument("-r", "--repeticiones", type=int, default=1)
    p.add_argument("--modalidad", default="texto", choices=["texto", "audio"])
    p.add_argument(
        "--reiniciar", action="store_true", help="reset the development agenda first"
    )
    a = p.parse_args(argv)

    escenarios = a.escenarios or escenarios_de_la_suite()
    faltan = [e for e in escenarios if not (DIR_EVALS / f"{e}.yaml").exists()]
    if faltan:
        print(f"No existen en evals/: {', '.join(faltan)}")
        return 64
    if a.reiniciar:
        from app.db.reiniciar import reiniciar, resumen

        print(resumen(reiniciar()))

    motor = cola.motor()
    with motor.begin() as con:
        version_id = cola.obtener_version(con, a.etiqueta, git_sha(), config_actual())
        vuelta_id = cola.crear_vuelta(
            con, a.nombre, version_id, escenarios, a.repeticiones, a.modalidad
        )
    print(
        f"Vuelta {a.nombre} (id {vuelta_id}, version {version_id}): "
        f"{len(escenarios) * a.repeticiones} trabajos ({len(escenarios)} escenarios x {a.repeticiones})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
