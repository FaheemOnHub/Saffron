import { describe, expect, it } from 'vitest'
import { formatDuration, formatMiles, nextQuarterHourLocal } from './format'

describe('formatDuration', () => {
  it('shows minutes only under an hour', () => {
    expect(formatDuration(45 * 60)).toBe('45m')
  })
  it('pads minutes after hours', () => {
    expect(formatDuration(14 * 3600 + 5 * 60)).toBe('14h 05m')
  })
  it('rounds to the nearest minute', () => {
    expect(formatDuration(3600 + 89)).toBe('1h 01m')
  })
})

describe('formatMiles', () => {
  it('rounds and groups thousands', () => {
    expect(formatMiles(1316.24)).toBe('1,316 mi')
  })
})

describe('nextQuarterHourLocal', () => {
  it('moves to the next quarter hour', () => {
    expect(nextQuarterHourLocal(new Date(2026, 10, 2, 8, 7, 30))).toBe('2026-11-02T08:15')
  })
  it('skips ahead when already on a quarter hour', () => {
    expect(nextQuarterHourLocal(new Date(2026, 10, 2, 8, 15))).toBe('2026-11-02T08:30')
  })
  it('rolls over to the next day', () => {
    expect(nextQuarterHourLocal(new Date(2026, 10, 2, 23, 58))).toBe('2026-11-03T00:00')
  })
})
