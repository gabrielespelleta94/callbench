"""API fixtures: real Postgres (pgserver) with a separate test database.

The `callbench_test` database lives in the same portable Postgres in .pgdata/ but is
kept apart from the development data. The schema comes from the Alembic migrations
(so they get tested too) and each test starts with empty tables and reseeded slots.
"""

import importlib

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import main
from app.db.config import RAIZ, normalizar, servidor_local
from app.db.conexion import get_session

BASE_TEST = "callbench_test"
# The migration name starts with a number: it cannot be imported with `import`
SEMILLA = importlib.import_module("migrations.versions.0002_semilla_huecos").HUECOS


@pytest.fixture(scope="session")
def url_test() -> str:
    admin = servidor_local("postgres").replace("postgresql+psycopg", "postgresql")
    with psycopg.connect(admin, autocommit=True) as con:
        existe = con.execute("SELECT 1 FROM pg_database WHERE datname = %s", (BASE_TEST,))
        if existe.fetchone() is None:
            con.execute(f"CREATE DATABASE {BASE_TEST}")
    url = normalizar(servidor_local(BASE_TEST))

    # Clean schema from the migrations: drop the previous one and recreate it
    motor = create_engine(url, poolclass=NullPool)
    with motor.begin() as con:
        con.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    motor.dispose()
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
def base_limpia(url_test):
    """Empty the tables, reset the ids and reseed the slots before each test."""
    motor = create_engine(url_test, poolclass=NullPool)
    with motor.begin() as con:
        con.execute(text("TRUNCATE citas, huecos RESTART IDENTITY"))
        for inicio, medico, libre in SEMILLA:
            con.execute(
                text("INSERT INTO huecos (inicio, medico, libre) VALUES (:i, :m, :l)"),
                {"i": inicio, "m": medico, "l": libre},
            )
    motor.dispose()
    return url_test


@pytest.fixture
def app_con_bd(base_limpia):
    """The app pointed at the test database. A pool-less engine per session: each
    TestClient / asyncio.run request runs in its own loop and cannot reuse connections."""

    async def sesion_de_test():
        motor = create_async_engine(
            base_limpia, poolclass=NullPool, connect_args={"options": "-c timezone=GMT"}
        )
        async with async_sessionmaker(motor, expire_on_commit=False)() as sesion:
            yield sesion
        await motor.dispose()

    main.app.dependency_overrides[get_session] = sesion_de_test
    yield main.app
    main.app.dependency_overrides.clear()


@pytest.fixture
def cliente(app_con_bd):
    return TestClient(app_con_bd)
