"""Load a round run with `evals/lanzar.py suite` (evals/runs/<round>/) into Postgres.

    uv run python tools/importar_vuelta.py <round dir or name> [-n name] [-e label] [--sha SHA]
    uv run python tools/importar_vuelta.py ... --reemplazar   # drop a round with that name first

Rounds run through the queue (bench/) are already in Postgres; this is for the older
suite rounds, so the scorecard can show them. Each results.jsonl row becomes a finished
job and a call, graded with the judge and the deterministic asserts; the transcript comes
from the call's conversation.json with the tool results attached, and the metrics from
`<round>/metrics/<n>.jsonl` if present (one file per row, in order).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from bench import resultados as res  # noqa: E402
from evals.informe import leer_filas  # noqa: E402


def _fichero_escenario(escenario: str) -> str:
    return escenario.split("/")[0]


def importar(
    motor: Engine,
    directorio: Path,
    nombre: str,
    etiqueta: str,
    git_sha: str = "desconocido",
    config: dict | None = None,
    reemplazar: bool = False,
) -> int:
    """Insert the round and its calls; returns the new round id."""
    filas = leer_filas(directorio / "results.jsonl")
    llamadas = res.llamadas_de_ficheros(directorio)
    with motor.begin() as con:
        previa = con.execute(text("SELECT id FROM vueltas WHERE nombre = :n"), {"n": nombre}).first()
        if previa is not None:
            if not reemplazar:
                raise SystemExit(f"Ya existe la vuelta {nombre}: usa --reemplazar")
            con.execute(text("DELETE FROM llamadas WHERE vuelta_id = :v"), {"v": previa.id})
            con.execute(text("DELETE FROM trabajos WHERE vuelta_id = :v"), {"v": previa.id})
            con.execute(text("DELETE FROM vueltas WHERE id = :v"), {"v": previa.id})
        version_id = con.execute(
            text(
                "INSERT INTO versiones (etiqueta, git_sha, config) "
                "VALUES (:e, :s, CAST(:c AS jsonb)) RETURNING id"
            ),
            {"e": etiqueta, "s": git_sha, "c": json.dumps(config or {})},
        ).scalar_one()
        escenarios = list(dict.fromkeys(_fichero_escenario(f.get("scenario", "?")) for f in filas))
        repeticiones = max([int(f.get("attempt") or 1) for f in filas] or [1])
        vuelta_id = con.execute(
            text(
                "INSERT INTO vueltas (nombre, version_id, escenarios, repeticiones, modalidad, creada_en) "
                "VALUES (:n, :v, CAST(:e AS jsonb), :r, 'texto', :f) RETURNING id"
            ),
            {
                "n": nombre,
                "v": version_id,
                "e": json.dumps(escenarios),
                "r": repeticiones,
                # when the round ran, not when it was imported
                "f": datetime.fromtimestamp((directorio / "results.jsonl").stat().st_mtime, timezone.utc),
            },
        ).scalar_one()
        metricas = sorted((directorio / "metrics").glob("*.jsonl"))
        vistos: set[tuple[str, int]] = set()
        for i, (fila, ll) in enumerate(zip(filas, llamadas, strict=True)):
            intento = int(fila.get("attempt") or 1)
            clave = (fila.get("scenario", "?"), intento)
            if clave in vistos:  # a reused round name appends repeated attempts: keep the first
                continue
            vistos.add(clave)
            infra = ll["veredicto"] == "infra"
            trabajo_id = con.execute(
                text(
                    "INSERT INTO trabajos (vuelta_id, escenario, intento, estado, intentos, terminado_en, error) "
                    "VALUES (:v, :e, :i, :s, 1, now(), :err) RETURNING id"
                ),
                {
                    "v": vuelta_id,
                    "e": clave[0],
                    "i": intento,
                    "s": "fallido" if infra else "hecho",
                    "err": ll["causa"] if infra else None,
                },
            ).scalar_one()
            m = res.metricas_de_fichero(metricas[i]) if i < len(metricas) else None
            con.execute(
                text(
                    """
                    INSERT INTO llamadas (trabajo_id, vuelta_id, escenario, intento, ejecucion,
                        veredicto, causa, aprobado_juez, confianza_juez, aprobado_asserts, asserts,
                        transcripcion, metricas, resultado, duracion_ms)
                    VALUES (:t, :v, :e, :i, 1, :ver, :c, :aj, :cj, :aa, CAST(:a AS jsonb),
                        CAST(:tr AS jsonb), CAST(:m AS jsonb), CAST(:res AS jsonb), :d)
                    """
                ),
                {
                    "t": trabajo_id,
                    "v": vuelta_id,
                    "e": clave[0],
                    "i": intento,
                    "ver": ll["juez"]["veredicto"],
                    "c": ll["causa"] if ll["juez"]["veredicto"] != "aprobado" else None,
                    "aj": None if infra else ll["juez"]["veredicto"] == "aprobado",
                    "cj": fila.get("confidence"),
                    "aa": {"aprobado": True, "suspenso": False}.get(ll["asserts"]["veredicto"]),
                    "a": json.dumps(ll["asserts"]),
                    "tr": None if ll["transcripcion"] is None else json.dumps(ll["transcripcion"]),
                    "m": None if m is None else json.dumps(m),
                    "res": json.dumps(fila),
                    "d": fila.get("duration_ms"),
                },
            )
    return vuelta_id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("vuelta", help="round directory, or its name under evals/runs/")
    ap.add_argument("-n", "--nombre", help="name in Postgres (default: the directory name)")
    ap.add_argument("-e", "--etiqueta", help="version label (default: the round name)")
    ap.add_argument("--sha", default="desconocido", help="git commit the round ran with")
    ap.add_argument("--reemplazar", action="store_true")
    args = ap.parse_args(argv)

    directorio = res.dir_vuelta(args.vuelta)
    if not (directorio / "results.jsonl").is_file():
        print(f"No hay results.jsonl en {directorio}", file=sys.stderr)
        return 1
    from app.db.config import database_url

    nombre = args.nombre or directorio.name
    motor = create_engine(database_url(), poolclass=NullPool)
    try:
        vid = importar(motor, directorio, nombre, args.etiqueta or nombre, args.sha, reemplazar=args.reemplazar)
    finally:
        motor.dispose()
    print(f"Vuelta {nombre} importada con id {vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
