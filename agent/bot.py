"""Agent under test: the voice receptionist of a fictional clinic.

Phase 0 of CallBench. Pipecat pipeline: browser audio -> STT (Deepgram)
-> LLM (Groq) -> TTS (Deepgram) -> audio back to the browser. To start:

    uv run agent/bot.py      then open http://localhost:7860
"""

import os
from datetime import date

from dotenv import load_dotenv
from loguru import logger

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
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams

from agent.herramientas import registrar_herramientas

load_dotenv(override=True)

def construir_prompt() -> str:
    # The date is computed at startup so that "tomorrow" or "on Monday" make sense
    hoy = date.today().strftime("%A, %B %d, %Y")
    return (
        "You are Ana, the receptionist of Sunrise Family Clinic. "
        "You help callers book appointments. "
        f"Today is {hoy}. "
        "Only offer doctors and times returned by the consultar_huecos tool; never invent any. "
        "Before booking, ask for the caller's full name. "
        "Never confirm an appointment unless reservar_cita returned ok. "
        "If a tool reports an error, say so simply and offer an alternative. "
        "Say times naturally, like 'ten thirty in the morning' or 'Tuesday at three'. "
        "Your words are converted to speech: answer in one or two short sentences, "
        "no lists, no emojis."
    )


async def run_bot(transport: BaseTransport):
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        # Reasoning model: with "low" it thinks little before speaking (less latency)
        settings=GroqLLMService.Settings(model="openai/gpt-oss-120b", reasoning_effort="low"),
    )
    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramTTSService.Settings(voice="aura-2-thalia-en"),
    )

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

    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Llamada conectada")
        context.add_message({"role": "user", "content": "Greet the caller."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Llamada colgada")
        await task.cancel()

    await PipelineRunner(handle_sigint=False).run(task)


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
