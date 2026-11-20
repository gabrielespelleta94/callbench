# CallBench · Plan de mejora (fin de semana 21-22 nov 2026)

Objetivo: dejar CallBench **completo, demostrable y publicado**, con cifras **medidas** para el
CV y una comparación Deepgram vs ElevenLabs que se pueda defender en la entrevista de
Applied AI Engineer en ElevenLabs.

Regla de oro: **ninguna cifra entra en el README o el CV si no sale de una vuelta guardada**
(nombre de la vuelta, fecha, N, modalidad y versión del agente al lado).

---

## 0. Estado real hoy (comprobado el 2026-11-20)

| Comprobación | Resultado |
|---|---|
| `uv run pytest` | **30 tests en verde** (78 s, contra Postgres real) |
| API (`uvicorn ... --loop app.db.bucle:selector_loop`) | Arranca; `/salud` ok; `/huecos` responde |
| Agenda | **Caducada**: los huecos eran del 4 de noviembre. Con `app.db.reiniciar` vuelve a la semana actual. Hay que reiniciar antes de cada vuelta |
| Claves de `.env` | Groq y Deepgram válidas (200 en un endpoint de solo lectura). No hay clave de ElevenLabs |
| Extremo a extremo | Bot en vivo + `saludo_y_huecos` y `cita_dr_lopez`: **2/2 aprobados** (27 s) |
| Historial de git | Sin `.env` ni patrones de clave (`gsk_`, `sk-`, claves de Deepgram) en ningún commit |

**Hallazgos que cambian el plan:**

1. **El juez es blando.** En `cita_dr_lopez` Ana reservó **sin repetir los datos ni esperar un
   "sí"** (su prompt lo exige) y el juez aprobó con P(yes)=0,98. Es el mejor argumento para
   los asserts deterministas: el LLM juez no basta.
2. **Los evals son en modalidad texto**: no pasan por STT ni TTS. Para medir latencia de voz y
   comparar Deepgram con ElevenLabs hay que usar la modalidad **audio** de `pipecat.evals`
   (el paciente habla con un TTS y el juez transcribe la voz de Ana con un STT).
3. **Las métricas existen pero se pierden.** Pipecat ya emite TTFB por servicio, uso de tokens y
   tiene `UserBotLatencyObserver`; hoy solo acaban en el log. Falta un observador que las guarde.
4. **El README promete cosas que no hay** (alternativa local Whisper/Ollama/Piper, dashboard
   React). Se corrige en el pulido: lo que no esté, va a "Roadmap".
5. **Cuota de Groq**: la capa gratuita da 200k tokens/día para `gpt-oss-120b` y una suite de 15
   llamadas gasta 40-50k. **Con la capa gratuita no salen 100 llamadas en un día.**

---

## 1. Fases, tareas y esfuerzo

Total estimado: **~22,5 h** de trabajo + vueltas de medición desatendidas (de noche o mientras se
hace otra cosa). Si faltan horas, ver el orden de recorte en §4.

### Fase A · Ponerlo en marcha y entenderlo (2 h)

| Tarea | h |
|---|---|
| Leer [guia-callbench.md](guia-callbench.md) con el código al lado | 0,5 |
| `reiniciar` + API + bot + una llamada real con el micrófono en http://localhost:7860 | 0,5 |
| `suite -r 3` completa (línea base de hoy) + `informe.py` | 0,5 (desatendida) |
| Añadir un `make`-equivalente: `tools/demo.py` que levanta API + bot y comprueba API, huecos libres y cuota **antes** de lanzar (pendiente desde el 2 de noviembre) | 0,5 |

### Fase B · Cerrar el roadmap (12 h)

**B1 · Resultados en Postgres + cola de trabajos (F3) · 3,5 h**

| Tarea | h |
|---|---|
| Migración `0003`: `versiones` (id, etiqueta, git_sha, config STT/LLM/TTS), `vueltas`, `trabajos` (estado, intentos, `lease_hasta`, error), `llamadas` (resultado, transcripción, métricas JSON) | 1 |
| Worker: `SELECT ... FOR UPDATE SKIP LOCKED` toma un trabajo (escenario × intento), arranca un bot en su puerto, ejecuta el escenario y guarda el resultado | 1,5 |
| Reintentos **solo para infraestructura** (reusar la clasificación de `informe.py`), con backoff y máximo 3; los suspensos de Ana no se reintentan | 0,5 |
| Chaos test: matar el worker a mitad → el lease caduca → otro worker lo recoge; test de pytest | 0,5 |

