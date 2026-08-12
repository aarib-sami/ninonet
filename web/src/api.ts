import type { Forecast, Impacts } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? body.error ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export function fetchForecast() {
  return getJson<Forecast>('/forecast')
}

export function fetchImpacts(lat: number, lon: number, oni?: number) {
  const q = new URLSearchParams({
    lat: lat.toFixed(4),
    lon: lon.toFixed(4),
  })
  if (oni != null && Number.isFinite(oni)) {
    q.set('oni', String(oni))
  }
  return getJson<Impacts>(`/impacts?${q}`)
}
