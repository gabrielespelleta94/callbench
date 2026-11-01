# Agent evals (pipecat.evals)

Scenarios that test Ana against the real bot, in text modality (no audio STT/TTS).
The judge and the simulated patient use Groq (`GROQ_API_KEY` from `.env`).

- `saludo_y_huecos.yaml`: scripted, greets and asks for a slot with Dr. Lopez.
- `cita_dr_lopez.yaml`: simulation, the patient books with Dr. Lopez some day this week.
- `lo_antes_posible.yaml`: simulation, earliest appointment without giving a date.
- `duda_y_pide_pensarlo.yaml`: simulation, the patient hesitates; Ana must not book.
- `suite.yaml`: manifest that spawns a fresh bot per run, for `--repeat`.
- `medico_inexistente.yaml`: simulation, asks for "Dr. Fernando" (does not exist).
- `juez_groq.yaml`, `persona_groq.yaml`, `servicios_groq.py`: Groq configuration.

## Run (cmd.exe, three terminals, from the project root)

    uv run fastapi dev app/main.py
    uv run agent/bot.py
    uv run python evals/lanzar.py run evals -v --logs-dir evals/logs

`evals/lanzar.py` is equivalent to `python -m pipecat.evals`. If port 7860 is busy:
`uv run agent/bot.py --port 7861` and add `--bot-url ws://localhost:7861/ws`.
A single scenario: `uv run python evals/lanzar.py run evals/saludo_y_huecos.yaml -v`.

## Reset the agenda and measure pass rates

The simulations really book, so reset the development agenda before each run
(next 5 working days, Dr. Lopez and Dr. Ruiz, some slots taken):

    uv run python -m app.db.reiniciar
    uv run python evals/lanzar.py suite evals/suite.yaml -r 3 -n my-run

`run` executes each scenario once; `suite -r N` repeats them N times against fresh bots
(concurrency 1: with more, Groq rate limits made the judge fail). Results go to
`evals/runs/<name>/` (ignored by git).

## Caveats

- The simulations **really book**: each run takes slots in the API and
  `cita_dr_lopez` can only pass if Dr. Lopez still has free slots.
  Run `uv run python -m app.db.reiniciar` before repeating.
- Groq free tier has a daily token cap (200k for gpt-oss-120b): about 4 full suites of 15 runs.
- Each run consumes Groq tokens (bot, judge and patient).
