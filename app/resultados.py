"""Scorecard API: rounds stored in Postgres, their calls, and the diff between two.

    GET /vueltas                          every round with its totals
    GET /vueltas/{id}                     summary + calls (transcript, judge, asserts, metrics)
    GET /diff?base=<id>&candidata=<id>    per-scenario comparison and the gate verdict

The grading and the regression rule live in bench/resultados.py, shared with the CLI gate
(tools/comparar.py), so the dashboard and CI never disagree.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.conexion import get_session
from bench import resultados as res

router = APIRouter(tags=["resultados"])


async def _vueltas(sesion: AsyncSession, vuelta_id: int | None = None) -> list[dict]:
    sql = res.SQL_VUELTAS + (" WHERE v.id = :id" if vuelta_id is not None else "") + " ORDER BY v.id DESC"
    filas = (await sesion.execute(text(sql), {"id": vuelta_id})).mappings().all()
    return [res.info_vuelta(dict(f)) for f in filas]


async def _llamadas(sesion: AsyncSession, vuelta_id: int) -> list[dict]:
    filas = (await sesion.execute(text(res.SQL_LLAMADAS), {"vuelta_id": vuelta_id})).mappings().all()
    llamadas = [res.llamada_de_fila_bd(dict(f)) for f in filas]
    return sorted(llamadas, key=lambda ll: (ll["escenario"], ll["intento"] or 0))


async def _una(sesion: AsyncSession, vuelta_id: int) -> tuple[dict, list[dict]]:
    vueltas = await _vueltas(sesion, vuelta_id)
    if not vueltas:
        raise HTTPException(status_code=404, detail=f"No existe la vuelta {vuelta_id}")
    return vueltas[0], await _llamadas(sesion, vuelta_id)


@router.get("/vueltas")
async def listar_vueltas(sesion: AsyncSession = Depends(get_session)) -> list[dict]:
    salida = []
    for v in await _vueltas(sesion):
        resumen = res.resumir(await _llamadas(sesion, v["id"]))
        salida.append(v | {"total": resumen["total"], "juez_vs_asserts": _jva(resumen["total"])})
    return salida


def _jva(total: dict) -> dict:
    return {k: total[k] for k in ("juez_ok", "asserts_ok", "evaluadas", "discrepa")}


@router.get("/vueltas/{vuelta_id}")
async def ver_vuelta(vuelta_id: int, sesion: AsyncSession = Depends(get_session)) -> dict:
    vuelta, llamadas = await _una(sesion, vuelta_id)
    return {"vuelta": vuelta, "resumen": res.resumir(llamadas), "llamadas": llamadas}


@router.get("/diff")
async def diff(base: int, candidata: int, sesion: AsyncSession = Depends(get_session)) -> dict:
    vb, lb = await _una(sesion, base)
    vc, lc = await _una(sesion, candidata)
    return {"base": vb, "candidata": vc, **res.comparar(res.resumir(lb), res.resumir(lc))}
