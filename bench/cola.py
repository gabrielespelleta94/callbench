"""Queue operations on Postgres: versions, rounds, jobs with leases, and results.

Every timestamp comparison uses the database clock (`now()`), so workers on machines
with skewed clocks still agree on when a lease has expired.

Job life cycle:

    pendiente --tomar--> en_curso --terminar--> hecho          (passed or failed by the agent)
                            |                   fallido        (infra error on the last attempt)
                            |--terminar (infra, attempts left)--> pendiente (after a backoff)
                            '--lease expired (worker died)------> taken again by `tomar`
"""

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.db.config import database_url

MAX_INTENTOS = 3
LEASE_S = 600  # a scenario takes 0.5-3 min; the worker renews the lease while it runs
BACKOFF_S = 30.0  # wait before retrying an infra failure: 30 s, then 60 s


def motor(url: str | None = None) -> Engine:
    return create_engine(
        url or database_url(), connect_args={"options": "-c timezone=GMT"}, pool_pre_ping=True
    )


@dataclass(frozen=True)
class Trabajo:
    id: int
    vuelta_id: int
    vuelta: str
    escenario: str
    intento: int
    intentos: int  # executions so far, including the current one


@dataclass(frozen=True)
class Resultado:
    """One scenario result, already classified (see evals/informe.py)."""

    escenario: str
    veredicto: str  # aprobado | suspenso | infra
    causa: str | None
    fila: dict[str, Any]  # the results.jsonl record written by pipecat.evals
    aprobado_juez: bool | None = None
    confianza_juez: float | None = None
    transcripcion: list[Any] | None = None
    metricas: dict[str, Any] | None = None
    duracion_ms: int | None = None


def obtener_version(con, etiqueta: str, git_sha: str, config: dict) -> int:
    """Id of the version with that label, commit and config; created if it does not exist."""
    config_json = json.dumps(config, sort_keys=True)
    fila = con.execute(
        text(
            "SELECT id FROM versiones WHERE etiqueta = :e AND git_sha = :g "
            "AND config = CAST(:c AS jsonb)"
        ),
        {"e": etiqueta, "g": git_sha, "c": config_json},
    ).first()
    if fila:
        return fila.id
    return con.execute(
        text(
            "INSERT INTO versiones (etiqueta, git_sha, config) "
            "VALUES (:e, :g, CAST(:c AS jsonb)) RETURNING id"
        ),
        {"e": etiqueta, "g": git_sha, "c": config_json},
    ).scalar_one()


def crear_vuelta(
    con,
    nombre: str,
    version_id: int,
    escenarios: list[str],
    repeticiones: int,
    modalidad: str = "texto",
) -> int:
    """Create the round and one job per scenario x attempt. Attempt 1 of every scenario
    comes first in the queue, so a round cut short still covers all scenarios."""
    vuelta_id = con.execute(
        text(
            "INSERT INTO vueltas (nombre, version_id, escenarios, repeticiones, modalidad) "
            "VALUES (:n, :v, CAST(:e AS jsonb), :r, :m) RETURNING id"
        ),
        {
            "n": nombre,
            "v": version_id,
            "e": json.dumps(escenarios),
            "r": repeticiones,
            "m": modalidad,
        },
    ).scalar_one()
    con.execute(
        text("INSERT INTO trabajos (vuelta_id, escenario, intento) VALUES (:v, :e, :i)"),
        [
            {"v": vuelta_id, "e": e, "i": i}
            for i in range(1, repeticiones + 1)
            for e in escenarios
        ],
    )
    return vuelta_id


def recoger_caducados(motor: Engine, max_intentos: int = MAX_INTENTOS) -> int:
    """Expired leases with no attempts left become `fallido` (the worker kept dying)."""
    with motor.begin() as con:
        return con.execute(
            text(
                "UPDATE trabajos SET estado = 'fallido', terminado_en = now(), lease_hasta = NULL, "
                "error = 'lease caducado (worker muerto) en el intento ' || intentos "
                "WHERE estado = 'en_curso' AND lease_hasta < now() AND intentos >= :max"
            ),
            {"max": max_intentos},
        ).rowcount


