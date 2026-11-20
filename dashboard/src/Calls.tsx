import { useEffect, useMemo, useState } from 'react'
import type { Llamada, VueltaDetalle } from './types'
import { fmtDuration, splitScenario } from './format'
import { IconAlert, IconClose } from './icons'
import { Drawer } from './Drawer'
import { Pill, Skeleton, VerdictPill } from './ui'

export const isMismatch = (c: Llamada): boolean => c.juez.veredicto === 'aprobado' && c.asserts.veredicto === 'suspenso'

type Filter = 'todas' | 'suspenso' | 'discrepa' | 'infra'
const FILTERS: { id: Filter; label: string }[] = [
  { id: 'todas', label: 'Todas' },
  { id: 'suspenso', label: 'Suspensas' },
  { id: 'discrepa', label: 'Juez ≠ asserts' },
  { id: 'infra', label: 'Infra' },
]

function matches(c: Llamada, f: Filter): boolean {
  if (f === 'suspenso') return c.veredicto === 'suspenso'
  if (f === 'discrepa') return isMismatch(c)
  if (f === 'infra') return c.veredicto === 'infra'
  return true
}

function JudgeCell({ c }: { c: Llamada }) {
  if (c.veredicto === 'infra') return <span className="vc vc-mute">—</span>
  const v = c.juez.veredicto
  const tone = v === 'aprobado' ? 'ok' : v === 'suspenso' ? 'bad' : 'mute'
  const label = v === 'aprobado' ? 'Aprobó' : v === 'suspenso' ? 'Suspendió' : v
  return (
    <span className={`vc vc-${tone}`}>
      <i className="vc-dot" />
      {label}
      {c.juez.confianza != null && <span className="vc-conf">{c.juez.confianza.toFixed(2)}</span>}
    </span>
  )
}

function AssertCell({ c }: { c: Llamada }) {
  if (c.veredicto === 'infra') return <span className="vc vc-mute">—</span>
  const v = c.asserts.veredicto
  if (v === 'n/a') return <span className="vc vc-mute">Sin asserts</span>
  const fails = c.asserts.lista.filter((a) => a.aprobado === false).length
  const tone = v === 'aprobado' ? 'ok' : 'bad'
  return (
    <span className={`vc vc-${tone}`}>
      <i className="vc-dot" />
      {v === 'aprobado' ? 'Aprobó' : 'Suspendió'}
      <span className="vc-conf">
        {fails > 0 ? `${fails}/${c.asserts.lista.length} fallan` : `${c.asserts.lista.length}/${c.asserts.lista.length}`}
      </span>
    </span>
  )
}

interface Props {
  base: VueltaDetalle | null
  cand: VueltaDetalle | null
  scenario: string | null
  onClearScenario: () => void
}

