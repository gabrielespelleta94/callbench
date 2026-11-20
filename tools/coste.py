"""Cost per call and p50/p95 latency from the per-call metrics files.

    uv run python tools/coste.py                     # every *.jsonl in CALLBENCH_METRICS_DIR (or metrics/)
    uv run python tools/coste.py metrics/ otra.jsonl # directories and/or files
    uv run python tools/coste.py --json              # machine-readable summary

Usage comes from agent/metricas.py (tokens, TTS characters, STT audio seconds); prices
from costes.toml at list price. Totals are recomputed from the event lines, not taken
from `call_end`, so a call that crashed before closing still counts.
"""

import argparse
import json
import math
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
STAGES = ("stt", "llm", "tts")


class PriceMissing(Exception):
    """A call used a service whose price is missing or marked `pendiente` in costes.toml."""


@dataclass
class Call:
    call_id: str
    config: dict = field(default_factory=dict)
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    tts_characters: int = 0
    tts_characters_estimated: bool = False
    stt_audio_seconds: float = 0.0
    voice_to_voice: list[float] = field(default_factory=list)
    ttfb: dict[str, list[float]] = field(default_factory=lambda: {s: [] for s in STAGES})


def load_call(path: Path) -> Call:
    call = Call(call_id=path.stem)
    texto_hablado = 0
    for n, linea in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        try:
            e = json.loads(linea)
        except ValueError:
            # A call killed mid-write leaves a truncated last line: skip it, keep the rest
            print(f"aviso: {path.name}:{n} no es JSON, se ignora", file=sys.stderr)
            continue
        call.call_id = e.get("call_id", call.call_id)
        tipo = e.get("event")
        if tipo == "call_start":
            call.config = e.get("config", {})
        elif tipo == "llm_usage":
            call.prompt_tokens += e["prompt_tokens"]
            call.completion_tokens += e["completion_tokens"]
            call.cached_tokens += e.get("cached_tokens", 0)
        elif tipo == "tts_usage":
            call.tts_characters += e["characters"]
        elif tipo == "stt_usage":
            call.stt_audio_seconds += e["audio_seconds"]
        elif tipo == "voice_to_voice":
            call.voice_to_voice.append(e["seconds"])
        elif tipo == "ttfb" and e.get("stage") in call.ttfb:
            call.ttfb[e["stage"]].append(e["value"])
        elif tipo == "call_end":
            texto_hablado = e.get("totals", {}).get("tts_text_characters", 0)
    if not call.tts_characters and texto_hablado:
        # The TTS service reported no usage: fall back to the spoken text (estimate)
        call.tts_characters = texto_hablado
        call.tts_characters_estimated = True
    return call


