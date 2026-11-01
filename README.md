# CallBench

> A voice agent without evals is a demo.

CallBench is a regression bench for [Pipecat](https://github.com/pipecat-ai/pipecat) voice agents.
The agent under test is a small clinic receptionist that books and reschedules appointments.
It is called by synthetic callers (the one who interrupts, the silent one, the one who gets
their date of birth wrong), every call is scored, and every new agent version is compared
with the last one on success rate, latency (p50/p95) and cost per call.

Status: **work in progress**, built in public while learning the stack end to end.

## How it fits together

```
browser mic ──WebRTC──┐
                      ├──> agent/bot.py  (Pipecat: Silero VAD + Smart Turn → Deepgram STT → Groq LLM → Deepgram TTS)
pipecat.evals ──WS────┘          │ tool calls: consultar_huecos, reservar_cita
 (synthetic callers + LLM judge) ▼
                           app/main.py  (FastAPI) ──> PostgreSQL (portable, Alembic migrations)
```

CallBench builds on `pipecat.evals` for scenarios, simulated callers and the judge, and adds
what it lacks: a Postgres job queue with retries, run history, version-to-version diffs,
cost and per-stage latency, a dashboard and a CI gate.

## Stack

| Piece | Tech |
|---|---|
| Voice agent | Pipecat 1.15, SmallWebRTC transport (browser mic, no phone needed) |
| Models | Groq `gpt-oss-120b` (LLM) + Deepgram nova-3 / aura-2 (STT/TTS), with a fully local alternative (Whisper, Ollama, Piper) |
| Clinic API (agent tools) | FastAPI + Pydantic, SQLAlchemy 2 async + psycopg 3 |
| Storage and job queue | PostgreSQL via `pgserver` (no Docker, no admin rights), Alembic; queue with `FOR UPDATE SKIP LOCKED` |
| Evals | `pipecat.evals` scenarios, judge and simulated caller served by Groq |
| Dashboard | React + TypeScript |

## Layout

```
agent/bot.py          voice agent under test (Pipecat pipeline)
agent/herramientas.py the agent's tools: list free slots, book an appointment
app/main.py           clinic API: slots and appointments
app/db/               connection, models and the portable Postgres
migrations/           Alembic migrations (schema + seed data)
evals/                pipecat.evals scenarios and the Groq-backed judge
tests/                pytest suite (runs against a real Postgres)
docs/bitacora/        project log, plan, decisions and Gantt (in Spanish)
```

## Run it

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). Windows commands shown.

```
uv sync
copy .env.example .env             (then add your Groq and Deepgram keys)
uv run alembic upgrade head        create the tables and seed the slots
uv run fastapi dev app/main.py     clinic API docs at http://127.0.0.1:8000/docs
uv run agent/bot.py                voice agent at http://localhost:7860
uv run pytest
```

Run the eval scenarios against the running agent (see [evals/README.md](evals/README.md)):

```
uv run python evals/lanzar.py run evals -v --logs-dir evals/logs
```

## Roadmap

- [x] Phase 0: end-to-end voice agent in the browser (first real call: ~0.9 s voice-to-voice)
- [x] Phase 1: clinic API with FastAPI (in memory)
- [x] Phase 2: PostgreSQL schema and migrations (portable Postgres via pgserver, Alembic)
- [ ] Phase 3: job queue on Postgres with leases, retries and a chaos test
- [ ] Phase 4: agent tool calling against the clinic API (done), synthetic callers on top of `pipecat.evals` (first scenarios running)
- [ ] Phase 4b: deterministic assertions, LLM judge, CI gate
- [ ] Phase 5: per-stage latency and cloud vs local comparison
- [ ] Phase 6: React scorecard with version diff
