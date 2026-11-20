import type { Cuenta, Diff } from './types'
import { pct } from './format'
import { DeltaPp, IntervalBars, Skeleton } from './ui'

function icText(c: Cuenta): string {
  return c.ic ? `IC95 ${Math.round(c.ic[0] * 100)}–${Math.round(c.ic[1] * 100)}%` : 'sin muestra'
}

function PassRate({ base, cand }: { base: Cuenta; cand: Cuenta }) {
  const delta = base.tasa != null && cand.tasa != null ? cand.tasa - base.tasa : null
  return (
    <article className="card kpi">
      <header className="kpi-head">
        <span className="eyebrow">Tasa de aprobación global</span>
      </header>
      <div className="kpi-figure">
        <span className="big">{pct(cand.tasa)}</span>
        <span className="from">
          desde <b>{pct(base.tasa)}</b>
        </span>
        <span className="kpi-delta">
          <DeltaPp delta={delta} />
        </span>
      </div>
      <div className="kpi-ci">
        <IntervalBars
          tall
          rows={[
            { kind: 'base', ic: base.ic, tasa: base.tasa, label: 'Base' },
            { kind: 'cand', ic: cand.ic, tasa: cand.tasa, label: 'Candidata' },
          ]}
        />
        <div className="ci-legend">
          <span>
            <i className="swatch swatch-base" />
            Base {base.aprobado}/{base.n} · {icText(base)}
          </span>
          <span>
            <i className="swatch swatch-cand" />
            Candidata {cand.aprobado}/{cand.n} · {icText(cand)}
          </span>
        </div>
      </div>
    </article>
  )
}

function Sample({ base, cand }: { base: Cuenta; cand: Cuenta }) {
  const row = (label: string, b: number, c: number, warn?: boolean) => (
    <div className="mini-row">
      <span className="mini-label">{label}</span>
      <span className="mini-val">{b}</span>
      <span className="mini-arrow">→</span>
      <span className={`mini-val mini-cand${warn && c > 0 ? ' is-warn' : ''}`}>{c}</span>
    </div>
  )
  return (
    <article className="card kpi">
      <header className="kpi-head">
        <span className="eyebrow">Muestra</span>
      </header>
      <div className="kpi-figure">
        <span className="big">{cand.n}</span>
        <span className="from">
          llamadas válidas <span className="muted">(base {base.n})</span>
        </span>
      </div>
      <div className="mini">
        {row('Aprobadas', base.aprobado, cand.aprobado)}
        {row('Suspensas', base.suspenso, cand.suspenso)}
        {row('Infra (no cuenta)', base.infra, cand.infra, true)}
      </div>
    </article>
  )
}

function inflation(c: Cuenta): number | null {
  return c.n > 0 && c.tasa != null ? c.juez_ok / c.n - c.tasa : null
}

function KeyCol({ label, kind, c }: { label: string; kind: 'base' | 'cand'; c: Cuenta }) {
  const share = c.evaluadas > 0 ? (c.discrepa / c.evaluadas) * 100 : 0
  const infl = inflation(c)
  return (
    <div className={`key-col key-${kind}`}>
      <div className="key-label">
        <i className={`swatch swatch-${kind}`} />
        {label}
      </div>
      <div className="key-num">
        <span className="big big-key">{c.discrepa}</span>
        <span className="key-of">
          de {c.evaluadas} <span className="muted">evaluadas</span>
        </span>
      </div>
      <div
        className="key-bar"
        role="img"
        aria-label={`${c.discrepa} de ${c.evaluadas} llamadas: juez aprobó, asserts suspendieron`}
      >
        <span style={{ width: `${share}%` }} />
      </div>
      <div className="key-line">
        Juez solo <b>{c.n > 0 ? pct(c.juez_ok / c.n) : '—'}</b> · con asserts <b>{pct(c.tasa)}</b>
        {infl != null && infl > 0.005 && <span className="key-infl" style={{ whiteSpace: 'nowrap' }}> · +{Math.round(infl * 100)} pp</span>}
      </div>
    </div>
  )
}

function Key({ base, cand }: { base: Cuenta; cand: Cuenta }) {
  const total = base.discrepa + cand.discrepa
  return (
    <article className="card kpi kpi-key">
      <header className="kpi-head">
        <span className="eyebrow eyebrow-amber">Hallazgo clave</span>
      </header>
      <h2 className="key-title">El juez aprobó, los asserts suspendieron</h2>
      <div className="key-cols">
        <KeyCol label="Base" kind="base" c={base} />
        <KeyCol label="Candidata" kind="cand" c={cand} />
      </div>
      <p className="key-foot">
        {total > 0
          ? 'Un juez LLM por sí solo es demasiado indulgente: da por buenas llamadas que los asserts deterministas ven rotas (reserva sin confirmación, datos inventados). Por eso el veredicto final es el de los asserts.'
          : 'En esta pareja de rondas no hay discrepancias entre el juez y los asserts.'}
      </p>
    </article>
  )
}

export function Kpis({ diff, loading }: { diff: Diff | null; loading: boolean }) {
  if (!diff)
    return (
      <div className="kpis">
        <Skeleton h={188} className="skel-card" />
        <Skeleton h={188} className="skel-card" />
        <Skeleton h={188} className="skel-card" />
      </div>
    )
  const { base, candidata } = diff.total
  return (
    <div className={`kpis${loading ? ' is-stale' : ''}`}>
      <PassRate base={base} cand={candidata} />
      <Sample base={base} cand={candidata} />
      <Key base={base} cand={candidata} />
    </div>
  )
}

