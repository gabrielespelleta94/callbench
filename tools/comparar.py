"""Regression gate: compare a candidate round against a base round, per scenario.

    uv run python tools/comparar.py <base> <candidata>          # table + exit code
    uv run python tools/comparar.py <base> <candidata> --json   # machine-readable diff
    uv run python tools/comparar.py --resumen <vuelta> > evals/baselines/<vuelta>.json

Each side can be: a summary JSON written with `--resumen` (a committed baseline), a round
directory or name under evals/runs/ with a results.jsonl (evals/lanzar.py suite), or the
name of a round stored in Postgres (bench queue / tools/importar_vuelta.py). `a+b` pools
the calls of several rounds of the same version.

Exit code: 1 if some scenario got worse beyond noise or the voice-to-voice p95 grew more
than 20 %; 2 if not conclusive (missing scenarios, infra failures, no valid calls);
0 otherwise. The rule is documented in bench/resultados.py and evals/README.md.
"""

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from bench import resultados as res  # noqa: E402

ICONO = {"empeora": "PEOR", "mejora": "MEJOR", "igual": "=", "no_concluyente": "?", "nuevo": "nuevo"}


class VueltaNoEncontrada(Exception):
    pass


def llamadas_de_bd(nombre: str) -> list[dict]:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from app.db.config import database_url

    motor = create_engine(database_url(), poolclass=NullPool)
    try:
        with motor.connect() as con:
            fila = con.execute(text("SELECT id FROM vueltas WHERE nombre = :n"), {"n": nombre}).first()
            if fila is None:
                raise VueltaNoEncontrada(nombre)
            filas = con.execute(text(res.SQL_LLAMADAS), {"vuelta_id": fila.id}).mappings().all()
    finally:
        motor.dispose()
    return [res.llamada_de_fila_bd(dict(f)) for f in filas]


def cargar_resumen(arg: str) -> dict:
    """Summary of one side of the comparison, from wherever it lives. `a+b` pools the
    calls of several rounds of the same version (more N)."""
    ruta = Path(arg)
    if ruta.suffix == ".json" and ruta.is_file():
        return json.loads(ruta.read_text(encoding="utf-8"))
    llamadas, metricas = [], []
    for parte in arg.split("+"):
        directorio = res.dir_vuelta(parte)
        if (directorio / "results.jsonl").is_file():
            llamadas += res.llamadas_de_ficheros(directorio)
            m = res.metricas_de_directorio(directorio / "metrics")
            if m:
                metricas.append(m)
        else:
            llamadas += llamadas_de_bd(parte)
    resumen = res.resumir(llamadas)
    if metricas and not resumen["latencia"]["voice_to_voice"]["n"]:
        # suite rounds keep metrics per round, not per call: pool them for latency
        resumen["latencia"] = {
            "voice_to_voice": res._p([v for m in metricas for v in m["voice_to_voice"]]),
            "ttfb": {s: res._p([v for m in metricas for v in m["ttfb"][s]]) for s in res.coste.STAGES},
        }
    return resumen | {"vuelta": "+".join(Path(p).name for p in arg.split("+"))}


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.0%}"


def _lado(e: dict | None) -> str:
    if not e:
        return "-"
    ic = e["ic"]
    texto_ic = f" [{ic[0]:.0%}-{ic[1]:.0%}]" if ic else ""
    return f"{e['aprobado']}/{e['n']} {_pct(e['tasa'])}{texto_ic}"


def formatear(diff: dict, nombre_base: str, nombre_cand: str) -> str:
    filas = diff["escenarios"]
    ancho = max([len(f["escenario"]) for f in filas] + [9])
    lineas = [f"Base: {nombre_base}   Candidata: {nombre_cand}", ""]
    lineas.append(f"{'escenario':<{ancho}}  {'base':<20}  {'candidata':<20}  {'delta':>6}  estado")
    for f in filas:
        delta = "-" if f["delta"] is None else f"{f['delta']:+.0%}"
        lineas.append(
            f"{f['escenario']:<{ancho}}  {_lado(f['base']):<20}  {_lado(f['candidata']):<20}  "
            f"{delta:>6}  {ICONO[f['estado']]}  {f['motivo']}"
        )
    t = diff["total"]
    lineas.append(f"{'TOTAL':<{ancho}}  {_lado(t['base']):<20}  {_lado(t['candidata']):<20}")
    v = diff["latencia"]["voice_to_voice"]
    if v["medible"]:
        lineas += ["", f"p95 voz a voz: {v['base']['p95']:.3f}s -> {v['candidata']['p95']:.3f}s "
                       f"({v['delta_rel']['p95']:+.0%})"]
    else:
        lineas += ["", "p95 voz a voz: sin métricas suficientes en alguna de las dos vueltas"]
    ver = diff["veredicto"]
    lineas += ["", f"Veredicto: {ver['texto']} (salida {ver['codigo']})"]
    lineas += [f"  - {m}" for m in ver["motivos"] + ver["dudas"]]
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("vueltas", nargs="*", help="<base> <candidata>")
    ap.add_argument("--resumen", metavar="VUELTA", help="print the summary JSON of one round")
    ap.add_argument("--json", action="store_true", help="print the diff as JSON")
    args = ap.parse_args(argv)
    try:
        if args.resumen:
            print(res.a_json(cargar_resumen(args.resumen)))
            return 0
        if len(args.vueltas) != 2:
            ap.error("hacen falta dos vueltas: <base> <candidata>")
        base, cand = (cargar_resumen(v) for v in args.vueltas)
    except VueltaNoEncontrada as e:
        print(f"No existe la vuelta {e} (ni en evals/runs/ ni en Postgres).", file=sys.stderr)
        return 2
    diff = res.comparar(base, cand)
    texto = res.a_json(diff) if args.json else formatear(diff, *args.vueltas)
    sys.stdout.buffer.write((texto + "\n").encode("utf-8"))
    return diff["veredicto"]["codigo"]


if __name__ == "__main__":
    sys.exit(main())
