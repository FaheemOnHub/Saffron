import { describe, expect, it } from 'vitest'
import { RISK_COLORS, UNKNOWN_RISK_COLOR, riskColor, riskSegments } from './risk'

const checkpoint = (level, coverageMiles) => ({
  risk: level ? { level } : null,
  coverage_miles: coverageMiles,
})

describe('riskSegments', () => {
  it('merges neighbouring checkpoints with the same level', () => {
    const segments = riskSegments([
      checkpoint('low', 12.5), checkpoint('low', 25), checkpoint('high', 25),
      checkpoint('low', 25), checkpoint(null, 12.5),
    ])
    expect(segments).toEqual([
      { level: 'low', miles: 37.5 },
      { level: 'high', miles: 25 },
      { level: 'low', miles: 25 },
      { level: 'unknown', miles: 12.5 },
    ])
  })
  it('handles an empty route', () => {
    expect(riskSegments([])).toEqual([])
  })
})

describe('riskColor', () => {
  it('maps every API level and falls back for unknown', () => {
    expect(riskColor('no_travel')).toBe(RISK_COLORS.no_travel)
    expect(riskColor('unknown')).toBe(UNKNOWN_RISK_COLOR)
  })
})
