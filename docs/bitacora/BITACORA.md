# CallBench · Bitácora

Registro cronológico de cambios, **la más reciente arriba**. Cada entrada empieza por
una cabecera con este formato exacto (el generador del Gantt la lee):

```
## AAAA-MM-DD · <fase> · <título corto>
```

`<fase>` es un id de [plan.toml](plan.toml) (`F0`, `F1`, `F4b`…) o `META` para lo
que no es de ninguna fase (estructura, documentación, herramientas).

---

## 2026-11-21 · F6 · Gate de regresión, API de resultados y scorecard React

- **Qué:** `bench/resultados.py` reúne la nota de cada llamada (juez + asserts), el resumen por escenario con intervalos de Wilson, la latencia y el coste, y la regla de regresión. Lo usan el gate `tools/comparar.py` (salida 1/2/0, `--json`, `--resumen a+b`) y el router `app/resultados.py` (`GET /vueltas`, `/vueltas/{id}`, `/diff`), montado en `app/main.py`. `tools/importar_vuelta.py` sube a Postgres las vueltas de `suite` con asserts y transcripción. El dashboard `dashboard/` (Vite + React + TS, oscuro) muestra el selector de dos vueltas, el veredicto del gate, la tabla por escenario con deltas e intervalos, la tarjeta "el juez aprobó / los asserts suspendieron", latencia y coste, y el detalle de cada llamada con la transcripción y qué assert falló. En CI, job `evals` manual (`workflow_dispatch`, `-r 2` por defecto) que corre una suite corta y el gate contra `evals/baselines/base.json`. El worker deja las métricas de cada trabajo en su carpeta (`CALLBENCH_METRICS_DIR`) para enlazar latencia y coste con cada llamada.
- **Regla (D-17):** un escenario empeora si pierde ≥2 aprobados respecto a lo que predice la tasa de la base y además su IC95 queda entero por debajo de esa tasa (o N≥10 en los dos lados). La regla literal (solo el IC) marcaba 3/3 → 2/3 como regresión. p95 voz a voz +20 % también falla.
- **Datos:** importadas las 8 vueltas guardadas en `main/evals/runs`. `base-c1` → `final-lunes`: 2/15 (13 %) → 9/13 (69 %), sin regresiones, mejora en `duda_y_pide_pensarlo`. Línea base del CI: `base-2026-11-20+base-2026-11-20-b`, 14/18 (78 %, IC 55-91 %). Ninguna vuelta guardada tiene métricas (modalidad texto): el bloque de latencia y coste sale vacío a propósito, sin cifras inventadas.
- **Por qué:** B3 y B5 de `docs/plan-mejora.md` (F6 se adelanta del 27 nov-4 dic al 21 nov, como en el plan del fin de semana). Un solo módulo para que el CI y el dashboard no discrepen (D-18).
- **Ficheros:** `bench/resultados.py`, `tools/comparar.py`, `tools/importar_vuelta.py`, `app/resultados.py`, `app/main.py`, `bench/worker.py`, `.github/workflows/ci.yml`, `evals/baselines/base.json`, `evals/README.md`, `dashboard/`, `docs/img/scorecard.png`, `tests/test_comparar.py`, `tests/test_resultados_api.py`, `.claude/launch.json`, `.gitignore`.
- **Pruebas:** `uv run pytest`: 189 en verde. `npm run build` sin errores. Scorecard comprobado en el navegador integrado a 1440 px con datos reales (diff, filtros, panel de llamada).
- **Siguiente:** primera vuelta por la cola con métricas para que se rellenen latencia y coste; lanzar el job `evals` en GitHub cuando estén los secretos (aún no se ha ejecutado allí).

## 2026-11-21 · F4 · Línea base con asserts: 14/18 válidas y el juez aprobó las 4 que fallan

