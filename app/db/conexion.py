"""Async engine and per-request session."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.config import database_url

# Created on first use: importing app.main must not start Postgres (e.g. in tests)
_fabrica: async_sessionmaker[AsyncSession] | None = None


def crear_engine(url: str | None = None, **kwargs):
    # timezone=GMT so timestamptz values come out the same on any machine
    return create_async_engine(
        url or database_url(), connect_args={"options": "-c timezone=GMT"}, **kwargs
    )


def _sesiones() -> async_sessionmaker[AsyncSession]:
    global _fabrica
    if _fabrica is None:
        _fabrica = async_sessionmaker(crear_engine(pool_pre_ping=True), expire_on_commit=False)
    return _fabrica


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed when it finishes."""
    async with _sesiones()() as sesion:
        yield sesion
