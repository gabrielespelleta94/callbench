# Agent evals (pipecat.evals)

Scenarios that test Ana against the real bot, in text modality (no audio STT/TTS).
The judge and the simulated patient use Groq (`GROQ_API_KEY` from `.env`).

- `saludo_y_huecos.yaml`: scripted, greets and asks for a slot with Dr. Lopez.
- `cita_dr_lopez.yaml`: simulation, the patient books with Dr. Lopez on November 3rd.
- `medico_inexistente.yaml`: simulation, asks for "Dr. Fernando" (does not exist).
- `juez_groq.yaml`, `persona_groq.yaml`, `servicios_groq.py`: Groq configuration.

## Run (cmd.exe, three terminals, from the project root)

    uv run fastapi dev app/main.py
    uv run agent/bot.py
    uv run python evals/lanzar.py run evals -v --logs-dir evals/logs

`evals/lanzar.py` is equivalent to `python -m pipecat.evals`. If port 7860 is busy:
`uv run agent/bot.py --port 7861` and add `--bot-url ws://localhost:7861/ws`.
A single scenario: `uv run python evals/lanzar.py run evals/saludo_y_huecos.yaml -v`.

## Caveats

- The simulations **really book**: each run takes slots in the API and
  `cita_dr_lopez` can only pass if Dr. Lopez still has free slots on 3 Nov.
  Restore the seed before repeating (`alembic downgrade base` and `upgrade head`
  on a test DB).
- Each run consumes Groq tokens (bot, judge and patient).
