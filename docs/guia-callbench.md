# CallBench en 20 minutos

Guía para entender (y defender en una entrevista) qué hace CallBench, cómo está montado
y por qué. Estado a 2026-11-20. El detalle día a día está en
[bitacora/BITACORA.md](bitacora/BITACORA.md) y las decisiones en
[bitacora/DECISIONES.md](bitacora/DECISIONES.md).

---

## 1. La idea en una frase

Un agente de voz cambia (prompt, modelo, proveedor de voz) y nadie sabe si ha mejorado o
empeorado. CallBench lo llama con **pacientes sintéticos**, **puntúa cada llamada** y
**compara la versión nueva con la anterior** en tasa de éxito, latencia y coste. Es lo
mismo que un test de regresión, pero para conversaciones.

## 2. Las tres piezas

```
                 ┌──────────────────────── agent/bot.py (Ana) ────────────────────────┐
navegador ─WebRTC─┤ entrada → VAD Silero → STT Deepgram → LLM Groq → TTS Deepgram → salida │
pipecat.evals ─WS─┤                                 │ tool calls                         │
                 └─────────────────────────────────┼────────────────────────────────────┘
                                                   ▼
                                  app/main.py (FastAPI)  ──>  PostgreSQL (pgserver, .pgdata/)
```

| Pieza | Qué es | Dónde |
|---|---|---|
| **Agente (Ana)** | Recepcionista de la "Sunrise Family Clinic". Pipeline de Pipecat que convierte audio en texto, lo pasa al LLM, y el texto de vuelta a audio | `agent/bot.py` |
| **Herramientas** | Dos funciones que el LLM puede llamar: `consultar_huecos` y `reservar_cita`. Llaman por HTTP a la API | `agent/herramientas.py` |
| **API de la clínica** | FastAPI con `/huecos`, `/citas`, `/citas/{id}`, `/salud`. Es el "sistema real" que el agente usa | `app/main.py`, `app/db/` |
| **Base de datos** | PostgreSQL portátil (`pgserver`, sin Docker ni admin). Dos tablas: `huecos` y `citas`. Migraciones con Alembic | `migrations/` |
| **Evals** | Escenarios YAML de `pipecat.evals`: guionizados o simulados con un paciente LLM, y un juez LLM que decide si aprobó | `evals/` |

## 3. Una llamada, paso a paso

1. **Conexión.** El navegador (WebRTC) o el harness de evals (websocket `/ws`) se conecta.
   `on_client_connected` mete "Greet the caller." en el contexto y lanza el LLM: Ana saluda.
2. **Turno del usuario.** El audio entra; **Silero VAD** detecta cuándo empieza y termina de
   hablar; **Deepgram STT** (nova-3) lo pasa a texto; el agregador de usuario lo añade al contexto.
3. **LLM.** Groq `openai/gpt-oss-120b` con `reasoning_effort="low"` (D-03): razona poco para
   que el primer token llegue pronto. Si decide llamar a una herramienta, Pipecat ejecuta el
   handler, devuelve el JSON al LLM y este sigue hablando.
4. **TTS.** El texto se va convirtiendo en audio en streaming (Deepgram `aura-2-thalia-en`) y
   sale por el transporte. El agregador de asistente guarda lo que dijo Ana.
5. **Métricas.** `enable_metrics=True` hace que cada servicio emita TTFB (tiempo hasta el
   primer byte) y uso de tokens. **Hoy solo se ven en el log; no se guardan en ningún sitio.**

**Latencia voz a voz** = desde que el usuario deja de hablar hasta que suena el primer audio
de Ana ≈ fin de VAD + STT final + TTFB del LLM + TTFB del TTS. El "~0,9 s" del README sale de
la primera llamada real (F0), no de una medición con muchas llamadas.

## 4. Las herramientas y la integridad de datos

- `consultar_huecos(medico?, fecha?)`: pide todos los huecos libres y filtra en el cliente.
  Devuelve como mucho 6 (el LLM los lee en voz alta). Normaliza "Doctor Lopez" = "Dr. Lopez".
  Los argumentos aceptan `null` porque Groq rechazaba la llamada entera si el modelo mandaba
  `null` en un campo declarado como `string`.
- `reservar_cita(hueco_id, paciente, motivo?)`: traduce 404/409/422 a mensajes que el LLM
  puede decir ("ese hueco acaba de ocuparse, ofrece otro").
- **Nunca se lanza una excepción al pipeline**: cualquier fallo devuelve
  `agenda_no_disponible`, y Ana se disculpa. Eso además sirve para detectar la API caída.
- **Doble reserva imposible en la base de datos** (D-09):
  `UPDATE huecos SET libre=false WHERE id=:id AND libre RETURNING ...` + `UNIQUE(citas.hueco_id)`.
  Con dos peticiones simultáneas, Postgres bloquea la fila y la segunda no actualiza nada → 409.

