"""Groq services for the judge and the simulated persona of pipecat.evals.

pipecat.evals resolves `factory: module.function` with importlib and passes it the
scenario's configuration block; it must return an OpenAI-compatible LLM.
The GROQ_API_KEY is loaded by the evals CLI from .env.
"""

import os

from pipecat.services.groq.llm import GroqLLMService

MODELO_POR_DEFECTO = "openai/gpt-oss-120b"


def _groq(config: dict, extra_por_defecto: dict) -> GroqLLMService:
    return GroqLLMService(
        api_key=os.environ["GROQ_API_KEY"],
        settings=GroqLLMService.Settings(
            model=config.get("model", MODELO_POR_DEFECTO),
            extra=config.get("extra", extra_por_defecto),
        ),
    )


def juez(config: dict) -> GroqLLMService:
    """LLM that judges the `eval:` expectations and the `success` of simulations."""
    # gpt-oss accepts low/medium/high; "low" makes it cheaper and faster
    return _groq(config, {"reasoning_effort": "low"})


def persona(config: dict) -> GroqLLMService:
    """LLM that plays the patient; needs function calling (end_call)."""
    return _groq(config, {})
