import { useEffect, useRef, useState } from 'react'
import type { AssertItem, Llamada, Mensaje } from './types'
import { fmtDuration, fmtMoney, fmtSec, splitScenario } from './format'
import { IconAlert, IconCheck, IconClose, IconMinus, IconNext, IconPrev, IconX } from './icons'
import { VerdictPill } from './ui'

const label = (v: string) => (v === 'aprobado' ? 'Aprobó' : v === 'suspenso' ? 'Suspendió' : v === 'n/a' ? 'Sin asserts' : v)

type Tool = Extract<Mensaje, { role: 'tool_call' }>

function argString(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ')
}

function ToolBlock({ m }: { m: Tool }) {
  const failed = m.resultado != null && (m.resultado as { ok?: unknown }).ok === false
  return (
    <div className={`tool${failed ? ' tool-bad' : ''}`}>
      <div className="tool-line">
        <span className="tool-tag">tool</span>
        <span className="tool-name">{m.name}</span>
        <span className="tool-args">({argString(m.arguments)})</span>
        {m.cancelled && <span className="chip chip-amber">cancelada</span>}
        {failed && <span className="chip chip-red">error</span>}
      </div>
      {m.resultado != null && (
        <details className="tool-res">
          <summary>resultado</summary>
          <pre>{JSON.stringify(m.resultado, null, 2)}</pre>
        </details>
      )}
    </div>
  )
}

function Transcript({ items }: { items: Mensaje[] }) {
  return (
    <div className="chat">
      {items.map((m, i) =>
        m.role === 'tool_call' ? (
          <ToolBlock key={i} m={m} />
        ) : (
          <div key={i} className={`msg msg-${m.role}`}>
            <span className="msg-who">{m.role === 'assistant' ? 'Ana' : 'Paciente'}</span>
            <p className="bubble">{m.content}</p>
          </div>
        ),
      )}
    </div>
  )
}

function AssertRow({ a }: { a: AssertItem }) {
  const state = a.aprobado === true ? 'ok' : a.aprobado === false ? 'bad' : 'na'
  return (
    <li className={`assert assert-${state}`}>
      <span className="assert-ico">
        {state === 'ok' ? <IconCheck width={13} height={13} /> : state === 'bad' ? <IconX width={13} height={13} /> : <IconMinus width={13} height={13} />}
      </span>
      <span className="assert-body">
        <span className="assert-name">{a.nombre}</span>
        {a.motivo && <span className="assert-why">{a.motivo}</span>}
      </span>
      <span className="assert-state">{state === 'ok' ? 'Pasa' : state === 'bad' ? 'Falla' : 'n.a.'}</span>
    </li>
  )
}

interface Props {
  call: Llamada
  position: number
  total: number
  onPrev?: () => void
  onNext?: () => void
  onClose: () => void
}

