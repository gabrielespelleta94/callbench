"""Genera el Gantt de CallBench a partir del plan y de la bitácora.

Lee docs/bitacora/plan.toml (fases y fechas planificadas) y docs/bitacora/BITACORA.md
(entradas con cabecera "## AAAA-MM-DD · <fase> · <título>") y escribe:

    docs/bitacora/GANTT.md     Mermaid (se ve en GitHub y en VS Code)
    docs/bitacora/GANTT.html   el mismo Gantt para abrir en el navegador

Solo usa la biblioteca estándar. Arranque:

    uv run python tools/bitacora.py
"""

import html
import re
import tomllib
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "docs" / "bitacora"
CABECERA = re.compile(r"^## (\d{4}-\d{2}-\d{2}) · (\S+) · (.+?)\s*$")
ICONO = {"hecho": "✅", "en_curso": "🔄", "pendiente": "⏳", "bloqueado": "⛔"}
PESO = {"hecho": 1.0, "en_curso": 0.5, "pendiente": 0.0, "bloqueado": 0.0}


def leer_entradas(texto: str) -> list[dict]:
    entradas = []
    for linea in texto.splitlines():
        m = CABECERA.match(linea)
        if m:
            entradas.append({"fecha": date.fromisoformat(m[1]), "fase": m[2], "titulo": m[3]})
    return entradas


def fechas_reales(fase: dict, entradas: list[dict], hoy: date) -> tuple[date, date] | None:
    """Primera y última entrada de la fase; si sigue en curso, la barra llega a hoy."""
    fechas = [e["fecha"] for e in entradas if e["fase"] == fase["id"]]
    if not fechas:
        return None
    fin = hoy if fase["estado"] == "en_curso" else max(fechas)
    return min(fechas), max(fin, min(fechas))


def limpiar(texto: str) -> str:
    # Mermaid usa ":" y "#" como separadores dentro de las tareas
    return texto.replace(":", " ").replace("#", "")


def mermaid(proyecto: dict, fases: list[dict], entradas: list[dict], hoy: date) -> str:
    lineas = [
        "gantt",
        f"    title {limpiar(proyecto['nombre'])} · plan vs real",
        "    dateFormat YYYY-MM-DD",
        "    axisFormat %d %b",
        "    todayMarker on",
    ]
    for f in fases:
        lineas.append(f"    section {f['id']}")
        # Mermaid toma el fin como exclusivo: +1 día para que una fase de un día se vea
        lineas.append(f"    {limpiar(f['nombre'])} (plan) :{f['id']}p, {f['inicio']}, {f['fin'] + timedelta(days=1)}")
        real = fechas_reales(f, entradas, hoy)
        if real:
            etiqueta = {"hecho": "done", "en_curso": "active", "bloqueado": "crit"}.get(f["estado"], "active")
            lineas.append(f"    Real :{etiqueta}, {f['id']}r, {real[0]}, {real[1] + timedelta(days=1)}")
    return "\n".join(lineas)


def resumen(fases: list[dict], entradas: list[dict], hoy: date) -> tuple[int, list[str]]:
    avance = round(100 * sum(PESO[f["estado"]] for f in fases) / len(fases))
    filas = []
    for f in fases:
        real = fechas_reales(f, entradas, hoy)
        aviso = ""
        if f["estado"] != "hecho" and hoy > f["fin"]:
            aviso = f"retraso {(hoy - f['fin']).days} d"
        elif f["estado"] == "pendiente" and real:
            aviso = "hay entradas pero sigue pendiente"
        n = sum(1 for e in entradas if e["fase"] == f["id"])
        filas.append(
            f"| {f['id']} | {f['nombre']} | {ICONO[f['estado']]} {f['estado']} | "
            f"{f['inicio']} → {f['fin']} | {f'{real[0]} → {real[1]}' if real else '—'} | {n} | {aviso} |"
        )
    return avance, filas


