# Cómo se hizo CallBench

Material de estudio para la entrevista de Applied AI Engineer. Cuenta **en qué orden se
construyó, qué falló y cómo se arregló**, y recorre el código importante línea a línea.

- Qué es y cómo funciona hoy: [guia-callbench.md](guia-callbench.md) (no se repite aquí).
- Día a día: [bitacora/BITACORA.md](bitacora/BITACORA.md). Decisiones D-01..D-15:
  [bitacora/DECISIONES.md](bitacora/DECISIONES.md). Plan futuro: [plan-mejora.md](plan-mejora.md).
- Todo lo que se afirma sale del repo (git, bitácora, código). **No hay cifras de latencia
  ni de coste más allá de las que se citan con su origen.** Si te preguntan algo que no
  está medido, la respuesta correcta es "no lo he medido todavía, y así lo mediría".

Estado a 2026-11-20. Los números de línea son de este commit; si el código cambia,
busca por el nombre de la función.

---

## 1. La historia en cuatro frases

1. Se montó primero el **agente** (Ana) y se comprobó con una llamada real. Sin agente no hay nada que evaluar.
2. Se construyó la **API de la clínica**, primero en memoria con tests y luego sobre Postgres con migraciones, dándole al agente algo real que reservar.
3. Se conectó el agente a esa API con **herramientas** y se midió con `pipecat.evals`: escenarios YAML, un paciente simulado y un juez LLM.
4. Al medir salieron fallos de Ana, de las herramientas y **del propio examen**; eso llevó a medir por escenario, repetir y **separar suspensos de fallos de infraestructura**.

El hilo conductor es una frase de la bitácora: *"un total agregado esconde regresiones:
hay que comparar por escenario"* (D-14).

---

## 2. Cronología por fases

Cinco commits de git, pero la bitácora tiene el detalle de cada paso.

| Commit | Fecha | Qué contiene |
|---|---|---|
| `1f075c8` | 2026-11-01 | Commit inicial: agente, API sobre Postgres y primeros evals (todo lo de F0, F1, F2 y el primer F4) |
| `c416f77` | 2026-11-01 | Entrada de bitácora sobre la publicación en GitHub |
| `55a8a28` | 2026-11-01 | Reinicio de agenda, dos escenarios nuevos y primer bucle medir → arreglar → medir |
| `8755210` | 2026-11-02 | Informe que separa suspensos de infraestructura |
| `405b43e` | 2026-11-20 | Plan de mejora y guía del proyecto |

> Ojo: el trabajo de F0-F2 ocurrió el 31 de octubre y el 1 de noviembre, pero el historial
> de git empieza con un único commit inicial. **La cronología real está en la bitácora, no en git.**
> Si te lo preguntan, dilo tal cual.

### Fase 0 · Arranque y primera llamada (2026-10-31)

**Qué se hizo.** Proyecto con `uv` (Python 3.12), dependencias de Pipecat (`deepgram`,
`groq`, `runner`, `silero`, `webrtc`), FastAPI y pytest. Luego `agent/bot.py`: audio WebRTC →
VAD Silero → STT Deepgram → LLM Groq (`gpt-oss-120b`, razonamiento `low`) → TTS Deepgram → audio.
Decisiones: D-01 (WebRTC del navegador, sin teléfono), D-02 (Groq y Deepgram), D-03
(razonamiento bajo para bajar la latencia al primer audio).

**Qué falló en la primera llamada real** (tres fallos, resueltos mirando el log):

| Síntoma | Causa | Arreglo |
|---|---|---|
| El LLM daba error 404 | Groq había **retirado** `llama-3.3-70b-versatile` | Pasar a `gpt-oss-120b` con razonamiento `low` |
| Ana callaba cuando se hablaba en español | El **STT de Deepgram estaba en inglés**: la frase llegaba vacía | Se probó la llamada en inglés (el agente es en inglés) |
| Ana se cortaba sola | Un "Yeah" del usuario contó como **interrupción** | La bitácora lo registra como fallo resuelto, pero no detalla el cambio concreto: no inventes el arreglo |

**Medido** (llamada en inglés, 14:15 del 31 oct): STT 0,32-0,40 s, LLM 0,08-0,82 s, TTS
0,15-0,16 s, unos 0,9 s de voz a voz hasta el primer audio. Smart Turn respetó una pausa a
mitad de frase (`INCOMPLETE` → `COMPLETE`).

**Lección que se apuntó:** con el LLM fallando, la gráfica de latencia marcaba 1,5 s falsos.
*Toda métrica de latencia debe ir acompañada del éxito o fallo de la llamada.* Es una buena
respuesta a "¿cómo mides la latencia?" (ver pregunta 6).

**Honestidad:** la cifra de 0,9 s sale de **una** llamada, no de una distribución. No es un p50.

### Fase 1 · API en memoria (2026-10-31)

FastAPI con `GET /salud`, `GET /huecos`, `POST /citas`, `GET /citas/{id}` y cuatro huecos de
ejemplo en memoria. Seis tests: lista solo libres, 201 y ocupa el hueco, 409 en doble reserva,
404 hueco inexistente, 422 datos inválidos. **Por qué en memoria primero (D-04):** validar el
contrato y los errores 404/409/422 antes de añadir base de datos. Esos códigos son después
exactamente lo que el agente traduce a frases (ver §3.2).

### Fase 2 · Postgres portátil y la reserva atómica (2026-11-01)

- **Postgres con `pgserver`** (D-08): sin Docker ni permisos de administrador en Windows.
  Los datos viven en `.pgdata/`; si existe `DATABASE_URL`, se usa esa.
