"""Results of a round, summarised and compared: shared by the gate (tools/comparar.py)
and the scorecard API (app/resultados.py).

A round can come from two places:

- **Postgres** (`llamadas` filled by the queue, or by tools/importar_vuelta.py). Only the
  last execution of each job counts: earlier ones were infrastructure failures that the
  queue retried.
- **Files** (`evals/runs/<round>/results.jsonl`, written by `evals/lanzar.py suite`).

Every call is graded by the judge and by the deterministic asserts of evals/asserts.py;
if the asserts were not stored, they are recomputed from the round's logs. A call passes
only if both pass (`evals/informe.combinar`). Per-call metrics (agent/metricas.py) give
voice-to-voice latency, TTFB per stage and cost, priced with costes.toml.

The regression rule (one scenario, base vs candidate, over valid calls only):

- **worse** if the candidate has at least 2 passes fewer than the base rate predicts for
  its N, and either its Wilson 95 % interval lies entirely below the base's pass rate or
  both sides have N >= 10. A single lost call is never a regression: with the base at
  100 % and N=3, one failure already puts the interval below the base;
- **inconclusive** if either side has no valid calls, or the candidate has more
  infrastructure failures than valid calls in that scenario;
- **better**, symmetrically: at least 2 passes more and the interval entirely above the
  base's rate; else **same**.

Latency regresses if the voice-to-voice p95 grows more than 20 % (both sides with at
least 5 measured turns). Exit code of the gate: 1 if anything regressed, else 2 if
anything was inconclusive, else 0.
"""

from __future__ import annotations

