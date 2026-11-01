# CallBench · Bitácora

Registro cronológico de cambios, **la más reciente arriba**. Cada entrada empieza por
una cabecera con este formato exacto (el generador del Gantt la lee):

```
## AAAA-MM-DD · <fase> · <título corto>
```

`<fase>` es un id de [plan.toml](plan.toml) (`F0`, `F1`, `F4b`…) o `META` para lo
que no es de ninguna fase (estructura, documentación, herramientas).

---

## 2026-11-01 · META · Publicado en GitHub

- **Qué:** repositorio público https://github.com/gabrielespelleta94/callbench, rama `main`. Commit inicial con 44 ficheros (agente, API, migraciones, evals, tests y bitácora). README reescrito para GitHub: diagrama, decisión sobre `pipecat.evals`, estructura y comandos.
- **Por qué:** enseñar el proyecto en la entrevista de Prosper.
- **Pruebas:** 14 tests en verde antes de subir; revisión de secretos y rutas personales sin hallazgos; en GitHub, `.env` no existe (404).
- **Siguiente:** reponer la semilla de la agenda antes de cada suite de evals; corregir el prompt de Ana con los fallos encontrados; cola (F3).

## 2026-11-01 · META · Preparación para publicar en GitHub

- **Qué:** comentarios y docstrings del código traducidos al inglés (la bitácora sigue en español). `.gitignore` en inglés; `CLAUDE.md` y `.claude/` se quedan en local. Revisión de secretos y rutas personales en los ficheros publicables: ninguno. Extra `cli` de Pipecat instalado (trae `questionary`), con lo que el lanzador de evals ya no necesita un simulacro.
- **Por qué:** el repositorio es público y lo leerán en inglés (D-12).
- **Ficheros:** `app/`, `agent/`, `migrations/`, `tests/`, `evals/`, `alembic.ini`, `.gitignore`, `pyproject.toml`, `uv.lock`.
- **Pruebas:** 14 tests en verde tras la traducción.

## 2026-11-01 · F4 · Primeros exámenes con pipecat.evals

- **Qué:** el bot acepta el transporte `eval` (websocket RTVI en `/ws`) además de WebRTC. Carpeta `evals/` con un escenario guionizado (`saludo_y_huecos`) y dos simulaciones con persona (`cita_dr_lopez`, `medico_inexistente`). Juez (`gpt-oss-120b`) y persona (`qwen3.8-27b`, sin razonamiento) servidos por Groq mediante `factory` (D-13). Lanzador `evals/lanzar.py`.
- **Resultados:** `saludo_y_huecos` aprobado tras darle nombre y fecha en el guion; `medico_inexistente` aprobado (P(yes)=0,98); `cita_dr_lopez` suspendido porque ya no quedaban huecos libres: Ana dijo la verdad y no reservó.
- **Fallos de Ana que han salido:** pide el nombre antes de consultar huecos; sin fecha se inventa una ("jueves 5"); en una ejecución inventó un "Dr. Martinez"; a veces reserva sin que el paciente lo confirme; el comportamiento varía entre ejecuciones. Con `gpt-oss` como persona, el simulador escribía varios turnos de golpe (por eso se cambió a Qwen).
- **Por qué importa:** son exactamente los fallos que CallBench debe medir a escala y por versión.
- **Ficheros:** `agent/bot.py`, `evals/*`.
- **Pendiente:** las pruebas dejaron ocupados los huecos 1, 2 y 4. Hace falta un modo de reponer la semilla antes de cada suite para que los exámenes sean reproducibles.
- **Siguiente:** reinicio de datos antes de cada suite; corregir el prompt con los fallos encontrados y medir si mejora; cola de trabajos (F3).

## 2026-11-01 · F2 · Postgres portátil sin procesos huérfanos

