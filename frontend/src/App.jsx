import { Suspense, lazy, useRef, useState } from 'react'
import { fetchTripPlan } from './api'
import RouteList from './components/RouteList'
import TripForm from './components/TripForm'

// mapbox-gl is most of the JavaScript; loading it separately lets the form
// appear and work while the map is still downloading.
const RouteMap = lazy(() => import('./components/RouteMap'))

export default function App() {
  const [plan, setPlan] = useState(null)
  const [selectedRouteId, setSelectedRouteId] = useState(null)
  const [isPlanning, setIsPlanning] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const activeRequest = useRef(null)

  async function handlePlan(trip) {
    // A new search cancels one still in flight, so a slow old answer can't overwrite it.
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller

    setIsPlanning(true)
    setErrorMessage('')
    setFieldErrors({})
    try {
      const nextPlan = await fetchTripPlan(trip, { signal: controller.signal })
      setPlan(nextPlan)
      setSelectedRouteId(nextPlan.routes.find((route) => route.is_recommended)?.id ?? null)
    } catch (error) {
      if (error.name === 'AbortError') return
      setErrorMessage(error.message)
      setFieldErrors(error.fieldErrors ?? {})
    } finally {
      if (activeRequest.current === controller) setIsPlanning(false)
    }
  }

  return (
    <div className="app">
      <aside className="panel">
        <header className="panel-header">
          <h1>Saffron</h1>
          <p>Compare truck routes by forecast weather along the way.</p>
        </header>

        <TripForm onPlan={handlePlan} isPlanning={isPlanning} fieldErrors={fieldErrors} />

        <div aria-live="polite">
          {errorMessage && <p className="form-error" role="alert">{errorMessage}</p>}
          {isPlanning && <p className="status">Finding truck routes and checking forecasts at each checkpoint…</p>}
        </div>

        {plan && (
          <RouteList plan={plan} selectedRouteId={selectedRouteId} onSelectRoute={setSelectedRouteId} />
        )}
      </aside>

      <main className="map-area" aria-label="Map">
        <Suspense fallback={<p className="map-message">Loading map…</p>}>
          <RouteMap plan={plan} selectedRouteId={selectedRouteId} onSelectRoute={setSelectedRouteId} />
        </Suspense>
      </main>
    </div>
  )
}
