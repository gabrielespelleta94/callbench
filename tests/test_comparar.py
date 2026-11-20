"""Unit tests of bench/resultados.py (Wilson, summary, regression rule) and of the CLI
gate tools/comparar.py. No database except the one "unknown round" case.

Run with:  uv run pytest tests/test_comparar.py
"""

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

import comparar  # noqa: E402
from bench import resultados as res  # noqa: E402

VUELTA = RAIZ / "tests" / "fixtures" / "vuelta_ejemplo"
ESC = "a/b"


# ---------------------------------------------------------------- helpers


def llamada(escenario=ESC, veredicto="aprobado", juez=None, asserts=None, v2v=None):
    """Minimal call dict in the shape resumir/comparar use."""
    juez = juez or ("infra" if veredicto == "infra" else veredicto)
    asserts = asserts or ("n/a" if veredicto == "infra" else veredicto)
    metricas = None
    if v2v is not None:
        metricas = {"voice_to_voice": v2v, "ttfb": {"stt": [], "llm": [], "tts": []}, "coste": None}
    return {
        "escenario": escenario,
        "veredicto": veredicto,
        "juez": {"veredicto": juez},
        "asserts": {"veredicto": asserts, "lista": []},
        "metricas": metricas,
    }


def llamadas(escenario=ESC, ok=0, ko=0, infra=0, v2v=None):
    out = [llamada(escenario, "aprobado", v2v=v2v) for _ in range(ok)]
    out += [llamada(escenario, "suspenso", v2v=v2v) for _ in range(ko)]
    out += [llamada(escenario, "infra") for _ in range(infra)]
    return out


def estado(base, cand):
    d = res.comparar(res.resumir(base), res.resumir(cand))
    return d["escenarios"][0]["estado"], d


# ---------------------------------------------------------------- wilson


@pytest.mark.parametrize(
    "k,n,lo,hi",
    [
        (0, 3, 0.0, 0.5615),  # hi = z^2 / (n + z^2)
        (3, 3, 0.4385, 1.0),
        (7, 10, 0.3968, 0.8923),
        (5, 10, 0.2366, 0.7634),
    ],
)
def test_wilson_valores_conocidos(k, n, lo, hi):
    got_lo, got_hi = res.wilson(k, n)
    assert got_lo == pytest.approx(lo, abs=1e-3)
    assert got_hi == pytest.approx(hi, abs=1e-3)


def test_wilson_n_cero_es_none():
    assert res.wilson(0, 0) is None


@pytest.mark.parametrize("n", range(1, 25))
def test_wilson_dentro_de_0_1(n):
    for k in range(n + 1):
        lo, hi = res.wilson(k, n)
        eps = 1e-9  # float rounding: hi can land at 0.9999999999999999 when k == n
        assert -eps <= lo <= k / n + eps and k / n - eps <= hi <= 1.0 + eps


# ---------------------------------------------------------------- regression rule


def test_perder_una_llamada_nunca_es_regresion():
    est, d = estado(llamadas(ok=3), llamadas(ok=2, ko=1))
    assert est == "igual"
    assert d["veredicto"]["codigo"] == 0


def test_3_de_3_a_0_de_3_empeora():
    est, d = estado(llamadas(ok=3), llamadas(ko=3))
    assert est == "empeora"
    assert d["veredicto"]["codigo"] == 1
    assert "IC95" in d["escenarios"][0]["motivo"]


def test_10_de_10_a_8_de_10_empeora():
    est, d = estado(llamadas(ok=10), llamadas(ok=8, ko=2))
    assert est == "empeora"
    assert d["veredicto"]["codigo"] == 1


def test_9_de_10_a_8_de_10_igual():
    est, d = estado(llamadas(ok=9, ko=1), llamadas(ok=8, ko=2))
    assert est == "igual"
    assert d["veredicto"]["codigo"] == 0


def test_regla_n_10_sin_ic_por_debajo():
    # 5/10 -> 3/10: the interval of 3/10 still contains 50 %, only the N>=10 rule flags it
    est, d = estado(llamadas(ok=5, ko=5), llamadas(ok=3, ko=7))
    assert est == "empeora"
    assert "IC95" not in d["escenarios"][0]["motivo"]


