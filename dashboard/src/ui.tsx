import { useEffect, type ReactNode, type RefObject } from 'react'
import type { Estado, Veredicto } from './types'
import { fmtPp } from './format'

export type Tone = 'green' | 'red' | 'amber' | 'blue' | 'neutral'

export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`pill pill-${tone}`}>
      <i className="pill-dot" />
      {children}
    </span>
  )
}

const ESTADO: Record<Estado, { tone: Tone; label: string }> = {
  empeora: { tone: 'red', label: 'Empeora' },
  mejora: { tone: 'green', label: 'Mejora' },
  igual: { tone: 'neutral', label: 'Igual' },
  no_concluyente: { tone: 'amber', label: 'No concluyente' },
  nuevo: { tone: 'blue', label: 'Nuevo' },
}

export function EstadoPill({ estado, motivo }: { estado: Estado; motivo: string }) {
  const { tone, label } = ESTADO[estado]
  return (
    <Tip text={motivo || label}>
      <Pill tone={tone}>{label}</Pill>
    </Tip>
  )
}

const VER: Record<string, { tone: Tone; label: string }> = {
  aprobado: { tone: 'green', label: 'Aprobada' },
  suspenso: { tone: 'red', label: 'Suspensa' },
  infra: { tone: 'amber', label: 'Infra' },
}
export function VerdictPill({ v }: { v: Veredicto }) {
  const { tone, label } = VER[v] ?? { tone: 'neutral' as Tone, label: v }
  return <Pill tone={tone}>{label}</Pill>
}

export function Tip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className="tip" tabIndex={0} data-tip={text}>
      {children}
    </span>
  )
}

/** Delta en pp coloreado. `quiet` atenua los cambios que caen dentro del ruido. */
export function DeltaPp({ delta, quiet }: { delta: number | null; quiet?: boolean }) {
  if (delta == null) return <span className="delta delta-0">—</span>
  const v = Math.round(delta * 100)
  const cls = v > 0 ? 'delta-up' : v < 0 ? 'delta-down' : 'delta-0'
  return <span className={`delta ${cls}${quiet ? ' delta-quiet' : ''}`}>{fmtPp(delta)}</span>
}

export interface Interval {
  ic: [number, number] | null
  tasa: number | null
  kind: 'base' | 'cand'
  label: string
}

/** Rangos de Wilson 95% de base y candidata sobre una pista 0-100%. */
export function IntervalBars({ rows, tall }: { rows: Interval[]; tall?: boolean }) {
  const title = rows
    .map((r) =>
      r.ic && r.tasa != null
        ? `${r.label}: ${Math.round(r.tasa * 100)}% (IC95 ${Math.round(r.ic[0] * 100)}–${Math.round(r.ic[1] * 100)}%)`
        : `${r.label}: sin muestra válida`,
    )
    .join('\n')
  return (
    <div className={`ci${tall ? ' ci-tall' : ''}`} role="img" aria-label={title} title={title}>
      <i className="ci-mid" />
      {rows.map((r) => (
        <div key={r.kind} className={`ci-row ci-${r.kind}`}>
          <span className="ci-track" />
          {r.ic && r.tasa != null && (
            <>
              <span
                className="ci-range"
                style={{ left: `${r.ic[0] * 100}%`, width: `${Math.max((r.ic[1] - r.ic[0]) * 100, 0.8)}%` }}
              />
              <span className="ci-dot" style={{ left: `${r.tasa * 100}%` }} />
            </>
          )}
        </div>
      ))}
    </div>
  )
}

export function Skeleton({ h, w, className = '' }: { h: number; w?: number | string; className?: string }) {
  return <div className={`skel ${className}`} style={{ height: h, width: w }} aria-hidden />
}

/** Cierra al pulsar fuera o Escape (en captura, para que no cierre tambien el cajon). */
export function useDismiss(open: boolean, onClose: () => void, ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return
    const down = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopImmediatePropagation()
        onClose()
      }
    }
    document.addEventListener('pointerdown', down)
    window.addEventListener('keydown', key, true)
    return () => {
      document.removeEventListener('pointerdown', down)
      window.removeEventListener('keydown', key, true)
    }
  }, [open, onClose, ref])
}