export function Drawer({ call, position, total, onPrev, onNext, onClose }: Props) {
  const [shown, setShown] = useState(false)
  const panel = useRef<HTMLElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const opener = useRef<Element | null>(null)
  const closing = useRef(false)

  const requestClose = () => {
    if (closing.current) return
    closing.current = true
    setShown(false)
    window.setTimeout(() => {
      onClose()
      if (opener.current instanceof HTMLElement) opener.current.focus()
    }, 150)
  }

  useEffect(() => {
    opener.current = document.activeElement
    const id = requestAnimationFrame(() => {
      setShown(true)
      panel.current?.focus()
    })
    return () => cancelAnimationFrame(id)
  }, [])

  // Al saltar de una llamada a otra vuelve arriba.
  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 })
  }, [call.id])

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') requestClose()
      else if (e.key === 'ArrowLeft' && onPrev && !(e.target instanceof HTMLInputElement)) onPrev()
      else if (e.key === 'ArrowRight' && onNext) onNext()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })

  const mismatch = call.juez.veredicto === 'aprobado' && call.asserts.veredicto === 'suspenso'
  const asserts = [...call.asserts.lista].sort((a, b) => {
    const w = (x: AssertItem) => (x.aprobado === false ? 0 : x.aprobado === null ? 2 : 1)
    return w(a) - w(b)
  })
  const { main, variant } = splitScenario(call.escenario)
  const m = call.metricas

  return (
    <div className={`drawer-root${shown ? ' is-open' : ''}`}>
      <div className="scrim" onClick={requestClose} />
      <aside className="drawer" ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`Llamada ${call.escenario} intento ${call.intento}`}>
        <header className="drawer-head">
          <div className="drawer-title">
            <span className="scn">
              <span className="scn-main">{main}</span>
              {variant && <span className="scn-var">{variant}</span>}
            </span>
            <span className="drawer-sub">
              Intento #{call.intento} · ejecución {call.ejecucion} · llamada #{call.id} · {position} de {total}
            </span>
          </div>
          <div className="drawer-actions">
            <button type="button" className="icon-btn" onClick={onPrev} disabled={!onPrev} aria-label="Llamada anterior" title="Anterior (←)">
              <IconPrev />
            </button>
            <button type="button" className="icon-btn" onClick={onNext} disabled={!onNext} aria-label="Llamada siguiente" title="Siguiente (→)">
              <IconNext />
            </button>
            <button type="button" className="icon-btn" onClick={requestClose} aria-label="Cerrar" title="Cerrar (Esc)">
              <IconClose />
            </button>
          </div>
        </header>

        <div className="drawer-body" ref={scroller}>
          <section className="dsec">
            <div className="dgrid">
              <div className="dcell">
                <span className="eyebrow">Veredicto final</span>
                <VerdictPill v={call.veredicto} />
              </div>
              <div className="dcell">
                <span className="eyebrow">Juez LLM</span>
                <span className="dval">{label(call.juez.veredicto)}</span>
                {call.juez.confianza != null && <span className="dsub">confianza {call.juez.confianza.toFixed(2)}</span>}
              </div>
              <div className="dcell">
                <span className="eyebrow">Asserts</span>
                <span className="dval">{label(call.asserts.veredicto)}</span>
                <span className="dsub">{call.asserts.lista.filter((a) => a.aprobado === false).length} de {call.asserts.lista.length} fallan</span>
              </div>
              <div className="dcell">
                <span className="eyebrow">Duración</span>
                <span className="dval">{fmtDuration(call.duracion_ms)}</span>
              </div>
            </div>
            {mismatch && (
              <div className="callout">
                <IconAlert width={15} height={15} />
                <p>
                  <b>El juez aprobó, los asserts suspendieron.</b> El veredicto final manda el determinista: el juez
                  LLM solo habría dado esta llamada por buena.
                </p>
              </div>
            )}
            {call.juez.motivo && <p className="dnote">Juez: {call.juez.motivo}</p>}
          </section>

          {call.causa && (
            <section className="dsec">
              <h3 className="dh">Causa</h3>
              <pre className="cause-block">{call.causa}</pre>
            </section>
          )}

          <section className="dsec">
            <h3 className="dh">
              Asserts <span className="dh-n">{asserts.filter((a) => a.aprobado === false).length} fallan · {asserts.length}</span>
            </h3>
            {asserts.length === 0 ? (
              <p className="muted">Esta llamada no tiene asserts deterministas.</p>
            ) : (
              <ul className="asserts">
                {asserts.map((a) => (
                  <AssertRow key={a.nombre} a={a} />
                ))}
              </ul>
            )}
          </section>

          {m && (
            <section className="dsec">
              <h3 className="dh">Métricas</h3>
              <div className="dgrid">
                <div className="dcell">
                  <span className="eyebrow">Voz a voz</span>
                  <span className="dval">{m.voice_to_voice.map((x) => fmtSec(x)).join(' · ') || '—'}</span>
                </div>
                <div className="dcell">
                  <span className="eyebrow">TTFB STT / LLM / TTS</span>
                  <span className="dval">
                    {[m.ttfb.stt, m.ttfb.llm, m.ttfb.tts].map((a) => (a.length ? fmtSec(a.reduce((s, x) => s + x, 0) / a.length) : '—')).join(' / ')}
                  </span>
                </div>
                <div className="dcell">
                  <span className="eyebrow">Coste</span>
                  <span className="dval">{m.coste ? fmtMoney(m.coste.total) : '—'}</span>
                </div>
              </div>
            </section>
          )}

          <section className="dsec">
            <h3 className="dh">
              Transcripción {call.transcripcion && <span className="dh-n">{call.transcripcion.length} turnos</span>}
            </h3>
            {call.transcripcion ? (
              <Transcript items={call.transcripcion} />
            ) : (
              <p className="muted">Sin transcripción: la llamada no llegó a ejecutarse (fallo de infraestructura).</p>
            )}
          </section>
        </div>
      </aside>
    </div>
  )
}
