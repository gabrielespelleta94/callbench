# CallBench · Decisiones

Decisiones de diseño con su porqué, para no volver a discutirlas. Numeradas; una
decisión que se cambia no se borra: se marca **Sustituida por D-xx**.

| # | Fecha | Decisión | Por qué | Alternativas descartadas | Estado |
|---|---|---|---|---|---|
| D-01 | 2026-10-31 | Transporte SmallWebRTC (micrófono del navegador) | Probar sin número de teléfono ni proveedor SIP | Twilio / Daily | Vigente |
| D-02 | 2026-10-31 | Groq para el LLM y Deepgram para STT/TTS | Latencia baja y capa gratuita; hay alternativa local para F5 | OpenAI, ElevenLabs | Vigente |
| D-03 | 2026-10-31 | `gpt-oss-120b` con `reasoning_effort="low"` | Piensa poco antes de hablar: menos latencia al primer audio | Modelo sin razonamiento | Vigente |
| D-04 | 2026-10-31 | API de la clínica en memoria en F1 | Validar contrato y errores (404/409/422) antes de meter base de datos | Postgres desde el día 1 | Sustituida por D-08 |
| D-05 | 2026-10-31 | Cola de trabajos en PostgreSQL con `FOR UPDATE SKIP LOCKED` | Una sola pieza de infraestructura; aprender leases y reintentos a mano | Redis, Celery, RabbitMQ | Vigente |
| D-06 | 2026-10-31 | Bitácora en Markdown + plan en TOML + Gantt generado | Todo en el repo, legible sin herramientas, Gantt siempre coherente con el plan | Jira, Notion, hoja de cálculo | Vigente |
| D-07 | 2026-11-01 | CallBench se monta encima de `pipecat.evals` (opción A) | Ya trae escenarios YAML, personas simuladas y juez; le faltan histórico, diff entre versiones, coste, p50/p95, cola con reintentos y CI, que es lo que aporta CallBench | Motor propio de llamantes y juez (opción B) | Vigente |
| D-08 | 2026-11-01 | PostgreSQL portátil con `pgserver` (datos en `.pgdata/`); `DATABASE_URL` si existe | Sin Docker ni permisos de administrador en Windows | Docker, instalador de Postgres, SQLite | Vigente |
| D-09 | 2026-11-01 | La doble reserva se impide en la base de datos: `UPDATE ... WHERE libre RETURNING` + `UNIQUE (citas.hueco_id)` | La integridad no puede depender del código de la aplicación con varios workers | Comprobar y escribir en Python | Vigente |
| D-10 | 2026-11-01 | Tool calling (parte de F4) antes que F3 | Es lo que hace Prosper y lo más visible; la cola tiene más sentido con algo real que repartir | Orden estricto F2 → F3 → F4 | Vigente |
| D-11 | 2026-11-01 | Proyecto instalable (hatchling, paquetes `agent` y `app`) | `uv run agent/bot.py` no encontraba `agent.herramientas`; los workers de F3 también importarán los dos paquetes | Manipular `sys.path` o lanzar con `python -m` | Vigente |
| D-12 | 2026-11-01 | Comentarios del código en inglés desde la publicación; bitácora en español | El repo es público y lo leerá gente que no habla español; la bitácora es material de trabajo propio | Publicar en español y traducir después | Vigente |
| D-13 | 2026-11-01 | Juez y persona simulada de `pipecat.evals` con Groq (`factory`), no con Ollama | Sin GPU; mismo proveedor que el agente. Persona con Qwen sin razonamiento porque `gpt-oss` escribía varios turnos de golpe | Ollama `gemma4:12b` (por defecto) | Vigente |
| D-14 | 2026-11-01 | Comparar versiones por escenario y con repeticiones (`suite -r 3`), no por el total de una ejecución | Ana no responde igual cada vez y un total igual (10/15) escondía mejoras y regresiones a la vez | Una ejecución por escenario; solo el total | Vigente |
