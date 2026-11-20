import { useCallback, useRef, useState } from 'react'
import type { Diff } from './types'
import { IconAlert, IconShieldCheck, IconShieldQ, IconShieldX } from './icons'
import { Skeleton, useDismiss } from './ui'

const META = {
  0: { cls: 'ok', Icon: IconShieldCheck, label: 'Sin regresiones' },
  1: { cls: 'bad', Icon: IconShieldX, label: 'La candidata empeora' },
  2: { cls: 'warn', Icon: IconShieldQ, label: 'No concluyente' },
} as const

function GateRule() {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLSpanElement>(null)
  const close = useCallback(() => setOpen(false), [])
  useDismiss(open, close, root)
  return (
    <span className="gate" ref={root}>
      <button
        type="button"
        className="help-btn"
        aria-expanded={open}
        aria-label="Regla del gate"
        onClick={() => setOpen((o) => !o)}
      >
        ?
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Regla del gate">
          <p className="popover-title">Regla del gate</p>
          <p>
            Un escenario <b>empeora</b> si la candidata pierde al menos 2 aprobadas respecto a lo que predice la tasa
            base <i>y</i> su intervalo de Wilson al 95% queda entero por debajo de la tasa base (o ambas rondas tienen
            N ≥ 10).
          </p>
          <p>
            Es <b>no concluyente</b> si no hay llamadas válidas o hay más infra que válidas. Infra no cuenta como
            suspenso.
          </p>
          <p className="popover-foot">
            <span className="mono">exit 0</span> sin regresiones · <span className="mono">exit 1</span> empeora ·{' '}
            <span className="mono">exit 2</span> no concluyente
          </p>
        </div>
      )}
    </span>
  )
}

export function Verdict({ diff, loading }: { diff: Diff | null; loading: boolean }) {
  if (!diff) return <Skeleton h={92} className="skel-card" />
  const v = diff.veredicto
  const m = META[v.codigo]
  const counts = { mejora: 0, empeora: 0, igual: 0, no_concluyente: 0, nuevo: 0 }
  diff.escenarios.forEach((e) => (counts[e.estado] += 1))
  const sub = `${diff.escenarios.length} escenarios comparados · ${counts.mejora} mejoran · ${counts.empeora} empeoran · ${counts.igual} sin cambio significativo${
    counts.no_concluyente ? ` · ${counts.no_concluyente} no concluyentes` : ''
  }`
  return (
    <section className={`verdict verdict-${m.cls}${loading ? ' is-stale' : ''}`} aria-live="polite">
      <div className="verdict-icon">
        <m.Icon width={20} height={20} />
      </div>
      <div className="verdict-main">
        <div className="verdict-head">
          <h1 className="verdict-title">{v.texto || m.label}</h1>
          <GateRule />
        </div>
        <p className="verdict-sub">{sub}</p>
        {(v.motivos.length > 0 || v.dudas.length > 0) && (
          <ul className="reasons">
            {v.motivos.map((t) => (
              <li key={t} className="reason reason-bad">
                <IconAlert width={13} height={13} />
                {t}
              </li>
            ))}
            {v.dudas.map((t) => (
              <li key={t} className="reason reason-warn">
                <IconAlert width={13} height={13} />
                {t}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="verdict-exit">
        <span className="exit-cmd">
          <span className="exit-prompt">$</span> callbench diff {diff.base.nombre} {diff.candidata.nombre}
        </span>
        <span className={`exit-code exit-${m.cls}`}>exit {v.codigo}</span>
      </div>
    </section>
  )
}
