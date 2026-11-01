"""Alembic environment: synchronous, with the same driver (psycopg) and URL as the app."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.config import database_url
from app.db.modelos import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests pass their own URL (test database) via config.attributes["url"]
    url = config.attributes.get("url") or database_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
