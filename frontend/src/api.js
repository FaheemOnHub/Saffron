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
    // Sent without an offset on purpose: the backend reads it as local time at
    // the origin ("leave Chicago at 8 AM" means 8 AM in Chicago).
    departure_time: departureTime,
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

// Suggestions for the From/To fields. Failures return no suggestions rather than
// an error: typing a full place name still works without them.
export async function fetchPlaceSuggestions(query, { signal } = {}) {
  try {
    const response = await fetch(`/api/places?${new URLSearchParams({ q: query })}`, { signal })
    if (!response.ok) return []
    const body = await response.json()
    return body.suggestions ?? []
  } catch (error) {
    if (error.name === 'AbortError') throw error
    return []
  }
}
