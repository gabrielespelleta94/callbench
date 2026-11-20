"""Scorecard API (app/resultados.py) and the round importer (tools/importar_vuelta.py)
against the real test database.

Run with:  uv run pytest tests/test_resultados_api.py
"""

import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

import importar_vuelta  # noqa: E402

VUELTA = RAIZ / "tests" / "fixtures" / "vuelta_ejemplo"
CITA = "cita_dr_lopez/reserva_real"
DUDA = "duda_y_pide_pensarlo/no_reservar_sin_confirmar"
MEDICO = "medico_inexistente/dr_fernando"


@pytest.fixture
def motor(url_test):
    m = create_engine(url_test, poolclass=NullPool)
    with m.begin() as con:
        con.execute(text("TRUNCATE llamadas, trabajos, vueltas, versiones RESTART IDENTITY"))
    yield m
    m.dispose()


@pytest.fixture
def rondas(motor):
    """Two copies of the example round (ids 1 and 2)."""
    a = importar_vuelta.importar(motor, VUELTA, "ejemplo", "v-ejemplo", git_sha="abc123", config={"stt": "x"})
    b = importar_vuelta.importar(motor, VUELTA, "ejemplo-b", "v-ejemplo-b")
    return a, b


def _insertar_vuelta_con_reintento(motor, nombre="reintento") -> int:
    """A round of one scenario with 3 jobs; job 1 ran twice (infra, then approved)."""
    with motor.begin() as con:
        version = con.execute(
            text("INSERT INTO versiones (etiqueta, git_sha) VALUES ('v-r', 'sha') RETURNING id")
        ).scalar_one()
        vuelta = con.execute(
            text(
                "INSERT INTO vueltas (nombre, version_id, escenarios, repeticiones) "
                "VALUES (:n, :v, CAST('[\"x\"]' AS jsonb), 3) RETURNING id"
            ),
            {"n": nombre, "v": version},
        ).scalar_one()
        for intento in (1, 2, 3):
            trabajo = con.execute(
                text(
                    "INSERT INTO trabajos (vuelta_id, escenario, intento, estado, intentos) "
                    "VALUES (:v, 'x/y', :i, 'hecho', 1) RETURNING id"
                ),
                {"v": vuelta, "i": intento},
            ).scalar_one()
            ejecuciones = [(1, "infra"), (2, "aprobado")] if intento == 1 else [(1, "aprobado")]
            for ejecucion, veredicto in ejecuciones:
                con.execute(
                    text(
                        "INSERT INTO llamadas (trabajo_id, vuelta_id, escenario, intento, ejecucion, "
                        "veredicto, resultado) VALUES (:t, :v, 'x/y', :i, :e, :ver, CAST('{}' AS jsonb))"
                    ),
                    {"t": trabajo, "v": vuelta, "i": intento, "e": ejecucion, "ver": veredicto},
                )
    return vuelta


# ---------------------------------------------------------------- list


def test_listar_vacio(cliente, motor):
    r = cliente.get("/vueltas")
    assert r.status_code == 200
    assert r.json() == []


def test_listar_vueltas_con_totales(cliente, rondas):
    r = cliente.get("/vueltas")
    assert r.status_code == 200
    datos = r.json()
    assert [v["nombre"] for v in datos] == ["ejemplo-b", "ejemplo"]  # newest first
    v = next(v for v in datos if v["nombre"] == "ejemplo")
    assert v["id"] == rondas[0]
    assert v["repeticiones"] == 3
    assert v["modalidad"] == "texto"
    assert v["escenarios"] == ["cita_dr_lopez", "duda_y_pide_pensarlo", "medico_inexistente"]
    assert v["version"]["etiqueta"] == "v-ejemplo"
    assert v["version"]["git_sha"] == "abc123"
    assert v["version"]["config"] == {"stt": "x"}
    t = v["total"]
    assert (t["aprobado"], t["suspenso"], t["infra"], t["n"]) == (2, 3, 1, 5)
    assert v["juez_vs_asserts"] == {"juez_ok": 4, "asserts_ok": 2, "evaluadas": 5, "discrepa": 2}


# ---------------------------------------------------------------- detail


