"""Code-side guard for reservar_cita: no booking without the caller's own yes.

The prompt already tells Ana to read the details back and wait for a yes, but the LLM
sometimes books straight away (baseline of 2026-11-21: the 4 failures out of 18 valid
calls). This check does not trust the model's word. It reads the conversation itself:

1. the model must pass `confirmado_por_paciente: true` and the caller's exact words;
2. those words must be in the caller's latest turn, and that turn must be a clear yes
   (no "wait", "maybe", "let me think");
3. Ana's turn just before it must name the doctor and the hour of the slot being booked
   (when the slot is in an earlier consultar_huecos result).

If any check fails, reservar_cita does not touch the API and returns an error that tells
the model to read the booking back and ask.
"""

import json
import re

ERROR = "confirmacion_requerida"
AFFIRMATIVE = re.compile(
    r"\b(yes|yeah|yep|yup|sure|correct|right|ok|okay|please do|go ahead|book it|"
    r"sounds good|perfect|absolutely|confirm|confirmed|works for me|that works|fine|great|"
    r"please book)\b"
)
NEGATIVE = re.compile(
    r"\b(no|not|don't|do not|hold on|wait|think about|think it over|call back|maybe)\b"
)
HOUR_WORDS = [
    "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve",
]  # fmt: skip
# The LLM mixes in non-breaking spaces, Unicode hyphens and curly apostrophes
_UNICODE = str.maketrans(
    {" ": " ", " ": " ", " ": " ", "’": "'", "‐": "-", "‑": "-"}
)


def _text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):  # OpenAI content parts
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content if isinstance(content, str) else ""


def _norm(text: str) -> str:
    """Lower case, words and apostrophes only, single spaces."""
    text = re.sub(r"[^\w']+", " ", text.translate(_UNICODE).lower())
    return " ".join(text.split())


def is_affirmative(text: str) -> bool:
    text = _norm(text)
    return bool(AFFIRMATIVE.search(text)) and not NEGATIVE.search(text)


def latest_exchange(messages: list[dict]) -> tuple[str, str]:
    """(Ana's last spoken turn before the caller's latest turn, the caller's latest turn).

    Skips what the model produced after the caller spoke (tool calls, tool results and
    any "let me book that" said in the same response).
    """
    i = len(messages) - 1
    while i >= 0 and messages[i].get("role") != "user":
        i -= 1
    end = i
    while i >= 0 and messages[i].get("role") == "user":
        i -= 1
    caller = " ".join(_text(m) for m in messages[i + 1 : end + 1])
    while i >= 0 and not (messages[i].get("role") == "assistant" and _text(messages[i]).strip()):
        i -= 1
    ana = _text(messages[i]) if i >= 0 else ""
    return ana, caller


def slot_from_context(messages: list[dict], hueco_id) -> dict | None:
    """The slot with this id in an earlier consultar_huecos result, if any."""
    for m in reversed(messages):
        if m.get("role") != "tool":
            continue
        try:
            result = json.loads(_text(m))
        except ValueError:
            continue
        slots = result.get("huecos") if isinstance(result, dict) else None
        for slot in slots or []:
            if str(slot.get("hueco_id")) == str(hueco_id):
                return slot
    return None


def _names_slot(ana: str, slot: dict) -> list[str]:
    """What Ana's read-back is missing from the slot: the doctor and/or the hour."""
    missing = []
    said = _norm(ana)
    surname = _norm(re.sub(r"^(dr\.?|doctor)\s+", "", slot.get("medico", ""), flags=re.IGNORECASE))
    if surname and not re.search(rf"\b{re.escape(surname)}\b", said):
        missing.append("the doctor")
    m = re.search(r"T(\d{2}):(\d{2})", slot.get("inicio", ""))
    if m:
        hour = int(m[1]) % 12 or 12
        if not re.search(rf"\b({hour}|0{hour}|{HOUR_WORDS[hour - 1]})\b", said):
            missing.append("the time")
    return missing


def refuse(reason: str) -> dict:
    return {
        "ok": False,
        "error": ERROR,
        "mensaje": (
            f"Not booked: {reason}. Say the doctor, day, time and the caller's name back "
            "to them and ask if that is correct. Call reservar_cita again only after they "
            "say yes, with confirmado_por_paciente=true and their exact words in "
            "frase_del_paciente."
        ),
    }


def check_confirmation(args: dict, messages: list[dict]) -> dict | None:
    """None if the booking may go ahead; otherwise the error result for the LLM."""
    if args.get("confirmado_por_paciente") is not True:
        return refuse("the caller has not confirmed this booking")
    phrase = _norm(str(args.get("frase_del_paciente") or ""))
    if not phrase:
        return refuse("frase_del_paciente is empty")
    ana, caller = latest_exchange(messages)
    if not caller:
        return refuse("the caller has not said anything yet")
    if phrase not in _norm(caller):
        return refuse("the caller did not say those words in their last turn")
    if not is_affirmative(caller):
        return refuse("the caller's last turn is not a clear yes")
    slot = slot_from_context(messages, args.get("hueco_id"))
    if slot:
        missing = _names_slot(ana, slot)
        if missing:
            return refuse(f"your last turn did not repeat {' and '.join(missing)}")
    return None
