"""Clinic and bench tables (SQLAlchemy 2). The real schema is created by Alembic: see migrations/."""

from datetime import datetime

from typing import Any

from sqlalchemy import ForeignKey, Identity, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    pass


class Hueco(Base):
    __tablename__ = "huecos"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    medico: Mapped[str]
    libre: Mapped[bool] = mapped_column(server_default=text("true"))


class Cita(Base):
    __tablename__ = "citas"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # UNIQUE: even if two requests arrive at once, the database prevents two appointments in one slot
    hueco_id: Mapped[int] = mapped_column(ForeignKey("huecos.id"), unique=True)
    paciente: Mapped[str]
    motivo: Mapped[str] = mapped_column(server_default=text("''"))
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


# --- Bench results and job queue (F3). Accessed with SQL in bench/; these classes
# document the schema and keep Alembic's metadata complete.

AHORA = text("now()")


class Version(Base):
    __tablename__ = "versiones"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    etiqueta: Mapped[str]
    git_sha: Mapped[str]
    # STT / LLM / TTS combination, e.g. {"stt": "deepgram", "llm": "groq:...", "tts": "deepgram:..."}
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=AHORA)


class Vuelta(Base):
    __tablename__ = "vueltas"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(unique=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("versiones.id"))
    escenarios: Mapped[list[str]] = mapped_column(JSONB)
    repeticiones: Mapped[int]
    modalidad: Mapped[str] = mapped_column(server_default=text("'texto'"))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=AHORA)


class Trabajo(Base):
    """One queued unit of work: one scenario file x one attempt number of a round."""

    __tablename__ = "trabajos"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    vuelta_id: Mapped[int] = mapped_column(ForeignKey("vueltas.id"))
    escenario: Mapped[str]
    intento: Mapped[int]
    # pendiente -> en_curso -> hecho | fallido (infra errors after the last retry)
    estado: Mapped[str] = mapped_column(server_default=text("'pendiente'"))
    intentos: Mapped[int] = mapped_column(server_default=text("0"))
    disponible_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=AHORA)
    lease_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker: Mapped[str | None]
    error: Mapped[str | None]
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=AHORA)
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Llamada(Base):
    """One scenario result (one execution of a job; retries add rows)."""

    __tablename__ = "llamadas"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    trabajo_id: Mapped[int] = mapped_column(ForeignKey("trabajos.id"))
    vuelta_id: Mapped[int] = mapped_column(ForeignKey("vueltas.id"))
    escenario: Mapped[str]
    intento: Mapped[int]
    ejecucion: Mapped[int]
    veredicto: Mapped[str]  # aprobado | suspenso | infra
    causa: Mapped[str | None]
    aprobado_juez: Mapped[bool | None]
    confianza_juez: Mapped[float | None]
    aprobado_asserts: Mapped[bool | None]
    asserts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    transcripcion: Mapped[list[Any] | None] = mapped_column(JSONB)
    metricas: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resultado: Mapped[dict[str, Any]] = mapped_column(JSONB)
    duracion_ms: Mapped[int | None]
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=AHORA)