def tomar(
    motor: Engine, worker: str, lease_s: float = LEASE_S, max_intentos: int = MAX_INTENTOS
) -> Trabajo | None:
    """Take the next runnable job, or None.

    Runnable: pending and past its backoff, or running with an expired lease (its worker
    died). SKIP LOCKED lets several workers claim at once without waiting for each other
    and without two of them getting the same row.
    """
    with motor.begin() as con:
        fila = con.execute(
            text(
                """
                UPDATE trabajos t
                SET estado = 'en_curso', intentos = t.intentos + 1, worker = :w,
                    lease_hasta = now() + make_interval(secs => :lease)
                FROM (
                    SELECT id FROM trabajos
                    WHERE (estado = 'pendiente' AND disponible_en <= now())
                       OR (estado = 'en_curso' AND lease_hasta < now() AND intentos < :max)
                    ORDER BY intento, id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                ) elegido, vueltas v
                WHERE t.id = elegido.id AND v.id = t.vuelta_id
                RETURNING t.id, t.vuelta_id, v.nombre, t.escenario, t.intento, t.intentos
                """
            ),
            {"w": worker, "lease": lease_s, "max": max_intentos},
        ).first()
    if fila is None:
        return None
    return Trabajo(*fila)


def renovar_lease(motor: Engine, trabajo_id: int, worker: str, lease_s: float = LEASE_S) -> bool:
    """Extend the lease. False if this worker no longer owns the job (it expired and
    another worker took it): the caller's result will then be discarded."""
    with motor.begin() as con:
        return (
            con.execute(
                text(
                    "UPDATE trabajos SET lease_hasta = now() + make_interval(secs => :lease) "
                    "WHERE id = :id AND worker = :w AND estado = 'en_curso'"
                ),
                {"id": trabajo_id, "w": worker, "lease": lease_s},
            ).rowcount
            == 1
        )


def terminar(
    motor: Engine,
    trabajo: Trabajo,
    worker: str,
    resultados: list[Resultado],
    max_intentos: int = MAX_INTENTOS,
    backoff_s: float = BACKOFF_S,
) -> str | None:
    """Store the results and move the job on. Returns the new state, or None if the
    job was no longer ours (lease lost): nothing is written then.

    Only infrastructure failures are retried; an agent failure is a valid measurement.
    """
    with motor.begin() as con:
        propio = con.execute(
            text(
                "SELECT 1 FROM trabajos WHERE id = :id AND worker = :w "
                "AND estado = 'en_curso' AND intentos = :n FOR UPDATE"
            ),
            {"id": trabajo.id, "w": worker, "n": trabajo.intentos},
        ).first()
        if propio is None:
            return None
        for r in resultados:
            con.execute(
                text(
                    """
                    INSERT INTO llamadas (trabajo_id, vuelta_id, escenario, intento, ejecucion,
                        veredicto, causa, aprobado_juez, confianza_juez, transcripcion, metricas,
                        resultado, duracion_ms)
                    VALUES (:t, :v, :e, :i, :x, :ver, :c, :aj, :cj, CAST(:tr AS jsonb),
                        CAST(:m AS jsonb), CAST(:res AS jsonb), :d)
                    """
                ),
                {
                    "t": trabajo.id,
                    "v": trabajo.vuelta_id,
                    "e": r.escenario,
                    "i": trabajo.intento,
                    "x": trabajo.intentos,
                    "ver": r.veredicto,
                    "c": r.causa,
                    "aj": r.aprobado_juez,
                    "cj": r.confianza_juez,
                    "tr": None if r.transcripcion is None else json.dumps(r.transcripcion),
                    "m": None if r.metricas is None else json.dumps(r.metricas),
                    "res": json.dumps(r.fila),
                    "d": r.duracion_ms,
                },
            )
        infra = [r for r in resultados if r.veredicto == "infra"] or (
            [] if resultados else [Resultado("?", "infra", "sin resultados", {})]
        )
        if not infra:
            estado, error, espera = "hecho", None, None
        elif trabajo.intentos < max_intentos:
            estado, error = "pendiente", infra[0].causa
            espera = backoff_s * 2 ** (trabajo.intentos - 1)
        else:
            estado, error, espera = "fallido", infra[0].causa, None
        con.execute(
            text(
                """
                UPDATE trabajos SET estado = CAST(:estado AS text), error = :error,
                    lease_hasta = NULL,
                    worker = CASE WHEN :reintento THEN NULL ELSE worker END,
                    disponible_en = CASE WHEN :reintento
                        THEN now() + make_interval(secs => :espera) ELSE disponible_en END,
                    terminado_en = CASE WHEN :reintento THEN NULL ELSE now() END
                WHERE id = :id
                """
            ),
            {
                "estado": estado,
                "error": error,
                "reintento": espera is not None,
                "espera": float(espera or 0),
                "id": trabajo.id,
            },
        )
    return estado


def quedan(motor: Engine, vuelta_id: int | None = None) -> int:
    """Jobs not finished yet (pending or running), in one round or in all."""
    with motor.connect() as con:
        return con.execute(
            text(
                "SELECT count(*) FROM trabajos WHERE estado IN ('pendiente', 'en_curso') "
                "AND (CAST(:v AS integer) IS NULL OR vuelta_id = :v)"
            ),
            {"v": vuelta_id},
        ).scalar_one()
