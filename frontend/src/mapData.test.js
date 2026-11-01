import { describe, expect, it } from 'vitest'
import {
  boundsOfRoutes,
  checkpointPopupHtml,
  checkpointsGeoJson,
  riskGradientExpression,
  routeLinesGeoJson,
} from './mapData'
import { RISK_COLORS, UNKNOWN_RISK_COLOR } from './risk'

const LABELS = { low: 'Low', moderate: 'Moderate', high: 'High', severe: 'Severe', no_travel: 'No Travel' }

function checkpoint(level, coverageMiles, extra = {}) {
  return {
    sequence: 0, distance_miles: 0, lat: 32, lng: -96, eta: '2026-11-02T14:00:00+00:00',
    coverage_miles: coverageMiles, forecast_available: level !== null,
    risk: level === null ? null : { level, wind_level: 'low', rain_level: level, snow_level: 'low', raised_by_load: false },
    weather: level === null ? null : { wind_mph: 12, wind_gust_mph: 20, rain_in_per_hr: 0.3, snow_in_per_hr: 0 },
    gust_warning: false,
    ...extra,
  }
}

const route = {
  id: 'route-1', rank: 1,
  path: [[32, -96], [31, -95.5], [30, -95]],
  checkpoints: [checkpoint('low', 25), checkpoint('low', 25), checkpoint('high', 25), checkpoint(null, 25)],
}

describe('GeoJSON conversion', () => {
  it('flips [lat, lng] to [lng, lat]', () => {
    const line = routeLinesGeoJson([route]).features[0]
    expect(line.geometry.coordinates[0]).toEqual([-96, 32])
    expect(line.properties.id).toBe('route-1')
  })
  it('colors checkpoints by level, grey when unknown', () => {
    const colors = checkpointsGeoJson(route).features.map((feature) => feature.properties.color)
    expect(colors).toEqual([RISK_COLORS.low, RISK_COLORS.low, RISK_COLORS.high, UNKNOWN_RISK_COLOR])
  })
})

describe('riskGradientExpression', () => {
  it('steps at each change of level, by share of miles', () => {
    expect(riskGradientExpression(route)).toEqual([
      'step', ['line-progress'], RISK_COLORS.low, 0.5, RISK_COLORS.high, 0.75, UNKNOWN_RISK_COLOR,
    ])
  })
  it('is a plain color when the whole route is one level', () => {
    const calm = { ...route, checkpoints: [checkpoint('low', 10), checkpoint('low', 10)] }
    expect(riskGradientExpression(calm)).toEqual(['step', ['line-progress'], RISK_COLORS.low])
  })
  it('skips zero-mile segments so stops keep increasing', () => {
    const odd = { ...route, checkpoints: [checkpoint('low', 10), checkpoint('high', 0), checkpoint('severe', 10)] }
    expect(riskGradientExpression(odd)).toEqual(['step', ['line-progress'], RISK_COLORS.low, 0.5, RISK_COLORS.severe])
  })
})

describe('boundsOfRoutes', () => {
  it('covers every point on every route', () => {
    const other = { path: [[33, -97], [29.5, -94]] }
    expect(boundsOfRoutes([route, other])).toEqual([[-97, 29.5], [-94, 33]])
  })
})

describe('checkpointPopupHtml', () => {
  it('names the level, the cause, and the weather', () => {
    const html = checkpointPopupHtml(checkpoint('high', 25, { distance_miles: 124.6 }), LABELS, 42000)
    expect(html).toContain('Mile 125')
    expect(html).toContain('High because of rain.')
    expect(html).toContain('Rain 0.30 in/hr')
  })
  it('mentions the load rule and gusts when they apply', () => {
    const windy = checkpoint('severe', 25, { gust_warning: true })
    windy.risk = { level: 'severe', wind_level: 'severe', rain_level: 'low', snow_level: 'low', raised_by_load: true }
    const html = checkpointPopupHtml(windy, LABELS, 42000)
    expect(html).toContain('Severe because of wind.')
    expect(html).toContain('42,000 lb load')
    expect(html).toContain('Gusts reach the High wind band.')
  })
  it('lists every condition tied for the worst level', () => {
    const both = checkpoint('high', 25)
    both.risk = { ...both.risk, wind_level: 'high' }
    expect(checkpointPopupHtml(both, LABELS, 0)).toContain('because of wind and rain.')
  })
  it('says when there is no forecast', () => {
    expect(checkpointPopupHtml(checkpoint(null, 25), LABELS, 0)).toContain('No forecast yet')
  })
})
