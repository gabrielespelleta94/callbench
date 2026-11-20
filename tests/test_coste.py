"""Tests for tools/coste.py: cost per call and percentiles from metrics files (no network).

Run with:  uv run pytest tests/test_coste.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import coste  # noqa: E402

CONFIG = {
    "stt": {"provider": "deepgram", "model": "nova-3-general"},
    "llm": {"provider": "groq", "model": "openai/gpt-oss-120b"},
    "tts": {"provider": "deepgram", "model": "aura-2-thalia-en"},
}
PRECIOS = {
    "moneda": "USD",
    "llm": {"groq": {"openai/gpt-oss-120b": {
        "input_per_million": 0.15, "cached_input_per_million": 0.075, "output_per_million": 0.60}}},
    "stt": {"deepgram": {"nova-3-general": {"per_minute": 0.0048}}},
    "tts": {"deepgram": {"aura-2-thalia-en": {"per_thousand_characters": 0.030}}},
}


def escribir(path: Path, call_id: str, eventos: list[dict], config=CONFIG) -> Path:
    lineas = [{"call_id": call_id, "event": "call_start", "config": config}]
    lineas += [{"call_id": call_id, **e} for e in eventos]
    path.write_text("\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
    return path


def llamada_tipica(tmp_path, nombre="a", v2v=(0.8, 1.0)):
    return escribir(tmp_path / f"{nombre}.jsonl", nombre, [
        {"event": "llm_usage", "prompt_tokens": 1_000_000, "completion_tokens": 100_000, "cached_tokens": 200_000},
        {"event": "tts_usage", "characters": 1500},
        {"event": "stt_usage", "audio_seconds": 90.0},
        *({"event": "voice_to_voice", "seconds": s} for s in v2v),
        {"event": "ttfb", "stage": "llm", "value": 0.3},
        {"event": "ttfb", "stage": "tts", "value": 0.15},
    ])


def test_cost_per_stage(tmp_path):
    c = coste.load_call(llamada_tipica(tmp_path))
    r = coste.call_cost(c, PRECIOS)
    # LLM: 800k uncached x 0.15 + 200k cached x 0.075 + 100k out x 0.60 (per million)
    assert r["llm"] == pytest.approx(0.12 + 0.015 + 0.06)
    assert r["stt"] == pytest.approx(1.5 * 0.0048)
    assert r["tts"] == pytest.approx(1.5 * 0.030)
    assert r["total"] == pytest.approx(r["llm"] + r["stt"] + r["tts"])


def test_unused_stage_needs_no_price(tmp_path):
    # Text-mode eval: no STT/TTS usage, so a missing TTS price does not matter
    f = escribir(tmp_path / "t.jsonl", "t", [
        {"event": "llm_usage", "prompt_tokens": 1000, "completion_tokens": 10},
    ], config={**CONFIG, "tts": {"provider": "elevenlabs", "model": "x"}})
    r = coste.call_cost(coste.load_call(f), PRECIOS)
    assert r["tts"] == 0 and r["stt"] == 0 and r["total"] > 0


def test_pending_price_is_refused(tmp_path):
    precios = {**PRECIOS, "tts": {"deepgram": {"aura-2-thalia-en": {"pendiente": True}}}}
    c = coste.load_call(llamada_tipica(tmp_path))
    with pytest.raises(coste.PriceMissing, match="tts deepgram/aura-2-thalia-en"):
        coste.call_cost(c, precios)


def test_truncated_last_line_is_skipped(tmp_path, capsys):
    f = llamada_tipica(tmp_path)
    with f.open("a", encoding="utf-8") as h:
        h.write('{"call_id": "a", "event": "tts_us')
    c = coste.load_call(f)
    assert c.tts_characters == 1500
    assert "no es JSON" in capsys.readouterr().err


def test_percentile_linear():
    assert coste.percentile([], 50) is None
    assert coste.percentile([3.0], 95) == 3.0
    assert coste.percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert coste.percentile(list(range(1, 101)), 95) == pytest.approx(95.05)


def test_summary_pools_turns_and_reports_unpriced(tmp_path):
    llamada_tipica(tmp_path, "a", v2v=(0.8, 1.0))
    llamada_tipica(tmp_path, "b", v2v=(1.2,))
    escribir(tmp_path / "c.jsonl", "c", [{"event": "tts_usage", "characters": 10}],
             config={**CONFIG, "tts": {"provider": "deepgram", "model": "otra-voz"}})
    llamadas = [coste.load_call(f) for f in coste.find_files([str(tmp_path)])]
    r = coste.summarize(llamadas, PRECIOS)
    assert r["cost_per_call"]["n"] == 2
    assert r["voice_to_voice"] == {"n": 3, "p50": 1.0, "p95": pytest.approx(1.18)}
    assert r["ttfb"]["llm"]["n"] == 2 and r["ttfb"]["stt"]["n"] == 0
    assert [u["call_id"] for u in r["unpriced"]] == ["c"]


def test_cli_reads_real_costes_toml(tmp_path, capsys):
    llamada_tipica(tmp_path)
    assert coste.main([str(tmp_path)]) == 0
    salida = capsys.readouterr().out
    assert "Coste por llamada" in salida and "USD" in salida
    assert coste.main([str(tmp_path / "vacio")]) == 1


def test_costes_toml_entries_have_source_and_date():
    precios = coste.load_prices(coste.RAIZ / "costes.toml")
    for tipo in ("llm", "stt", "tts"):
        for proveedor, modelos in precios[tipo].items():
            for modelo, e in modelos.items():
                assert e.get("fuente", "").startswith("https://"), (tipo, proveedor, modelo)
                assert "fecha" in e, (tipo, proveedor, modelo)


def test_spoken_text_is_fallback_for_missing_tts_usage(tmp_path):
    f = escribir(tmp_path / "e.jsonl", "e", [
        {"event": "call_end", "totals": {"tts_text_characters": 2000}},
    ])
    c = coste.load_call(f)
    assert c.tts_characters == 2000 and c.tts_characters_estimated
    assert coste.call_cost(c, PRECIOS)["tts"] == pytest.approx(2 * 0.030)
    # Real usage wins over the estimate
    g = escribir(tmp_path / "g.jsonl", "g", [
        {"event": "tts_usage", "characters": 10},
        {"event": "call_end", "totals": {"tts_text_characters": 2000}},
    ])
    c = coste.load_call(g)
    assert c.tts_characters == 10 and not c.tts_characters_estimated