- **Qué:** dos rondas de la versión actual de Ana (`base-2026-11-20`, `suite -r 3`, y `base-2026-11-20-b`, `-r 5`), calificadas con juez + asserts por `evals/informe.py`.
- **Resultados:** 40 intentos: 18 válidos y 22 de infraestructura. De los válidos, **14 aprueban (78 %, Wilson 95 %: 55-91 %)**. Los 4 suspensos son todos del mismo assert, `confirmacion_antes_de_reservar` (reserva sin repetir médico y hora o sin un "sí"), y **el juez aprobó los 4**. En `medico_inexistente` #2 (ronda b) Ana dijo "Dr. Fernando has no openings tomorrow", como si existiera.
- **Infraestructura:** 17 intentos de la ronda b murieron con `harness worker exited 3221225794` (0xC0000142, no se pudo iniciar el proceso) cuando terminó la sesión que lanzaba la suite; el resto, procesos del harness caídos y un rechazo de Groq. Además, una vez el LLM de Ana pidió una herramienta inexistente (`file`) y Groq la rechazó: el informe lo cuenta como infra, pero es un fallo del modelo.
- **Por qué:** primera medida con asserts; confirma que el juez solo no basta y que hace falta la cola con reintentos para no perder la mitad de los intentos.
- **Ficheros:** solo bitácora (vueltas en `evals/runs/`, fuera de git).
- **Siguiente:** arreglar la confirmación antes de reservar (prompt y guarda en la herramienta) y volver a medir por la cola (`bench`), con N≥10 por escenario.
- **Pruebas:** `informe.py` sobre las dos rondas.

## 2026-11-20 · META · Unidas en main las ramas de cola, asserts, métricas+CI y guía

- **Qué:** merge en `main` de `claude/docs-como-se-hizo`, `claude/f3-cola`, `claude/f4b-asserts` y `claude/f5-metricas-ci`. Conflictos solo en bitácora, Gantt y `evals/README.md` (se conservan las secciones de las dos ramas). `evals/informe.py` importa `asserts` como script o como `evals.asserts`, porque el worker de la cola lo importa como paquete.
- **Por qué:** juntar el trabajo de las sesiones en paralelo antes de medir y publicar.
- **Observado:** `informe.py final-lunes` con asserts: el juez aprobó 4 llamadas que los asserts suspendieron.
- **Ficheros:** `evals/informe.py`, bitácora, Gantt.
- **Siguiente:** vuelta de línea base con cola, asserts y métricas guardadas; workflow de CI en GitHub tras el push.
- **Pruebas:** `uv run pytest`: 110 en verde.

## 2026-11-20 · META · Documento "Cómo se hizo" para preparar la entrevista

- **Qué:** `docs/como-se-hizo.md`: cronología por fases con lo que falló y cómo se arregló, recorrido comentado de `agent/bot.py`, `agent/herramientas.py`, la reserva atómica de `app/main.py` y `evals/informe.py`, receta para escribir un escenario, 7 ejercicios de 15 minutos y 20 preguntas de entrevista con respuesta corta.
- **Por qué:** poder explicar y defender cada decisión en la entrevista de ElevenLabs sin inventar cifras; enlaza `guia-callbench.md` en lugar de repetirla.
- **Hallazgo:** el historial de git empieza con un commit inicial único; la cronología real de F0-F2 solo está en la bitácora. La bitácora no detalla el arreglo del "Yeah" que cortó a Ana.
- **Ficheros:** `docs/como-se-hizo.md`, `docs/bitacora/BITACORA.md`, Gantt regenerado.
- **Pruebas:** solo documentación; números de línea y cifras contrastados con el código y la bitácora. Los ejercicios no se han ejecutado.

## 2026-11-20 · F3 · Resultados en Postgres y cola de trabajos con leases y reintentos