Concurrencia: 1-2 workers (Groq limita). Con dos workers se gana tiempo sin disparar 429s
del juez; medirlo.

**B2 · Asserts deterministas + juez (F4b) · 2,5 h**

| Assert | Cómo se comprueba |
|---|---|
| Reserva correcta | Tras la llamada, la tabla `citas` tiene una cita para ese paciente, con ese médico, en un hueco que devolvió `consultar_huecos` |
| No reservar sin "sí" | En `duda_y_pide_pensarlo`, cero citas nuevas. En todos: antes de `reservar_cita`, el turno anterior de Ana repite médico + hora y el siguiente del paciente es afirmativo (caza el hallazgo 1) |
| No inventar | Ningún médico ni hora en lo que dice Ana que no salga de la base de datos (lista cerrada de médicos + horas devueltas) |
| Orden de herramientas | `consultar_huecos` antes de pedir el nombre y antes de `reservar_cita` |

Una llamada aprueba si **pasan los asserts y el juez**; se guardan los dos por separado para
poder decir "el juez aprobó X llamadas que los asserts suspendieron". Ese número es oro para
la entrevista. Añadir dos personas nuevas si da tiempo: el que da mal su nombre y lo corrige,
y el que interrumpe (este solo tiene sentido en modalidad audio). 2,5 h incluyendo tests.

**B3 · Gate de CI · 1,5 h**

- GitHub Actions en cada push: `uv sync` + `pytest` (pgserver trae binarios de Linux; si falla,
  servicio `postgres` de Actions con `DATABASE_URL`).
- `tools/comparar.py <base> <candidata>`: sale con 1 si **algún escenario** baja su tasa de
  aprobado más allá del ruido (regla simple y explicable: intervalo de Wilson al 95 % de la
  candidata por debajo del de la base, o caída ≥ 2 aprobados con N=10), o si p95 sube > 20 %.
- Job `evals` manual (`workflow_dispatch`) con `GROQ_API_KEY` y `DEEPGRAM_API_KEY` como secretos
  de GitHub, N pequeño, que ejecuta la suite y el gate. Las evals no corren en cada push (cuota).

**B4 · Latencia por etapa y coste (F5) · 1,5 h**

- Observador en `agent/bot.py` que escribe un JSONL por llamada: TTFB de STT, LLM y TTS por
  turno, latencia voz a voz (`UserBotLatencyObserver`), tokens de entrada/salida, caracteres
  enviados al TTS y segundos de audio al STT. El worker lo guarda en `llamadas`.
- `costes.toml`: precio por unidad de cada proveedor **copiado de su página de precios con la
  fecha**; el coste por llamada se calcula con lo medido × tarifa de lista (aunque se use capa
  gratuita, se informa al precio de lista y se dice).
- Fuera de este fin de semana: la alternativa local (Whisper/Ollama/Piper); sale del README.

**B5 · Scorecard React (F6) · 3 h** (sin contar el pulido visual)

- FastAPI: `GET /vueltas`, `GET /vueltas/{id}`, `GET /diff?base=&candidata=`.
- Vite + React + TypeScript en `dashboard/`: selector de dos vueltas; tabla por escenario
  (aprobado base → candidata, con color), p50/p95 voz a voz y por etapa, coste por llamada, y
  "juez vs asserts". Clic en una llamada → transcripción.
- Captura del scorecard para el README.

### Fase C · Métricas reales para el CV (1,5 h propias + vueltas desatendidas)

| Vuelta | Config | N | Modalidad |
|---|---|---|---|
| `base-texto` | Groq + (sin voz) | 50 (5 escenarios × 10) | texto: tasa de éxito y asserts |
| `deepgram-audio` | Deepgram STT + Groq + Deepgram TTS | 30-50 | audio: latencia y coste reales |
| `elevenlabs-audio` | ver Fase D | 30-50 | audio |

