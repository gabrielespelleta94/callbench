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

## Round report (agent failures vs infrastructure)

    uv run python evals/informe.py <name or path of the round>

Reads `evals/runs/<name>/results.jsonl` and classifies each attempt as passed, failed
(agent) or infra (judge call failed, Groq rejecting a tool call, dead bot process, clinic
API down detected as `agenda_no_disponible` in the attempt log, or any other error).
The pass rate is computed over valid attempts (passed + failed). Exit code: 0 all passed,
1 some agent failure, 2 no agent failures but infra errors (inconclusive round).

## Queue and stored results (bench/)

Rounds stored in Postgres, run by one or two workers (API running first):

    uv run alembic upgrade head
    uv run python -m bench.encolar -n my-round -e v1 -r 3 --reiniciar
    uv run python -m bench.worker --puerto 7970 --api-url http://127.0.0.1:8000

Each job (scenario x attempt) gets a fresh bot on the worker's port; results land in the
`llamadas` table, with logs under `evals/runs/<round>/`. Only infrastructure failures are
retried (backoff, at most 3 executions); a second worker needs another `--puerto`.

## Deterministic asserts (on top of the judge)

    uv run python evals/asserts.py foto <round>     # after the round: snapshot huecos/citas
    uv run python evals/informe.py <round>          # judge + asserts
    uv run python evals/informe.py <round> --solo-juez

`evals/asserts.py` re-grades every call from its transcript (`conversation.json`), the tool
results in the bot log and, if present, `estado_bd.json`: correct booking in the database,
no booking without a repeated doctor + time and a "yes", no invented doctors or times, and
`consultar_huecos` before asking the name and before booking. Which asserts apply to each
scenario is set in `evals/asserts.toml`. A call passes only if the judge and the asserts
pass; the report also counts the calls the judge passed and the asserts failed.

## Regression gate (tools/comparar.py)

    uv run python tools/comparar.py <base> <candidate>           # per-scenario table + exit code
    uv run python tools/comparar.py <base> <candidate> --json    # the same diff the scorecard shows
    uv run python tools/comparar.py --resumen a+b > evals/baselines/base.json

Each side is a committed summary JSON (`evals/baselines/*.json`), a suite round under
`evals/runs/` (results.jsonl + logs, graded with judge + asserts on the fly) or a round
stored in Postgres (queue rounds, or suite rounds loaded with `tools/importar_vuelta.py`).
`a+b` pools the calls of several rounds of the same version. Only the last execution of
each queue job counts, and infrastructure failures are left out of the rates.

The rule, per scenario, over valid calls (passed + failed) of each side:

| State | When |
|---|---|
| **worse** | the candidate has **at least 2 passes fewer** than the base rate predicts for its N, **and** either its Wilson 95 % interval lies entirely below the base's pass rate or both sides have N >= 10 |
| **inconclusive** | the scenario is missing or has 0 valid calls on one side, or the candidate has more infra failures than valid calls in it |
| **better** | at least 2 passes more and the interval entirely above the base's rate |
| **same** | anything else: within noise |

The latency rule: the voice-to-voice p95 (agent/metricas.py) grows more than 20 %, with at
least 5 measured turns on each side. Exit code: **1** if a scenario got worse or latency
regressed, else **2** if something was inconclusive, else **0**.

Why the 2-pass minimum: with the base at 100 % (3/3), a single failure (2/3, interval
21-94 %) already puts the interval below the base rate; one lost call is noise, not a
regression. Consequently a CI run needs at least 2 attempts per scenario to be able to flag
anything (the `evals` job defaults to `-r 2`).

`evals/baselines/base.json` is `base-2026-11-20+base-2026-11-20-b` (14/18 valid calls
passed, 22 infra). CI runs the `evals` job only on demand (Actions → CI → Run workflow),
with the `GROQ_API_KEY` and `DEEPGRAM_API_KEY` secrets; the push job runs only pytest.

## Scorecard (dashboard/)

    uv run python tools/importar_vuelta.py <suite round>         # suite rounds into Postgres
    uv run uvicorn app.main:app --port 8005 --loop app.db.bucle:selector_loop
    npm --prefix dashboard install && npm --prefix dashboard run dev   # http://localhost:5173

The API (`app/resultados.py`) serves `GET /vueltas`, `GET /vueltas/{id}` (calls with
transcript, judge and asserts) and `GET /diff?base=&candidata=`; the dashboard shows the
per-scenario diff, the gate verdict, judge vs asserts, latency and cost per call.