def test_ver_vuelta_llamadas(cliente, rondas):
    r = cliente.get(f"/vueltas/{rondas[0]}")
    assert r.status_code == 200
    datos = r.json()
    assert datos["vuelta"]["nombre"] == "ejemplo"
    assert len(datos["llamadas"]) == 6
    assert datos["resumen"]["total"]["n"] == 5
    # sorted by scenario and attempt
    claves = [(ll["escenario"], ll["intento"]) for ll in datos["llamadas"]]
    assert claves == sorted(claves)

    por = {(ll["escenario"], ll["intento"]): ll for ll in datos["llamadas"]}
    assert por[(CITA, 1)]["veredicto"] == "suspenso"
    assert por[(CITA, 1)]["juez"]["veredicto"] == "aprobado"
    assert por[(CITA, 1)]["asserts"]["veredicto"] == "suspenso"
    assert por[(CITA, 2)]["veredicto"] == "aprobado"
    assert por[(CITA, 3)]["veredicto"] == "infra"
    assert por[(DUDA, 1)]["veredicto"] == "aprobado"
    assert por[(DUDA, 2)]["veredicto"] == "suspenso"
    assert por[(MEDICO, 1)]["veredicto"] == "suspenso"


def test_llamada_tiene_transcripcion_con_resultado_de_herramientas(cliente, rondas):
    llamadas = cliente.get(f"/vueltas/{rondas[0]}").json()["llamadas"]
    ll = next(x for x in llamadas if x["escenario"] == CITA and x["intento"] == 2)
    assert isinstance(ll["transcripcion"], list) and ll["transcripcion"]
    herramientas = [m for m in ll["transcripcion"] if m["role"] == "tool_call"]
    assert herramientas
    assert all("resultado" in m for m in herramientas)
    consulta = next(m for m in herramientas if m["name"] == "consultar_huecos")
    assert consulta["resultado"]["ok"] is True
    assert consulta["resultado"]["huecos"]


def test_llamada_tiene_listas_de_juez_y_asserts(cliente, rondas):
    llamadas = cliente.get(f"/vueltas/{rondas[0]}").json()["llamadas"]
    ll = next(x for x in llamadas if x["escenario"] == CITA and x["intento"] == 1)
    assert ll["juez"]["confianza"] == pytest.approx(0.98)
    assert ll["juez"]["motivo"]
    lista = ll["asserts"]["lista"]
    assert isinstance(lista, list) and lista
    assert {"nombre", "aprobado", "motivo"} <= set(lista[0])
    fallidos = [a["nombre"] for a in lista if a["aprobado"] is False]
    assert "confirmacion_antes_de_reservar" in fallidos
    assert ll["causa"].startswith("asserts: ")


def test_vuelta_inexistente_404(cliente, motor):
    r = cliente.get("/vueltas/999")
    assert r.status_code == 404
    assert "999" in r.json()["detail"]


# ---------------------------------------------------------------- diff


def test_diff_de_vueltas_identicas_codigo_0(cliente, rondas):
    r = cliente.get("/diff", params={"base": rondas[0], "candidata": rondas[1]})
    assert r.status_code == 200
    d = r.json()
    assert d["veredicto"]["codigo"] == 0
    assert d["base"]["nombre"] == "ejemplo" and d["candidata"]["nombre"] == "ejemplo-b"
    assert {f["escenario"] for f in d["escenarios"]} == {CITA, DUDA, MEDICO}
    assert all(f["estado"] == "igual" for f in d["escenarios"])
    assert d["total"]["base"]["n"] == d["total"]["candidata"]["n"] == 5


def test_diff_vuelta_inexistente_404(cliente, rondas):
    assert cliente.get("/diff", params={"base": rondas[0], "candidata": 999}).status_code == 404
    assert cliente.get("/diff", params={"base": 999, "candidata": rondas[0]}).status_code == 404


def test_diff_pide_ambos_parametros(cliente, rondas):
    assert cliente.get("/diff", params={"base": rondas[0]}).status_code == 422


def test_diff_candidata_con_escenarios_de_menos_no_concluyente(cliente, rondas, motor):
    # a candidate round with only one of the base's scenarios
    candidata = _insertar_vuelta_con_reintento(motor)
    d = cliente.get("/diff", params={"base": rondas[0], "candidata": candidata}).json()
    estados = {f["escenario"]: f["estado"] for f in d["escenarios"]}
    assert estados[CITA] == "no_concluyente"
    assert estados["x/y"] == "nuevo"
    assert d["veredicto"]["codigo"] == 2