- **SQLAlchemy 2 async + psycopg 3 + Alembic.** Dos migraciones: esquema (`huecos`, `citas`
  con `UNIQUE (hueco_id)`) y semilla.
- **La doble reserva la impide la base de datos** (D-09), no el código. Ver §3.3.
- Un test de concurrencia: dos reservas simultáneas del mismo hueco dan un 201 y un 409.

**Dos problemas de plataforma, ambos de Windows:**

1. **psycopg async necesita el `SelectorEventLoop`.** Por eso existe `app/db/bucle.py` y el
   comando de arranque lleva `--loop app.db.bucle:selector_loop`.
2. **Postgres huérfano.** pgserver solo apaga Postgres si `.handle_pids.json` contiene
   exactamente su propio PID y nunca poda los PID muertos. Un proceso matado a la fuerza dejaba
   Postgres vivo para siempre. Arreglo: `podar_pids()` en `app/db/config.py`, que quita los PID que
   ya no existen (`psutil.pid_exists`) dentro del mismo `InterProcessLock` que usa pgserver.
   Riesgo aceptado: si Windows reutiliza el PID muerto para otro proceso, no se poda (raro y
   sin daño). Dos tests en `tests/test_pgserver_pids.py`.

### Fase 4 (parte 1) · Herramientas del agente (2026-11-01)

`consultar_huecos` y `reservar_cita`, con `FunctionSchema`/`ToolsSchema`. **Por qué se adelantó
a la cola (D-10):** es lo que hace el puesto (tool calling) y lo más visible; la cola tiene más
sentido con algo real que repartir.

**El fallo que lo motivó:** sin agenda, Ana aceptó una cita con un médico que no existe
("doctor Fernando"). Ese caso es hoy el escenario `medico_inexistente`.

Se hizo el proyecto **instalable** (hatchling, D-11) porque `uv run agent/bot.py` no encontraba
`agent.herramientas`. Se probó con `httpx.MockTransport`, sin red.

### Decisión sobre `pipecat.evals` (2026-11-01)

Inventario de lo que trae (Pipecat 1.15): escenarios YAML guionizados y simulados con persona,
juez LLM (por defecto Ollama `gemma4:12b`), suites con concurrencia 4, resultados en
`results.jsonl`, conexión por websocket RTVI. **No** trae histórico, diff entre versiones,
coste, p50/p95 por etapa, cola distribuida ni CI. Decisión D-07: **construir encima** y aportar
lo que falta. Alternativa descartada: motor propio de llamantes y juez.

### Fase 4 (parte 2) · Primeros exámenes (2026-11-01)

El bot acepta el transporte `eval` (websocket en `/ws`) además de WebRTC. Un escenario
guionizado (`saludo_y_huecos`) y dos simulaciones (`cita_dr_lopez`, `medico_inexistente`).

**Qué falló, y cómo se resolvió:**

| Problema | Causa | Arreglo |
|---|---|---|
| `saludo_y_huecos` suspendía | El guion no daba nombre ni fecha | Se añadieron al guion |
| `cita_dr_lopez` suspendía | Ya no quedaban huecos libres: Ana dijo la verdad y no reservó. Las pruebas anteriores habían ocupado los huecos 1, 2 y 4 | Hace falta reponer la agenda antes de cada suite (`reiniciar`) |
| El paciente simulado escribía **varios turnos de golpe**, incluidos los de Ana | Con `gpt-oss-120b` como persona | Persona con **Qwen sin razonamiento** (D-13) |
| Juez y persona usaban Ollama por defecto | No hay GPU | Un `factory` propio (`evals/servicios_groq.py`) que sirve ambos con Groq (D-13) |

**Los fallos de Ana que salieron** (justo lo que CallBench debe medir): pide el nombre antes de
consultar huecos; sin fecha se inventa una ("jueves 5"); una vez inventó un "Dr. Martinez"; a
veces reserva sin que el paciente lo confirme; el comportamiento varía entre ejecuciones.

### Publicación en GitHub (2026-11-01)

Repo público. Antes de subir: comentarios y docstrings **traducidos al inglés** (D-12; la
bitácora sigue en español), `.gitignore` en inglés, `CLAUDE.md` y `.claude/` fuera, y revisión de
secretos y rutas personales sin hallazgos. 14 tests en verde. Se instaló el extra `cli` de
Pipecat (trae `questionary`), con lo que el lanzador de evals ya no necesita un simulacro.

### Primer bucle medir → arreglar → medir (2026-11-01)

1. **`reiniciar`** (`python -m app.db.reiniciar`): repone la agenda con huecos de los próximos 5
   días laborables, **relativos a hoy** (35 huecos), para que los exámenes sean reproducibles.
2. Dos escenarios nuevos: `lo_antes_posible` y `duda_y_pide_pensarlo`. Un manifiesto
   `evals/suite.yaml` para repetir con `suite -r 3`.
3. **Prompt de Ana reescrito:** consultar antes de pedir el nombre; no filtrar por la fecha de
   hoy si no la dan; solo médicos y horas que devuelva la herramienta; repetir los datos y
   esperar un sí antes de reservar.
4. **Herramientas:** los argumentos opcionales admiten `null`, y "Doctor Lopez" casa con "Dr. Lopez".

Medido (aprobados de 3 por escenario):

| Escenario | Línea base | Solo prompt |
|---|---|---|
| saludo_y_huecos | 2 | 0 |
| cita_dr_lopez | 1 | 3 |
| medico_inexistente | 2 | 3 |
| lo_antes_posible | 3 | 1 |
| duda_y_pide_pensarlo | 2 | 3 |
| **Total** | **10/15** | **10/15** |

