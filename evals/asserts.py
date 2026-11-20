"""Deterministic asserts for a call, evaluated on top of the LLM judge.

Inputs, as pipecat.evals leaves them in `evals/runs/<round>/`:
- `logs/<attempt>.conversation.json`: transcript in order, with `tool_call` entries (name and
  arguments, no result);
- `logs/<attempt>.log`: bot log; its last "Generating LLM response [...]" line holds the whole LLM
  context, tool results included;
- optional `estado_bd.json`: snapshot of the `huecos` and `citas` tables taken after the round
  (`uv run python evals/asserts.py foto <round>`). The snapshot covers the whole round, so the
  appointment a call made is found by the id that reservar_cita returned.

Which asserts apply to each scenario is configured in `evals/asserts.toml`.
The text checks (times, doctors, "yes") are simple English patterns: they are meant to be
explainable, not exhaustive. Each assert says why it passed or failed.

Usage: `uv run python evals/asserts.py foto <name or path of the round>`.
"""

import ast
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ_EVALS = Path(__file__).resolve().parent
CONFIG = RAIZ_EVALS / "asserts.toml"
FOTO_BD = "estado_bd.json"
MARCA_CONTEXTO = "Generating LLM response "
RECHAZO_GUARDA = "confirmacion_requerida"  # agent/confirmacion.py ERROR
ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class Assert:
    nombre: str
    aprobado: bool | None  # None: could not be evaluated (missing data)
    motivo: str


@dataclass
class Llamada:
    escenario: str
    # conversation.json entries; tool_call entries get a "resultado" key (dict or None)
    mensajes: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- loading


def contexto_llm(texto_log: str) -> list[dict] | None:
    """Last LLM context written to the bot log (a Python repr of the message list)."""
    for linea in reversed(texto_log.splitlines()):
        if MARCA_CONTEXTO + "[" in linea:
            crudo = ANSI.sub("", linea.split(MARCA_CONTEXTO, 1)[1]).strip()
            try:
                contexto = ast.literal_eval(crudo)
            except (ValueError, SyntaxError):
                return None
            return contexto if isinstance(contexto, list) else None
    return None


def resultados_herramientas(contexto: list[dict]) -> list[tuple[str, dict | None]]:
    """(tool name, parsed result) for every tool call in the context, in order."""
    resultados: dict[str, dict | None] = {}
    for m in contexto:
        if m.get("role") == "tool":
            try:
                resultados[m.get("tool_call_id")] = json.loads(m.get("content") or "")
            except ValueError:
                resultados[m.get("tool_call_id")] = None
    salida = []
    for m in contexto:
        for llamada in m.get("tool_calls") or []:
            nombre = (llamada.get("function") or {}).get("name", "")
            salida.append((nombre, resultados.get(llamada.get("id"))))
    return salida


def unir(mensajes: list[dict], resultados: list[tuple[str, dict | None]]) -> list[dict]:
    """Attach each result to the tool_call in the transcript, matching by order and name."""
    pendientes = list(resultados)
    unidos = []
    for m in mensajes:
        m = dict(m)
        if m.get("role") == "tool_call":
            m["resultado"] = None
            if pendientes and pendientes[0][0] == m.get("name"):
                m["resultado"] = pendientes.pop(0)[1]
        unidos.append(m)
    return unidos


def _candidatos(fila: dict, dir_vuelta: Path) -> list[Path]:
    ruta = (fila.get("artifacts") or {}).get("log")
    if not ruta:
        return []
    nombre = Path(str(ruta).replace("\\", "/")).name
    return [Path(ruta), dir_vuelta / "logs" / nombre]


def ruta_log(fila: dict, dir_vuelta: Path) -> Path | None:
    """The bot log of a row. `suite` writes it next to the transcript; a bench.worker job
    keeps it in `<job dir>/bot.log` (the bot is started by the worker, not by pipecat)."""
    candidatos = _candidatos(fila, dir_vuelta)
    if candidatos:
        candidatos.append(dir_vuelta / "bot.log")
    return next((c for c in candidatos if c.exists()), None)


def ruta_conversacion(fila: dict, dir_vuelta: Path) -> Path | None:
    for log in _candidatos(fila, dir_vuelta):
        conversacion = log.with_name(log.name.removesuffix(".log") + ".conversation.json")
        if conversacion.exists():
            return conversacion
    return None