- **Qué:** migración `0003` con `versiones` (etiqueta, commit, config STT/LLM/TTS en JSONB), `vueltas`, `trabajos` (estado, intentos, `disponible_en`, `lease_hasta`, worker, error) y `llamadas` (veredicto, causa, juez y asserts en columnas separadas, transcripción, métricas, el registro completo de pipecat). Paquete `bench/`: `bench.encolar` crea la vuelta (escenario × intentos, primero todos los intentos 1), `bench.worker` toma trabajos con `FOR UPDATE SKIP LOCKED` y lease renovado por un hilo, arranca un bot nuevo en su puerto, ejecuta el escenario y guarda el resultado clasificado con `evals/informe.py`. Solo se reintenta la infraestructura (backoff 30 s, 60 s; máximo 3 ejecuciones); los suspensos de Ana son definitivos. Un worker que perdió su lease no escribe nada.
- **Por qué:** guardar cada llamada con su versión para comparar vueltas (B3, B5) y que una caída o un 429 no cuenten como suspenso ni maten la vuelta.
- **Decisión:** `pipecat eval run` no deja `results.jsonl` (solo `suite`, que arranca sus propios bots). `bench.ejecutar` ejecuta el mismo código que `run` y añade el registro que escribe `suite`, así `informe.py` lo clasifica sin cambios (D-16).
- **Ficheros:** `migrations/versions/0003_cola_y_resultados.py`, `app/db/modelos.py`, `bench/` (`cola.py`, `encolar.py`, `worker.py`, `ejecutar.py`), `pyproject.toml`, `tests/test_cola.py`, `tests/worker_que_muere.py`, `evals/README.md`.
- **Pruebas:** `uv run pytest`: 54 en verde (24 nuevos, sin Groq: SKIP LOCKED con 6 hilos, leases, backoff, lease perdido, clasificación). Chaos test: un proceso worker real toma un trabajo, se mata con `kill`, el lease caduca y otro worker lo termina (ejecución 2). Contra el bot real (API en 8001, bot en 7970): `saludo_y_huecos` aprobado en 26 s y `cita_dr_lopez` aprobado (juez P=0,97) en 72 s, guardados en `llamadas`.
- **Siguiente:** B2 rellena `aprobado_asserts` y `asserts`; B4 rellena `metricas`. Medir 1 vs 2 workers en una vuelta real.

## 2026-11-20 · F4b · Asserts deterministas junto al juez LLM

- **Qué:** `evals/asserts.py` evalúa cada llamada con cinco asserts (`reserva_correcta`, `sin_reserva`, `confirmacion_antes_de_reservar`, `no_inventa`, `orden_herramientas`) a partir de `conversation.json`, de los resultados de las herramientas que deja el log del bot y, si existe, de una foto de `huecos`/`citas` (`uv run python evals/asserts.py foto <vuelta>` → `estado_bd.json`). Qué asserts aplican a cada escenario va en `evals/asserts.toml`. `evals/informe.py` da el veredicto combinado (aprueba solo si pasan juez y asserts; infra sigue siendo infra), una tabla juez vs asserts y la línea "el juez aprobó N llamadas que los asserts suspendieron". Códigos de salida 0/1/2 sin cambios; `--solo-juez` reproduce el informe de antes.
- **Por qué:** el juez aprobó con P(yes)=0,98 una reserva hecha sin repetir los datos ni esperar un sí. Un criterio determinista y explicable no depende del humor del juez.
- **Hallazgos:** sobre las vueltas ya guardadas, el juez aprobó llamadas que los asserts suspenden: `final-lunes` 4 de 13, `nuevo` 3, `base` 3, `base-c1` 8. Casos claros: `base` #1 (el del hallazgo: pide el nombre antes de consultar y reserva sin repetir nada) y `nuevo` `medico_inexistente` #3 (reserva a nombre de "Maria Garcia" cuando llama Pedro, sin confirmar, y el juez aprueba). La regla de confirmación es estricta a propósito: si Ana repite médico y hora, pide el nombre y reserva sin un sí después, suspende (pasa mucho en `final-lunes`). Si se quiere aceptar el "sí" dado antes de repetir, es un cambio de una línea en `confirmacion_antes_de_reservar`.
- **Límites:** las comprobaciones de texto (horas, médicos, "sí") son patrones en inglés, simples y explicables, no exhaustivos. La foto de BD es de toda la vuelta: la cita de cada llamada se busca por el id que devolvió `reservar_cita`; `sin_reserva` suspende si hay cualquier cita del paciente del escenario. Los escenarios de guion (`saludo_y_huecos`) no dejan `conversation.json`: sus asserts salen n/a.
- **Ficheros:** `evals/asserts.py`, `evals/asserts.toml`, `evals/informe.py`, `evals/README.md`, `tests/test_asserts.py`, `tests/fixtures/vuelta_ejemplo/` (6 llamadas reales recortadas: transcripción y última línea de contexto del log, sin rutas).
- **Siguiente:** sacar la foto de BD al final de cada vuelta (en `lanzar.py` o en el worker de la cola) y re-ejecutar la línea base con asserts. Gate de CI (B3).
- **Pruebas:** `uv run pytest`: 67 en verde (37 nuevos, uno contra el Postgres de test). Sin llamadas al bot ni a Groq.