**La lectura que hay que saber contar:** el total no se movió (10/15), pero por dentro sí. El
prompt arregló "reserva sin confirmar" y "médico inventado" (1→3 y 2→3), pero **empeoró**
`saludo_y_huecos` (2→0) y `lo_antes_posible` (3→1), y destapó dos fallos de las herramientas
que antes quedaban tapados:

- **`null` en argumentos opcionales.** El modelo mandaba `"medico": null`; el esquema decía
  `string` y **Groq rechazaba la llamada entera**. Arreglo: `"type": ["string", "null"]`.
- **"Doctor Lopez" ≠ "Dr. Lopez".** El filtro comparaba texto crudo y no encontraba al médico.
  Arreglo: `_normalizar_medico`.

### La cuota de Groq (429) y la vuelta perdida

Al ir a medir la versión con las herramientas arregladas, **se agotó la cuota diaria de Groq**
(200.000 tokens/día para `gpt-oss-120b`, error 429) y **14 de 15 ejecuciones fallaron por eso**,
no por Ana. Cada suite completa gasta 40-50k tokens. Se hicieron unas 90 llamadas simuladas ese
día. Aprendizaje: hay que renovar la cuota, repetir, y sobre todo **no contar esos fallos como
suspensos de Ana**.

### Versión final: 13/15, y los 2 fallos no son de Ana (2026-11-02)

`suite -r 3 -n final-lunes` con API levantada y agenda reiniciada:

| Escenario | Línea base | Solo prompt | Prompt + herramientas |
|---|---|---|---|
| saludo_y_huecos | 2 | 0 | 3 |
| cita_dr_lopez | 1 | 3 | 2 |
| medico_inexistente | 2 | 3 | 3 |
| lo_antes_posible | 3 | 1 | 2 |
| duda_y_pide_pensarlo | 2 | 3 | 3 |
| **Total** | **10/15** | **10/15** | **13/15** |

Los 2 suspensos son `harness_error`: Groq rechazó una llamada a herramienta mal formada
(`target_text`, inexistente, y `Failed to call a function`). La sospecha es la persona
simulada (Qwen), que es quien cuelga con `end_call`; **no está confirmado**. Ana aprueba 13 de
los 13 intentos que terminaron bien.

Antes de esa vuelta se perdieron **tres** por causas ajenas a Ana:

1. **API sin levantar** → `agenda_no_disponible` en el log.
2. **Cuota diaria agotada** → `judge call failed`.
3. **PC suspendido durante la noche** → `ProcessLookupError` e intentos de casi 14 horas.

Además: reutilizar el nombre con `-n` **acumula** las vueltas en el mismo `results.jsonl`
(cada vuelta necesita nombre nuevo), y cada suite reserva unos 7 huecos (hay que reiniciar la
agenda antes de cada vuelta).

### El informe que separa suspensos de infraestructura (2026-11-02)

Respuesta directa a esas tres vueltas perdidas. `evals/informe.py` clasifica cada intento como
**aprobado, suspenso o infra**; la tasa se calcula sobre intentos válidos; el código de salida es
0/1/2. Ver §3.4. Resultado sobre `final-lunes`: 13 aprobados, 0 suspensos, 2 infra, salida 2.
30 tests en verde.

### Hallazgos del 2026-11-20 (revisión antes del plan de mejora)

- La agenda estaba **caducada** (huecos del 4 de noviembre) hasta ejecutar `reiniciar`: la semilla
  es relativa a hoy, no se actualiza sola.
- En `cita_dr_lopez`, Ana **reservó sin repetir los datos ni esperar un sí** y el juez aprobó con
  P(yes)=0,98. **Un juez LLM solo no basta: hacen falta asserts deterministas.** Es el hallazgo
  más defendible de todo el proyecto (ver pregunta 8).
- Los evals van en modalidad texto: **no miden STT ni TTS**.
- Las métricas de Pipecat (TTFB, tokens) solo llegan al log, no se guardan.
- El README prometía la alternativa local y el dashboard; no existen todavía.

### Qué falta (para no vender humo)

Cola de trabajos (F3), asserts deterministas y gate de CI (F4b), latencia por etapa y coste
(F5), scorecard React (F6). Ver [plan-mejora.md](plan-mejora.md). **Si en la entrevista dices
"CallBench compara versiones y bloquea el CI", hoy es el objetivo, no un hecho.** Lo que hay: un
banco de evals con repeticiones y un informe que ya devuelve el código de salida pensado para el CI.

---

## 3. Recorrido comentado del código

Se explica por bloques. Entre paréntesis, las líneas.

### 3.1 `agent/bot.py` (122 líneas)

**Imports y entorno (1-35).** El docstring dice que es la Fase 0. `load_dotenv(override=True)`
carga las claves de `.env`. Importa `EvalTransportParams` de `pipecat.evals.transport`: así el
mismo bot puede hablar con los exámenes.

**`construir_prompt` (37-58).** El prompt se construye **al arrancar** porque lleva la fecha de
hoy (`hoy = date.today().strftime(...)`, línea 39), para que "mañana" o "el lunes" signifiquen
algo. Cada frase del prompt es la cicatriz de un fallo medido:

| Frase del prompt | Fallo que corrige |
|---|---|
| "call consultar_huecos **before** asking for their name" (44) | Pedía el nombre antes de consultar |
| "never use today's date as a filter" (45-46) | Sin fecha, se inventaba una o filtraba por hoy |
| "Only name doctors, days and times returned by consultar_huecos" (47) | Inventaba "Dr. Martinez" o "doctor Fernando" |
| "Before calling reservar_cita, say [it] back and wait for an explicit yes" (51-52) | Reservaba sin confirmación |
| "Never confirm an appointment unless reservar_cita returned ok" (53) | Confirmaba sin haber reservado |
| "answer in one or two short sentences, no lists, no emojis" (56-57) | Es voz: el texto se convierte en audio |