import json
import math
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
for _p in (RAIZ, RAIZ / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import coste  # noqa: E402  (tools/coste.py)
from evals import asserts as asr  # noqa: E402
from evals.informe import _leer_log, clasificar, combinar, leer_filas  # noqa: E402

DIR_RUNS = RAIZ / "evals" / "runs"
COSTES = RAIZ / "costes.toml"
Z95 = 1.959964
MIN_N_CAIDA = 10  # the "2 passes fewer" rule needs at least this N on both sides
CAIDA_MIN = 2
SUBIDA_P95_MAX = 0.20
MIN_TURNOS_P95 = 5
VEREDICTOS = ("aprobado", "suspenso", "infra")


# ---------------------------------------------------------------- statistics


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes out of n; None if n == 0."""
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - margen), min(1.0, centro + margen)


def _p(values: list[float]) -> dict:
    return {
        "n": len(values),
        "p50": coste.percentile(values, 50),
        "p95": coste.percentile(values, 95),
    }


# ---------------------------------------------------------------- per-call metrics


def metricas_de_fichero(ruta: Path, precios: dict | None = None) -> dict:
    """Summary of one agent/metricas.py JSONL file: raw latencies (to pool across calls),
    usage and cost at list price (None if a price is missing)."""
    call = coste.load_call(ruta)
    try:
        importe = coste.call_cost(call, precios if precios is not None else _precios())
    except coste.PriceMissing:
        importe = None
    return {
        "call_id": call.call_id,
        "config": call.config,
        "voice_to_voice": call.voice_to_voice,
        "ttfb": call.ttfb,
        "uso": {
            "prompt_tokens": call.prompt_tokens,
            "completion_tokens": call.completion_tokens,
            "tts_characters": call.tts_characters,
            "tts_characters_estimated": call.tts_characters_estimated,
            "stt_audio_seconds": round(call.stt_audio_seconds, 3),
        },
        "coste": importe,
    }


def metricas_de_directorio(directorio: Path, precios: dict | None = None) -> dict | None:
    """Merge every metrics file under `directorio` (one call may restart the bot)."""
    ficheros = sorted(directorio.glob("*.jsonl")) if directorio.is_dir() else []
    if not ficheros:
        return None
    partes = [metricas_de_fichero(f, precios) for f in ficheros]
    if len(partes) == 1:
        return partes[0]
    junta = partes[0] | {
        "voice_to_voice": [v for p in partes for v in p["voice_to_voice"]],
        "ttfb": {s: [v for p in partes for v in p["ttfb"][s]] for s in coste.STAGES},
    }
    costes = [p["coste"] for p in partes]
    junta["coste"] = (
        None
        if any(c is None for c in costes)
        else {k: sum(c[k] for c in costes) for k in costes[0]}
    )
    return junta


_PRECIOS: dict | None = None


def _precios() -> dict:
    global _PRECIOS
    if _PRECIOS is None:
        _PRECIOS = coste.load_prices(COSTES)
    return _PRECIOS


# ---------------------------------------------------------------- one call


def _juez(fila: dict, dir_logs: Path | None) -> tuple[str, str | None]:
    veredicto, causa = clasificar(fila)
    if veredicto == "suspenso" and dir_logs is not None:
        veredicto, causa = clasificar(fila, _leer_log(fila, dir_logs))
    return veredicto, causa


def _asserts_de_ficheros(fila: dict, dir_logs: Path, escenario: str, bd: dict | None):
    llamada = asr.cargar_llamada(fila, dir_logs)
    lista = asr.evaluar(llamada, bd, asr.cargar_config(), escenario)
    asserts = {
        "veredicto": asr.veredicto(lista),
        "lista": [{"nombre": a.nombre, "aprobado": a.aprobado, "motivo": a.motivo} for a in lista],
    }
    return asserts, (llamada.mensajes if llamada else None)


def construir_llamada(
    fila: dict,
    *,
    juez: str,
    causa: str | None,
    asserts: dict | None,
    transcripcion: list | None,
    metricas: dict | None,
    **extra: Any,
) -> dict:
    """One call in the shape the gate and the API use."""
    v_asserts = (asserts or {}).get("veredicto", "n/a")
    veredicto = combinar(juez, v_asserts)
    if veredicto == "suspenso" and juez == "aprobado":
        fallidos = [a for a in (asserts or {}).get("lista", []) if a.get("aprobado") is False]
        causa = "asserts: " + "; ".join(f"{a['nombre']}: {a['motivo']}" for a in fallidos)
    return {
        "escenario": fila.get("scenario", extra.pop("escenario", "?")),
        "intento": fila.get("attempt", extra.pop("intento", None)),
        "veredicto": veredicto,
        "causa": causa,
        "juez": {
            "veredicto": juez,
            "confianza": fila.get("confidence"),
            "motivo": fila.get("reason"),
        },
        "asserts": asserts or {"veredicto": "n/a", "lista": []},
        "transcripcion": transcripcion if isinstance(transcripcion, list) else None,
        "metricas": metricas,
        "duracion_ms": fila.get("duration_ms"),
        **extra,
    }


# ---------------------------------------------------------------- loading a round


def dir_vuelta(nombre: str) -> Path:
    ruta = Path(nombre)
    return ruta if ruta.exists() else DIR_RUNS / nombre


def llamadas_de_ficheros(directorio: Path, con_asserts: bool = True) -> list[dict]:
    """Calls of a round run with `evals/lanzar.py suite` (results.jsonl + logs/)."""
    bd = asr.leer_foto_bd(directorio) if con_asserts else None
    salida = []
    for fila in leer_filas(directorio / "results.jsonl"):
        juez, causa = _juez(fila, directorio)
        escenario = fila.get("scenario", "?")
        asserts, mensajes = (None, None)
        if con_asserts:
            asserts, mensajes = _asserts_de_ficheros(fila, directorio, escenario, bd)
            if juez == "infra":  # an aborted call proves nothing: keep the transcript only
                asserts = None
        salida.append(
            construir_llamada(
                fila, juez=juez, causa=causa, asserts=asserts, transcripcion=mensajes, metricas=None
            )
        )
    return salida


# Last execution of every job of a round, with what is needed to rebuild the call
SQL_LLAMADAS = """
SELECT DISTINCT ON (l.trabajo_id)
       l.id, l.trabajo_id, l.escenario, l.intento, l.ejecucion, l.veredicto, l.causa,
       l.aprobado_juez, l.confianza_juez, l.asserts, l.transcripcion, l.metricas,
       l.resultado, l.duracion_ms, l.creada_en, t.escenario AS fichero, v.nombre AS vuelta
FROM llamadas l
JOIN trabajos t ON t.id = l.trabajo_id
JOIN vueltas v ON v.id = l.vuelta_id
WHERE l.vuelta_id = :vuelta_id
ORDER BY l.trabajo_id, l.ejecucion DESC, l.id DESC
"""

SQL_VUELTAS = """
SELECT v.id, v.nombre, v.escenarios, v.repeticiones, v.modalidad, v.creada_en,
       ve.etiqueta, ve.git_sha, ve.config
FROM vueltas v JOIN versiones ve ON ve.id = v.version_id
"""


def dir_trabajo(vuelta: str, fichero: str, intento: int, ejecucion: int) -> Path:
    """Where bench/worker.py leaves the files of one job execution."""
    return DIR_RUNS / vuelta / f"{fichero}__{intento:03d}__e{ejecucion}"


def llamada_de_fila_bd(fila_bd: dict, recalcular_asserts: bool = True) -> dict:
    """Rebuild one call from a `SQL_LLAMADAS` row. Asserts and metrics that were not
    stored are computed from the job's directory if it is still on disk."""
    fila = fila_bd["resultado"] or {}
    directorio = dir_trabajo(
        fila_bd["vuelta"], fila_bd["fichero"], fila_bd["intento"], fila_bd["ejecucion"]
    )
    juez = fila_bd["veredicto"]  # the worker stores the judge-only classification
    asserts, mensajes = fila_bd["asserts"], fila_bd["transcripcion"]
    if asserts is None and recalcular_asserts and juez != "infra" and directorio.is_dir():
        asserts, desde_logs = _asserts_de_ficheros(
            fila, directorio, fila_bd["escenario"], asr.leer_foto_bd(directorio.parent)
        )
        mensajes = desde_logs or mensajes
    metricas = fila_bd["metricas"]
    if metricas is None:
        metricas = metricas_de_directorio(directorio / "metrics")
    return construir_llamada(
        fila,
        juez=juez,
        causa=fila_bd["causa"],
        asserts=asserts,
        transcripcion=mensajes,
        metricas=metricas,
        id=fila_bd["id"],
        ejecucion=fila_bd["ejecucion"],
        escenario=fila_bd["escenario"],
        intento=fila_bd["intento"],
    )


def info_vuelta(fila: dict) -> dict:
    creada = fila.get("creada_en")
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "escenarios": fila["escenarios"],
        "repeticiones": fila["repeticiones"],
        "modalidad": fila["modalidad"],
        "creada_en": creada.isoformat() if hasattr(creada, "isoformat") else creada,
        "version": {
            "etiqueta": fila["etiqueta"],
            "git_sha": fila["git_sha"],
            "config": fila["config"],
        },
    }