## 2026-11-20 · F5 · Métricas por llamada, coste y CI con pytest

- **Qué:** observador `CallMetricsRecorder` (`agent/metricas.py`) que escribe un JSONL por llamada en `CALLBENCH_METRICS_DIR` (por defecto `metrics/`, fuera de git) con id de llamada (`CALLBENCH_CALL_ID` si lo pone un worker): `call_start` con la combinación STT/LLM/TTS, TTFB por etapa, tokens (con caché y razonamiento), caracteres al TTS, segundos de audio al STT, voz a voz y su desglose (`UserBotLatencyObserver`) y `call_end` con totales. El bot activa `enable_usage_metrics`. STT y TTS se eligen con `CALLBENCH_STT`/`CALLBENCH_TTS` (`agent/proveedores.py`, solo `deepgram`; ElevenLabs es una entrada más en la Fase D). `costes.toml` con tarifas de lista leídas hoy: Groq `gpt-oss-120b` 0,15 $/M entrada, 0,075 $/M en caché, 0,60 $/M salida (console.groq.com; groq.com/pricing no da precios por modelo); Deepgram Nova-3 streaming 0,0048 $/min (precio promocional, antes 0,0077) y Aura-2 0,030 $/1k caracteres (deepgram.com/pricing). `tools/coste.py` da coste por llamada y p50/p95 de coste, voz a voz y TTFB por etapa; se niega a poner coste si falta una tarifa o está `pendiente`. CI (`.github/workflows/ci.yml`): uv + Python 3.12 + `uv run pytest` en push y PR, con servicio `postgres:16` y `DATABASE_URL` (`tests/conftest.py` ahora lo respeta); el job `evals` manual queda comentado hasta que haya secretos.
- **Por qué:** las métricas de Pipecat solo acababan en el log (hallazgo 3 del plan); sin ellas no hay p50/p95 ni coste, ni comparación con ElevenLabs.
- **Hallazgos:** (1) Pipecat 1.15 **no emite uso de TTS** con el `DeepgramTTSService` por websocket (solo la variante HTTP y el modo de tokens en streaming), así que el observador cuenta además el texto hablado (`TTSTextFrame`) y `coste.py` lo usa como estimación marcada con `*` si no hay `tts_usage`. (2) En modalidad texto de `pipecat.evals` no hay STT ni VAD: cero segundos de audio y ninguna línea de voz a voz; esas cifras solo saldrán de la modalidad audio (Fase D) o de llamadas reales. (3) Groq informa `prompt_tokens` bruto (incluye la caché): el coste descuenta los tokens en caché y los cobra a su tarifa.
- **Ficheros:** `agent/metricas.py`, `agent/proveedores.py`, `agent/bot.py`, `costes.toml`, `tools/coste.py`, `tests/test_metricas.py`, `tests/test_coste.py`, `tests/conftest.py`, `.github/workflows/ci.yml`, `.env.example`, `.gitignore`, `docs/bitacora/plan.toml`.
- **Pruebas:** `uv run pytest` 49 en verde (19 nuevos, sin red); el camino `DATABASE_URL` probado en local con los tests de API. Dos llamadas cortas de `saludo_y_huecos` contra el bot real (API 8003, bot 7990), aprobadas: la primera mostró el hueco del TTS y la segunda confirmó el arreglo (115 caracteres estimados). Unos 2.000 tokens de Groq por llamada, 0,0037 $ a precio de lista. El workflow de CI no se ha ejecutado todavía en GitHub (la rama no está subida).
- **Plan:** F5 pasa a `en_curso`, fechas al 20-22 nov y sin la alternativa local (fuera del fin de semana según `docs/plan-mejora.md`).
- **Siguiente:** que el worker de F3 guarde el JSONL en `llamadas`; `tools/comparar.py` (gate de B3) y descomentar el job `evals` cuando estén los secretos; ElevenLabs en `proveedores.py` y `costes.toml` (Fase D).

