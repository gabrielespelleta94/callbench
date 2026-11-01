"""Reset the development agenda: `uv run python -m app.db.reiniciar`.

Empties the appointments and slots of the development database (never the test one)
and reseeds a realistic agenda relative to today: the next 5 working days,
Dr. Lopez in the morning and Dr. Ruiz in the afternoon, a few slots already taken.
Run it before each eval run, because the simulated patients really book.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.db.config import database_url

DIAS_LABORABLES = 5
# (doctor, start times). Dr. Lopez has 4 slots a day, Dr. Ruiz 3
JORNADAS = [
    ("Dr. Lopez", [time(9, 0), time(9, 30), time(10, 0), time(10, 30)]),
    ("Dr. Ruiz", [time(16, 0), time(16, 30), time(17, 0)]),
]


def proximos_laborables(hoy: date, cuantos: int = DIAS_LABORABLES) -> list[date]:
    """The next `cuantos` Monday-to-Friday days strictly after `hoy`."""
    dias: list[date] = []
    dia = hoy
    while len(dias) < cuantos:
        dia += timedelta(days=1)
        if dia.weekday() < 5:
            dias.append(dia)
    return dias


def generar_huecos(hoy: date, cuantos: int = DIAS_LABORABLES) -> list[tuple[datetime, str, bool]]:
    """Slots as (start, doctor, free) for the next working days after `hoy`.

    Deterministic: on each day one slot of each doctor is already taken (the position
    rotates with the day), so the agenda never looks empty or completely free.
    """
    huecos = []
    for n, dia in enumerate(proximos_laborables(hoy, cuantos)):
        for medico, horas in JORNADAS:
            ocupado = n % len(horas)
            for i, hora in enumerate(horas):
                inicio = datetime.combine(dia, hora, tzinfo=timezone.utc)
                huecos.append((inicio, medico, i != ocupado))
    return huecos


def reiniciar(url: str | None = None, hoy: date | None = None) -> list[tuple[datetime, str, bool]]:
    """Empty appointments and slots and insert the generated agenda."""
    huecos = generar_huecos(hoy or date.today())
    motor = create_engine(url or database_url(), poolclass=NullPool)
    with motor.begin() as con:
        con.execute(text("TRUNCATE citas, huecos RESTART IDENTITY"))
        for inicio, medico, libre in huecos:
            con.execute(
                text("INSERT INTO huecos (inicio, medico, libre) VALUES (:i, :m, :l)"),
                {"i": inicio, "m": medico, "l": libre},
            )
    motor.dispose()
    return huecos


def resumen(huecos: list[tuple[datetime, str, bool]]) -> str:
    lineas = [f"Agenda reiniciada: {len(huecos)} huecos, {sum(h[2] for h in huecos)} libres"]
    for dia in sorted({h[0].date() for h in huecos}):
        partes = []
        for medico, _ in JORNADAS:
            del_dia = [h for h in huecos if h[0].date() == dia and h[1] == medico]
            libres = sum(h[2] for h in del_dia)
            partes.append(f"{medico} {libres}/{len(del_dia)} libres")
        lineas.append(f"  {dia:%a %Y-%m-%d}: " + ", ".join(partes))
    return "\n".join(lineas)


if __name__ == "__main__":
    print(resumen(reiniciar()))
