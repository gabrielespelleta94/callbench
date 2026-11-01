"""The agenda generator is pure: no database needed."""

from datetime import date

from app.db.reiniciar import generar_huecos, proximos_laborables


def test_proximos_laborables_saltan_el_fin_de_semana():
    # Friday 2026-10-30 -> Mon 2 .. Fri 6 November
    dias = proximos_laborables(date(2026, 10, 30))
    assert dias == [date(2026, 11, d) for d in (2, 3, 4, 5, 6)]
    # From a Sunday the first day is the next Monday
    assert proximos_laborables(date(2026, 11, 1))[0] == date(2026, 11, 2)


def test_generar_huecos_relativos_a_la_fecha():
    huecos = generar_huecos(date(2026, 11, 1))
    fechas = {h[0].date() for h in huecos}
    assert len(fechas) == 5
    assert all(f > date(2026, 11, 1) and f.weekday() < 5 for f in fechas)
    assert {h[1] for h in huecos} == {"Dr. Lopez", "Dr. Ruiz"}
    for dia in fechas:
        for medico in ("Dr. Lopez", "Dr. Ruiz"):
            del_dia = [h for h in huecos if h[0].date() == dia and h[1] == medico]
            assert 3 <= len(del_dia) <= 4
            assert any(not h[2] for h in del_dia) and any(h[2] for h in del_dia)
