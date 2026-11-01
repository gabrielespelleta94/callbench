"""Where the database URL comes from.

If DATABASE_URL exists it is used as is (any Postgres). Otherwise pgserver starts
a portable Postgres (no Docker or admin rights needed) with data in .pgdata/.
"""

import json
import os
from pathlib import Path

import psutil
from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parents[2]
PGDATA = RAIZ / ".pgdata"


def normalizar(url: str) -> str:
    """Force the psycopg 3 driver: a bare `postgresql://` would use psycopg2."""
    u = make_url(url)
    if u.drivername in ("postgresql", "postgres"):
        u = u.set(drivername="postgresql+psycopg")
    return u.render_as_string(hide_password=False)


def podar_pids(pgdata: Path = PGDATA) -> list[int]:
    """Remove PIDs that no longer exist from .handle_pids.json and return the remaining ones.

    pgserver shuts Postgres down when the last PID in that file exits; if a process was
    killed, its PID stays and Postgres never shuts down (it is left orphaned).
    """
    fichero = pgdata / ".handle_pids.json"
    if not fichero.exists():
        return []
    try:
        pids = json.loads(fichero.read_text())
    except ValueError:
        pids = []  # corrupt file: pgserver will rewrite it
    vivos = [p for p in pids if psutil.pid_exists(p)]
    if vivos != pids:
        fichero.write_text(json.dumps(vivos))
    return vivos


def servidor_local(base: str = "postgres") -> str:
    """Start (or reuse) the Postgres in .pgdata/ and return its URL for database `base`.

    The server stops by itself when the last process using it ends (atexit),
    so the port changes on every start: do not store the URL.
    """
    import pgserver
    from pgserver.postgres_server import PostgresServer

    PGDATA.mkdir(exist_ok=True)
    # Same cross-process lock pgserver uses, so we do not clash with another process starting at the same time
    with PostgresServer._lock:
        podar_pids()
    return pgserver.get_server(PGDATA).get_uri(database=base)


def database_url(base: str = "postgres") -> str:
    return normalizar(os.environ.get("DATABASE_URL") or servidor_local(base))
