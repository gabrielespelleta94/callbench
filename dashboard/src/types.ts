export interface Pct {
  n: number
  p50: number | null
  p95: number | null
}

export interface Cuenta {
  escenario?: string
  aprobado: number
  suspenso: number
  infra: number
  juez_ok: number
  asserts_ok: number
  evaluadas: number
  discrepa: number
  n: number
  tasa: number | null
  ic: [number, number] | null
  voice_to_voice?: Pct
}

export interface Version {
  etiqueta: string
  git_sha: string
  config: Record<string, unknown>
}

export interface VueltaMeta {
  id: number
  nombre: string
  escenarios: string[]
  repeticiones: number
  modalidad: string
  creada_en: string
  version: Version
}

export interface VueltaListItem extends VueltaMeta {
  total: Cuenta
  juez_vs_asserts: {
    juez_ok: number
    asserts_ok: number
    evaluadas: number
    discrepa: number
  }
}

export type Veredicto = 'aprobado' | 'suspenso' | 'infra'

export interface AssertItem {
  nombre: string
  aprobado: boolean | null
  motivo: string | null
}

export type Mensaje =
  | { role: 'assistant' | 'user'; content: string }
  | {
      role: 'tool_call'
      name: string
      arguments: Record<string, unknown>
      cancelled: boolean
      resultado?: Record<string, unknown> | null
    }

export interface Coste {
  stt: number
  llm: number
  tts: number
  total: number
}

export interface MetricasLlamada {
  voice_to_voice: number[]
  ttfb: { stt: number[]; llm: number[]; tts: number[] }
  uso: Record<string, unknown>
  coste: Coste | null
}

export interface Llamada {
  id: number
  escenario: string
  intento: number
  ejecucion: number
  veredicto: Veredicto
  causa: string | null
  juez: { veredicto: string; confianza: number | null; motivo: string | null }
  asserts: { veredicto: 'aprobado' | 'suspenso' | 'n/a'; lista: AssertItem[] }
  transcripcion: Mensaje[] | null
  metricas: MetricasLlamada | null
  duracion_ms: number | null
}

export interface CosteResumen {
  n: number
  p50: number | null
  p95: number | null
  media: number | null
  moneda: string
}

export interface Resumen {
  escenarios: Cuenta[]
  total: Cuenta
  latencia: {
    voice_to_voice: Pct
    ttfb: { stt: Pct; llm: Pct; tts: Pct }
  }
  coste: CosteResumen
}

export interface VueltaDetalle {
  vuelta: VueltaMeta
  resumen: Resumen
  llamadas: Llamada[]
}

export type Estado = 'empeora' | 'mejora' | 'igual' | 'no_concluyente' | 'nuevo'

export interface FilaDiff {
  escenario: string
  base: Cuenta | null
  candidata: Cuenta | null
  delta: number | null
  estado: Estado
  motivo: string
}

export interface DeltaPct {
  base: Pct
  candidata: Pct
  delta_rel: { p50: number | null; p95: number | null }
}

export interface Diff {
  base: VueltaMeta
  candidata: VueltaMeta
  escenarios: FilaDiff[]
  total: { base: Cuenta; candidata: Cuenta }
  latencia: {
    voice_to_voice: DeltaPct & { empeora: boolean; medible: boolean }
    ttfb: { stt: DeltaPct; llm: DeltaPct; tts: DeltaPct }
  }
  coste: { base: CosteResumen; candidata: CosteResumen }
  veredicto: {
    codigo: 0 | 1 | 2
    texto: string
    motivos: string[]
    dudas: string[]
  }
}