# ---------------------------------------------------------------- summary of a round


def _cuenta() -> dict:
    return {
        "aprobado": 0, "suspenso": 0, "infra": 0,
        "juez_ok": 0, "asserts_ok": 0, "evaluadas": 0, "discrepa": 0,
    }


def _cerrar(c: dict) -> dict:
    n = c["aprobado"] + c["suspenso"]
    ic = wilson(c["aprobado"], n)
    return c | {"n": n, "tasa": c["aprobado"] / n if n else None, "ic": list(ic) if ic else None}


def resumir(llamadas: list[dict]) -> dict:
    """Per-scenario counts with Wilson intervals, judge vs asserts, latency and cost."""
    escenarios: OrderedDict[str, dict] = OrderedDict()
    total = _cuenta()
    v2v: list[float] = []
    ttfb: dict[str, list[float]] = {s: [] for s in coste.STAGES}
    costes: list[float] = []
    por_escenario_v2v: dict[str, list[float]] = {}
    for ll in llamadas:
        c = escenarios.setdefault(ll["escenario"], _cuenta())
        claves = [ll["veredicto"]]
        juez, v_asserts = ll["juez"]["veredicto"], ll["asserts"]["veredicto"]
        if juez != "infra":
            if juez == "aprobado":
                claves.append("juez_ok")
            if v_asserts != "n/a":
                claves.append("evaluadas")
                if v_asserts == "aprobado":
                    claves.append("asserts_ok")
            if juez == "aprobado" and v_asserts == "suspenso":
                claves.append("discrepa")
        for k in claves:
            c[k] += 1
            total[k] += 1
        m = ll.get("metricas")
        if m and ll["veredicto"] != "infra":
            v2v += m.get("voice_to_voice") or []
            por_escenario_v2v.setdefault(ll["escenario"], []).extend(m.get("voice_to_voice") or [])
            for s in coste.STAGES:
                ttfb[s] += (m.get("ttfb") or {}).get(s) or []
            if m.get("coste"):
                costes.append(m["coste"]["total"])
    filas = []
    for nombre, c in escenarios.items():
        filas.append({"escenario": nombre, **_cerrar(c), "voice_to_voice": _p(por_escenario_v2v.get(nombre, []))})
    return {
        "escenarios": filas,
        "total": _cerrar(total),
        "latencia": {
            "voice_to_voice": _p(v2v),
            "ttfb": {s: _p(ttfb[s]) for s in coste.STAGES},
        },
        "coste": {
            **_p(costes),
            "media": sum(costes) / len(costes) if costes else None,
            "moneda": _precios().get("moneda", "USD"),
        },
    }


