import { describe, expect, it } from 'vitest'
import {
  QUARTER_HOURS,
  formatClockTime,
  formatDepartureLabel,
  formatDuration,
  formatMiles,
  joinLocalDateTime,
  nextQuarterHourLocal,
  splitLocalDateTime,
} from './format'

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

describe('departure picker helpers', () => {
  it('splits and joins the local date-time string', () => {
    const { date, time } = splitLocalDateTime('2026-11-02T08:15')
    expect([date.getFullYear(), date.getMonth(), date.getDate(), time]).toEqual([2026, 10, 2, '08:15'])
    expect(joinLocalDateTime(date, '21:45')).toBe('2026-11-02T21:45')
  })

  it('lists every quarter hour', () => {
    expect(QUARTER_HOURS).toHaveLength(96)
    expect(QUARTER_HOURS.slice(0, 2)).toEqual(['00:00', '00:15'])
    expect(QUARTER_HOURS.at(-1)).toBe('23:45')
  })

  it('formats clock times and the trigger label', () => {
    expect([formatClockTime('00:00'), formatClockTime('12:30'), formatClockTime('21:05')]).toEqual(['12:00 AM', '12:30 PM', '9:05 PM'])
    expect(formatDepartureLabel('2026-11-02T08:15')).toBe('Mon, Nov 2 at 8:15 AM')
  })
})
