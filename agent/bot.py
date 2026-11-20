"""Agent under test: the voice receptionist of a fictional clinic.

Phase 0 of CallBench. Pipecat pipeline: browser audio -> STT (Deepgram)
-> LLM (Groq) -> TTS (Deepgram) -> audio back to the browser. STT and TTS are
chosen with CALLBENCH_STT / CALLBENCH_TTS (agent/proveedores.py) and every call
writes its metrics to a JSONL file (agent/metricas.py). To start:

    uv run agent/bot.py      then open http://localhost:7860
"""

import os
from datetime import date

from dotenv import load_dotenv
from loguru import logger

from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.evals.transport import EvalTransportParams
from pipecat.runner.utils import create_transport
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams

from agent.herramientas import registrar_herramientas
from agent.metricas import CallMetricsRecorder, metrics_dir, new_call_id
from agent.proveedores import stt_provider, tts_provider

load_dotenv(override=True)

def construir_prompt() -> str:
    # The date is computed at startup so that "tomorrow" or "on Monday" make sense
    hoy = date.today().strftime("%A, %B %d, %Y")
    return (
        "You are Ana, the receptionist of Sunrise Family Clinic. "
        "You help callers book appointments. "
        f"Today is {hoy}. "
        "As soon as the caller wants an appointment, call consultar_huecos before asking for their name. "
        "If the caller gives no date, call consultar_huecos without a date (never use today's date "
        "as a filter) and offer the first one or two slots it returns. "
        "Only name doctors, days and times returned by consultar_huecos; never invent any. "
        "If the doctor the caller asks for is not in the results, say so and offer the doctors "
        "that consultar_huecos returns without a doctor filter. "
        "Ask for the caller's full name only once they have chosen a slot. "
        "Booking takes two turns, never one. First turn: say the doctor, day, time and name "
        "back to the caller and ask 'Shall I book it?', then stop and wait. Second turn: only "
        "if the caller's reply is a clear yes, call reservar_cita with confirmado_por_paciente "
        "true and their exact words in frase_del_paciente. A yes given earlier in the call, "
        "before you read the booking back, does not count. If they hesitate or ask to think, "
        "do not book. If reservar_cita returns confirmacion_requerida, read the booking back "
        "and ask. "
        "Never confirm an appointment unless reservar_cita returned ok. "
        "If a tool reports an error, say so simply and offer an alternative. "
        "Say times naturally, like 'ten thirty in the morning' or 'Tuesday at three'. "
        "Your words are converted to speech: answer in one or two short sentences, "
        "no lists, no emojis."
    )


LLM_MODEL = "openai/gpt-oss-120b"


async def run_bot(transport: BaseTransport):
    stt_spec, tts_spec = stt_provider(), tts_provider()
    stt = stt_spec.build(stt_spec)
    llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        # Reasoning model: with "low" it thinks little before speaking (less latency)
        settings=GroqLLMService.Settings(model=LLM_MODEL, reasoning_effort="low"),
    )
    tts = tts_spec.build(tts_spec)

    # Register the clinic tools and pass them to the context
    tools = registrar_herramientas(llm)
    context = LLMContext([{"role": "system", "content": construir_prompt()}], tools=tools)
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline([
        transport.input(),        # browser audio
        stt,                      # audio -> text
        aggregators.user(),       # collects the user's turn into the context
        llm,                      # context -> text (streaming)
        tts,                      # text -> audio
        transport.output(),       # audio back to the browser
        aggregators.assistant(),  # stores what the agent said
    ])

    # Metrics: TTFB per service + usage (tokens, TTS characters, STT audio seconds),
    # voice-to-voice latency, all written to one JSONL file per call
    latency = UserBotLatencyObserver()
    recorder = CallMetricsRecorder(
        call_id=new_call_id(),
        directory=metrics_dir(),
        stages={stt.name: "stt", llm.name: "llm", tts.name: "tts"},
        config={
            "stt": stt_spec.describe(),
            "llm": {"provider": "groq", "model": LLM_MODEL},
            "tts": tts_spec.describe(),
        },
        latency=latency,
    )
    logger.info(f"Métricas de la llamada en {recorder.path}")
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[latency, recorder],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Llamada conectada")
        context.add_message({"role": "user", "content": "Greet the caller."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Llamada colgada")
        await task.cancel()

    try:
        await PipelineRunner(handle_sigint=False).run(task)
    finally:
        recorder.close()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(
        runner_args,
        {
            "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
            # Evals (pipecat.evals): they connect over websocket at /ws using the RTVI protocol
            "eval": lambda: EvalTransportParams(audio_in_enabled=True, audio_out_enabled=True),
        },
    )
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