Es la respuesta ideal a "¿cómo iteras un prompt?": **no se escribe a ojo, cada regla responde
a un fallo observado en un eval.**

**`run_bot` (61-104).**

- *62-71, servicios.* STT Deepgram, LLM Groq y TTS Deepgram con voz `aura-2-thalia-en`. En el
  LLM, `reasoning_effort="low"` (D-03): un modelo de razonamiento piensa antes de hablar y eso
  es latencia; "low" la recorta.
- *74-75, herramientas y contexto.* `registrar_herramientas(llm)` registra los handlers y devuelve
  el esquema; el `LLMContext` recibe el mensaje de sistema y las herramientas.
- *76-79, agregadores.* `LLMContextAggregatorPair` con `SileroVADAnalyzer`: el VAD decide cuándo
  empieza y acaba el turno del usuario, y el agregador de usuario junta lo transcrito en el contexto.
- *81-89, la tubería, en orden.* `transport.input()` → `stt` → `aggregators.user()` → `llm` →
  `tts` → `transport.output()` → `aggregators.assistant()`. El agregador de asistente va **al
  final** (tras la salida) para guardar en el contexto lo que Ana ha dicho de verdad.
- *91, métricas.* `enable_metrics=True` hace que cada servicio emita TTFB y uso de tokens. Hoy
  solo van al log.
- *93-97, `on_client_connected`.* Mete "Greet the caller." como mensaje de usuario y encola un
  `LLMRunFrame` para que Ana hable primero. Es el motivo de que `saludo_y_huecos` tenga un primer
  turno **sin** `user:` (espera el saludo).
- *99-102, `on_client_disconnected`.* `task.cancel()` para no dejar la tubería viva.
- *104.* `handle_sigint=False`: el runner de Pipecat gestiona la señal.

**`bot` (107-116).** `create_transport` con **dos** transportes: `webrtc` (el navegador) y `eval`
(websocket `/ws` con RTVI). **Esta es la razón por la que el mismo agente sirve para las
llamadas reales y para los exámenes**: se evalúa el código que se despliega, no una copia.

### 3.2 `agent/herramientas.py` (177 líneas)

Principio del módulo (docstring): la lógica HTTP vive en funciones normales que reciben el
cliente `httpx` y devuelven un `dict`; los handlers de Pipecat solo las llaman. **Nada lanza
excepciones al pipeline.** Por eso se pudo testear con `MockTransport`.

- *17-18, constantes.* `TIMEOUT_SEGUNDOS = 5.0` y `MAX_HUECOS = 6`: pocos huecos porque el LLM los
  va a **leer en voz alta**.
