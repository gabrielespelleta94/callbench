import type { Cuenta } from './types'

export const pct = (x: number | null | undefined, digits = 0): string =>
  x == null ? '—' : `${(x * 100).toFixed(digits)}%`

export const pctInt = (x: number | null | undefined): string =>
  x == null ? '—' : `${Math.round(x * 100)}`

/** Diferencia en puntos porcentuales con signo explícito. */
export function fmtPp(delta: number | null | undefined): string {
  if (delta == null) return '—'
  const v = Math.round(delta * 100)
  if (v === 0) return '0 pp'
  return `${v > 0 ? '+' : '−'}${Math.abs(v)} pp`
}

export function fmtRel(delta: number | null | undefined): string {
  if (delta == null) return '—'
  const v = Math.round(delta * 100)
  if (v === 0) return '0%'
  return `${v > 0 ? '+' : '−'}${Math.abs(v)}%`
}

export function fmtSec(s: number | null | undefined): string {
  if (s == null) return '—'
  if (s < 1) return `${Math.round(s * 1000)} ms`
  return `${s.toFixed(2)} s`
}

export function fmtMoney(x: number | null | undefined, moneda = 'USD'): string {
  if (x == null) return '—'
  const sym = moneda === 'USD' ? '$' : moneda === 'EUR' ? '€' : `${moneda} `
  return `${sym}${x < 0.1 ? x.toFixed(4) : x.toFixed(3)}`
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  const s = ms / 1000
  return s < 100 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

const dateFmt = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short' })
const timeFmt = new Intl.DateTimeFormat('es-ES', { hour: '2-digit', minute: '2-digit' })

export const fmtDate = (iso: string): string => dateFmt.format(new Date(iso)).replace('.', '')
export const fmtDateTime = (iso: string): string =>
  `${fmtDate(iso)} · ${timeFmt.format(new Date(iso))}`

export function splitScenario(name: string): { main: string; variant: string | null } {
  const i = name.indexOf('/')
  return i < 0 ? { main: name, variant: null } : { main: name.slice(0, i), variant: name.slice(i + 1) }
}

export const rate = (c: Cuenta | null): string => (c ? pct(c.tasa) : '—')
