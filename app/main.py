"""API for the fictional clinic: slots (huecos) and appointments (citas).

Phase 2 of CallBench. It is the backend the voice agent uses as tools
(find slots, book). Data lives in PostgreSQL (async SQLAlchemy + psycopg).

Without DATABASE_URL a portable Postgres (pgserver) is used, with data in .pgdata/;
it starts with the API and stops when the API is closed. To start:

    uv run alembic upgrade head          creates the tables and seeds the slots (once)
    uv run fastapi dev app/main.py       then open http://127.0.0.1:8000/docs

Without auto-reload (on Windows psycopg needs a different event loop):
    uv run uvicorn app.main:app --loop app.db.bucle:selector_loop
"""

from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.conexion import get_session
from app.db.modelos import Cita as CitaDB
from app.db.modelos import Hueco as HuecoDB

app = FastAPI(title="CallBench · Clinic API")


class Hueco(BaseModel):
    id: int
    inicio: datetime
    medico: str
    libre: bool = True


class CitaIn(BaseModel):
    """What the caller sends when booking. Pydantic rejects anything invalid with a 422."""

    hueco_id: int
    paciente: str = Field(min_length=2, max_length=80)
    motivo: str = Field(default="", max_length=200)


class Cita(BaseModel):
    """What the API returns: the created appointment, with its id."""

    id: int
    hueco_id: int
    paciente: str
    motivo: str
    inicio: datetime
    medico: str


@app.get("/salud")
async def salud() -> dict:
    return {"estado": "ok"}


@app.get("/huecos")
async def listar_huecos(
    solo_libres: bool = True, sesion: AsyncSession = Depends(get_session)
) -> list[Hueco]:
    consulta = select(HuecoDB).order_by(HuecoDB.id)
    if solo_libres:
        consulta = consulta.where(HuecoDB.libre)
    huecos = (await sesion.scalars(consulta)).all()
    return [Hueco.model_validate(h, from_attributes=True) for h in huecos]


@app.post("/citas", status_code=status.HTTP_201_CREATED)
async def crear_cita(datos: CitaIn, sesion: AsyncSession = Depends(get_session)) -> Cita:
    # A single UPDATE takes the slot only if it is still free (UPDATE huecos SET libre = false
    # WHERE id = :id AND libre RETURNING ...). With two simultaneous requests, Postgres
    # locks the row: the second one sees libre = false and updates nothing.
    ocupado = await sesion.execute(
        update(HuecoDB)
        .where(HuecoDB.id == datos.hueco_id, HuecoDB.libre)
        .values(libre=False)
        .returning(HuecoDB.inicio, HuecoDB.medico)
    )
    hueco = ocupado.one_or_none()
    if hueco is None:
        # Nothing was updated: either it does not exist (404) or it was already taken (409)
        existe = await sesion.scalar(select(HuecoDB.id).where(HuecoDB.id == datos.hueco_id))
        if existe is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "El hueco no existe")
        # 409 Conflict: the request is valid, but clashes with the current state
        raise HTTPException(status.HTTP_409_CONFLICT, "El hueco ya está ocupado")

    try:
        cita_id = await sesion.scalar(
            CitaDB.__table__.insert().values(**datos.model_dump()).returning(CitaDB.id)
        )
        await sesion.commit()
    except IntegrityError:
        # Safety net: the UNIQUE on citas.hueco_id also prevents double booking
        await sesion.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El hueco ya está ocupado")
    return Cita(id=cita_id, inicio=hueco.inicio, medico=hueco.medico, **datos.model_dump())


@app.get("/citas/{cita_id}")
async def leer_cita(cita_id: int, sesion: AsyncSession = Depends(get_session)) -> Cita:
    # citas JOIN huecos: the appointment stores neither time nor doctor, the slot provides them
    fila = (
        await sesion.execute(
            select(
                CitaDB.id,
                CitaDB.hueco_id,
                CitaDB.paciente,
                CitaDB.motivo,
                HuecoDB.inicio,
                HuecoDB.medico,
            )
            .join(HuecoDB, HuecoDB.id == CitaDB.hueco_id)
            .where(CitaDB.id == cita_id)
        )
    ).one_or_none()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La cita no existe")
    return Cita.model_validate(fila, from_attributes=True)