def main() -> None:
    plan = tomllib.loads((RAIZ / "plan.toml").read_text(encoding="utf-8"))
    proyecto, fases = plan["proyecto"], plan["fase"]
    entradas = leer_entradas((RAIZ / "BITACORA.md").read_text(encoding="utf-8"))
    hoy = date.today()

    ids = {f["id"] for f in fases} | {"META"}
    desconocidas = sorted({e["fase"] for e in entradas} - ids)
    if desconocidas:
        print(f"Aviso: fases en la bitácora que no están en plan.toml: {', '.join(desconocidas)}")

    gantt = mermaid(proyecto, fases, entradas, hoy)
    avance, filas = resumen(fases, entradas, hoy)
    actual = next((f for f in fases if f["estado"] == "en_curso"), None)
    ultimas = sorted(entradas, key=lambda e: e["fecha"], reverse=True)[:8]

    tabla = [
        "| Fase | Nombre | Estado | Plan | Real | Entradas | Aviso |",
        "|---|---|---|---|---|---|---|",
        *filas,
    ]
    md = [
        f"# {proyecto['nombre']} · Gantt",
        "",
        "> Generado por `tools/bitacora.py` desde `plan.toml` y `BITACORA.md`. No editar a mano.",
        "",
        f"**Objetivo:** {proyecto['objetivo']}",
        "",
        f"**Actualizado:** {hoy} · **Avance:** {avance} % · "
        f"**Fase actual:** {f'{actual['id']} {actual['nombre']}' if actual else '—'}",
        "",
        "```mermaid",
        gantt,
        "```",
        "",
        *tabla,
        "",
        "## Últimas entradas de la bitácora",
        "",
        *[f"- {e['fecha']} · **{e['fase']}** · {e['titulo']}" for e in ultimas],
        "",
    ]
    (RAIZ / "GANTT.md").write_text("\n".join(md), encoding="utf-8")

    filas_html = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c.strip())}</td>" for c in fila.strip("|").split("|")) + "</tr>"
        for fila in filas
    )
    entradas_html = "".join(
        f"<li><b>{e['fecha']}</b> · {html.escape(e['fase'])} · {html.escape(e['titulo'])}</li>" for e in ultimas
    )
    pagina = PLANTILLA.format(
        nombre=html.escape(proyecto["nombre"]),
        objetivo=html.escape(proyecto["objetivo"]),
        hoy=hoy,
        avance=avance,
        actual=html.escape(f"{actual['id']} · {actual['nombre']}" if actual else "—"),
        gantt=html.escape(gantt),
        filas=filas_html,
        entradas=entradas_html,
    )
    (RAIZ / "GANTT.html").write_text(pagina, encoding="utf-8")
    print(f"Gantt generado: avance {avance} %, {len(entradas)} entradas, {len(fases)} fases")


PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{nombre} Gantt</title>
<style>
  :root {{ --fondo:#fafaf9; --texto:#1c1917; --suave:#78716c; --borde:#e7e5e4; --acento:#0f766e; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fondo:#1c1917; --texto:#f5f5f4; --suave:#a8a29e; --borde:#44403c; --acento:#2dd4bf; }}
  }}
  body {{ background:var(--fondo); color:var(--texto); font:15px/1.5 system-ui, sans-serif;
         max-width:1100px; margin:0 auto; padding:24px 16px; }}
  h1 {{ margin:0 0 4px; }} .suave {{ color:var(--suave); }}
  .kpis {{ display:flex; gap:24px; flex-wrap:wrap; margin:16px 0; }}
  .kpis b {{ display:block; font-size:24px; color:var(--acento); }}
  .scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; }}
  td, th {{ border-bottom:1px solid var(--borde); padding:6px 8px; text-align:left; white-space:nowrap; }}
</style></head><body>
<h1>{nombre}</h1>
<p class="suave">{objetivo}</p>
<div class="kpis">
  <div><b>{avance} %</b><span class="suave">avance</span></div>
  <div><b>{actual}</b><span class="suave">fase actual</span></div>
  <div><b>{hoy}</b><span class="suave">actualizado</span></div>
</div>
<div class="scroll"><pre class="mermaid">{gantt}</pre></div>
<h2>Fases</h2>
<div class="scroll"><table>
<tr><th>Fase</th><th>Nombre</th><th>Estado</th><th>Plan</th><th>Real</th><th>Entradas</th><th>Aviso</th></tr>
{filas}
</table></div>
<h2>Últimas entradas</h2>
<ul>{entradas}</ul>
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";
  const oscuro = matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({{ startOnLoad: true, theme: oscuro ? "dark" : "default" }});
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
