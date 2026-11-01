import { afterEach, describe, expect, it, vi } from 'vitest'
import { TripPlanError, buildTripPlanQuery, fetchTripPlan } from './api'

const trip = {
  origin: ' Dallas, TX ',
  destination: 'Houston, TX',
  departureTime: '2026-11-02T08:00',
  loadWeightLb: '42000',
  checkpointIntervalMiles: 25,
}

function mockFetch(status, body) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: () => (body === undefined ? Promise.reject(new Error('no body')) : Promise.resolve(body)),
  })
}

afterEach(() => vi.restoreAllMocks())

describe('buildTripPlanQuery', () => {
  it('trims places and sends departure as UTC ISO', () => {
    const params = new URLSearchParams(buildTripPlanQuery(trip))
    expect(params.get('origin')).toBe('Dallas, TX')
    expect(params.get('departure_time')).toBe(new Date('2026-11-02T08:00').toISOString())
    expect(params.get('checkpoint_interval_miles')).toBe('25')
  })
})

describe('fetchTripPlan', () => {
  it('returns the plan on success', async () => {
    mockFetch(200, { routes: [] })
    await expect(fetchTripPlan(trip)).resolves.toEqual({ routes: [] })
  })
  it('passes field errors through', async () => {
    mockFetch(400, { errors: { load_weight_lb: 'Must be between 0 and 80,000 lb.' } })
    const error = await fetchTripPlan(trip).catch((e) => e)
    expect(error).toBeInstanceOf(TripPlanError)
    expect(error.fieldErrors.load_weight_lb).toMatch('80,000')
  })
  it('uses the server detail message', async () => {
    mockFetch(422, { detail: 'HERE found no truck route between these places.' })
    await expect(fetchTripPlan(trip)).rejects.toThrow('no truck route')
  })
  it('explains a response without JSON', async () => {
    mockFetch(500, undefined)
    await expect(fetchTripPlan(trip)).rejects.toThrow('(500)')
  })
  it('explains a network failure', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(fetchTripPlan(trip)).rejects.toThrow('Could not reach the planner')
  })
})