## 5. Cómo se evalúa hoy

CallBench se apoya en `pipecat.evals` (D-07) y le añade lo que no tiene.

| Tipo | Cómo funciona | Ejemplo |
|---|---|---|
| **Guionizado** (`turns:`) | Frases fijas del usuario; en cada turno se espera un evento (`function_call`, `response`) y el juez comprueba una frase `eval:` | `saludo_y_huecos` |
| **Simulado** (`simulator:` + `persona:` + `goal:`) | Un LLM hace de paciente (Qwen en Groq, D-13) y cuelga con `end_call`. Al final el juez decide si se cumplió `success:` (da una probabilidad P(yes)) | `cita_dr_lopez`, `lo_antes_posible`, `duda_y_pide_pensarlo`, `medico_inexistente` |
| **Métrica determinista** (`metrics: function_calls`) | Comprueba que se llamaron las herramientas esperadas | `cita_dr_lopez` |

- **Modalidad texto**: hoy los evals mandan texto, no audio. Es decir, **no ejercitan ni el STT
  ni el TTS**. Prueban el cerebro de Ana (prompt + LLM + herramientas), no su voz.
- **Repeticiones** (D-14): `suite evals/suite.yaml -r 3` arranca un bot limpio por intento. Ana
  no responde igual cada vez; un total igual (10/15) escondía mejoras y regresiones.
- **Infraestructura aparte** (D-15): `evals/informe.py` separa suspensos de Ana de fallos
  ajenos (429 de Groq, juez caído, API caída, bot muerto). La tasa se calcula sobre intentos
  válidos; código de salida 0/1/2, pensado ya para el CI.
- **Reiniciar la agenda** antes de cada vuelta (`uv run python -m app.db.reiniciar`): las
  simulaciones reservan de verdad y la semilla es relativa a hoy (5 días laborables).

**Resultado medido hasta ahora** (bitácora, 2026-11-02): 10/15 → 13/15 tras arreglar prompt y
herramientas; los 2 fallos restantes son de infraestructura del examen. N=15, orientativo.

## 6. Decisiones que te van a preguntar

| Pregunta | Respuesta corta | Decisión |
|---|---|---|
| ¿Por qué WebRTC del navegador y no teléfono? | Probar sin número ni proveedor SIP; la telefonía queda fuera de alcance | D-01 |
| ¿Por qué Groq + Deepgram? | Latencia baja y capa gratuita | D-02 |
| ¿Por qué Postgres para la cola y no Redis/Celery? | Una sola pieza de infraestructura; `FOR UPDATE SKIP LOCKED` da reparto entre workers sin colas extra | D-05 |
| ¿Por qué `pgserver`? | Windows sin Docker ni admin | D-08 |
| ¿Por qué encima de `pipecat.evals` y no un motor propio? | Ya trae escenarios, persona y juez; lo que falta es histórico, diff, coste, p50/p95, reintentos y CI | D-07 |
| ¿Por qué otro modelo para el paciente simulado? | `gpt-oss` escribía varios turnos de golpe, incluidos los del bot | D-13 |
| ¿Cómo sabes que una mejora es real y no ruido? | Por escenario, con repeticiones, y quitando la infraestructura del denominador | D-14, D-15 |

## 7. Lo que aún no está (y es el plan del fin de semana)

Cola de trabajos (F3), asserts deterministas sobre la base de datos y gate de CI (F4b),
latencia por etapa guardada y coste por llamada (F5), scorecard React (F6), comparación con
ElevenLabs y pulido del repo. Ver [plan-mejora.md](plan-mejora.md).

## 8. Comandos

```powershell
uv sync
uv run pytest                                   # 30 tests, ~80 s (Postgres real)
uv run python -m app.db.reiniciar               # agenda limpia relativa a hoy
uv run uvicorn app.main:app --loop app.db.bucle:selector_loop   # API en :8000
uv run agent/bot.py                             # Ana en http://localhost:7860
uv run python evals/lanzar.py run evals -v      # todos los escenarios, una vez
uv run python evals/lanzar.py suite evals/suite.yaml -r 3 -n <nombre-nuevo>
uv run python evals/informe.py <nombre>         # aprobados / suspensos / infra
```

## 9. Glosario mínimo

- **VAD**: detector de voz; decide cuándo el usuario ha terminado su turno.
- **STT / TTS**: voz a texto / texto a voz.
- **TTFB**: tiempo hasta el primer byte de respuesta de un servicio.
- **p50 / p95**: mediana y percentil 95; el p95 es la cola lenta que nota el usuario.
- **Juez LLM**: un LLM que lee la transcripción y dice si se cumplió el criterio.
- **Assert determinista**: comprobación sin LLM (¿existe la cita en la base de datos?).
- **Lease**: un worker "alquila" un trabajo durante X segundos; si muere, el trabajo vuelve a la cola.
