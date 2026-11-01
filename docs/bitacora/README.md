# Bitácora de CallBench

| Fichero | Para qué | Quién lo toca |
|---|---|---|
| [CONTEXTO.md](CONTEXTO.md) | Objetivo, alcance, arquitectura y **dónde estoy** | A mano, al cerrar cada sesión |
| [plan.toml](plan.toml) | Fases, estado y fechas planificadas | A mano, al cambiar de fase o replanificar |
| [BITACORA.md](BITACORA.md) | Diario de cambios (qué, por qué, ficheros, siguiente) | A mano, tras cada cambio relevante |
| [DECISIONES.md](DECISIONES.md) | Decisiones de diseño con su porqué | A mano, al decidir algo que no es obvio |
| [GANTT.md](GANTT.md) / [GANTT.html](GANTT.html) | Gantt plan vs real, avance y últimas entradas | **Generado**, no editar |

## Rutina tras cada cambio

1. Añadir una entrada arriba del todo en `BITACORA.md`:
   ```
   ## 2026-11-02 · F2 · Tablas de huecos y citas en Postgres
   - **Qué:** ...
   - **Por qué:** ...
   - **Ficheros:** ...
   - **Siguiente:** ...
   ```
2. Si cambia el estado de una fase, actualizar `estado` en `plan.toml`.
3. Regenerar el Gantt:
   ```
   uv run python tools/bitacora.py
   ```
4. Al cerrar la sesión, actualizar "Dónde estoy" en `CONTEXTO.md`.

## Cómo se lee el Gantt

Cada fase tiene dos barras: **plan** (fechas de `plan.toml`) y **real** (de la primera
a la última entrada de la bitácora con ese id de fase). Si la real se va a la derecha
del plan, vas con retraso en esa fase. La línea vertical es hoy. La tabla de debajo
avisa de fases con retraso o con entradas pero aún marcadas como pendientes.
