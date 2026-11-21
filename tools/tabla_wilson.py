"""Version vs version table per scenario, with Wilson 95 % intervals.

Each version is one or more round directories (suite or bench layout), graded by
evals/informe.py (judge + asserts). Prints the failures, the infra retries, how many
bookings the confirmation guard refused, and a Markdown table for the log.

    uv run python tools/tabla_wilson.py v1-base:evals/runs/v1-a,evals/runs/v1-b v2:evals/runs/v2-a
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))
import informe  # noqa: E402


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({lo:.0%}-{hi:.0%})" if n else "0/0"


def cargar(dirs):
    filas, reintentos, guarda = [], 0, 0
    for d in dirs:
        det, res = informe.analizar(Path(d))
        filas += det
        reintentos += res.get("reintentos", 0)
        guarda += sum(
            (Path(p) / "bot.log").read_text(encoding="utf-8", errors="replace").count(
                "rechazada por la guarda"
            )
            for p in Path(d).iterdir() if (Path(p) / "bot.log").exists()
        )
    return filas, reintentos, guarda


versiones = {}
for arg in sys.argv[1:]:
    etiqueta, dirs = arg.split(":", 1)
    versiones[etiqueta] = cargar(dirs.split(","))

tabla = defaultdict(dict)
for v, (filas, reint, guarda) in versiones.items():
    for f in filas + [dict(d, escenario="TOTAL") for d in filas]:
        c = tabla[f["escenario"]].setdefault(v, defaultdict(int))
        c[f["veredicto"]] += 1
        if f["juez"] != "infra":
            c["juez_ok"] += f["juez"] == "aprobado"
            c["asserts_ok"] += f["asserts"] == "aprobado"
            c["asserts_eval"] += f["asserts"] != "n/a"
            c["juez_n"] += 1
    print(f"{v}: reintentos de infra {reint}; reservas paradas por la guarda {guarda}")
    for f in filas:
        if f["veredicto"] != "aprobado":
            print(f"   - {f['escenario']} #{f['intento']} [{f['veredicto']}] {f['causa']}")

vs = list(versiones)
print("\n| Escenario | " + " | ".join(f"{v} aprobadas/válidas (IC 95 %)" for v in vs)
      + " | " + " | ".join(f"{v} juez / asserts" for v in vs) + " | "
      + " | ".join(f"{v} infra" for v in vs) + " |")
print("|---" * (1 + 3 * len(vs)) + "|")
for esc in sorted(tabla, key=lambda e: (e == "TOTAL", e)):
    cs = [tabla[esc].get(v, defaultdict(int)) for v in vs]
    celdas = [fmt(c["aprobado"], c["aprobado"] + c["suspenso"]) for c in cs]
    celdas += [f"{c['juez_ok']}/{c['juez_n']} / {c['asserts_ok']}/{c['asserts_eval']}" for c in cs]
    celdas += [str(c["infra"]) for c in cs]
    print(f"| {esc} | " + " | ".join(celdas) + " |")
