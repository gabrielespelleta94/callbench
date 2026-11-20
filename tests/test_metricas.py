"""Tests for the per-call metrics recorder and the provider selection (no network).

Run with:  uv run pytest tests/test_metricas.py
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from pipecat.frames.frames import MetricsFrame
from pipecat.metrics.metrics import (
    LLMTokenUsage,
    LLMUsageMetricsData,
    ProcessingMetricsData,
    STTUsage,
    STTUsageMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver

from agent import metricas, proveedores
from agent.metricas import CallMetricsRecorder

STAGES = {"DeepgramSTTService#0": "stt", "GroqLLMService#0": "llm", "DeepgramTTSService#0": "tts"}


def leer(path):
    return [json.loads(linea) for linea in path.read_text(encoding="utf-8").splitlines()]


def grabador(tmp_path, **kw):
    return CallMetricsRecorder(
        call_id="c1", directory=tmp_path, stages=STAGES, clock=lambda: 100.0, **kw
    )


def empujar(rec, *items):
    frame = MetricsFrame(data=list(items))
    asyncio.run(rec.on_push_frame(SimpleNamespace(frame=frame)))


def test_start_line_has_config(tmp_path):
    rec = grabador(tmp_path, config={"stt": {"provider": "deepgram", "model": "nova-3-general"}})
    (linea,) = leer(rec.path)
    assert rec.path == tmp_path / "c1.jsonl"
    assert linea == {
        "call_id": "c1",
        "ts": 100.0,
        "event": "call_start",
        "config": {"stt": {"provider": "deepgram", "model": "nova-3-general"}},
    }


def test_metrics_frame_is_written_by_stage_and_totalled(tmp_path):
    rec = grabador(tmp_path)
    empujar(
        rec,
        TTFBMetricsData(processor="GroqLLMService#0", model="openai/gpt-oss-120b", value=0.3123456),
        TTFBMetricsData(processor="DeepgramTTSService#0", value=0.15),
        TTFBMetricsData(processor="DeepgramTTSService#0", value=0.0),  # no output: ignored
        LLMUsageMetricsData(
            processor="GroqLLMService#0",
            value=LLMTokenUsage(prompt_tokens=900, completion_tokens=40, total_tokens=940,
                                cache_read_input_tokens=512, reasoning_tokens=12),
        ),
        TTSUsageMetricsData(processor="DeepgramTTSService#0", value=84),
        STTUsageMetricsData(processor="DeepgramSTTService#0", value=STTUsage(audio_seconds=3.25)),
        ProcessingMetricsData(processor="X", value=1.0),  # not used: ignored
    )
    empujar(rec, TTSUsageMetricsData(processor="DeepgramTTSService#0", value=16))
    rec.close()
    rec.close()  # idempotent

    eventos = leer(rec.path)
    tipos = [e["event"] for e in eventos]
    assert tipos == ["call_start", "ttfb", "ttfb", "llm_usage", "tts_usage", "stt_usage",
                     "tts_usage", "call_end"]
    assert eventos[1]["stage"] == "llm" and eventos[1]["value"] == 0.3123
    assert eventos[1]["model"] == "openai/gpt-oss-120b"
    assert eventos[2]["stage"] == "tts"
    assert eventos[3]["cached_tokens"] == 512 and eventos[3]["reasoning_tokens"] == 12
    assert eventos[-1]["totals"] == {
        "prompt_tokens": 900, "completion_tokens": 40, "cached_tokens": 512,
        "tts_characters": 100, "tts_text_characters": 0, "stt_audio_seconds": 3.25, "turns": 0,
    }


def test_unknown_processor_is_stage_other(tmp_path):
    rec = grabador(tmp_path)
    empujar(rec, TTFBMetricsData(processor="Otro#0", value=0.2))
    assert leer(rec.path)[-1]["stage"] == "other"


def test_latency_observer_events_are_recorded(tmp_path):
    lat = UserBotLatencyObserver()
    rec = grabador(tmp_path, latency=lat)

    async def disparar():
        await lat._call_event_handler("on_first_bot_speech_latency", 1.5)
        await lat._call_event_handler("on_latency_measured", 0.912345)
        await asyncio.sleep(0.05)  # handlers may run as tasks

    asyncio.run(disparar())
    rec.close()
    eventos = {e["event"]: e for e in leer(rec.path)}
    assert eventos["first_bot_speech"]["seconds"] == 1.5
    assert eventos["voice_to_voice"]["seconds"] == 0.9123
    assert eventos["call_end"]["totals"]["turns"] == 1


def test_metrics_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CALLBENCH_METRICS_DIR", str(tmp_path))
    assert metricas.metrics_dir() == tmp_path
    monkeypatch.delenv("CALLBENCH_METRICS_DIR")
    assert metricas.metrics_dir() == metricas.RAIZ / "metrics"


def test_call_id_from_env_or_unique(monkeypatch):
    monkeypatch.setenv("CALLBENCH_CALL_ID", "trabajo-42")
    assert metricas.new_call_id() == "trabajo-42"
    monkeypatch.delenv("CALLBENCH_CALL_ID")
    a, b = metricas.new_call_id(), metricas.new_call_id()
    assert a != b and a[:8].isdigit()


def test_providers_default_to_deepgram(monkeypatch):
    monkeypatch.delenv("CALLBENCH_STT", raising=False)
    monkeypatch.setenv("CALLBENCH_TTS", " Deepgram ")
    assert proveedores.stt_provider().describe() == {"provider": "deepgram", "model": "nova-3-general"}
    assert proveedores.tts_provider().describe() == {"provider": "deepgram", "model": "aura-2-thalia-en"}


def test_unknown_provider_fails_clearly(monkeypatch):
    monkeypatch.setenv("CALLBENCH_TTS", "elevenlabs")
    with pytest.raises(ValueError, match="CALLBENCH_TTS='elevenlabs'.*deepgram"):
        proveedores.tts_provider()


def test_deepgram_services_build_without_network(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    stt_spec, tts_spec = proveedores.stt_provider(), proveedores.tts_provider()
    stt, tts = stt_spec.build(stt_spec), tts_spec.build(tts_spec)
    assert type(stt).__name__ == "DeepgramSTTService"
    assert type(tts).__name__ == "DeepgramTTSService"


def test_spoken_text_counted_only_from_the_tts(tmp_path):
    from pipecat.frames.frames import TTSTextFrame
    from pipecat.utils.text.base_text_aggregator import TextType

    rec = grabador(tmp_path)
    tts, otro = SimpleNamespace(name="DeepgramTTSService#0"), SimpleNamespace(name="Otro#0")
    frases = [
        (tts, TTSTextFrame("Hello there. ", text_type=TextType.SENTENCE)),
        (tts, TTSTextFrame("Bye", text_type=TextType.WORD)),
        (otro, TTSTextFrame("ignored", text_type=TextType.SENTENCE)),
    ]
    for fuente, frame in frases:
        asyncio.run(rec.on_push_frame(SimpleNamespace(frame=frame, source=fuente)))
    rec.close()
    assert leer(rec.path)[-1]["totals"]["tts_text_characters"] == len("Hello there. ") + 4