def load_prices(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def _price(prices: dict, kind: str, cfg: dict, key: str) -> float:
    proveedor, modelo = cfg.get("provider"), cfg.get("model")
    entrada = prices.get(kind, {}).get(proveedor, {}).get(modelo)
    if not entrada or entrada.get("pendiente") or key not in entrada:
        raise PriceMissing(f"sin tarifa verificada para {kind} {proveedor}/{modelo} ({key}) en costes.toml")
    return float(entrada[key])


def call_cost(call: Call, prices: dict) -> dict[str, float]:
    """Cost in the costes.toml currency, per stage and total. A stage the call did not
    use (e.g. no STT in a text-mode eval) costs 0 and needs no price."""
    coste = {s: 0.0 for s in STAGES}
    if call.prompt_tokens or call.completion_tokens:
        cfg = call.config.get("llm", {})
        # OpenAI-compatible services (Groq) report prompt_tokens gross of the cache
        sin_cache = call.prompt_tokens - call.cached_tokens
        coste["llm"] = (
            sin_cache * _price(prices, "llm", cfg, "input_per_million")
            + call.completion_tokens * _price(prices, "llm", cfg, "output_per_million")
        ) / 1e6
        if call.cached_tokens:
            coste["llm"] += call.cached_tokens * _price(prices, "llm", cfg, "cached_input_per_million") / 1e6
    if call.stt_audio_seconds:
        coste["stt"] = call.stt_audio_seconds / 60 * _price(prices, "stt", call.config.get("stt", {}), "per_minute")
    if call.tts_characters:
        coste["tts"] = (
            call.tts_characters / 1000
            * _price(prices, "tts", call.config.get("tts", {}), "per_thousand_characters")
        )
    coste["total"] = sum(coste[s] for s in STAGES)
    return coste


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile (same as numpy's default); None if empty."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _p50_p95(values: list[float]) -> dict:
    return {"n": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95)}


def summarize(calls: list[Call], prices: dict) -> dict:
    filas, costes, sin_precio = [], [], []
    for c in calls:
        try:
            coste = call_cost(c, prices)
        except PriceMissing as e:
            sin_precio.append({"call_id": c.call_id, "error": str(e)})
            coste = None
        if coste:
            costes.append(coste["total"])
        filas.append({
            "call_id": c.call_id,
            "config": c.config,
            "usage": {
                "prompt_tokens": c.prompt_tokens,
                "cached_tokens": c.cached_tokens,
                "completion_tokens": c.completion_tokens,
                "tts_characters": c.tts_characters,
                "tts_characters_estimated": c.tts_characters_estimated,
                "stt_audio_seconds": round(c.stt_audio_seconds, 3),
            },
            "cost": coste,
        })
    return {
        "currency": prices.get("moneda", "USD"),
        "calls": filas,
        "unpriced": sin_precio,
        "cost_per_call": _p50_p95(costes),
        "voice_to_voice": _p50_p95([v for c in calls for v in c.voice_to_voice]),
        "ttfb": {s: _p50_p95([v for c in calls for v in c.ttfb[s]]) for s in STAGES},
    }


def find_files(targets: list[str]) -> list[Path]:
    rutas = targets or [os.environ.get("CALLBENCH_METRICS_DIR") or str(RAIZ / "metrics")]
    ficheros: list[Path] = []
    for t in rutas:
        p = Path(t)
        if p.is_dir():
            ficheros += sorted(p.glob("*.jsonl"))
        elif p.is_file():
            ficheros.append(p)
        else:
            print(f"aviso: {p} no existe", file=sys.stderr)
    return ficheros


def _fmt(x: float | None, unidad: str = "s", dec: int = 3) -> str:
    return "-" if x is None else f"{x:.{dec}f}{unidad}"


def informe_texto(r: dict) -> str:
    mon = r["currency"]
    out = [f"{'llamada':<34} {'tokens in/out':>14} {'chars TTS':>9} {'audio STT':>9} {'coste':>12}"]
    for f in r["calls"]:
        u = f["usage"]
        coste = "sin tarifa" if f["cost"] is None else f"{f['cost']['total']:.5f} {mon}"
        out.append(
            f"{f['call_id']:<34} {u['prompt_tokens']:>6}/{u['completion_tokens']:<7} "
            f"{u['tts_characters']:>8}{'*' if u['tts_characters_estimated'] else ' '}"
            f" {u['stt_audio_seconds']:>8.1f}s {coste:>12}"
        )
    if any(f["usage"]["tts_characters_estimated"] for f in r["calls"]):
        out.append("* caracteres TTS estimados con el texto hablado (el servicio no informó de uso)")
    c = r["cost_per_call"]
    out.append("")
    out.append(f"Coste por llamada (precio de lista, N={c['n']}): "
               f"p50 {_fmt(c['p50'], ' ' + mon, 5)} · p95 {_fmt(c['p95'], ' ' + mon, 5)}")
    v = r["voice_to_voice"]
    out.append(f"Voz a voz (N={v['n']} turnos): p50 {_fmt(v['p50'])} · p95 {_fmt(v['p95'])}")
    for s in STAGES:
        t = r["ttfb"][s]
        out.append(f"TTFB {s.upper()} (N={t['n']}): p50 {_fmt(t['p50'])} · p95 {_fmt(t['p95'])}")
    for s in r["unpriced"]:
        out.append(f"SIN TARIFA {s['call_id']}: {s['error']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("targets", nargs="*", help="JSONL files or directories")
    ap.add_argument("--costes", default=str(RAIZ / "costes.toml"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ficheros = find_files(args.targets)
    if not ficheros:
        print("No hay ficheros de métricas.", file=sys.stderr)
        return 1
    r = summarize([load_call(f) for f in ficheros], load_prices(Path(args.costes)))
    print(json.dumps(r, indent=2, ensure_ascii=False) if args.json else informe_texto(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