- **Qué:** `podar_pids()` quita de `.pgdata/.handle_pids.json` los PID que ya no existen (`psutil.pid_exists`) justo antes de arrancar pgserver, dentro del mismo `InterProcessLock` que usa pgserver.
- **Por qué:** pgserver solo apaga Postgres si el fichero contiene exactamente su propio PID y nunca poda los muertos (`pgserver/postgres_server.py:203`). Un proceso matado a la fuerza dejaba Postgres huérfano para siempre.
- **Ficheros:** `app/db/config.py`, `tests/test_pgserver_pids.py`.
- **Pruebas:** 2 tests nuevos; con un PID muerto en el fichero, `alembic current` arranca y al terminar no queda ningún `postgres.exe`.
- **Riesgo aceptado:** si Windows reutiliza el PID muerto para otro proceso, ese PID no se poda (raro y sin daño: Postgres solo tarda en apagarse).

## 2026-11-01 · F2 · API sobre PostgreSQL portátil con migraciones

- **Qué:** la API pasa de memoria a PostgreSQL con `pgserver` (datos en `.pgdata/`, o `DATABASE_URL` si existe). SQLAlchemy 2 async + psycopg 3, endpoints async con `Depends(get_session)`. Alembic con dos migraciones: esquema (`huecos`, `citas` con `UNIQUE (hueco_id)`) y semilla de los 4 huecos. Reserva con `UPDATE ... WHERE libre RETURNING` en una transacción.
- **Por qué:** persistir los datos y que la doble reserva la impida la base de datos, no el código (D-08, D-09).
- **Ficheros:** `app/main.py`, `app/db/` (`config.py`, `conexion.py`, `modelos.py`, `bucle.py`), `alembic.ini`, `migrations/`, `tests/conftest.py`, `tests/test_api.py`, `.gitignore`.
- **Pruebas:** 7 tests en verde contra Postgres real, incluido uno de concurrencia (dos reservas simultáneas del mismo hueco: un 201 y un 409). Prueba manual con `fastapi dev`: 3 huecos libres, 201 y después 409.
- **Notas:** `inicio` sale ahora con zona (`2026-11-03T09:00:00Z`). psycopg async necesita el `SelectorEventLoop` en Windows (`app/db/bucle.py`). Si se mata la API a la fuerza, Postgres puede quedar huérfano y `.pgdata/.handle_pids.json` con un PID muerto: se arregla con `pg_ctl stop -D .pgdata` y vaciando ese fichero (`[]`).
- **Siguiente:** cola de trabajos (F3).

## 2026-11-01 · F4 · Herramientas del agente: consultar huecos y reservar

- **Qué:** `consultar_huecos` (filtra por médico y fecha) y `reservar_cita`, con `FunctionSchema` y `ToolsSchema` registrados en el LLM y pasados al `LLMContext`. Los errores HTTP se traducen a resultados que Ana puede decir (`hueco_ocupado`, `hueco_no_existe`, `datos_invalidos`, `agenda_no_disponible`). Prompt con la fecha de hoy y reglas: solo huecos reales, pedir el nombre completo, no confirmar sin `ok`.
- **Por qué:** sin agenda, Ana aceptó citas con un médico que no existe ("doctor Fernando"). Se adelanta a F3 (D-10).
- **Ficheros:** `agent/herramientas.py`, `agent/bot.py`, `tests/test_herramientas.py`, `.env.example` (`CLINICA_API_URL`), `pyproject.toml` (proyecto instalable, D-11).
- **Pruebas:** 5 tests en verde con `httpx.MockTransport`. `uv run agent/bot.py --help` arranca. Falta una llamada de voz real reservando.
- **Siguiente:** llamada real; transporte `eval` en el bot (extra `websocket` de Pipecat) para `pipecat.evals`; llamantes sintéticos.

## 2026-11-01 · META · Decisión sobre pipecat.evals

