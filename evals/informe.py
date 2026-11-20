"""Report for an eval round: separates agent failures from infrastructure failures.

Each call is graded twice: by the LLM judge (pipecat.evals) and by the deterministic asserts
of `evals/asserts.py`. A call passes only if both pass; both verdicts are kept so the report can
say how many calls the judge passed and the asserts failed.

Usage: `uv run python evals/informe.py <name or path of the round> [--solo-juez]`.
Exit code: 0 all passed, 1 some agent failure, 2 no failures but infra errors.
"""

import json
import sys
from collections import OrderedDict
from pathlib import Path

import asserts as asr

RAIZ_RUNS = Path(__file__).resolve().parent / "runs"
MARCA_AGENDA = '"error": "agenda_no_disponible"'
TRUNCADO = 80


def causa_infra(fila: dict) -> str | None:
    error = fila.get("error") or ""
    razones = [str(f.get("reason") or "") for f in fila.get("failures") or []]
    if any("judge call failed" in t for t in [error, *razones]):
        return "juez sin respuesta (cuota Groq)"
    if error.startswith("Error during completion"):
        return "Groq rechaza la llamada a herramienta"
    if "ProcessLookupError" in error:
        return "proceso del bot muerto"
    if error:
        return "error: " + error.strip()[:TRUNCADO]
    if fila.get("ended_by") == "error":
        return "intento terminado con error (ended_by=error)"
    return None


def api_caida(texto_log: str | None) -> bool:
    return bool(texto_log) and MARCA_AGENDA in texto_log


def _motivo_suspenso(fila: dict) -> str | None:
    fallos = fila.get("failures") or []
    if fallos:
        return str(fallos[0].get("reason") or fallos[0].get("kind") or "")[:TRUNCADO]
    return fila.get("reason") or None


def clasificar(fila: dict, texto_log: str | None = None) -> tuple[str, str | None]:
    if fila.get("passed"):
        return "aprobado", None
    causa = causa_infra(fila)
    if causa:
        return "infra", causa
    if api_caida(texto_log):
        return "infra", "API de la clinica caida (agenda_no_disponible)"
    return "suspenso", _motivo_suspenso(fila)


def agregar(resultados: list[tuple[str, str]]) -> dict:
    """`resultados`: (escenario, veredicto) pairs. Returns per-scenario counts and totals."""
    escenarios: OrderedDict[str, dict] = OrderedDict()
    total = {"aprobado": 0, "suspenso": 0, "infra": 0}
    for escenario, veredicto in resultados:
        cuenta = escenarios.setdefault(escenario, {"aprobado": 0, "suspenso": 0, "infra": 0})
        cuenta[veredicto] += 1
        total[veredicto] += 1
    validos = total["aprobado"] + total["suspenso"]
    tasa = total["aprobado"] / validos if validos else None
    return {"escenarios": escenarios, "total": total, "tasa": tasa}


def leer_filas(ruta: Path) -> list[dict]:
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def _leer_log(fila: dict, dir_vuelta: Path) -> str | None:
    ruta = (fila.get("artifacts") or {}).get("log")
    if not ruta:
        return None
    nombre = Path(str(ruta).replace("\\", "/")).name
    for candidato in (Path(ruta), dir_vuelta / "logs" / nombre):
        try:
            return candidato.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None


def dir_de_vuelta(arg: str) -> Path:
    ruta = Path(arg)
    return ruta if ruta.exists() else RAIZ_RUNS / arg


def combinar(juez: str, veredicto_asserts: str) -> str:
    """Final verdict: infra wins (not conclusive), then any failure, else passed."""
    if juez == "infra":
        return "infra"
    if juez == "suspenso" or veredicto_asserts == "suspenso":
        return "suspenso"
    return "aprobado"


def analizar(dir_vuelta: Path, con_asserts: bool = True) -> tuple[list[dict], dict]:
    config = asr.cargar_config() if con_asserts else None
    bd = asr.leer_foto_bd(dir_vuelta) if con_asserts else None
    detalle = []
    for fila in leer_filas(dir_vuelta / "results.jsonl"):
        juez, causa = clasificar(fila)
        if juez == "suspenso":
            juez, causa = clasificar(fila, _leer_log(fila, dir_vuelta))
        escenario = fila.get("scenario", "?")
        lista = []
        if con_asserts:
            lista = asr.evaluar(asr.cargar_llamada(fila, dir_vuelta), bd, config, escenario)
        v_asserts = asr.veredicto(lista) if con_asserts else "n/a"
        veredicto = combinar(juez, v_asserts)
        if veredicto == "suspenso" and juez == "aprobado":
            fallidos = [a for a in lista if a.aprobado is False]
            causa = "asserts: " + "; ".join(f"{a.nombre}: {a.motivo}" for a in fallidos)
        detalle.append(
            {
                "escenario": escenario,
                "intento": fila.get("attempt"),
                "veredicto": veredicto,
                "causa": causa,
                "juez": juez,
                "asserts": v_asserts,
                "lista_asserts": lista,
            }
        )
    resumen = agregar([(d["escenario"], d["veredicto"]) for d in detalle])
    resumen["juez_vs_asserts"] = juez_vs_asserts(detalle)
    resumen["con_asserts"] = con_asserts
    return detalle, resumen


