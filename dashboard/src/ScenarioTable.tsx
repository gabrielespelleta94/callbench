import type { Cuenta, Diff, FilaDiff } from './types'
import { pct, splitScenario } from './format'
import { DeltaPp, EstadoPill, IntervalBars, Skeleton } from './ui'

function Rate({ c }: { c: Cuenta | null }) {
  if (!c) return <span className="muted">—</span>
  if (c.n === 0) return <span className="muted">0/0</span>
  return (
    <span className="rate">
      <span className="rate-k">
        {c.aprobado}/{c.n}
      </span>
      <span className="rate-p">{pct(c.tasa)}</span>
    </span>
  )
}

function Pair({ b, c, warn }: { b: number | undefined; c: number | undefined; warn?: boolean }) {
  if (b == null && c == null) return <span className="muted">—</span>
  return (
    <span className="pair">
      <span className="pair-b">{b ?? '—'}</span>
      <span className="pair-arrow">→</span>
      <span className={`pair-c${warn && (c ?? 0) > 0 ? ' is-warn' : ''}`}>{c ?? '—'}</span>
    </span>
  )
}

function Name({ name }: { name: string }) {
  const { main, variant } = splitScenario(name)
  return (
    <span className="scn">
      <span className="scn-main">{main}</span>
      {variant && <span className="scn-var">{variant}</span>}
    </span>
  )
}

function Row({ r, active, onPick }: { r: FilaDiff; active: boolean; onPick: (name: string) => void }) {
  const quiet = r.estado === 'igual' || r.estado === 'no_concluyente'
  return (
    <tr
      className={`row${active ? ' is-active' : ''}`}
      tabIndex={0}
      aria-selected={active}
      onClick={() => onPick(r.escenario)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onPick(r.escenario)
        }
      }}
    >
      <td>
        <Name name={r.escenario} />
      </td>
      <td className="num">
        <Rate c={r.base} />
      </td>
      <td className="num">
        <Rate c={r.candidata} />
      </td>
      <td>
        <IntervalBars
          rows={[
            { kind: 'base', ic: r.base?.ic ?? null, tasa: r.base?.tasa ?? null, label: 'Base' },
            { kind: 'cand', ic: r.candidata?.ic ?? null, tasa: r.candidata?.tasa ?? null, label: 'Candidata' },
          ]}
        />
      </td>
      <td className="num">
        <DeltaPp delta={r.delta} quiet={quiet} />
      </td>
      <td>
        <EstadoPill estado={r.estado} motivo={r.motivo} />
      </td>
      <td className="num">
        <Pair b={r.base?.infra} c={r.candidata?.infra} warn />
      </td>
      <td className="num">
        <Pair b={r.base?.discrepa} c={r.candidata?.discrepa} warn />
      </td>
    </tr>
  )
}

interface Props {
  diff: Diff | null
  loading: boolean
  selected: string | null
  onPick: (name: string) => void
}

export function ScenarioTable({ diff, loading, selected, onPick }: Props) {
  if (!diff) return <Skeleton h={340} className="skel-card" />
  const t = diff.total
  const tDelta = t.base.tasa != null && t.candidata.tasa != null ? t.candidata.tasa - t.base.tasa : null
  return (
    <section className={`card table-card${loading ? ' is-stale' : ''}`} aria-label="Escenarios">
      <header className="card-head">
        <div>
          <h2 className="card-title">Escenarios</h2>
          <p className="card-sub">Pulsa una fila para filtrar las llamadas de ese escenario.</p>
        </div>
        <div className="legend">
          <span>
            <i className="swatch swatch-base" />
            Base
          </span>
          <span>
            <i className="swatch swatch-cand" />
            Candidata
          </span>
          <span className="muted">intervalo de Wilson 95%</span>
        </div>
      </header>
      <table className="tbl">
        <colgroup>
          <col style={{ width: '25%' }} />
          <col style={{ width: '9%' }} />
          <col style={{ width: '9%' }} />
          <col style={{ width: '19%' }} />
          <col style={{ width: '8%' }} />
          <col style={{ width: '12%' }} />
          <col style={{ width: '7%' }} />
          <col style={{ width: '11%' }} />
        </colgroup>
        <thead>
          <tr>
            <th>Escenario</th>
            <th className="num">Base</th>
            <th className="num">Candidata</th>
            <th>Intervalo 0–100%</th>
            <th className="num">Δ</th>
            <th>Estado</th>
            <th className="num">Infra</th>
            <th className="num" title="El juez aprobó, los asserts suspendieron">
              Juez ≠ asserts
            </th>
          </tr>
        </thead>
        <tbody>
          {diff.escenarios.map((r) => (
            <Row key={r.escenario} r={r} active={selected === r.escenario} onPick={onPick} />
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td>
              <span className="scn-main">Total</span>
            </td>
            <td className="num">
              <Rate c={t.base} />
            </td>
            <td className="num">
              <Rate c={t.candidata} />
            </td>
            <td>
              <IntervalBars
                rows={[
                  { kind: 'base', ic: t.base.ic, tasa: t.base.tasa, label: 'Base' },
                  { kind: 'cand', ic: t.candidata.ic, tasa: t.candidata.tasa, label: 'Candidata' },
                ]}
              />
            </td>
            <td className="num">
              <DeltaPp delta={tDelta} />
            </td>
            <td />
            <td className="num">
              <Pair b={t.base.infra} c={t.candidata.infra} warn />
            </td>
            <td className="num">
              <Pair b={t.base.discrepa} c={t.candidata.discrepa} warn />
            </td>
          </tr>
        </tfoot>
      </table>
    </section>
  )
}
