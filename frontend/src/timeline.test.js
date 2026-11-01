import { describe, expect, it } from 'vitest'
import { cumulativeDistances, pointAlongPath, timelineSegments, truckProgress } from './timeline'

const START = Date.parse('2026-11-02T00:00:00Z')
const at = (hours) => new Date(START + hours * 3_600_000).toISOString()

function checkpoint(hours, miles, level) {
  return { eta: at(hours), distance_miles: miles, risk: level ? { level } : null }
}

// Departs at +2 h, checkpoints every 2 h, arrives at +10 h.
const route = {
  checkpoints: [
    checkpoint(2, 0, 'low'),
    checkpoint(4, 100, 'low'),
    checkpoint(6, 200, 'high'),
    checkpoint(8, 300, 'low'),
    checkpoint(10, 400, null),
  ],
}

describe('timelineSegments', () => {
  it('places each level at the time the truck is there, merging neighbours', () => {
    const segments = timelineSegments(route, START, 48)
    const hours = segments.map(({ level, start, end }) => [level, start * 48, end * 48])
    expect(hours).toEqual([
      ['low', 2, 5],
      ['high', 5, 7],
      ['low', 7, 9],
      ['unknown', 9, 10],
    ])
  })

  it('clips a trip that runs past the end of the axis', () => {
    const segments = timelineSegments(route, START, 6)
    expect(segments.at(-1)).toEqual({ level: 'high', start: 5 / 6, end: 1 })
  })
})

describe('truckProgress', () => {
  it('is waiting before departure and arrived after the last checkpoint', () => {
    expect(truckProgress(route, START)).toEqual({ status: 'waiting', miles: 0 })
    expect(truckProgress(route, START + 11 * 3_600_000)).toEqual({ status: 'arrived', miles: 400 })
  })

  it('interpolates miles between checkpoints by time', () => {
    expect(truckProgress(route, START + 5 * 3_600_000)).toEqual({ status: 'driving', miles: 150 })
  })
})

describe('pointAlongPath', () => {
  // An L-shaped path: north 1 degree, then east 1 degree (at the equator, equal lengths).
  const path = [[0, 0], [1, 0], [1, 1]]
  const distances = cumulativeDistances(path)

  it('measures the path', () => {
    expect(distances[1]).toBeCloseTo(111_195, -1)
    expect(distances[2]).toBeGreaterThan(distances[1])
  })

  it('follows the path rather than cutting the corner', () => {
    const [lat, lng] = pointAlongPath(path, distances, 0.25)
    expect(lng).toBe(0)
    expect(lat).toBeCloseTo(0.5, 2)
  })

  it('clamps to the ends', () => {
    expect(pointAlongPath(path, distances, -1)).toEqual([0, 0])
    expect(pointAlongPath(path, distances, 2)).toEqual([1, 1])
  })
})
