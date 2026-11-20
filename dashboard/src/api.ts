import type { Diff, VueltaDetalle, VueltaListItem } from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message)
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, { signal })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError('No se pudo conectar con la API', null)
  }
  if (!res.ok) {
    // El proxy de Vite responde 500/502 cuando la API no está levantada.
    throw new ApiError(`La API respondió ${res.status}`, res.status)
  }
  return (await res.json()) as T
}

export const fetchVueltas = (signal?: AbortSignal) =>
  getJson<VueltaListItem[]>('/vueltas', signal)

const detailCache = new Map<number, VueltaDetalle>()

export async function fetchVuelta(id: number, signal?: AbortSignal): Promise<VueltaDetalle> {
  const hit = detailCache.get(id)
  if (hit) return hit
  const data = await getJson<VueltaDetalle>(`/vueltas/${id}`, signal)
  detailCache.set(id, data)
  return data
}

export const fetchDiff = (base: number, candidata: number, signal?: AbortSignal) =>
  getJson<Diff>(`/diff?base=${base}&candidata=${candidata}`, signal)