def test_regla_n_10_no_aplica_con_candidata_pequena():
    est, _ = estado(llamadas(ok=5, ko=5), llamadas(ok=2, ko=6))
    assert est == "igual"


def test_escenario_ausente_en_candidata_no_concluyente_codigo_2():
    base = llamadas("a/b", ok=3) + llamadas("c/d", ok=3)
    cand = llamadas("a/b", ok=3)
    d = res.comparar(res.resumir(base), res.resumir(cand))
    estados = {f["escenario"]: f["estado"] for f in d["escenarios"]}
    assert estados == {"a/b": "igual", "c/d": "no_concluyente"}
    assert d["veredicto"]["codigo"] == 2


def test_mas_infra_que_validas_no_concluyente():
    est, d = estado(llamadas(ok=3), llamadas(ok=1, infra=2))
    assert est == "no_concluyente"
    assert d["veredicto"]["codigo"] == 2


def test_infra_igual_a_validas_no_basta():
    est, _ = estado(llamadas(ok=3), llamadas(ok=2, infra=2))
    assert est == "igual"


def test_candidata_sin_validas_no_concluyente():
    est, d = estado(llamadas(ok=3), llamadas(infra=3))
    assert est == "no_concluyente"
    assert d["veredicto"]["codigo"] == 2


def test_base_sin_validas_no_concluyente():
    est, _ = estado(llamadas(infra=2), llamadas(ok=3))
    assert est == "no_concluyente"


def test_escenario_solo_en_candidata_es_nuevo_y_no_cambia_codigo():
    base = llamadas("a/b", ok=3)
    cand = llamadas("a/b", ok=3) + llamadas("n/n", ko=3)
    d = res.comparar(res.resumir(base), res.resumir(cand))
    estados = {f["escenario"]: f["estado"] for f in d["escenarios"]}
    assert estados["n/n"] == "nuevo"
    assert d["veredicto"]["codigo"] == 0


def test_0_de_3_a_3_de_3_mejora():
    est, d = estado(llamadas(ko=3), llamadas(ok=3))
    assert est == "mejora"
    assert d["veredicto"]["codigo"] == 0


def test_codigo_1_gana_a_2():
    base = llamadas("a/b", ok=3) + llamadas("c/d", ok=3)
    cand = llamadas("a/b", ko=3)  # a/b worse, c/d missing
    d = res.comparar(res.resumir(base), res.resumir(cand))
    estados = {f["escenario"]: f["estado"] for f in d["escenarios"]}
    assert estados == {"a/b": "empeora", "c/d": "no_concluyente"}
    assert d["veredicto"]["codigo"] == 1
    assert d["veredicto"]["dudas"]


def test_candidata_vacia_no_concluyente():
    d = res.comparar(res.resumir(llamadas(ok=3)), res.resumir([]))
    assert d["veredicto"]["codigo"] == 2


# ---------------------------------------------------------------- latency rule


def lat(base_v2v, cand_v2v):
    # the turns live in one call per side, so N of turns is exactly len(v2v)
    base = llamadas(ok=2) + llamadas(ok=1, v2v=base_v2v)
    cand = llamadas(ok=2) + llamadas(ok=1, v2v=cand_v2v)
    return res.comparar(res.resumir(base), res.resumir(cand))


def test_p95_sube_30_por_ciento_empeora():
    d = lat([1.0] * 5, [1.3] * 5)
    v = d["latencia"]["voice_to_voice"]
    assert v["medible"] and v["empeora"]
    assert d["veredicto"]["codigo"] == 1
    assert any("p95" in m for m in d["veredicto"]["motivos"])


def test_p95_sube_15_por_ciento_no_empeora():
    d = lat([1.0] * 5, [1.15] * 5)
    v = d["latencia"]["voice_to_voice"]
    assert v["medible"] and not v["empeora"]
    assert d["veredicto"]["codigo"] == 0


def test_menos_de_5_turnos_no_es_medible():
    d = lat([1.0] * 4, [3.0] * 4)
    v = d["latencia"]["voice_to_voice"]
    assert not v["medible"] and not v["empeora"]
    assert d["veredicto"]["codigo"] == 0


def test_un_solo_lado_sin_turnos_suficientes_no_es_medible():
    d = lat([1.0] * 5, [3.0] * 4)
    assert not d["latencia"]["voice_to_voice"]["medible"]