- Informe por vuelta: % éxito con intervalo de confianza, p50/p95 voz a voz y por etapa, coste
  medio por llamada, fallos de infraestructura aparte.
- **N depende de la cuota de Groq.** Con la capa gratuita: ~4 suites de 15 al día. Para N≥100
  hace falta el plan de pago de Groq (pago por uso) o repartir las vueltas entre sábado y domingo.
- Texto para el CV, **con huecos que solo se rellenan con datos de una vuelta guardada**:
  > CallBench: regression bench for Pipecat voice agents. X% task success over N synthetic
  > calls (deterministic DB asserts + LLM judge), p50/p95 voice-to-voice Y/Z s, $W per call;
  > Postgres job queue with leases and retries, CI gate on per-scenario regressions.

### Fase D · ElevenLabs como opción y comparación con Deepgram (4 h)

| Tarea | h |
|---|---|
| Añadir el extra `elevenlabs` a `pipecat-ai`; `ELEVENLABS_API_KEY` en `.env.example` | 0,25 |
| Selección por configuración: `CALLBENCH_TTS=deepgram\|elevenlabs` y `CALLBENCH_STT=deepgram\|elevenlabs` (ElevenLabs TTS por websocket con un modelo Flash de baja latencia; STT Scribe v2 realtime). La etiqueta de versión guarda la combinación | 1 |
| Escenarios en modalidad audio (`user.modality: audio` con un TTS para el paciente; `judge.modality: audio` con transcripción). La voz del paciente se fija y se cachea (`CachingTTSService` de `pipecat.evals`) para que sea **la misma en las dos configuraciones** | 1 |
| Vueltas `deepgram-audio` y `elevenlabs-audio` (y si da tiempo la cruzada STT Deepgram + TTS ElevenLabs) | 0,5 + desatendido |
| Tabla comparativa y nota de metodología | 1,25 |

**Qué se compara y cómo, sin trampas:**

| Eje | Métrica | Objetiva |
|---|---|---|
| Latencia | TTFB del TTS p50/p95; voz a voz p50/p95; TTFB del STT | Sí |
| Coste | caracteres TTS × tarifa + minutos STT × tarifa, por llamada | Sí |
| Calidad STT | **WER** de lo que transcribe el STT de Ana frente al texto que dijo el paciente (lo conocemos: lo generó el LLM persona) | Sí |
| Calidad TTS | Inteligibilidad: transcribir el audio de Ana con un STT fijo y comparar con el texto que mandó el LLM (WER inverso). Más una escucha ciega propia de 10 pares, puntuada 1-5, diciendo que es subjetiva | Parcial |
| Efecto en la tarea | % éxito de la suite en audio con cada combinación | Sí |

Mismo LLM, mismos escenarios, misma voz del paciente, misma red y misma hora aproximada; se
publica el N y la fecha. Si ElevenLabs gana en algo y pierde en otro, se cuenta tal cual: en la
entrevista vale más una comparación honesta que una favorable.

### Fase E · Pulido para GitHub (3 h)

| Tarea | h |
|---|---|
| README en inglés: qué es, diagrama en Mermaid (se renderiza en GitHub), tabla de resultados con N/fecha/vuelta, Deepgram vs ElevenLabs, cómo ejecutarlo, roadmap honesto | 1,25 |
| Vídeo/GIF de una llamada: grabación con la barra de juegos de Windows (Win+Alt+R, sin admin) de una llamada real en el navegador con el log al lado; se sube como mp4 al README (GitHub lo reproduce) o GIF corto | 0,5 |
| Badge de CI, `LICENSE` (MIT), `.env.example` en inglés con las tres claves vacías y comentarios | 0,25 |
| Revisión de secretos: historial (`git log -p` con patrones + `uvx detect-secrets scan` o `gitleaks` portable), `.gitignore` (añadir `dashboard/node_modules`, `*.wav`), y que `evals/runs` siga fuera | 0,5 |
| Bitácora, `plan.toml` (fases nuevas F7 ElevenLabs y F8 publicación, fechas de F3-F6 a 21-22 nov), Gantt, CONTEXTO | 0,5 |

---

## 2. Orden del fin de semana

**Sábado 21 (~10,5 h)**

