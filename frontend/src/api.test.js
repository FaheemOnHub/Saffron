import { afterEach, describe, expect, it, vi } from 'vitest'
import { TripPlanError, buildTripPlanQuery, fetchPlaceSuggestions, fetchTripPlan } from './api'

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
  it('trims places and sends departure as origin-local wall-clock time', () => {
    const params = new URLSearchParams(buildTripPlanQuery(trip))
    expect(params.get('origin')).toBe('Dallas, TX')
    expect(params.get('departure_time')).toBe('2026-11-02T08:00')
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

describe('fetchPlaceSuggestions', () => {
  it('returns the suggestions list', async () => {
    mockFetch(200, { suggestions: [{ id: 'a', label: 'Denver, CO, United States' }] })
    await expect(fetchPlaceSuggestions('Denv')).resolves.toEqual([{ id: 'a', label: 'Denver, CO, United States' }])
    expect(globalThis.fetch.mock.calls[0][0]).toBe('/api/places?q=Denv')
  })
  it('treats failures as no suggestions', async () => {
    mockFetch(502, { detail: 'HERE down' })
    await expect(fetchPlaceSuggestions('Denv')).resolves.toEqual([])
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(fetchPlaceSuggestions('Denv')).resolves.toEqual([])
  })
})
