import { useCallback, useEffect, useState } from 'react'
import { fetchDiff, fetchVuelta, fetchVueltas } from './api'
import type { Diff, VueltaDetalle, VueltaListItem } from './types'
import { Topbar } from './Topbar'
import { Verdict } from './Verdict'
import { Kpis } from './Kpis'
import { ScenarioTable } from './ScenarioTable'
import { Perf } from './Perf'
import { Calls } from './Calls'
import { IconAlert, IconRefresh } from './icons'

interface Selection {
  base: number | null
  cand: number | null
}

function readUrl(): Selection {
  const q = new URLSearchParams(window.location.search)
  const num = (k: string) => {
    const v = Number(q.get(k))
    return Number.isInteger(v) && v > 0 ? v : null
  }
  return { base: num('base'), cand: num('candidata') }
}

function writeUrl(sel: Selection) {
  const q = new URLSearchParams()
  if (sel.base != null) q.set('base', String(sel.base))
  if (sel.cand != null) q.set('candidata', String(sel.cand))
  window.history.replaceState(null, '', `?${q.toString()}`)
}

/** base-c1 -> final-lunes si existen; si no, las dos rondas mas recientes. */
function defaults(rounds: VueltaListItem[]): Selection {
  const byName = (n: string) => rounds.find((r) => r.nombre === n)
  const b = byName('base-c1')
  const c = byName('final-lunes')
  if (b && c) return { base: b.id, cand: c.id }
  const sorted = [...rounds].sort((x, y) => y.creada_en.localeCompare(x.creada_en))
  return { base: sorted[1]?.id ?? sorted[0]?.id ?? null, cand: sorted[0]?.id ?? null }
}

interface Bundle {
  diff: Diff
  base: VueltaDetalle
  cand: VueltaDetalle
}

function useBundle(base: number | null, cand: number | null) {
  const [data, setData] = useState<Bundle | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(false)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (base == null || cand == null) return
    const ac = new AbortController()
    setLoading(true)
    setError(null)
    Promise.all([fetchDiff(base, cand, ac.signal), fetchVuelta(base, ac.signal), fetchVuelta(cand, ac.signal)])
      .then(([diff, b, c]) => {
        if (ac.signal.aborted) return
        setData({ diff, base: b, cand: c })
        setLoading(false)
      })
      .catch((e: Error) => {
        if (e.name === 'AbortError') return
        setError(e)
        setLoading(false)
      })
    return () => ac.abort()
  }, [base, cand, nonce])

  return { data, error, loading, retry: () => setNonce((n) => n + 1) }
}

function ErrorState({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="error card" role="alert">
      <span className="error-ico">
        <IconAlert width={18} height={18} />
      </span>
      <div className="error-body">
        <h2 className="error-title">No se pudo cargar el scorecard</h2>
        <p className="error-text">{error.message}. Arranca la API y vuelve a intentarlo:</p>
        <pre className="error-cmd">uv run uvicorn app.main:app --port 8005</pre>
        <p className="error-hint">
          El dashboard proxea <span className="mono">/api</span> a <span className="mono">127.0.0.1:8005</span>.
        </p>
      </div>
      <button type="button" className="btn" onClick={onRetry}>
        <IconRefresh /> Reintentar
      </button>
    </div>
  )
}

export default function App() {
  const [rounds, setRounds] = useState<VueltaListItem[] | null>(null)
  const [listError, setListError] = useState<Error | null>(null)
  const [sel, setSel] = useState<Selection>(readUrl)
  const [scenario, setScenario] = useState<string | null>(null)
  const [listNonce, setListNonce] = useState(0)

  useEffect(() => {
    const ac = new AbortController()
    setListError(null)
    fetchVueltas(ac.signal)
      .then((list) => {
        setRounds(list)
        setSel((cur) => {
          const ids = new Set(list.map((r) => r.id))
          const ok = cur.base != null && cur.cand != null && ids.has(cur.base) && ids.has(cur.cand)
          const next = ok ? cur : defaults(list)
          writeUrl(next)
          return next
        })
      })
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setListError(e)
      })
    return () => ac.abort()
  }, [listNonce])

  const update = useCallback((next: Selection) => {
    setSel(next)
    setScenario(null)
    writeUrl(next)
  }, [])

  const { data, error, loading, retry } = useBundle(rounds ? sel.base : null, rounds ? sel.cand : null)
  const failure = listError ?? error

  const pick = (name: string) => {
    setScenario((cur) => (cur === name ? null : name))
    if (scenario !== name) document.getElementById('llamadas')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <Topbar
        rounds={rounds}
        base={sel.base}
        cand={sel.cand}
        onBase={(id) => update({ ...sel, base: id })}
        onCand={(id) => update({ ...sel, cand: id })}
        onSwap={() => update({ base: sel.cand, cand: sel.base })}
      />
      <main className="page">
        {failure ? (
          <ErrorState
            error={failure}
            onRetry={() => {
              if (listError) setListNonce((n) => n + 1)
              else retry()
            }}
          />
        ) : (
          <>
            <Verdict diff={data?.diff ?? null} loading={loading} />
            <Kpis diff={data?.diff ?? null} loading={loading} />
            <ScenarioTable diff={data?.diff ?? null} loading={loading} selected={scenario} onPick={pick} />
            <Perf diff={data?.diff ?? null} loading={loading} />
            <Calls
              base={data?.base ?? null}
              cand={data?.cand ?? null}
              scenario={scenario}
              onClearScenario={() => setScenario(null)}
            />
            <footer className="foot">
              <span>CallBench · regression bench para Ana (Pipecat)</span>
              <span className="mono">GET /vueltas · /vueltas/&#123;id&#125; · /diff</span>
            </footer>
          </>
        )}
      </main>
    </>
  )
}