| Hora | Bloque |
|---|---|
| 09:00-11:00 | **A**: guía, llamada real, línea base `suite -r 3`, `tools/demo.py` |
| 11:00-14:30 | **B1**: migración, worker, reintentos, chaos test |
| 15:30-18:00 | **B2**: asserts deterministas + tests; re-ejecutar la línea base con asserts |
| 18:00-19:30 | **B4**: observador de métricas + `costes.toml` |
| 19:30-20:00 | Lanzar `base-texto` N=50 desatendida (si la cuota lo permite) |
| (noche) | Vuelta desatendida. Activar "mantener despierto" (el 2 de noviembre una suspensión del PC mató una vuelta) |

**Domingo 22 (~10,5 h)**

| Hora | Bloque |
|---|---|
| 09:00-09:30 | Revisar la vuelta nocturna con `informe.py` |
| 09:30-13:30 | **D**: ElevenLabs, modalidad audio, vueltas `deepgram-audio` y `elevenlabs-audio` (corren mientras se hace B3) |
| 13:30-15:00 | **B3**: GitHub Actions + `comparar.py` |
| 16:00-19:00 | **B5**: scorecard React con las vueltas reales |
| 19:00-21:00 | **C + E**: tabla de resultados, README, vídeo, licencia, revisión de secretos |
| 21:00 | Commit y push **solo con tu OK** |

---

## 3. Riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Cuota diaria de Groq (429) | Alta | No salen las vueltas grandes | Plan de pago de Groq, o N=30-50 repartido en dos días; el informe ya separa infra |
| Juez y persona no deterministas | Alta | Diferencias que son ruido | Repeticiones, intervalos de confianza, asserts deterministas como criterio principal |
| Modalidad audio de `pipecat.evals` inestable o lenta | Media | Fase D sin cifras | Probarla el domingo a primera hora con un escenario; plan B: medir latencia con llamadas reales del navegador (pocas, N≈10, dicho así) |
| Créditos de ElevenLabs insuficientes en la capa gratuita | Media | Corta la comparación | Plan de entrada de pago un mes; respuestas cortas de Ana ya ahorran caracteres |
| Postgres portátil (pgserver) en Actions | Media | CI rojo | Servicio `postgres` de Actions con `DATABASE_URL` (ya soportado) |
| PC suspendido / red corporativa | Media | Vueltas perdidas | Mantener despierto; preflight de API, huecos y cuota antes de lanzar |
| Cambios de API en `pipecat-ai` | Baja | Roturas | Fijar la versión en `uv.lock` (ya está) |
| Exceso de alcance | Alta | No se publica nada | Orden de recorte (§4); publicar el domingo aunque falte algo |
| Cifras exageradas en el CV | — | Credibilidad en la entrevista | Cada cifra con N, fecha, modalidad y vuelta; nada estimado |

## 4. Si falta tiempo, se recorta en este orden

1. Scorecard React → informe HTML estático generado desde Postgres (1 h en vez de 3).
2. Personas nuevas (interrumpe, nombre erróneo).
3. Configuración cruzada STT/TTS en la Fase D (quedarse con Deepgram-Deepgram vs ElevenLabs-ElevenLabs).
4. Chaos test (dejar reintentos y leases con un test unitario).

**No se recorta**: asserts deterministas, métricas guardadas, comparación ElevenLabs, README
honesto y revisión de secretos.

## 5. Qué necesito de ti

| Qué | Para qué | Cuándo |
|---|---|---|
| Cuenta de **ElevenLabs** y `ELEVENLABS_API_KEY` en tu `.env` (nunca en el chat ni en el repo). Mirar si la capa gratuita llega; si no, el plan de entrada | Fase D | Antes del domingo |
| Decidir si pasas Groq a **pago por uso** | N≥100 y vueltas sin 429 | Sábado por la mañana |
| Comprobar el saldo de Deepgram | Vueltas en audio | Sábado |
| Secretos de GitHub (`GROQ_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`) en el repo, si quieres el job de evals en CI | B3 | Domingo |
| Elegir licencia (propuesta: MIT) | E | Domingo |
| Grabar tú la llamada (tu voz y tu micrófono) | Vídeo del README | Domingo |
| OK explícito para: empezar a implementar, cada commit y el push | Todo | Ahora |
