import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, useMapEvents, CircleMarker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { fetchForecast, fetchImpacts } from './api'
import type { Forecast, Impacts } from './types'
import './App.css'

type ClickPoint = { lat: number; lon: number }

function MapClickLayer({
  onPick,
}: {
  onPick: (p: ClickPoint) => void
}) {
  useMapEvents({
    click(e) {
      onPick({ lat: e.latlng.lat, lon: e.latlng.lng })
    },
  })
  return null
}

function oniLabel(oni: number) {
  if (oni >= 0.5) return 'El Niño leaning'
  if (oni <= -0.5) return 'La Niña leaning'
  return 'near neutral'
}

function arrowFor(anom: number) {
  if (Math.abs(anom) < 1e-6) return '→'
  return anom > 0 ? '↑' : '↓'
}

export default function App() {
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const [forecastError, setForecastError] = useState<string | null>(null)
  const [point, setPoint] = useState<ClickPoint | null>(null)
  const [impacts, setImpacts] = useState<Impacts | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchForecast()
      .then(setForecast)
      .catch((e: Error) => setForecastError(e.message))
  }, [])

  useEffect(() => {
    if (!point) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setImpacts(null)
    fetchImpacts(point.lat, point.lon)
      .then((data) => {
        if (!cancelled) setImpacts(data)
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [point])

  const oni = forecast?.forecast_oni

  return (
    <div className="shell">
      <header className="top">
        <div className="brand-block">
          <p className="eyebrow">Pacific signal → local winter</p>
          <h1 className="brand">ENSOcast</h1>
        </div>
        <div className="oni-chip" aria-live="polite">
          {forecastError && <span className="warn">API offline — start uvicorn</span>}
          {!forecastError && !forecast && <span className="muted">Loading forecast…</span>}
          {forecast && oni != null && (
            <>
              <span className="oni-season">Winter {forecast.winter}</span>
              <strong className="oni-value">
                ONI {oni >= 0 ? '+' : ''}
                {oni.toFixed(2)}
              </strong>
              <span className="oni-state">{oniLabel(oni)}</span>
            </>
          )}
        </div>
      </header>

      <main className="stage">
        <div className="map-wrap">
          <MapContainer
            center={[40, -100]}
            zoom={4}
            className="map"
            scrollWheelZoom
            worldCopyJump={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
              url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            />
            <MapClickLayer onPick={setPoint} />
            {point && (
              <CircleMarker
                center={[point.lat, point.lon]}
                radius={8}
                pathOptions={{
                  color: '#0b4f5c',
                  fillColor: '#c45c26',
                  fillOpacity: 0.9,
                  weight: 2,
                }}
              />
            )}
          </MapContainer>
          <p className="map-hint">Click anywhere to estimate that place’s winter</p>
        </div>

        <aside className="panel" aria-live="polite">
          {!point && (
            <div className="panel-empty">
              <h2>Pick a place</h2>
              <p>
                We’ll pull that spot’s winter history, relate it to past ONI, and apply this
                season’s forecast.
              </p>
            </div>
          )}

          {point && (
            <>
              <p className="coords">
                {point.lat.toFixed(2)}°, {point.lon.toFixed(2)}°
              </p>
              {loading && <p className="muted">Fetching winters and fitting…</p>}
              {error && (
                <div className="error">
                  <strong>Couldn’t load impacts</strong>
                  <p>{error}</p>
                </div>
              )}
              {impacts && !loading && (
                <div className="readouts">
                  <h2>Winter {impacts.winter}</h2>
                  <ul>
                    <li>
                      <span className="metric">Temperature</span>
                      <span className="arrow" data-dir={impacts.temp_anom >= 0 ? 'warm' : 'cold'}>
                        {arrowFor(impacts.temp_anom)}
                      </span>
                      <span className="phrase">{impacts.temp_phrase}</span>
                      <span className="delta">
                        {impacts.temp_anom >= 0 ? '+' : ''}
                        {impacts.temp_anom.toFixed(1)}°C
                      </span>
                    </li>
                    <li>
                      <span className="metric">Precipitation</span>
                      <span className="arrow">{arrowFor(impacts.precip_anom)}</span>
                      <span className="phrase">{impacts.precip_phrase}</span>
                      <span className="delta">
                        {impacts.precip_anom >= 0 ? '+' : ''}
                        {impacts.precip_anom.toFixed(0)} mm
                      </span>
                    </li>
                    <li>
                      <span className="metric">Snow</span>
                      <span className="arrow">{arrowFor(impacts.snow_anom)}</span>
                      <span className="phrase">{impacts.snow_phrase}</span>
                      <span className="delta">
                        {impacts.snow_anom >= 0 ? '+' : ''}
                        {impacts.snow_anom.toFixed(0)} cm
                      </span>
                    </li>
                  </ul>
                  <p className={`confidence tag-${impacts.confidence_tag}`}>
                    Confidence: <strong>{impacts.confidence_tag}</strong>
                    {impacts.n_winters != null && (
                      <span className="muted"> · {impacts.n_winters} winters</span>
                    )}
                  </p>
                </div>
              )}
            </>
          )}
        </aside>
      </main>

      <footer className="foot">
        <p>
          Model forecast fed through a historical ONI–local winter relationship — not an
          official outlook. Mid-latitude signal can be weak.
        </p>
      </footer>
    </div>
  )
}