## 2026-11-20 · META · Plan de mejora para el fin de semana y guía del proyecto

- **Qué:** `docs/plan-mejora.md` (fases A-E con horas, orden sábado/domingo, riesgos, recortes y lo que hace falta de Gabriel) y `docs/guia-callbench.md` (pipeline, herramientas, evals y decisiones, en 20 minutos). Comprobado el estado real: tests, API, claves y dos escenarios contra el bot en vivo.
- **Por qué:** dejar CallBench completo y publicado con cifras medidas, y comparar Deepgram con ElevenLabs.
- **Hallazgos:** la agenda estaba caducada (huecos del 4 de noviembre) hasta `reiniciar`. En `cita_dr_lopez` Ana reservó sin repetir los datos ni esperar un sí y el juez aprobó con P(yes)=0,98: hacen falta asserts deterministas. Los evals van en modalidad texto, así que no miden STT ni TTS. Las métricas de Pipecat (TTFB, tokens) solo llegan al log. El README promete la alternativa local y el dashboard, que no existen.
- **Ficheros:** `docs/plan-mejora.md`, `docs/guia-callbench.md`.
- **Siguiente:** con el OK de Gabriel, actualizar `plan.toml` (F3-F6 al 21-22 nov, fases nuevas de ElevenLabs y publicación) y empezar por la Fase A.
- **Pruebas:** `uv run pytest`: 30 en verde (78 s). `saludo_y_huecos` + `cita_dr_lopez` contra el bot en vivo: 2/2 (27 s). Claves de Groq y Deepgram válidas. Historial de git sin `.env` ni patrones de clave.

## 2026-11-02 · F4 · Informe que separa suspensos de fallos de infraestructura

- **Qué:** `uv run python evals/informe.py <vuelta>` clasifica cada intento como aprobado, suspenso o infra (juez sin respuesta, Groq rechaza la llamada a herramienta, proceso del bot muerto, API caída detectada por `agenda_no_disponible` en el log, cualquier otro error). La tasa se calcula sobre intentos válidos. Código de salida: 0 todo aprobado, 1 algún suspenso, 2 sin suspensos pero con infra (no concluyente). Avisa si hay intentos repetidos por reutilizar el nombre.
- **Por qué:** se perdieron tres vueltas por causas ajenas a Ana que contaban como suspensos. El código de salida deja preparada la puerta de CI de F4b.
- **Limitación:** la caída de la API solo se ve en el log del intento, y reutilizar el nombre los sobrescribe. En `final`, tres intentos de la vuelta sin API salen como suspenso porque su log ya es de una vuelta posterior; de ahí el aviso. La cuota agotada y la API caída se detectan después de gastar la vuelta: falta comprobarlas antes de lanzar.
- **Ficheros:** `evals/informe.py`, `tests/test_informe.py`, `evals/README.md`.
- **Siguiente:** comprobación previa de API, huecos y cuota; cola (F3).
- **Pruebas:** `final-lunes` da 13 aprobados, 0 suspensos, 2 infra, salida 2. 30 tests en verde.

## 2026-11-02 · F4 · Versión final medida: 13/15, y los 2 fallos no son de Ana

- **Qué:** medida la versión con prompt y herramientas corregidos (`suite -r 3 -n final-lunes`, API levantada y agenda reiniciada).
- **Resultados (aprobados/3):**

  | Escenario | Línea base | Solo prompt | Prompt + herramientas |
  |---|---|---|---|
  | saludo_y_huecos | 2 | 0 | 3 |
  | cita_dr_lopez | 1 | 3 | 2 |
  | medico_inexistente | 2 | 3 | 3 |
  | lo_antes_posible | 3 | 1 | 2 |
  | duda_y_pide_pensarlo | 2 | 3 | 3 |
  | **Total** | **10/15** | **10/15** | **13/15** |