def test_latencia_baja_no_empeora():
    d = lat([1.0] * 5, [0.5] * 5)
    assert not d["latencia"]["voice_to_voice"]["empeora"]


# ---------------------------------------------------------------- resumir: judge vs asserts


def test_juez_aprobado_asserts_suspenso_discrepa():
    ll = [llamada(veredicto="suspenso", juez="aprobado", asserts="suspenso")]
    r = res.resumir(ll)
    t = r["total"]
    assert t["suspenso"] == 1 and t["aprobado"] == 0
    assert t["discrepa"] == 1
    assert t["juez_ok"] == 1 and t["asserts_ok"] == 0 and t["evaluadas"] == 1
    assert r["escenarios"][0]["discrepa"] == 1


def test_infra_no_cuenta_en_evaluadas():
    ll = [llamada(veredicto="infra"), llamada(veredicto="aprobado")]
    # even if asserts were computed for the infra call, it must not be evaluated
    ll[0]["asserts"]["veredicto"] = "aprobado"
    t = res.resumir(ll)["total"]
    assert t["infra"] == 1
    assert t["evaluadas"] == 1
    assert t["n"] == 1  # valid calls only
    assert t["juez_ok"] == 1


def test_asserts_na_no_cuenta_en_evaluadas():
    t = res.resumir([llamada(juez="aprobado", asserts="n/a", veredicto="aprobado")])["total"]
    assert t["evaluadas"] == 0 and t["juez_ok"] == 1


def test_resumen_tasa_e_intervalo():
    r = res.resumir(llamadas(ok=3, ko=1))
    e = r["escenarios"][0]
    assert e["n"] == 4 and e["tasa"] == 0.75
    assert e["ic"] == pytest.approx(list(res.wilson(3, 4)))


def test_resumen_sin_validas_tasa_none():
    e = res.resumir(llamadas(infra=2))["escenarios"][0]
    assert e["n"] == 0 and e["tasa"] is None and e["ic"] is None


def test_latencia_de_infra_no_cuenta():
    ll = [llamada(veredicto="infra"), llamada(veredicto="aprobado", v2v=[1.0, 2.0])]
    ll[0]["metricas"] = {"voice_to_voice": [99.0], "ttfb": {"stt": [], "llm": [], "tts": []}, "coste": None}
    r = res.resumir(ll)
    assert r["latencia"]["voice_to_voice"]["n"] == 2


# ---------------------------------------------------------------- CLI


def test_cli_resumen_imprime_json(capsys):
    assert comparar.main(["--resumen", str(VUELTA)]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["total"]["aprobado"] == 2
    assert datos["total"]["infra"] == 1
    assert len(datos["escenarios"]) == 3


def test_cli_vuelta_contra_si_misma_sale_0(capsys):
    assert comparar.main([str(VUELTA), str(VUELTA)]) == 0
    out = capsys.readouterr().out
    assert "Sin regresiones" in out


def test_cli_json_de_diff(capsys):
    assert comparar.main([str(VUELTA), str(VUELTA), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["veredicto"]["codigo"] == 0


def _escribir(ruta: Path, llamadas_):
    ruta.write_text(res.a_json(res.resumir(llamadas_)), encoding="utf-8")
    return str(ruta)


def test_cli_dos_json_empeora_sale_1(tmp_path, capsys):
    base = _escribir(tmp_path / "base.json", llamadas(ok=3))
    cand = _escribir(tmp_path / "cand.json", llamadas(ko=3))
    assert comparar.main([base, cand]) == 1
    assert "PEOR" in capsys.readouterr().out


def test_cli_dos_json_no_concluyente_sale_2(tmp_path, capsys):
    base = _escribir(tmp_path / "base.json", llamadas("a/b", ok=3) + llamadas("c/d", ok=3))
    cand = _escribir(tmp_path / "cand.json", llamadas("a/b", ok=3))
    assert comparar.main([base, cand]) == 2


def test_cli_numero_de_vueltas_incorrecto():
    with pytest.raises(SystemExit) as e:
        comparar.main(["una_sola"])
    assert e.value.code == 2


def test_cli_vuelta_inexistente_sale_2(url_test, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", url_test)
    assert comparar.main(["--resumen", "no_existe_esta_vuelta_zzz"]) == 2
    assert "No existe la vuelta" in capsys.readouterr().err
