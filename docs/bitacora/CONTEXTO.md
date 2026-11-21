# CallBench · Contexto del proyecto

> Documento vivo. Se lee primero al retomar el proyecto (tú o Claude).
> Lo que cambia cada día va en [BITACORA.md](BITACORA.md); el plan y las fechas, en
> [plan.toml](plan.toml); la foto del avance, en [GANTT.md](GANTT.md).

## Objetivo

Construir un **banco de regresión para agentes de voz** hechos con Pipecat.
"Un agente de voz sin evals es una demo."

El agente bajo prueba es Ana, la recepcionista de una clínica ficticia que reserva
y cambia citas. CallBench la llama con **llamantes sintéticos** (el que interrumpe,
el que se queda callado, el que da mal la fecha de nacimiento), **puntúa cada
llamada** y **compara cada versión nueva del agente con la anterior** en:

- tasa de éxito (¿reservó lo que tocaba?),
- latencia p50 / p95 (por etapa: STT, LLM, TTS),
- coste por llamada.

Proyecto personal, construido en público mientras aprendo el stack de punta a punta.

## Criterio de "terminado"

1. Una versión nueva del agente se lanza contra N llamadas sintéticas con un comando.
2. Cada llamada queda puntuada (asserts deterministas + juez LLM) y guardada en Postgres.
3. CI bloquea una versión que empeora respecto a la anterior.
4. Un scorecard en React enseña el diff entre dos versiones.

## Alcance

**Dentro:** agente de voz en navegador (WebRTC), API de la clínica, cola de trabajos
en Postgres, llamantes sintéticos, evaluación, métricas de latencia y coste, dashboard.

**Fuera (por ahora):** telefonía real (SIP/PSTN), multiidioma, autenticación,
despliegue en la nube.

## Arquitectura

```
navegador (mic) ──WebRTC──> agent/bot.py  (Pipecat: VAD Silero → STT Deepgram → LLM Groq → TTS Deepgram)
                                   │ tool calls (F4)
                                   ▼
                            app/main.py   (FastAPI: /huecos, /citas)  ──> PostgreSQL (F2)
                                                                            ▲
llamantes sintéticos (F4) ──> cola de trabajos en Postgres (F3) ────────────┘
                                   │
                                   ▼
                     evaluación (F4b) → métricas (F5) → scorecard React (F6)
```

| Pieza | Tecnología |
|---|---|
| Agente de voz | Pipecat 1.15, transporte SmallWebRTC |
| Modelos | Groq `openai/gpt-oss-120b` (LLM), Deepgram (STT y TTS `aura-2-thalia-en`) |
| Alternativa local | Whisper, Ollama, Piper (F5) |
| API de la clínica | FastAPI + Pydantic, SQLAlchemy 2 async + psycopg 3 |
| Datos y cola | PostgreSQL portátil (`pgserver`) con migraciones Alembic; cola con `FOR UPDATE SKIP LOCKED` (F3) |
| Llamantes y juez | `pipecat.evals` (escenarios YAML, personas simuladas, juez LLM) |
| Dashboard | React + TypeScript |
| Entorno | Python 3.12, uv, pytest |

## Dónde estoy

<!-- Actualizar al cerrar cada sesión de trabajo (2-4 líneas). -->

- **Fase actual:** fin de semana 21-22 nov ([docs/plan-mejora.md](../plan-mejora.md)). En `main`: cola (F3), asserts (F4b), métricas (F5), guarda de confirmación en `reservar_cita` (comprueba el sí del paciente en la conversación) y F6: gate `tools/comparar.py`, API `/vueltas` `/diff` y scorecard en `dashboard/` (captura en `docs/img/scorecard.png`).
- **Hecho:** línea base con asserts: 14/18 (78 %), 4 fallos de confirmación que el juez aprobó. `v1-base` por la cola: 3/6 válidas (la mitad perdida por la cuota de Groq). El juez aprueba llamadas que los asserts suspenden (8 de 12 en `base-c1`).
- **Siguiente paso:** medir `v1-base-b` y `v2-confirmacion` cuando Groq libere cuota y compararlas con `tools/comparar.py` (salen ya con métricas por llamada para el scorecard); ElevenLabs (Fase D); lanzar el job `evals` en GitHub con los secretos.
- **Bloqueos:** cuota diaria de Groq (200k tokens en ventana móvil de 24 h). Repo público: https://github.com/gabrielespelleta94/callbench

## Convenciones

- Código y comentarios en inglés (repo público, D-12); bitácora en español.
- Claves en `.env` (nunca al repo). Plantilla en `.env.example`.
- Cada cambio relevante deja una entrada en la bitácora (ver cómo en [README.md](README.md)).