def juez_vs_asserts(detalle: list[dict]) -> dict:
    """Per scenario, over non-infra calls: judge passes, assert passes, judge yes + asserts no."""
    salida: OrderedDict[str, dict] = OrderedDict()
    total = {"juez": 0, "asserts": 0, "evaluadas": 0, "discrepa": 0}
    for d in detalle:
        cuenta = salida.setdefault(
            d["escenario"], {"juez": 0, "asserts": 0, "evaluadas": 0, "discrepa": 0}
        )
        if d["juez"] == "infra":
            continue
        claves = []
        if d["juez"] == "aprobado":
            claves.append("juez")
        if d["asserts"] != "n/a":
            claves.append("evaluadas")
            if d["asserts"] == "aprobado":
                claves.append("asserts")
        if d["juez"] == "aprobado" and d["asserts"] == "suspenso":
            claves.append("discrepa")
        for k in claves:
            cuenta[k] += 1
            total[k] += 1
    return {"escenarios": salida, "total": total}


def codigo_salida(total: dict) -> int:
    if total["suspenso"]:
        return 1
    return 2 if total["infra"] else 0


def intentos_repetidos(detalle: list[dict]) -> bool:
    """A reused round name appends to results.jsonl and overwrites earlier attempts' logs."""
    intentos = [(d["escenario"], d["intento"]) for d in detalle]
    return len(intentos) != len(set(intentos))


def formatear(detalle: list[dict], resumen: dict) -> str:
    ancho = max([len(e) for e in resumen["escenarios"]] + [len("escenario")])
    lineas = [f"{'escenario':<{ancho}}  aprobados  suspensos  infra"]
    for escenario, c in resumen["escenarios"].items():
        lineas.append(
            f"{escenario:<{ancho}}  {c['aprobado']:>9}  {c['suspenso']:>9}  {c['infra']:>5}"
        )
    t = resumen["total"]
    lineas.append(f"{'TOTAL':<{ancho}}  {t['aprobado']:>9}  {t['suspenso']:>9}  {t['infra']:>5}")
    validos = t["aprobado"] + t["suspenso"]
    tasa = resumen["tasa"]
    texto_tasa = "n/a (0 intentos validos)" if tasa is None else f"{tasa:.0%} de {validos}"
    lineas += ["", f"Tasa de aprobado sobre intentos validos: {texto_tasa}"]
    fallos = [d for d in detalle if d["veredicto"] != "aprobado"]
    if fallos:
        lineas += ["", "Fallos:"]
        for d in fallos:
            lineas.append(
                f"- {d['escenario']} #{d['intento']} [{d['veredicto']}] {d['causa'] or '-'}"
            )
    if resumen.get("con_asserts"):
        lineas += ["", *formatear_juez_vs_asserts(resumen["juez_vs_asserts"], ancho)]
    if t["infra"] and not t["suspenso"]:
        lineas += ["", "Vuelta no concluyente: hay fallos de infraestructura."]
    if intentos_repetidos(detalle):
        lineas += ["", "AVISO: intentos repetidos (nombre reutilizado); recuento no fiable."]
    return "\n".join(lineas).encode("ascii", "replace").decode("ascii")


def formatear_juez_vs_asserts(jva: dict, ancho: int) -> list[str]:
    lineas = [
        "Juez vs asserts (intentos sin fallo de infraestructura):",
        f"{'escenario':<{ancho}}  juez_ok  asserts_ok  juez_si_asserts_no",
    ]
    filas = [*jva["escenarios"].items(), ("TOTAL", jva["total"])]
    for escenario, c in filas:
        asserts_ok = f"{c['asserts']}/{c['evaluadas']}"
        lineas.append(
            f"{escenario:<{ancho}}  {c['juez']:>7}  {asserts_ok:>10}  {c['discrepa']:>18}"
        )
    n = jva["total"]["discrepa"]
    lineas += ["", f"El juez aprobo {n} llamada(s) que los asserts suspendieron."]
    return lineas


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--solo-juez"]
    if len(args) != 1:
        print("uso: uv run python evals/informe.py <nombre_o_ruta_de_la_vuelta> [--solo-juez]")
        return 64
    detalle, resumen = analizar(dir_de_vuelta(args[0]), con_asserts="--solo-juez" not in argv)
    print(formatear(detalle, resumen))
    return codigo_salida(resumen["total"])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
