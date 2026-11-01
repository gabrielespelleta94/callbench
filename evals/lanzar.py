"""Launcher for the pipecat.evals CLI: `uv run python evals/lanzar.py run ...`.

Equivalent to `pipecat eval`, but adds the project root to the path so that
`factory: evals.servicios_groq.juez` resolves.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipecat.cli.commands.eval import eval_app  # noqa: E402

if __name__ == "__main__":
    eval_app()