def cargar_llamada(fila: dict, dir_vuelta: Path) -> Llamada | None:
    """Transcript + tool results of one results.jsonl row; None if the files are missing."""
    log, conversacion = ruta_log(fila, dir_vuelta), ruta_conversacion(fila, dir_vuelta)
    if log is None or conversacion is None:
        return None
    try:
        mensajes = json.loads(conversacion.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    contexto = contexto_llm(log.read_text(encoding="utf-8", errors="replace")) or []
    return Llamada(fila.get("scenario", "?"), unir(mensajes, resultados_herramientas(contexto)))


def leer_foto_bd(dir_vuelta: Path) -> dict | None:
    try:
        return json.loads((dir_vuelta / FOTO_BD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cargar_config(ruta: Path = CONFIG) -> dict:
    with open(ruta, "rb") as f:
        return tomllib.load(f)


def config_escenario(escenario: str, config: dict) -> dict:
    defecto = config.get("defecto", {})
    return {**defecto, **config.get("escenarios", {}).get(escenario, {})}


# ---------------------------------------------------------------- text helpers

HORAS = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]
MINUTOS = {
    "o'clock": 0,
    "oclock": 0,
    "fifteen": 15,
    "thirty": 30,
    "forty-five": 45,
    "forty five": 45,
}
_H = "|".join(HORAS)
_M = "|".join(re.escape(m) for m in MINUTOS)
PATRONES_HORA = [
    # 9:30, 09.30, 10:00
    (re.compile(r"\b(\d{1,2})[:.](\d{2})\b"), lambda g: (int(g[0]), int(g[1]))),
    # 9 am, 4 p.m.
    (re.compile(r"(?<![:.\d])\b(\d{1,2})\s*(?:a\.?m\.?|p\.?m\.?)(?!\w)"), lambda g: (int(g[0]), 0)),
    # half past four, quarter past nine, quarter to ten
    (re.compile(rf"\bhalf past ({_H})\b"), lambda g: (HORAS.index(g[0]) + 1, 30)),
    (re.compile(rf"\bquarter past ({_H})\b"), lambda g: (HORAS.index(g[0]) + 1, 15)),
    (re.compile(rf"\bquarter to ({_H})\b"), lambda g: (HORAS.index(g[0]) % 12, 45)),
    # nine thirty, ten o'clock
    (re.compile(rf"\b({_H})[ -]({_M})\b"), lambda g: (HORAS.index(g[0]) + 1, MINUTOS[g[1]])),
    # at five, ten in the morning, four in the afternoon
    (
        re.compile(
            rf"\b(?:at|or|and) ({_H})\b(?![ -](?:{_M}))(?! (?:of|more|other|moment|second))"
        ),
        lambda g: (HORAS.index(g[0]) + 1, 0),
    ),
    (
        re.compile(
            rf"(?<!past )(?<!to )\b({_H}) (?:in the (?:morning|afternoon|evening)|a\.?m\.?|p\.?m\.?)"
        ),
        lambda g: (HORAS.index(g[0]) + 1, 0),
    ),
]
DOCTOR = re.compile(r"\b(?:Dr\.?|Doctor)\s+([A-Z][a-z]+)")
NEGATIVO = re.compile(
    r"\b(no|not|don't|do not|hold on|wait|think about|think it over|call back|maybe)\b",
    re.IGNORECASE,
)
AFIRMATIVO = re.compile(
    r"\b(yes|yeah|yep|sure|correct|right|ok|okay|please do|go ahead|book it|sounds good|"
    r"perfect|absolutely|confirm|works for me|that works|fine|great|please book)\b",
    re.IGNORECASE,
)
PIDE_NOMBRE = re.compile(
    r"\b(your (full )?name|name,? please|who is the appointment for|who's the appointment for)\b",
    re.IGNORECASE,
)


# The LLM mixes in non-breaking spaces, Unicode hyphens and curly apostrophes
ESPACIOS = str.maketrans(
    {
        "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u200b": None,
        "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-", "\u2019": "'",
    }
)  # fmt: skip


def _normalizar(texto: str) -> str:
    return re.sub(r" +", " ", texto.translate(ESPACIOS)).lower()


def menciones_hora(texto: str) -> set[tuple[int, int]]:
    """Clock times said in a sentence, as (hour on a 12 h clock, minute)."""
    texto = _normalizar(texto)
    vistas = set()
    for patron, convertir in PATRONES_HORA:
        for m in patron.finditer(texto):
            hora, minuto = convertir(m.groups())
            vistas.add((hora % 12, minuto))
    return vistas


def hora_de(inicio: str) -> tuple[int, int] | None:
    """'2026-11-03T09:30:00Z' -> (9, 30). The agent reads the slot time as given."""
    m = re.search(r"T(\d{2}):(\d{2})", inicio or "")
    return (int(m[1]) % 12, int(m[2])) if m else None


def apellido(medico: str) -> str:
    return re.sub(r"^(dr\.?|doctor)\s+", "", medico.strip(), flags=re.IGNORECASE).lower()


def doctores_mencionados(texto: str) -> set[str]:
    return {m.lower() for m in DOCTOR.findall(texto.translate(ESPACIOS))}


def es_afirmativo(texto: str) -> bool:
    texto = _normalizar(texto)
    return bool(AFIRMATIVO.search(texto)) and not NEGATIVO.search(texto)


def _mismo_nombre(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


# ---------------------------------------------------------------- call helpers


def _llamadas(llamada: Llamada, nombre: str) -> list[int]:
    return [
        i
        for i, m in enumerate(llamada.mensajes)
        if m.get("role") == "tool_call" and m.get("name") == nombre
    ]


def _huecos_hasta(llamada: Llamada, hasta: int) -> dict[int, dict]:
    """Slots returned by consultar_huecos before position `hasta`, by id."""
    huecos = {}
    for m in llamada.mensajes[:hasta]:
        if m.get("role") == "tool_call" and m.get("name") == "consultar_huecos":
            for h in (m.get("resultado") or {}).get("huecos") or []:
                huecos[h.get("hueco_id")] = h
    return huecos


def _hueco_reservado(llamada: Llamada, i: int) -> dict | None:
    """Slot booked by the reservar_cita at position i (from its result or from consultar)."""
    m = llamada.mensajes[i]
    cita = (m.get("resultado") or {}).get("cita")
    if cita:
        return {
            "hueco_id": cita.get("hueco_id"),
            "medico": cita.get("medico"),
            "inicio": cita.get("inicio"),
        }
    hueco_id = (m.get("arguments") or {}).get("hueco_id")
    return _huecos_hasta(llamada, i).get(hueco_id)


def _reservas_ok(llamada: Llamada) -> list[int]:
    return [
        i
        for i in _llamadas(llamada, "reservar_cita")
        if (llamada.mensajes[i].get("resultado") or {}).get("ok")
    ]


# ---------------------------------------------------------------- asserts


def reserva_correcta(llamada: Llamada, cfg: dict, bd: dict | None) -> Assert:
    nombre = "reserva_correcta"
    reservas = _reservas_ok(llamada)
    if not reservas:
        intentos = _llamadas(llamada, "reservar_cita")
        motivo = "reservar_cita sin resultado ok" if intentos else "no llamo a reservar_cita"
        return Assert(nombre, False, motivo)
    i = reservas[-1]
    args = llamada.mensajes[i].get("arguments") or {}
    cita = llamada.mensajes[i]["resultado"].get("cita") or {}
    devueltos = _huecos_hasta(llamada, i)
    hueco_id = args.get("hueco_id")
    if hueco_id not in devueltos:
        return Assert(nombre, False, f"hueco {hueco_id} no lo devolvio consultar_huecos")
    paciente = cfg.get("paciente")
    if paciente and not _mismo_nombre(str(args.get("paciente", "")), paciente):
        return Assert(nombre, False, f"paciente {args.get('paciente')!r}, esperado {paciente!r}")
    medico = cfg.get("medico")
    if medico and apellido(devueltos[hueco_id].get("medico", "")) != apellido(medico):
        return Assert(
            nombre, False, f"medico {devueltos[hueco_id].get('medico')!r}, esperado {medico!r}"
        )
    if bd is None:
        return Assert(nombre, True, f"hueco {hueco_id} devuelto y reservado (sin foto de BD)")
    en_bd = [c for c in bd.get("citas", []) if c.get("id") == cita.get("id")]
    if not en_bd:
        return Assert(nombre, False, f"la cita {cita.get('id')} no esta en la tabla citas")
    c = en_bd[0]
    if c.get("hueco_id") != hueco_id or (
        paciente and not _mismo_nombre(c.get("paciente", ""), paciente)
    ):
        return Assert(nombre, False, f"la cita {c.get('id')} en BD no coincide: {c}")
    hueco_bd = next((h for h in bd.get("huecos", []) if h.get("id") == hueco_id), None)
    if medico and (hueco_bd is None or apellido(hueco_bd.get("medico", "")) != apellido(medico)):
        return Assert(nombre, False, f"en BD el hueco {hueco_id} no es de {medico}")
    return Assert(nombre, True, f"cita {c.get('id')} en BD: {c.get('paciente')}, hueco {hueco_id}")


def sin_reserva(llamada: Llamada, cfg: dict, bd: dict | None) -> Assert:
    nombre = "sin_reserva"
    if _llamadas(llamada, "reservar_cita"):
        return Assert(nombre, False, "llamo a reservar_cita")
    paciente = cfg.get("paciente")
    if bd is not None and paciente:
        citas = [c for c in bd.get("citas", []) if _mismo_nombre(c.get("paciente", ""), paciente)]
        if citas:
            return Assert(nombre, False, f"la BD tiene {len(citas)} cita(s) de {paciente}")
        return Assert(nombre, True, f"sin reservar_cita y 0 citas de {paciente} en BD")
    return Assert(nombre, True, "no llamo a reservar_cita (sin foto de BD)")


def confirmacion_antes_de_reservar(llamada: Llamada, cfg: dict, bd: dict | None) -> Assert:
    nombre = "confirmacion_antes_de_reservar"
    # A call refused by the agent's confirmation guard booked nothing: it is not a booking
    reservas = [
        i
        for i in _llamadas(llamada, "reservar_cita")
        if (llamada.mensajes[i].get("resultado") or {}).get("error") != RECHAZO_GUARDA
    ]
    if not reservas:
        return Assert(nombre, True, "no hubo reservar_cita (o la guarda las paro todas)")
    for i in reservas:
        previos = llamada.mensajes[:i]
        idx_ana = next(
            (
                j
                for j in range(i - 1, -1, -1)
                if previos[j].get("role") == "assistant" and previos[j].get("content")
            ),
            None,
        )
        if idx_ana is None:
            return Assert(nombre, False, "reservo sin que Ana dijera nada antes")
        ana = previos[idx_ana]["content"]
        respuestas = [
            m.get("content") or "" for m in previos[idx_ana + 1 :] if m.get("role") == "user"
        ]
        hueco = _hueco_reservado(llamada, i)
        if hueco:
            repite_medico = apellido(hueco.get("medico", "")) in doctores_mencionados(ana)
            repite_hora = hora_de(hueco.get("inicio", "")) in menciones_hora(ana)
        else:
            repite_medico = bool(doctores_mencionados(ana))
            repite_hora = bool(menciones_hora(ana))
        if not (repite_medico and repite_hora):
            falta = " y ".join(
                x for x, ok in (("medico", repite_medico), ("hora", repite_hora)) if not ok
            )
            return Assert(nombre, False, f"antes de reservar Ana no repite {falta}: {ana[:70]!r}")
        if not respuestas:
            return Assert(nombre, False, f"reservo sin esperar respuesta: {ana[:70]!r}")
        if not all(es_afirmativo(r) for r in respuestas):
            return Assert(nombre, False, f"el paciente no dijo que si: {respuestas[-1][:60]!r}")
    return Assert(nombre, True, f"{len(reservas)} reserva(s) con medico+hora repetidos y un si")


def no_inventa(llamada: Llamada, cfg: dict, bd: dict | None) -> Assert:
    nombre = "no_inventa"
    conocidos = {apellido(m) for m in cfg.get("medicos", [])}
    conocidos |= {apellido(h.get("medico", "")) for h in (bd or {}).get("huecos", [])}
    dichos_paciente: set[str] = set()
    horas_paciente: set[tuple[int, int]] = set()
    for i, m in enumerate(llamada.mensajes):
        texto = m.get("content") or ""
        if m.get("role") == "user":
            # Echoing what the patient said ("no slots with Dr. Fernando") is not inventing
            dichos_paciente |= doctores_mencionados(texto)
            horas_paciente |= menciones_hora(texto)
            continue
        if m.get("role") != "assistant":
            continue
        devueltos = _huecos_hasta(llamada, i).values()
        medicos_ok = (
            conocidos | {apellido(h.get("medico", "")) for h in devueltos} | dichos_paciente
        )
        horas_ok = {hora_de(h.get("inicio", "")) for h in devueltos} | horas_paciente
        inventados = doctores_mencionados(texto) - medicos_ok
        if inventados:
            return Assert(nombre, False, f"medico inventado {sorted(inventados)}: {texto[:60]!r}")
        horas = menciones_hora(texto) - horas_ok
        if horas:
            dichas = ", ".join(f"{h or 12}:{mi:02d}" for h, mi in sorted(horas))
            return Assert(
                nombre, False, f"hora no devuelta por consultar_huecos ({dichas}): {texto[:60]!r}"
            )
    return Assert(nombre, True, "medicos y horas salen de la BD o de las herramientas")


def orden_herramientas(llamada: Llamada, cfg: dict, bd: dict | None) -> Assert:
    nombre = "orden_herramientas"
    consultas = _llamadas(llamada, "consultar_huecos")
    primera = consultas[0] if consultas else None
    for i in _llamadas(llamada, "reservar_cita"):
        if primera is None or primera > i:
            return Assert(nombre, False, "reservar_cita antes de consultar_huecos")
    pide_nombre = next(
        (
            i
            for i, m in enumerate(llamada.mensajes)
            if m.get("role") == "assistant" and PIDE_NOMBRE.search(m.get("content") or "")
        ),
        None,
    )
    if pide_nombre is not None and (primera is None or primera > pide_nombre):
        return Assert(nombre, False, "pidio el nombre antes de consultar_huecos")
    if primera is None:
        return Assert(nombre, True, "no consulto huecos, pero tampoco pidio nombre ni reservo")
    return Assert(nombre, True, "consultar_huecos antes de pedir el nombre y de reservar")


ASSERTS = {
    f.__name__: f
    for f in (
        reserva_correcta,
        sin_reserva,
        confirmacion_antes_de_reservar,
        no_inventa,
        orden_herramientas,
    )
}


def evaluar(
    llamada: Llamada | None,
    bd: dict | None = None,
    config: dict | None = None,
    escenario: str | None = None,
) -> list[Assert]:
    """Run the asserts configured for the call's scenario."""
    config = cargar_config() if config is None else config
    escenario = escenario or (llamada.escenario if llamada else "?")
    cfg = config_escenario(escenario, config)
    nombres = cfg.get("asserts", [])
    if llamada is None:
        return [Assert(n, None, "sin transcripcion (conversation.json)") for n in nombres]
    salida = []
    for n in nombres:
        funcion = ASSERTS.get(n)
        salida.append(
            funcion(llamada, cfg, bd) if funcion else Assert(n, None, "assert desconocido")
        )
    return salida


def veredicto(asserts: list[Assert]) -> str:
    """'suspenso' if any assert failed, 'aprobado' if some passed and none failed, else 'n/a'."""
    if any(a.aprobado is False for a in asserts):
        return "suspenso"
    return "aprobado" if any(a.aprobado for a in asserts) else "n/a"


# ---------------------------------------------------------------- database snapshot


def leer_estado_bd(url: str | None = None) -> dict:
    """Read huecos and citas (sync engine; starts the portable Postgres if needed)."""
    from sqlalchemy import create_engine, text

    sys.path.insert(0, str(RAIZ_EVALS.parent))
    from app.db.config import database_url

    engine = create_engine(url or database_url(), connect_args={"options": "-c timezone=GMT"})
    try:
        with engine.connect() as con:
            huecos = con.execute(text("SELECT id, inicio, medico, libre FROM huecos ORDER BY id"))
            citas = con.execute(
                text("SELECT id, hueco_id, paciente, creada_en FROM citas ORDER BY id")
            )
            return {
                "huecos": [
                    {
                        "id": h.id,
                        "inicio": h.inicio.isoformat(),
                        "medico": h.medico,
                        "libre": h.libre,
                    }
                    for h in huecos
                ],
                "citas": [
                    {
                        "id": c.id,
                        "hueco_id": c.hueco_id,
                        "paciente": c.paciente,
                        "creada_en": c.creada_en.isoformat(),
                    }
                    for c in citas
                ],
            }
    finally:
        engine.dispose()


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "foto":
        print("uso: uv run python evals/asserts.py foto <nombre_o_ruta_de_la_vuelta>")
        return 64
    dir_vuelta = Path(argv[2]) if Path(argv[2]).exists() else RAIZ_EVALS / "runs" / argv[2]
    estado = leer_estado_bd()
    (dir_vuelta / FOTO_BD).write_text(
        json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"{FOTO_BD}: {len(estado['huecos'])} huecos, {len(estado['citas'])} citas -> {dir_vuelta}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