- **Los 2 suspensos:** son `harness_error` del lado del examen, no de Ana: Groq rechaza una llamada a herramienta mal formada (`target_text`, inexistente, y `Failed to call a function`). Lo más probable es que venga de la persona simulada (qwen), que es quien cuelga con `end_call`; falta confirmarlo. En `cita_dr_lopez` #2 Ana ya había confirmado la reserva; en `lo_antes_posible` #2 la llamada se cortó antes de reservar. Ana aprueba 13 de los 13 intentos que terminaron bien.
- **Por qué:** cierra el bucle medir → arreglar → medir. Antes de esta vuelta se perdieron tres por causas ajenas a Ana: API sin levantar (`agenda_no_disponible`), cuota diaria de Groq agotada (`judge call failed`) y PC suspendido durante la noche (`ProcessLookupError`, intentos de casi 14 h).
- **Observado:** reutilizar el nombre con `-n` acumula las vueltas en el mismo `results.jsonl`, así que cada vuelta necesita un nombre nuevo. Cada suite reserva unos 7 huecos: conviene reiniciar la agenda antes de cada vuelta. En `cita_dr_lopez` #2 un turno de Ana junta dos frases ("Which would you prefer?I'll book you for Dr. Lopez..."), adelantándose al paciente; sin efecto en la nota, pero el juez no lo penaliza.
- **Ficheros:** solo bitácora y contexto; sin cambios de código.
- **Siguiente:** contar los errores de infraestructura aparte de los suspensos y comprobar API, huecos y cuota antes de lanzar; cola (F3). Con 3 repeticiones por escenario la diferencia es orientativa.
- **Pruebas:** `suite -r 3` en `evals/runs/final-lunes`, 13/15.

## 2026-11-01 · F4 · Primer bucle medir → arreglar → medir

- **Qué:** `uv run python -m app.db.reiniciar` repone la agenda de desarrollo con huecos de los próximos 5 días laborables (35 huecos, relativos a hoy). Dos escenarios nuevos: `lo_antes_posible` (sin fecha) y `duda_y_pide_pensarlo` (no reservar sin un sí). Manifiesto `evals/suite.yaml` para repetir con `suite -r 3`. Prompt de Ana reescrito: consultar antes de pedir el nombre, no filtrar por la fecha de hoy si no la dan, solo médicos y horas que devuelva la herramienta, repetir los datos y esperar un sí antes de reservar. Herramientas: argumentos opcionales admiten `null` y "Doctor Lopez" casa con "Dr. Lopez".
- **Resultados (aprobados/3):**

  | Escenario | Línea base | Solo prompt |
  |---|---|---|
  | saludo_y_huecos | 2 | 0 |
  | cita_dr_lopez | 1 | 3 |
  | medico_inexistente | 2 | 3 |
  | lo_antes_posible | 3 | 1 |
  | duda_y_pide_pensarlo | 2 | 3 |
  | **Total** | **10/15** | **10/15** |

- **Lectura:** el total no cambia, pero por dentro sí: el prompt arregla reservar sin confirmación y el médico inventado, y destapa dos fallos de las herramientas (el filtro no reconocía "Doctor Lopez"; Groq rechazaba la llamada si el modelo mandaba `null` en un argumento opcional). **Un total agregado esconde regresiones: hay que comparar por escenario.**
- **Sin medir:** la versión con las herramientas arregladas. Se agotó la cuota diaria de Groq (200.000 tokens/día para `gpt-oss-120b`, error 429) y 14 de 15 ejecuciones fallaron por eso, no por Ana.
- **Ficheros:** `app/db/reiniciar.py`, `tests/test_reiniciar.py`, `tests/test_herramientas.py`, `agent/bot.py`, `agent/herramientas.py`, `evals/*`.
- **Pruebas:** 17 tests en verde. Unas 90 llamadas simuladas; cada suite completa gasta 40-50k tokens de Groq.
- **Siguiente:** cuando se renueve la cuota, `reiniciar` y repetir la suite para medir la versión final. Distinguir en los resultados un fallo de infraestructura (429, juez caído) de un suspenso de Ana: hoy los dos cuentan igual.

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
