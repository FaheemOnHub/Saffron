import { AlertCircle } from 'lucide-react'
import { Suspense, lazy, useRef, useState } from 'react'
import { fetchTripPlan } from './api'
import BrandMark from './components/BrandMark'
import PlanningOverlay from './components/PlanningOverlay'
import RouteList from './components/RouteList'
import TripForm from './components/TripForm'
import TripSummary from './components/TripSummary'

// mapbox-gl is most of the JavaScript; loading it separately lets the form
// appear and work while the map is still downloading.
const RouteMap = lazy(() => import('./components/RouteMap'))

export default function App() {
  const [plan, setPlan] = useState(null)
  const [plannedTrip, setPlannedTrip] = useState(null)
  const [isEditingTrip, setIsEditingTrip] = useState(true)
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
      setPlannedTrip(trip)
      setIsEditingTrip(false)
      setSelectedRouteId(nextPlan.routes.find((route) => route.is_recommended)?.id ?? null)
    } catch (error) {
      if (error.name === 'AbortError') return
      setErrorMessage(error.message)
      setFieldErrors(error.fieldErrors ?? {})
    } finally {
      if (activeRequest.current === controller) setIsPlanning(false)
    }
  }

  // The form stays mounted while folded away, so "Edit trip" brings back what was typed.
  const showForm = isEditingTrip || !plan

  return (
    <div className={plan ? 'app has-plan' : 'app'}>
      <aside className="panel flex flex-col gap-5">
        <header className="flex items-center gap-3">
          <BrandMark className="size-11" />
          <div>
            <h1 className="text-2xl leading-none font-extrabold tracking-tight text-brand-navy">Saffron</h1>
            <p className="mt-1 text-sm text-muted-foreground">Truck routes compared by the weather along the way</p>
          </div>
        </header>

        {!showForm && <TripSummary plan={plan} trip={plannedTrip} onEdit={() => setIsEditingTrip(true)} />}
        <TripForm onPlan={handlePlan} isPlanning={isPlanning} fieldErrors={fieldErrors} hidden={!showForm} />

        {/* role="alert" announces the message itself, so the empty wrapper can collapse. */}
        <div className="empty:hidden">
          {errorMessage && (
            <p role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm font-medium text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {errorMessage}
            </p>
          )}
        </div>

        {plan && (
          <RouteList plan={plan} selectedRouteId={selectedRouteId} onSelectRoute={setSelectedRouteId} />
        )}
      </aside>

      <main className="map-area" aria-label="Map">
        <Suspense fallback={<p className="map-message">Loading map…</p>}>
          <RouteMap plan={plan} selectedRouteId={selectedRouteId} onSelectRoute={setSelectedRouteId} />
        </Suspense>
        <PlanningOverlay isPlanning={isPlanning} />
      </main>
    </div>
  )
}