# ---------------------------------------------------------------- the gate


def _escenario_estado(b: dict | None, c: dict | None) -> tuple[str, str]:
    if b is None:
        return "nuevo", "no está en la base"
    if c is None:
        return "no_concluyente", "falta en la candidata"
    if not b["n"] or not c["n"]:
        lado = "base" if not b["n"] else "candidata"
        return "no_concluyente", f"0 llamadas válidas en la {lado}"
    p_base = b["tasa"]
    lo, hi = c["ic"]
    esperados = p_base * c["n"]
    caida = esperados - c["aprobado"]  # passes lost vs what the base rate predicts
    perdidos = f"{caida:.1f} aprobados menos de los {esperados:.1f} esperados con N={c['n']}"
    if caida >= CAIDA_MIN - 1e-9:
        if hi < p_base:
            return "empeora", f"IC95 [{lo:.0%}, {hi:.0%}] por debajo del {p_base:.0%} de la base; {perdidos}"
        if b["n"] >= MIN_N_CAIDA and c["n"] >= MIN_N_CAIDA:
            return "empeora", perdidos
    if c["infra"] > c["n"]:
        return "no_concluyente", f"más fallos de infraestructura ({c['infra']}) que llamadas válidas ({c['n']})"
    if -caida >= CAIDA_MIN - 1e-9 and lo > p_base:
        return "mejora", f"IC95 [{lo:.0%}, {hi:.0%}] por encima del {p_base:.0%} de la base"
    return "igual", "dentro del ruido"


def comparar(base: dict, candidata: dict) -> dict:
    """Compare two `resumir` outputs. Returns per-scenario states and the gate verdict."""
    b_esc = {e["escenario"]: e for e in base["escenarios"]}
    c_esc = {e["escenario"]: e for e in candidata["escenarios"]}
    filas = []
    for nombre in [*b_esc, *[n for n in c_esc if n not in b_esc]]:
        b, c = b_esc.get(nombre), c_esc.get(nombre)
        estado, motivo = _escenario_estado(b, c)
        delta = None
        if b and c and b["tasa"] is not None and c["tasa"] is not None:
            delta = c["tasa"] - b["tasa"]
        filas.append(
            {"escenario": nombre, "base": b, "candidata": c, "delta": delta, "estado": estado, "motivo": motivo}
        )

    bl, cl = base["latencia"], candidata["latencia"]
    lat = {"voice_to_voice": {}, "ttfb": {}}
    for clave, pb, pc in [("voice_to_voice", bl["voice_to_voice"], cl["voice_to_voice"])] + [
        (s, bl["ttfb"][s], cl["ttfb"][s]) for s in coste.STAGES
    ]:
        d = {k: _delta_rel(pb.get(k), pc.get(k)) for k in ("p50", "p95")}
        fila = {"base": pb, "candidata": pc, "delta_rel": d}
        if clave == "voice_to_voice":
            lat["voice_to_voice"] = fila
        else:
            lat["ttfb"][clave] = fila
    v = lat["voice_to_voice"]
    medible = v["base"]["n"] >= MIN_TURNOS_P95 and v["candidata"]["n"] >= MIN_TURNOS_P95
    subida = v["delta_rel"]["p95"]
    v["empeora"] = bool(medible and subida is not None and subida > SUBIDA_P95_MAX)
    v["medible"] = medible

    motivos = [f"{f['escenario']}: {f['motivo']}" for f in filas if f["estado"] == "empeora"]
    if v["empeora"]:
        motivos.append(f"p95 voz a voz +{subida:.0%} (límite +{SUBIDA_P95_MAX:.0%})")
    dudas = [f"{f['escenario']}: {f['motivo']}" for f in filas if f["estado"] == "no_concluyente"]
    if not candidata["total"]["n"]:
        dudas.append("la candidata no tiene ninguna llamada válida")
    if motivos:
        codigo, texto = 1, "La candidata empeora"
    elif dudas:
        codigo, texto = 2, "No concluyente"
    else:
        codigo, texto = 0, "Sin regresiones"
    return {
        "escenarios": filas,
        "total": {"base": base["total"], "candidata": candidata["total"]},
        "latencia": lat,
        "coste": {"base": base["coste"], "candidata": candidata["coste"]},
        "veredicto": {"codigo": codigo, "texto": texto, "motivos": motivos, "dudas": dudas},
    }


def _delta_rel(b: float | None, c: float | None) -> float | None:
    if b is None or c is None or b == 0:
        return None
    return (c - b) / b


def a_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