export function Calls({ base, cand, scenario, onClearScenario }: Props) {
  const [tab, setTab] = useState<'cand' | 'base'>('cand')
  const [filter, setFilter] = useState<Filter>('todas')
  const [openId, setOpenId] = useState<number | null>(null)

  const run = tab === 'cand' ? cand : base

  // Al cambiar de pestana o de ronda el cajon deja de tener sentido.
  const runId = run?.vuelta.id ?? null
  useEffect(() => setOpenId(null), [runId])

  const groups = useMemo(() => {
    if (!run) return []
    const map = new Map<string, Llamada[]>()
    run.llamadas
      .filter((c) => matches(c, filter) && (!scenario || c.escenario === scenario))
      .forEach((c) => map.set(c.escenario, [...(map.get(c.escenario) ?? []), c]))
    return [...map.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([name, calls]) => ({
        name,
        calls: calls.sort((a, b) => a.intento - b.intento || a.ejecucion - b.ejecucion),
      }))
  }, [run, filter, scenario])

  const flat = useMemo(() => groups.flatMap((g) => g.calls), [groups])
  const counts = useMemo(() => {
    const all = run?.llamadas ?? []
    return {
      todas: all.length,
      suspenso: all.filter((c) => matches(c, 'suspenso')).length,
      discrepa: all.filter(isMismatch).length,
      infra: all.filter((c) => c.veredicto === 'infra').length,
    }
  }, [run])

  const opened = flat.find((c) => c.id === openId) ?? null
  const idx = opened ? flat.indexOf(opened) : -1

  if (!base || !cand) return <Skeleton h={320} className="skel-card" />

  return (
    <section className="card calls" id="llamadas" aria-label="Llamadas">
      <header className="card-head calls-head">
        <div>
          <h2 className="card-title">Llamadas</h2>
          <p className="card-sub">Pulsa una llamada para ver asserts y transcripción.</p>
        </div>
        <div className="calls-ctrl">
          {scenario && (
            <button type="button" className="chip chip-btn" onClick={onClearScenario}>
              {splitScenario(scenario).main}
              {splitScenario(scenario).variant && <span className="mono-dim">/{splitScenario(scenario).variant}</span>}
              <IconClose width={12} height={12} />
            </button>
          )}
          <div className="seg" role="tablist" aria-label="Ronda">
            <button type="button" role="tab" aria-selected={tab === 'cand'} className={tab === 'cand' ? 'is-on' : ''} onClick={() => setTab('cand')}>
              <i className="swatch swatch-cand" />
              Candidata <span className="seg-sub">{cand.vuelta.nombre}</span>
            </button>
            <button type="button" role="tab" aria-selected={tab === 'base'} className={tab === 'base' ? 'is-on' : ''} onClick={() => setTab('base')}>
              <i className="swatch swatch-base" />
              Base <span className="seg-sub">{base.vuelta.nombre}</span>
            </button>
          </div>
        </div>
      </header>

      <div className="filters" role="group" aria-label="Filtro de llamadas">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`fchip${filter === f.id ? ' is-on' : ''}`}
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
            <span className="fchip-n">{counts[f.id]}</span>
          </button>
        ))}
      </div>

      <div className="clist-head" aria-hidden>
        <span>Intento</span>
        <span>Veredicto</span>
        <span>Juez LLM</span>
        <span>Asserts</span>
        <span>Causa</span>
        <span className="r">Duración</span>
      </div>

      <div className="clist">
        {groups.length === 0 && <p className="muted pad">Ninguna llamada coincide con el filtro.</p>}
        {groups.map((g) => {
          const { main, variant } = splitScenario(g.name)
          const ok = g.calls.filter((c) => c.veredicto === 'aprobado').length
          const valid = g.calls.filter((c) => c.veredicto !== 'infra').length
          return (
            <div className="group" key={g.name}>
              <div className="group-head">
                <span className="scn">
                  <span className="scn-main">{main}</span>
                  {variant && <span className="scn-var">{variant}</span>}
                </span>
                <span className="group-count">
                  {ok}/{valid} aprobadas · {g.calls.length} llamadas
                </span>
              </div>
              {g.calls.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`crow${c.id === openId ? ' is-open' : ''}`}
                  onClick={() => setOpenId(c.id)}
                >
                  <span className="crow-n">#{c.intento}</span>
                  <span>
                    <VerdictPill v={c.veredicto} />
                  </span>
                  <JudgeCell c={c} />
                  <AssertCell c={c} />
                  <span className="crow-cause">
                    {isMismatch(c) && (
                      <Pill tone="amber">
                        <IconAlert width={11} height={11} /> Juez aprobó, asserts no
                      </Pill>
                    )}
                    {!isMismatch(c) && c.causa && <span className="cause-text">{c.causa}</span>}
                  </span>
                  <span className="crow-dur">{fmtDuration(c.duracion_ms)}</span>
                </button>
              ))}
            </div>
          )
        })}
      </div>

      {opened && (
        <Drawer
          call={opened}
          position={idx + 1}
          total={flat.length}
          onPrev={idx > 0 ? () => setOpenId(flat[idx - 1].id) : undefined}
          onNext={idx < flat.length - 1 ? () => setOpenId(flat[idx + 1].id) : undefined}
          onClose={() => setOpenId(null)}
        />
      )}
    </section>
  )
}
