import { useCallback, useRef, useState } from 'react'
import type { VueltaListItem } from './types'
import { fmtDate, pct } from './format'
import { IconCheck, IconChevron, IconSwap, Mark } from './icons'
import { Skeleton, useDismiss } from './ui'

interface SelectProps {
  kind: 'base' | 'cand'
  label: string
  rounds: VueltaListItem[]
  value: number | null
  onChange: (id: number) => void
}

function meta(r: VueltaListItem): string {
  const parts = [fmtDate(r.creada_en)]
  parts.push(r.version.etiqueta !== r.nombre ? r.version.etiqueta : `${r.repeticiones} rep · ${r.modalidad}`)
  parts.push(`N=${r.total.n}`)
  return parts.join(' · ')
}

function RoundSelect({ kind, label, rounds, value, onChange }: SelectProps) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => {
    setOpen(false)
    trigger.current?.focus()
  }, [])
  useDismiss(open, close, root)
  const current = rounds.find((r) => r.id === value)

  return (
    <div className="sel" ref={root}>
      <button
        ref={trigger}
        type="button"
        className={`sel-btn sel-${kind}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="sel-tag">{label}</span>
        <span className="sel-body">
          <span className="sel-name">{current?.nombre ?? '—'}</span>
          <span className="sel-meta">{current ? meta(current) : 'Sin selección'}</span>
        </span>
        <IconChevron className="sel-chev" />
      </button>
      {open && (
        <div className="menu" role="listbox" aria-label={`Ronda ${label.toLowerCase()}`}>
          {rounds.map((r) => (
            <button
              key={r.id}
              type="button"
              role="option"
              aria-selected={r.id === value}
              className={`menu-item${r.id === value ? ' is-on' : ''}`}
              onClick={() => {
                onChange(r.id)
                close()
              }}
            >
              <span className="menu-main">
                <span className="menu-name">{r.nombre}</span>
                <span className="menu-meta">{meta(r)}</span>
              </span>
              <span className="menu-rate">{pct(r.total.tasa)}</span>
              <span className="menu-check">{r.id === value && <IconCheck />}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

interface Props {
  rounds: VueltaListItem[] | null
  base: number | null
  cand: number | null
  onBase: (id: number) => void
  onCand: (id: number) => void
  onSwap: () => void
}

export function Topbar({ rounds, base, cand, onBase, onCand, onSwap }: Props) {
  return (
    <header className="topbar">
      <div className="topbar-in">
        <div className="brand">
          <Mark />
          <span className="brand-name">CallBench</span>
          <span className="brand-sep" aria-hidden>
            /
          </span>
          <span className="brand-sub">Scorecard</span>
        </div>
        <div className="picker">
          {rounds ? (
            <>
              <RoundSelect kind="base" label="Base" rounds={rounds} value={base} onChange={onBase} />
              <button type="button" className="icon-btn swap" onClick={onSwap} aria-label="Intercambiar base y candidata" title="Intercambiar">
                <IconSwap />
              </button>
              <RoundSelect kind="cand" label="Candidata" rounds={rounds} value={cand} onChange={onCand} />
            </>
          ) : (
            <>
              <Skeleton h={44} w={300} />
              <Skeleton h={32} w={32} />
              <Skeleton h={44} w={300} />
            </>
          )}
        </div>
        <div className="topbar-end">
          <span className="agent">
            <span className="agent-dot" />
            Ana · Pipecat
          </span>
        </div>
      </div>
    </header>
  )
}