- *20-37, `ESQUEMA_CONSULTAR`.* Los argumentos son `["string", "null"]` y `required=[]`. El
  comentario del código explica por qué: el modelo manda `null` a menudo y Groq rechaza la llamada
  si el esquema dice solo `string`. La descripción de `fecha` ("only when the caller names a
  specific day") es **prompt dentro del esquema**: también guía al modelo.
- *39-52, `ESQUEMA_RESERVAR`.* `hueco_id` entero y `paciente` obligatorios; `motivo` opcional. La
  descripción repite "only call it after the caller explicitly agreed": refuerzo del prompt.
- *54-58, `AGENDA_NO_DISPONIBLE`.* Un único resultado de error con un `mensaje` en inglés que le
  dice al LLM qué hacer ("apologise and offer to try again"). **Además es la marca que el informe
  busca en el log** para detectar la API caída (`MARCA_AGENDA` en `evals/informe.py`).
- *61-66, `url_base` y `_cliente`.* La URL sale de `CLINICA_API_URL`. Se crea un cliente por
  llamada: simple y sin estado compartido.
- *69-73, `_dia_legible`.* Convierte `2026-11-03T09:00:00Z` en "Tuesday November 03 at 09:00",
  pensado para que Ana lo diga en voz alta.
- *76-79, `_normalizar_medico`.* Minúsculas y `doctor ` → `dr. `. Arregla "Doctor Lopez".
- *82-114, `buscar_huecos`.*
  1. Pide **todos** los libres a la API y **filtra en el cliente** por médico y fecha.
  2. Cualquier error HTTP o de JSON devuelve `AGENDA_NO_DISPONIBLE` (con un `logger.warning`).
  3. El filtro de médico es "contiene" (`buscado in ...`), el de fecha es "empieza por" sobre el
     ISO (`startswith`).
  4. Ordena por `inicio` y corta a 6.
  5. Sin resultados devuelve `ok: True` con lista vacía y un mensaje: **no es un error**, es un
     resultado que Ana debe comunicar. Distinguirlo del error es lo que permite que "no hay
     Dr. Fernando" no se confunda con "la agenda está caída".
  - *Trade-off a conocer:* filtrar en el cliente es sencillo pero trae todos los huecos; con una
    agenda grande habría que filtrar en la API.
- *117-146, `crear_cita`.* Traduce estados HTTP a frases: 201 → `ok` con la cita; 404 →
  `hueco_no_existe`; 409 → `hueco_ocupado` ("offer another slot"); 422 → `datos_invalidos` ("ask
  for their full name again"); cualquier otra cosa → `AGENDA_NO_DISPONIBLE`. Es el puente entre
  el contrato de la API (§3.3) y la conversación.
- *149-170, handlers.* Cada uno abre el cliente, llama a la lógica y entrega el resultado con
  `params.result_callback`. El `except Exception` genérico (con `logger.exception`) es
  deliberado: **una herramienta rota no debe tumbar una llamada en curso.**
- *173-177, `registrar_herramientas`.* `llm.register_function(...)` por herramienta y devuelve el
  `ToolsSchema`.

### 3.3 `app/main.py`: la reserva atómica (74-103)

El problema: dos llamadas simultáneas intentan reservar el **mismo hueco**. Con "leer y luego
escribir" en Python, las dos leerían `libre = true` y las dos reservarían (condición de
carrera). La solución es que **la comprobación y la escritura sean una sola sentencia**:

```python
ocupado = await sesion.execute(
    update(HuecoDB)
    .where(HuecoDB.id == datos.hueco_id, HuecoDB.libre)
    .values(libre=False)
    .returning(HuecoDB.inicio, HuecoDB.medico)
)
hueco = ocupado.one_or_none()
```

Es `UPDATE huecos SET libre = false WHERE id = :id AND libre RETURNING inicio, medico`.

- *78-83.* La sentencia. `WHERE ... AND libre` es la comprobación; `RETURNING` devuelve la hora y
  el médico en el mismo viaje, sin una segunda consulta.
- *84.* `one_or_none()`: una fila si se ocupó, `None` si no se actualizó nada.
- *85-91, `None`.* Hay dos causas y hay que distinguirlas. Se consulta si el hueco existe: si no,
  **404**; si existe, ya estaba ocupado y es **409 Conflict** ("la petición es válida pero choca
  con el estado actual").
- *93-96, el INSERT.* Se inserta la cita y se hace `commit` (que cierra la transacción).
- *98-100, `IntegrityError`.* Red de seguridad: `UNIQUE (citas.hueco_id)` impide dos citas en un
  hueco incluso si el `UPDATE` se saltara. Se hace `rollback` y se devuelve 409.
- *101.* Se construye la respuesta con la hora y el médico que devolvió el `RETURNING`.

**Por qué funciona con concurrencia (lo que te preguntarán).** En Postgres, un `UPDATE` bloquea
la fila hasta que termina la transacción. Con dos peticiones: la primera actualiza y mantiene el
bloqueo; la segunda **espera** en su `UPDATE`; cuando la primera hace `commit`, la segunda
reevalúa `WHERE ... AND libre`, ve `libre = false` y actualiza **cero filas** → 409. (Esto
describe el comportamiento estándar de Postgres en `READ COMMITTED`, el nivel por defecto.)
Si el `INSERT` fallara, el `rollback` deshace también el `UPDATE`: el hueco no queda "ocupado sin
cita". La prueba es `test_reservas_simultaneas_del_mismo_hueco` (un 201 y un 409).

**Otras piezas del fichero.**

- *`CitaIn` (38-43):* Pydantic valida (`paciente` de 2 a 80 caracteres, `motivo` hasta 200); lo
  inválido es un **422** automático. No hay validación manual.
- *`listar_huecos` (61-70):* `solo_libres` por defecto. Es lo que consume `buscar_huecos`.
- *`leer_cita` (106-):* hace `JOIN` porque la cita no guarda hora ni médico, los da el hueco.
- *`Depends(get_session)`:* inyecta la sesión; en los tests se sustituye por una apuntando a una
  base `callbench_test` aparte (`tests/conftest.py`), con el esquema creado **por las
  migraciones**, así que se prueban también.

**El esquema** (`migrations/versions/0001_esquema_inicial.py`): `huecos(id, inicio timestamptz,
medico, libre)` y `citas(id, hueco_id UNIQUE → huecos, paciente, motivo, creada_en)`. El
`UNIQUE` en la migración, no solo en el modelo, es la garantía final. Las fechas llevan zona.

### 3.4 `evals/informe.py` (157 líneas)

Problema que resuelve: perder una vuelta por la cuota de Groq y contarla como "Ana suspende".
Un **suspenso** significa "Ana lo hizo mal"; **infra** significa "el examen no pudo medir".

- *12-14.* `MARCA_AGENDA = '"error": "agenda_no_disponible"'`: la cadena que busca en el log. Es la
  misma que genera `AGENDA_NO_DISPONIBLE` en las herramientas: **las dos piezas están acopladas
  por esa cadena.**
- *17-30, `causa_infra`.* Mira el `error` y las razones de `failures` de una fila de
  `results.jsonl`. Por orden: `judge call failed` → "juez sin respuesta (cuota Groq)"; error que
  empieza por `Error during completion` → "Groq rechaza la llamada a herramienta"; `ProcessLookupError`
  → "proceso del bot muerto"; cualquier otro `error` → infra con el texto truncado a 80;
  `ended_by == "error"` → infra. **Cualquier error desconocido cuenta como infra, no como suspenso**:
  es conservador, pero puede esconder un fallo real (ver pregunta 18).
- *33-34, `api_caida`.* Busca la marca en el texto del log.
- *37-41, `_motivo_suspenso`.* La razón del primer fallo, truncada.
- *44-52, `clasificar`.* El corazón: `passed` → aprobado; si no, ¿hay causa de infra? → infra; si
  no, ¿el log del intento muestra la API caída? → infra; si no, **suspenso**.
- *55-65, `agregar`.* Cuenta por escenario y total. `validos = aprobado + suspenso` y
  `tasa = aprobado / validos` (o `None` si no hay válidos): **la infraestructura sale del
  denominador** (D-15).
- *73-83, `_leer_log`.* Localiza el log del intento (normaliza barras de Windows).
- *91-105, `analizar`.* Clasifica sin log; **solo si salió suspenso** lee el log para ver si en
  realidad fue la API caída. Es una optimización: no leer logs de intentos aprobados.
- *108-111, `codigo_salida`.* 1 si hay suspensos; 2 si no hay suspensos pero sí infra (**vuelta no
  concluyente**); 0 si todo aprobó. Está pensado para que un CI distinga "empeoró" de "no he
  podido medir".
- *114-117, `intentos_repetidos`.* Detecta pares (escenario, intento) duplicados: el síntoma de
  reutilizar el nombre de la vuelta.
- *120-144, `formatear`.* Tabla por escenario, tasa, lista de fallos, aviso de no concluyente y
  aviso de intentos repetidos. Termina con `.encode("ascii", "replace")`: salida solo ASCII para no
  romper la consola de Windows (por eso no hay acentos en las cadenas del informe).

**Limitación conocida y documentada:** la caída de la API solo se ve en el log del intento, y
reutilizar el nombre los sobrescribe; en `final`, tres intentos salen como suspenso porque su log
ya es de una vuelta posterior (de ahí el aviso). Y la cuota agotada y la API caída se detectan
**después** de gastar la vuelta: falta comprobarlas **antes** de lanzar. Hay 13 tests en
`tests/test_informe.py`.

---

## 4. Cómo se escribe un escenario nuevo

Un escenario es un YAML en `evals/`. Hay dos tipos.

### Guionizado (frases fijas)

Ejemplo real: `evals/saludo_y_huecos.yaml`. Cada turno puede llevar `user:` (lo que dice el
paciente) y `expect:` (eventos esperados). `event: function_call` comprueba que Ana llamó a una
herramienta; `event: response` pasa el texto de Ana por el juez con una frase `eval:`. Sin `user:`,
espera el saludo inicial. Sirve para comprobar algo concreto y repetible.

### Simulado (un LLM hace de paciente)

Ejemplo real: `evals/duda_y_pide_pensarlo.yaml`. Campos:

| Campo | Para qué |
|---|---|
| `judge: !include juez_groq.yaml` | Qué LLM juzga (Groq vía `factory`) |
| `simulator: !include persona_groq.yaml` | Qué LLM hace de paciente (Qwen) |
| `persona` | Cómo es y cómo habla. Pon "one short sentence at a time" |
| `goal` | Qué intenta conseguir el paciente |
| `success` | Lo que el juez comprueba **sobre Ana** (no sobre el paciente) |
| `metrics` | Comprobación determinista (`measure: function_calls`) |
| `max_turns` | Tope de turnos |

**Receta, paso a paso:**

1. Decide **un solo comportamiento** a vigilar (p. ej. "no reservar con un nombre incompleto").
2. Copia un YAML de simulación y cambia `name`, `persona`, `goal` y `success`.
3. Escribe `success` en términos observables ("el bot nunca llamó a `reservar_cita`"), no
   sensaciones ("el bot fue amable").
4. Si puedes, añade una métrica determinista con `function_calls`: no depende del juez.
5. Añádelo a la lista `scenarios:` de `evals/suite.yaml`.
6. Reinicia la agenda y ejecútalo solo: `uv run python evals/lanzar.py run evals/<tu_escenario>.yaml -v`.
7. **Pruébalo contra una versión rota de Ana** (ver ejercicio 2): un escenario que no puede
   fallar no vigila nada.
8. Mídelo con `suite -r 3` y un nombre de vuelta nuevo; léelo con `informe.py`.

**Reglas aprendidas aquí:** la persona debe poder cumplir su objetivo (si pide un médico sin
huecos, el escenario suspende por la agenda, no por Ana); las simulaciones **reservan de
verdad**, así que `reiniciar` antes; y concurrencia 1 en la suite porque con más Groq limitó el
ritmo y el juez falló.

---

## 5. Ejercicios prácticos (15 minutos cada uno)

Todos desde la raíz del proyecto. Claves en `.env`. El orden importa: el 1 deja la base lista.

**Ejercicio 1 · Ver que todo funciona (15 min).**
`uv run python -m app.db.reiniciar`, luego en dos terminales la API
(`uv run uvicorn app.main:app --loop app.db.bucle:selector_loop`) y el bot (`uv run agent/bot.py`),
y en una tercera `uv run python evals/lanzar.py run evals/saludo_y_huecos.yaml -v`.
*Objetivo:* ver el saludo, la llamada a `consultar_huecos` y el veredicto del juez.
*Pregunta para ti:* ¿qué terminal ve cada pieza del diagrama de la guía?

**Ejercicio 2 · Romper el prompt y ver cómo lo detecta el eval (15 min).**
En `agent/bot.py` borra la frase "Before calling reservar_cita, say the doctor, day, time and
name back to the caller and wait for an explicit yes; if they hesitate or ask to think, do not
book." Reinicia agenda, reinicia el bot y ejecuta
`uv run python evals/lanzar.py run evals/duda_y_pide_pensarlo.yaml -v`.
*Qué esperar:* el escenario debería suspender si Ana reserva con un paciente que duda; el
escenario `cita_dr_lopez` puede seguir aprobando. **Lo importante:** anota si el juez lo detecta y
con qué P(yes). Repítelo 3 veces: ¿siempre falla? Eso es la varianza de la que habla D-14.
Después **restaura el fichero** (`git checkout agent/bot.py`).

**Ejercicio 3 · Añadir un escenario (15 min).**
Crea `evals/nombre_incompleto.yaml`: un paciente que solo da su nombre de pila ("Ana") y Ana debe
pedir el nombre completo. Copia `duda_y_pide_pensarlo.yaml`. Pon un `success` observable y una
métrica `function_calls`. Añádelo a `suite.yaml` y pruébalo suelto. *Pregunta:* ¿qué pasa si Ana
llama a `reservar_cita` con "Ana"? (mira la validación `min_length=2` de `CitaIn`: ¿es suficiente?
Es un buen hueco para discutir).

**Ejercicio 4 · Provocar un fallo de infraestructura (15 min).**
Ejecuta una vuelta con la API **apagada**:
`uv run python evals/lanzar.py suite evals/suite.yaml -r 1 -n prueba-sin-api` (cuesta tokens de
Groq; si te preocupa, usa solo un escenario) y luego
`uv run python evals/informe.py prueba-sin-api`. *Qué esperar:* los intentos deberían salir como
`infra` (API caída) y el código de salida ser 2, no 1. *Comprueba:* `echo $LASTEXITCODE`.

**Ejercicio 5 · Reserva concurrente a mano (15 min).**
Lee `test_reservas_simultaneas_del_mismo_hueco` en `tests/test_api.py` y ejecútalo:
`uv run pytest tests/test_api.py -k simultaneas -v`. Luego cambia temporalmente `update(...)` por
"seleccionar y después escribir" en dos pasos y mira si el test aún lo detecta. Restaura con git.
*Objetivo:* poder explicar por qué la solución de una sola sentencia es la correcta.

**Ejercicio 6 · Leer un `results.jsonl` (15 min).**
Abre `evals/runs/<alguna vuelta>/results.jsonl` (si no tienes ninguna, ejecuta el ejercicio 1 con
`suite -r 1`). Localiza los campos `passed`, `failures`, `error`, `ended_by` y `artifacts.log`.
Predice a mano qué diría `clasificar` y compruébalo con `informe.py`.

**Ejercicio 7 · Explicarlo en voz alta (15 min).**
Cronometra 3 minutos contando el proyecto sin mirar: idea (§1), el bucle 10/15 → 13/15, la
distinción suspenso/infra y una limitación honesta (modalidad texto). Grábate y revisa si has
dicho alguna cifra que no esté en este documento.

---

## 6. Veinte preguntas probables de entrevista

Respuestas cortas y apoyadas en el repo. Donde algo no está hecho, se dice.

**1. ¿Qué es CallBench y qué problema resuelve?**
Un banco de regresión para agentes de voz: llama al agente con pacientes simulados, puntúa cada
llamada y compara versiones. El problema: cambiar un prompt o un modelo y no saber si mejoró o
empeoró. Hoy tiene los escenarios, las repeticiones y el informe; la cola, el gate de CI, la
latencia guardada y el dashboard son el plan.

**2. ¿Por qué evaluar un agente de voz es distinto de testear código?**
Porque la salida no es determinista: Ana no responde igual dos veces. Un test de una ejecución no
dice nada. Hay que repetir, medir tasas y comparar por escenario. En el proyecto, el mismo total
(10/15) escondía dos mejoras y dos empeoramientos.

**3. ¿Por qué mides por escenario y no un total?**
Porque el total se compensa. Con solo el prompt, el total seguía en 10/15, pero `cita_dr_lopez`
pasó de 1 a 3 y `saludo_y_huecos` de 2 a 0. El total decía "nada cambió"; el desglose decía
"arreglé una cosa y rompí otra". Es la lección de D-14. (Con 3 repeticiones es orientativo, no
estadísticamente concluyente.)

**4. ¿Es 13/15 una mejora real?**
Es una señal, no una prueba. N=15, 3 repeticiones por escenario. Los 2 fallos restantes eran
errores del lado del examen (Groq rechazando una llamada), y Ana aprobó los 13 intentos que
terminaron bien. Para afirmar una mejora haría falta más repeticiones y comparar versiones sobre
las mismas condiciones.

**5. ¿Qué mide cada pieza: asserts o juez LLM?**
Hoy: el juez LLM evalúa `success:` y las frases `eval:`, y hay una métrica determinista
(`function_calls`) en `cita_dr_lopez`. Lo que falta: asserts sobre la base de datos (¿existe la
cita?). El caso que lo justifica: Ana reservó sin esperar un sí y el juez aprobó con P(yes)=0,98.

**6. ¿Cómo mides la latencia de voz?**
Lo medido es una llamada real (F0): STT 0,32-0,40 s, LLM 0,08-0,82 s, TTS 0,15-0,16 s, unos 0,9 s
de voz a voz. Pipecat emite TTFB por servicio con `enable_metrics=True`, pero hoy solo van al log.
El plan es guardarlas y sacar p50/p95 por etapa. Y la lección: no reportar latencia sin el éxito
de la llamada (con el LLM fallando se vio 1,5 s falsos).

**7. ¿Por qué p95 y no la media?**
Porque el usuario nota la cola lenta: una media buena puede esconder un 5 % de llamadas con
silencios largos. Dicho esto, **hoy no tengo un p95 medido**; tengo una llamada.

**8. ¿Juez LLM o asserts deterministas?**
Ambos, con roles distintos. El juez sirve para lo cualitativo ("no inventó médicos") pero puede
equivocarse: aprobó una reserva sin confirmación. Los asserts (¿se llamó a `reservar_cita` sin
un sí previo? ¿existe la cita en la base?) son baratos, repetibles y no dependen de un modelo. Lo
barato y objetivo, determinista; lo demás, juez.

**9. ¿Qué limitaciones tiene tu juez?**
Es el mismo proveedor y la misma familia de modelo que el agente (`gpt-oss-120b` en Groq), así
que puede compartir sesgos; devuelve una probabilidad (P(yes)) que depende del prompt de
`success`; y si su llamada falla, no hay veredicto (eso es `infra`, no suspenso). Un ejercicio
posible: contrastar con otro modelo juez.

**10. ¿Por qué un LLM distinto para el paciente simulado?**
Con `gpt-oss-120b` como persona, el simulador escribía varios turnos de golpe, incluidos los del
bot. Con Qwen sin razonamiento se comportó (D-13). Detalle: el fallo de las herramientas mal
formadas de los 2 suspensos finales suele atribuirse a esa persona, **pero no está confirmado**.

**11. ¿Qué diferencia hay entre un suspenso y un fallo de infraestructura?**
Suspenso: Ana lo hizo mal. Infra: el examen no pudo medir (cuota 429, juez caído, API caída,
proceso muerto). Mezclarlos falsea la nota y bloquearía el CI sin motivo. `informe.py` los separa,
calcula la tasa sobre intentos válidos y devuelve 2 si no hay suspensos pero sí infra (D-15).

**12. ¿Qué ha fallado en el proyecto que no era culpa del agente?**
Tres vueltas perdidas: API sin levantar, cuota diaria de Groq agotada (200.000 tokens/día para
`gpt-oss-120b`, error 429) y el PC suspendido en la noche (`ProcessLookupError`, intentos de casi
14 horas). También agenda caducada.

**13. ¿Cómo evitas la doble reserva?**
La garantía está en la base de datos, no en el código: `UPDATE huecos SET libre=false WHERE id=:id
AND libre RETURNING ...` en una sola sentencia y `UNIQUE(citas.hueco_id)` como red de seguridad. Con
dos peticiones, Postgres bloquea la fila; la segunda reevalúa `libre`, ve `false` y no actualiza
nada → 409. Hay un test de concurrencia.

**14. ¿Por qué una cola en Postgres con `FOR UPDATE SKIP LOCKED` y no Redis/Celery?** *(F3: aún no
implementado)*
Una sola pieza de infraestructura (D-05) y aprender a mano leases y reintentos. `SKIP LOCKED` hace
que cada worker tome el primer trabajo **no bloqueado** por otro, así que varios workers reparten
trabajo sin pisarse ni esperar. Con un lease, si un worker muere, el trabajo vuelve a la cola. Hay
que decir claramente que **no está construida**; es la siguiente fase.

**15. ¿Qué pasa si un worker muere a mitad de un trabajo (con esa cola)?**
Se alquila el trabajo con un plazo (lease). Si no se renueva ni se completa, otro worker puede
tomarlo. El riesgo es duplicar trabajo, y por eso el trabajo debe ser idempotente o llevar un
número de intento. (Diseño; aún sin código.)

**16. ¿Qué no mide tu eval de voz?**
Los evals van en modalidad texto: **no pasan por STT ni TTS**. Prueban el cerebro de Ana (prompt +
LLM + herramientas), no cómo suena ni cómo transcribe. Es una limitación que conozco y que el
plan aborda comparando Deepgram con ElevenLabs. No tengo aún medida de interrupciones ni de
turnos.

**17. ¿Cómo se interrumpe a un agente de voz y cómo lo cubres?**
Pipecat usa VAD (Silero) para detectar cuándo habla el usuario y cancelar la salida. En la primera
llamada, un "Yeah" contó como interrupción y cortó a Ana. En evals de texto **no se ejercita**.
Un escenario de interrupción real exigiría modalidad audio.

**18. ¿Qué riesgo tiene tratar todo error desconocido como infra?**
Que un fallo real de Ana se esconda como "no concluyente". Mitigación actual: la vuelta no pasa
con 2, sino que se declara no concluyente y se ve en la lista de fallos con su causa. Mejora
posible: lista cerrada de causas de infra y avisar de las desconocidas aparte.

**19. ¿Por qué construir encima de `pipecat.evals` y no un motor propio?**
Ya trae escenarios YAML, personas simuladas, juez y suites; no trae histórico, diff entre
versiones, coste, p50/p95 por etapa, cola con reintentos ni CI. Hacer un motor propio sería
reconstruir lo que ya existe (D-07). El valor propio está en lo que se le añade.

**20. ¿Qué harías distinto / qué sigue?**
Primero, asserts deterministas contra la base de datos y un gate de CI, porque el juez ya se
equivocó. Segundo, guardar métricas por etapa para hablar de p50/p95 con datos. Tercero,
comparar proveedores de voz (Deepgram frente a ElevenLabs) en audio, no en texto. Cuarto, subir
las repeticiones antes de afirmar mejoras.

---

## 7. Cosas que NO debes decir

- "Bloquea el CI": hoy no hay CI; el informe solo **devuelve** un código de salida.
- "p50 / p95 de latencia": solo hay una llamada medida (~0,9 s de voz a voz).
- "Cola de trabajos": es F3, sin implementar.
- "Funciona con ElevenLabs": está en el plan, no en el código.
- "13/15 demuestra que Ana es mejor": es orientativo con N=15.
- "Cubre voz": los evals son en texto.

## 8. Mapa para repasar

| Si te preguntan por... | Repasa |
|---|---|
| Orden de construcción y fallos | §2 |
| Cómo es el código | §3 |
| Evals y escenarios | §4 y `evals/README.md` |
| Concurrencia | §3.3 y ejercicio 5 |
| Medición honesta | preguntas 3, 4, 6, 7, 11 |
| Lo que falta | §2 «Qué falta» y [plan-mejora.md](plan-mejora.md) |