- **Qué:** inventario de `pipecat.evals` (Pipecat 1.15): escenarios YAML guionizados y de simulación con persona, juez LLM (por defecto Ollama `gemma4:12b`, configurable), suites con concurrencia 4 en un proceso, resultados en `results.jsonl`. Se conecta al bot por websocket RTVI (`ws://localhost:7860/ws`). No trae histórico, diff entre versiones, coste, p50/p95 por etapa, cola distribuida ni CI.
- **Por qué:** decidir si CallBench reutiliza ese motor. Decisión: sí (D-07).
- **Siguiente:** que el bot acepte el transporte `eval` y un primer escenario.

## 2026-10-31 · F0 · Primera llamada real

- **Qué:** tres fallos resueltos a partir del log: Groq había retirado `llama-3.3-70b-versatile` (404; se pasa a `gpt-oss-120b` con razonamiento `low`); el STT de Deepgram está en inglés, así que una frase en español llegaba vacía y Ana callaba; un "Yeah" contó como interrupción y cortó a Ana.
- **Pruebas:** llamada en inglés a las 14:15. STT 0,32–0,40 s, LLM 0,08–0,82 s, TTS 0,15–0,16 s; ~0,9 s de voz a voz hasta el primer audio. Smart Turn respetó una pausa a mitad de frase (`INCOMPLETE` → `COMPLETE`).
- **Por qué importa:** con el LLM fallando, la gráfica marcaba 1,5 s de latencia falsa. Toda métrica de latencia debe ir acompañada del éxito o fallo de la llamada.
- **Siguiente:** herramientas contra la API (F4).

## 2026-10-31 · META · Bitácora y Gantt del proyecto

- **Qué:** carpeta `docs/bitacora/` con contexto, plan por fases, bitácora y registro de decisiones; script `tools/bitacora.py` que genera el Gantt (Markdown con Mermaid y HTML).
- **Por qué:** tener a la vista el objetivo, el avance real frente al plan y el porqué de cada cambio.
- **Ficheros:** `docs/bitacora/*`, `tools/bitacora.py`, `CLAUDE.md`.
- **Siguiente:** primera llamada real con el agente (F0).

## 2026-10-31 · F1 · API de la clínica en memoria con tests

- **Qué:** FastAPI con `GET /salud`, `GET /huecos`, `POST /citas`, `GET /citas/{id}`. Modelos Pydantic (`Hueco`, `CitaIn`, `Cita`). Datos en memoria con 4 huecos de ejemplo.
- **Por qué:** son las herramientas que el agente llamará en F4; primero se prueban solas.
- **Ficheros:** `app/main.py`, `tests/test_api.py`.
- **Pruebas:** 6 tests en verde (salud, solo libres, 201 y ocupa hueco, 409 doble reserva, 404 hueco inexistente, 422 datos inválidos).
- **Siguiente:** pasar el almacenamiento a PostgreSQL (F2).

## 2026-10-31 · F0 · Agente de voz con Pipecat en el navegador

- **Qué:** tubería Pipecat: audio WebRTC → VAD Silero → STT Deepgram → LLM Groq (`gpt-oss-120b`, razonamiento `low`) → TTS Deepgram (`aura-2-thalia-en`) → audio. Saluda al conectar y cancela al colgar. Métricas de Pipecat activadas.
- **Por qué:** es el agente bajo prueba; sin él no hay nada que evaluar.
- **Ficheros:** `agent/bot.py`.
- **Pendiente:** primera llamada real para validar la tubería de punta a punta.

## 2026-10-31 · META · Arranque del proyecto

- **Qué:** proyecto con uv (Python 3.12), dependencias `pipecat-ai[deepgram,groq,runner,silero,webrtc]`, `fastapi[standard]`, `python-dotenv`, pytest. README con stack y roadmap. `.env.example` y `.gitignore` (excluye `.env` y logs).
- **Ficheros:** `pyproject.toml`, `uv.lock`, `README.md`, `.env.example`, `.gitignore`.
