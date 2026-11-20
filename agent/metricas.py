"""Per-call metrics: one JSONL file per call with what Pipecat measures.

Pipecat already emits MetricsFrame (TTFB per service, LLM token usage, characters
sent to the TTS, seconds of audio sent to the STT) and UserBotLatencyObserver measures
voice-to-voice latency. Without an observer all of that only ends up in the log; this
module writes it to `<CALLBENCH_METRICS_DIR>/<call_id>.jsonl`, one event per line:

    {"call_id": ..., "ts": ..., "event": "call_start", "config": {...}}
    {"call_id": ..., "ts": ..., "event": "ttfb", "stage": "llm", "processor": ..., "value": 0.31}
    {"call_id": ..., "ts": ..., "event": "llm_usage", "prompt_tokens": ..., ...}
    {"call_id": ..., "ts": ..., "event": "tts_usage", "characters": 84}
    {"call_id": ..., "ts": ..., "event": "stt_usage", "audio_seconds": 3.2}
    {"call_id": ..., "ts": ..., "event": "voice_to_voice", "seconds": 0.92}
    {"call_id": ..., "ts": ..., "event": "call_end", "totals": {...}}

Pipecat 1.15 does not emit TTS usage for the websocket DeepgramTTSService (only for the
HTTP variant and in token-streaming mode), so the recorder also counts the text the TTS
reports as spoken (TTSTextFrame) and stores it as `tts_text_characters` in `call_end`.
tools/coste.py uses it only when there is no `tts_usage`, and says it is an estimate.

`tools/coste.py` reads these files and prices them with `costes.toml`.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipecat.frames.frames import MetricsFrame, TTSTextFrame
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    STTUsageMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.observers.user_bot_latency_observer import LatencyBreakdown, UserBotLatencyObserver

RAIZ = Path(__file__).resolve().parents[1]


def metrics_dir() -> Path:
    """Directory for the JSONL files: CALLBENCH_METRICS_DIR or metrics/ at the repo root."""
    return Path(os.environ.get("CALLBENCH_METRICS_DIR") or RAIZ / "metrics")


def new_call_id() -> str:
    """CALLBENCH_CALL_ID if a worker set it (one bot per job), else a sortable unique id."""
    fijo = os.environ.get("CALLBENCH_CALL_ID")
    if fijo:
        return fijo
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{marca}-{uuid.uuid4().hex[:8]}"


class CallMetricsRecorder(BaseObserver):
    """Observer that appends every metric of one call to its JSONL file.

    `stages` maps processor names (e.g. "DeepgramSTTService#0") to "stt", "llm" or
    "tts", so that TTFB lines say which stage they belong to without guessing from
    class names. Pass the UserBotLatencyObserver of the same task as `latency` to
    also record voice-to-voice latency.
    """

    def __init__(
        self,
        *,
        call_id: str,
        directory: Path,
        stages: dict[str, str],
        config: dict | None = None,
        latency: UserBotLatencyObserver | None = None,
        clock=time.time,
    ):
        # Each frame only once: a MetricsFrame is pushed again by every processor it crosses
        super().__init__(observe_every_push=False)
        self.call_id = call_id
        self.stages = stages
        self._clock = clock
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{call_id}.jsonl"
        self._totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "tts_characters": 0,
            "tts_text_characters": 0,
            "stt_audio_seconds": 0.0,
            "turns": 0,
        }
        self._closed = False
        self._write("call_start", config=config or {})
        if latency is not None:
            latency.add_event_handler("on_latency_measured", self._on_latency)
            latency.add_event_handler("on_latency_breakdown", self._on_breakdown)
            latency.add_event_handler("on_first_bot_speech_latency", self._on_first_speech)

    def _write(self, event: str, **fields) -> None:
        linea = {"call_id": self.call_id, "ts": round(self._clock(), 3), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if isinstance(frame, MetricsFrame):
            for item in frame.data:
                self.record(item)
        elif isinstance(frame, TTSTextFrame) and self.stages.get(data.source.name) == "tts":
            self.count_spoken_text(frame)

    def count_spoken_text(self, frame: TTSTextFrame) -> None:
        """Characters the TTS spoke. Word-level frames lose the space between words."""
        por_palabra = str(frame.text_type).lower() == "word"
        self._totals["tts_text_characters"] += len(frame.text) + (1 if por_palabra else 0)

    def record(self, item) -> None:
        """Write one MetricsData item. Other metric types (processing time, turn
        analyzer...) are ignored: they do not feed latency per stage or cost."""
        base = {"processor": item.processor, "model": item.model}
        if isinstance(item, TTFBMetricsData):
            # Pipecat reports a 0 TTFB when a measurement is started and stopped
            # without any output (e.g. an interrupted turn): not a real latency
            if item.value > 0:
                stage = self.stages.get(item.processor, "other")
                self._write("ttfb", stage=stage, value=round(item.value, 4), **base)
        elif isinstance(item, LLMUsageMetricsData):
            u = item.value
            cached = u.cache_read_input_tokens or 0
            self._totals["prompt_tokens"] += u.prompt_tokens
            self._totals["completion_tokens"] += u.completion_tokens
            self._totals["cached_tokens"] += cached
            self._write(
                "llm_usage",
                prompt_tokens=u.prompt_tokens,
                completion_tokens=u.completion_tokens,
                cached_tokens=cached,
                reasoning_tokens=u.reasoning_tokens or 0,
                **base,
            )
        elif isinstance(item, TTSUsageMetricsData):
            self._totals["tts_characters"] += item.value
            self._write("tts_usage", characters=item.value, **base)
        elif isinstance(item, STTUsageMetricsData):
            segundos = item.value.audio_seconds
            self._totals["stt_audio_seconds"] += segundos
            self._write("stt_usage", audio_seconds=round(segundos, 3), **base)

    async def _on_latency(self, _observer, seconds: float):
        self._totals["turns"] += 1
        self._write("voice_to_voice", seconds=round(seconds, 4))

    async def _on_first_speech(self, _observer, seconds: float):
        self._write("first_bot_speech", seconds=round(seconds, 4))

    async def _on_breakdown(self, _observer, breakdown: LatencyBreakdown):
        self._write(
            "latency_breakdown",
            measured_from=str(breakdown.measured_from) if breakdown.measured_from else None,
            total_secs=round(breakdown.total_secs, 4),
            parts=[
                {"key": c.key, "owner": c.owner, "secs": round(c.duration_secs, 4)}
                for c in breakdown.contributions
            ],
        )

    def close(self) -> None:
        """Write the call_end line with the totals (idempotent)."""
        if self._closed:
            return
        self._closed = True
        totales = dict(self._totals)
        totales["stt_audio_seconds"] = round(totales["stt_audio_seconds"], 3)
        self._write("call_end", totals=totales)
