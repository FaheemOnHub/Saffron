const TRIP_PLAN_URL = '/api/trip-plan'

export class TripPlanError extends Error {
  constructor(message, fieldErrors = {}) {
    super(message)
    this.fieldErrors = fieldErrors
  }
}

export function buildTripPlanQuery({ origin, destination, departureTime, loadWeightLb, checkpointIntervalMiles }) {
  return new URLSearchParams({
    origin: origin.trim(),
    destination: destination.trim(),
    // The datetime-local input has no timezone; Date reads it as browser local time.
    departure_time: new Date(departureTime).toISOString(),
    load_weight_lb: String(loadWeightLb),
    checkpoint_interval_miles: String(checkpointIntervalMiles),
  }).toString()
}

export async function fetchTripPlan(trip, { signal } = {}) {
  let response
  try {
    response = await fetch(`${TRIP_PLAN_URL}?${buildTripPlanQuery(trip)}`, { signal })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new TripPlanError('Could not reach the planner. Check that the backend is running.')
  }

  const body = await response.json().catch(() => null)
  if (response.ok && body) return body
  if (body?.errors) throw new TripPlanError('Fix the highlighted fields and try again.', body.errors)
  if (body?.detail) throw new TripPlanError(body.detail)
  throw new TripPlanError(`The planner returned an unexpected error (${response.status}).`)
}
