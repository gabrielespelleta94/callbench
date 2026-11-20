"""Speech providers chosen by environment variable.

    CALLBENCH_STT=deepgram     (default)
    CALLBENCH_TTS=deepgram     (default)

Each provider is a small spec: the model/voice it uses (written into the metrics file
so every call says which combination produced it) and a factory that builds the
Pipecat service. Adding ElevenLabs later means adding one entry per table and the
`elevenlabs` extra of pipecat-ai; bot.py does not change.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    model: str  # model (STT) or voice (TTS); priced in costes.toml under [stt.<name>] / [tts.<name>]
    build: Callable[["Provider"], object]

    def describe(self) -> dict:
        return {"provider": self.name, "model": self.model}


def _deepgram_stt(p: Provider):
    from pipecat.services.deepgram.stt import DeepgramSTTService

    return DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramSTTService.Settings(model=p.model),
    )


def _deepgram_tts(p: Provider):
    from pipecat.services.deepgram.tts import DeepgramTTSService

    return DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramTTSService.Settings(voice=p.model),
    )


STT_PROVIDERS = {
    "deepgram": Provider("deepgram", "nova-3-general", _deepgram_stt),
    # "elevenlabs": Provider("elevenlabs", "scribe_v2_realtime", _elevenlabs_stt),  # phase D
}

TTS_PROVIDERS = {
    "deepgram": Provider("deepgram", "aura-2-thalia-en", _deepgram_tts),
    # "elevenlabs": Provider("elevenlabs", "<flash model + voice>", _elevenlabs_tts),  # phase D
}


def _choose(table: dict[str, Provider], var: str) -> Provider:
    name = (os.environ.get(var) or "deepgram").strip().lower()
    if name not in table:
        raise ValueError(f"{var}={name!r} is not supported; options: {', '.join(sorted(table))}")
    return table[name]


def stt_provider() -> Provider:
    return _choose(STT_PROVIDERS, "CALLBENCH_STT")


def tts_provider() -> Provider:
    return _choose(TTS_PROVIDERS, "CALLBENCH_TTS")
