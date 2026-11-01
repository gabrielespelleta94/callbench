"""Clinic tables (SQLAlchemy 2). The real schema is created by Alembic: see migrations/."""

from datetime import datetime

from sqlalchemy import ForeignKey, Identity, text
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
