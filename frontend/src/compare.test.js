import { describe, expect, it } from 'vitest'
import { ordinal, rankingRows, routeName } from './compare'

const RULES = [
  { key: 'no_travel_miles', label: 'No Travel miles' },
  { key: 'severe_miles', label: 'Severe miles' },
  { key: 'high_miles', label: 'High miles' },
  { key: 'average_risk', label: 'average risk' },
  { key: 'travel_time', label: 'travel time' },
]

function route(rank, { severe = 0, high = 0, average = 0, durationS = 3600, beatsNextOn = null, highways = [] } = {}) {
  return {
    rank,
    highways,
    beats_next_on: beatsNextOn,
    duration_s: durationS,
    risk_summary: {
      average_risk: average,
      miles_by_level: { low: 0, moderate: 0, high, severe, no_travel: 0 },
    },
  }
}

describe('routeName', () => {
  it('joins highway names, falling back to the rank', () => {
    expect(routeName(route(1, { highways: ['I-90', 'I-25'] }))).toBe('I-90 / I-25')
    expect(routeName(route(2))).toBe('Route 2')
  })
})

describe('ordinal', () => {
  it('handles the first few ranks', () => {
    expect([1, 2, 3, 4].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th'])
  })
})

describe('rankingRows', () => {
  const plan = {
    ranking_rules: RULES,
    routes: [
      route(1, { high: 25, average: 0.22, durationS: 69420, beatsNextOn: 'high_miles' }),
      route(2, { high: 62, average: 0.38, durationS: 61800, beatsNextOn: 'severe_miles' }),
      route(3, { severe: 38, high: 50, average: 0.41, durationS: 53220 }),
    ],
  }

  it('keeps the API rule order and capitalizes labels', () => {
    expect(rankingRows(plan).map((row) => row.label)).toEqual([
      'No Travel miles', 'Severe miles', 'High miles', 'Average risk', 'Travel time',
    ])
  })

  it('formats each value per rule', () => {
    const rows = Object.fromEntries(rankingRows(plan).map((row) => [row.key, row.values]))
    expect(rows.severe_miles).toEqual(['0 mi', '0 mi', '38 mi'])
    expect(rows.average_risk).toEqual(['0.22', '0.38', '0.41'])
    expect(rows.travel_time).toEqual(['19h 17m', '17h 10m', '14h 47m'])
  })

  it('tags the rows that decide each pair of ranks', () => {
    const decides = Object.fromEntries(rankingRows(plan).map((row) => [row.key, row.decides]))
    expect(decides.high_miles).toEqual(['Decides 1st vs 2nd'])
    expect(decides.severe_miles).toEqual(['Decides 2nd vs 3rd'])
    expect(decides.travel_time).toEqual([])
  })
})
