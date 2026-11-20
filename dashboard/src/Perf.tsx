import type { CosteResumen, Diff, DeltaPct, Pct } from './types'
import { fmtMoney, fmtRel, fmtSec } from './format'
import { IconWaveOff } from './icons'
import { Skeleton } from './ui'

/** Latencia y coste: menos es mejor, asi que subir es malo. */
function Rel({ v }: { v: number | null }) {
  if (v == null) return <span className="muted">—</span>
  const r = Math.round(v * 100)
  const cls = r === 0 ? 'delta-0' : r > 0 ? 'delta-down' : 'delta-up'
  return <span className={`delta ${cls}${Math.abs(v) < 0.05 ? ' delta-quiet' : ''}`}>{fmtRel(v)}</span>
}

const hasData = (p: Pct) => p.n > 0 && (p.p50 != null || p.p95 != null)

function LatRow({ label, d }: { label: string; d: DeltaPct }) {
  return (
    <tr>
      <td>
        <span className="scn-main">{label}</span>
        <span className="n-note">
          n {d.base.n} → {d.candidata.n}
        </span>
      </td>
      <td className="num">{fmtSec(d.base.p50)}</td>
      <td className="num">{fmtSec(d.candidata.p50)}</td>
      <td className="num">
        <Rel v={d.delta_rel.p50} />
      </td>
      <td className="num sep">{fmtSec(d.base.p95)}</td>
      <td className="num">{fmtSec(d.candidata.p95)}</td>
      <td className="num">
        <Rel v={d.delta_rel.p95} />
      </td>
    </tr>
  )
}

function LatHead() {
  return (
    <thead>
      <tr>
        <th rowSpan={2}>Etapa</th>
        <th colSpan={3} className="num grp">
          p50
        </th>
        <th colSpan={3} className="num grp sep">
          p95
        </th>
      </tr>
      <tr>
        <th className="num">Base</th>
        <th className="num">Cand.</th>
        <th className="num">Δ</th>
        <th className="num sep">Base</th>
        <th className="num">Cand.</th>
        <th className="num">Δ</th>
      </tr>
    </thead>
  )
}

function relOf(b: number | null, c: number | null): number | null {
  return b != null && b > 0 && c != null ? (c - b) / b : null
}

function CostCard({ base, cand }: { base: CosteResumen; cand: CosteResumen }) {
  const rows: { label: string; b: number | null; c: number | null }[] = [
    { label: 'Media por llamada', b: base.media, c: cand.media },
    { label: 'p50', b: base.p50, c: cand.p50 },
    { label: 'p95', b: base.p95, c: cand.p95 },
  ]
  return (
    <table className="tbl tbl-sm">
      <thead>
        <tr>
          <th>Coste por llamada</th>
          <th className="num">Base</th>
          <th className="num">Cand.</th>
          <th className="num">Δ</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <td>
              <span className="scn-main">{r.label}</span>
            </td>
            <td className="num">{fmtMoney(r.b, base.moneda)}</td>
            <td className="num">{fmtMoney(r.c, cand.moneda)}</td>
            <td className="num">
              <Rel v={relOf(r.b, r.c)} />
            </td>
          </tr>
        ))}
        <tr>
          <td>
            <span className="n-note n-note-solo">
              n {base.n} → {cand.n} llamadas · {cand.moneda}
            </span>
          </td>
          <td colSpan={3} />
        </tr>
      </tbody>
    </table>
  )
}

const GHOST = ['Voz a voz', 'TTFB · STT', 'TTFB · LLM', 'TTFB · TTS', 'Coste / llamada']

function Empty() {
  return (
    <div className="empty">
      <div className="empty-msg">
        <span className="empty-ico">
          <IconWaveOff />
        </span>
        <p className="empty-title">Sin métricas</p>
        <p className="empty-text">
          Sin métricas: vueltas en modalidad texto; la latencia voz a voz y el coste se miden en modalidad audio.
        </p>
      </div>
      <div className="ghost" aria-hidden>
        <div className="ghost-head">
          <span>Métrica</span>
          <span>Base</span>
          <span>Cand.</span>
          <span>Δ</span>
        </div>
        {GHOST.map((g) => (
          <div className="ghost-row" key={g}>
            <span>{g}</span>
            <span>—</span>
            <span>—</span>
            <span>—</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Perf({ diff, loading }: { diff: Diff | null; loading: boolean }) {
  if (!diff) return <Skeleton h={230} className="skel-card" />
  const { voice_to_voice: v2v, ttfb } = diff.latencia
  const latData = [v2v, ttfb.stt, ttfb.llm, ttfb.tts].some((d) => hasData(d.base) || hasData(d.candidata))
  const costData = diff.coste.base.n > 0 || diff.coste.candidata.n > 0
  const any = latData || costData
  return (
    <section className={`card perf${loading ? ' is-stale' : ''}`} aria-label="Latencia y coste">
      <header className="card-head">
        <div>
          <h2 className="card-title">Latencia y coste</h2>
          <p className="card-sub">
            Voz a voz y TTFB por etapa (STT, LLM, TTS); coste por llamada. Menos es mejor.
          </p>
        </div>
        {any && v2v.medible && v2v.empeora && <span className="chip chip-red">Voz a voz empeora</span>}
      </header>
      {!any ? (
        <Empty />
      ) : (
        <div className="perf-grid">
          <div>
            {latData ? (
              <table className="tbl tbl-sm">
                <LatHead />
                <tbody>
                  <LatRow label="Voz a voz" d={v2v} />
                  <LatRow label="TTFB · STT" d={ttfb.stt} />
                  <LatRow label="TTFB · LLM" d={ttfb.llm} />
                  <LatRow label="TTFB · TTS" d={ttfb.tts} />
                </tbody>
              </table>
            ) : (
              <p className="muted pad">Sin latencia medida en estas rondas.</p>
            )}
          </div>
          <div>
            {costData ? (
              <CostCard base={diff.coste.base} cand={diff.coste.candidata} />
            ) : (
              <p className="muted pad">Sin coste medido en estas rondas.</p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