# ---------------------------------------------------------------- retried jobs


def test_solo_cuenta_la_ultima_ejecucion(cliente, motor):
    vid = _insertar_vuelta_con_reintento(motor)
    datos = cliente.get(f"/vueltas/{vid}").json()
    assert len(datos["llamadas"]) == 3  # 4 rows, 3 jobs
    t = datos["resumen"]["total"]
    assert t["aprobado"] == 3 and t["infra"] == 0 and t["suspenso"] == 0
    reintentada = next(ll for ll in datos["llamadas"] if ll["intento"] == 1)
    assert reintentada["ejecucion"] == 2
    assert reintentada["veredicto"] == "aprobado"
    # no asserts stored and no job directory on disk: reported as not evaluated
    assert reintentada["asserts"]["veredicto"] == "n/a"
    assert reintentada["transcripcion"] is None


def test_reintento_en_el_listado(cliente, motor):
    _insertar_vuelta_con_reintento(motor)
    (v,) = cliente.get("/vueltas").json()
    assert (v["total"]["aprobado"], v["total"]["infra"]) == (3, 0)


# ---------------------------------------------------------------- importer


def test_importar_dos_veces_sin_reemplazar_falla(motor):
    importar_vuelta.importar(motor, VUELTA, "dup", "e")
    with pytest.raises(SystemExit) as e:
        importar_vuelta.importar(motor, VUELTA, "dup", "e")
    assert "--reemplazar" in str(e.value)
    with motor.connect() as con:
        assert con.execute(text("SELECT count(*) FROM vueltas WHERE nombre = 'dup'")).scalar_one() == 1


def test_importar_con_reemplazar_sustituye(motor):
    primera = importar_vuelta.importar(motor, VUELTA, "dup", "e")
    segunda = importar_vuelta.importar(motor, VUELTA, "dup", "e2", reemplazar=True)
    assert segunda != primera
    with motor.connect() as con:
        assert con.execute(text("SELECT count(*) FROM vueltas")).scalar_one() == 1
        assert con.execute(text("SELECT count(*) FROM trabajos")).scalar_one() == 6
        assert con.execute(text("SELECT count(*) FROM llamadas")).scalar_one() == 6
        assert con.execute(text("SELECT count(*) FROM llamadas WHERE vuelta_id = :v"), {"v": primera}).scalar_one() == 0


def test_importar_estados_de_trabajo_y_llamada(motor):
    vid = importar_vuelta.importar(motor, VUELTA, "estados", "e")
    with motor.connect() as con:
        estados = dict(
            con.execute(
                text("SELECT intento || escenario, estado FROM trabajos WHERE vuelta_id = :v"), {"v": vid}
            ).all()
        )
        assert estados["3" + CITA] == "fallido"
        assert estados["1" + CITA] == "hecho"
        fila = con.execute(
            text("SELECT veredicto, aprobado_juez, aprobado_asserts, ejecucion FROM llamadas "
                 "WHERE vuelta_id = :v AND escenario = :e AND intento = 1"),
            {"v": vid, "e": CITA},
        ).one()
        assert tuple(fila) == ("aprobado", True, False, 1)  # judge ok, asserts failed


def test_importar_ignora_intentos_repetidos(motor, tmp_path):
    ronda = tmp_path / "repetida"
    ronda.mkdir()
    filas = [json.loads(linea) for linea in (VUELTA / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    # same scenario/attempt twice (a reused round name appends): the first one is kept
    (ronda / "results.jsonl").write_text(
        "\n".join(json.dumps(f) for f in [filas[0], filas[0]]) + "\n", encoding="utf-8"
    )
    # the call logs are looked up under the round directory
    import shutil

    shutil.copytree(VUELTA / "logs", ronda / "logs")
    vid = importar_vuelta.importar(motor, ronda, "repetida", "e")
    with motor.connect() as con:
        assert con.execute(text("SELECT count(*) FROM llamadas WHERE vuelta_id = :v"), {"v": vid}).scalar_one() == 1


def test_main_sin_results_jsonl_sale_1(tmp_path, capsys):
    assert importar_vuelta.main([str(tmp_path)]) == 1
    assert "No hay results.jsonl" in capsys.readouterr().err
