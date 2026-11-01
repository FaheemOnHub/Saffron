import { describe, expect, it } from 'vitest'
import {
  averageLatitude,
  boundsOfRoutes,
  checkpointPopupHtml,
  checkpointsGeoJson,
  corridorGeoJson,
  heatmapRadiusExpression,
  heatmapWeightExpression,
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
    // Mapbox rejects a 'step' with no stops, so this must not be an expression.
    expect(riskGradientExpression(calm)).toBe(RISK_COLORS.low)
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
    expect(html).toContain('<span class="popup-stat-value">0.30</span> in/hr')
    expect(html).toMatch(/popup-stat is-cause[^>]*>\s*<dt>Rain/)
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

describe('corridor heatmap data', () => {
  const corridor = {
    points: [[40, -100], [41, -99]],
    frames: {
      risk: [[3, null], [0, 1]],
      wind: [[2.5, null], [0.4, 1.2]],
      rain: [[0, null], [0, 0]],
      snow: [[0, null], [0, 0]],
    },
  }

  it('puts every metric and hour on each point', () => {
    const [first, second] = corridorGeoJson(corridor).features
    expect(first.geometry.coordinates).toEqual([-100, 40])
    expect(first.properties.risk0).toBe(3)
    expect(first.properties.wind1).toBe(0.4)
    expect(Object.keys(first.properties)).toHaveLength(8)
    expect(second.properties.risk0).toBe(0) // null -> no heat
    expect(second.properties.risk1).toBe(1)
  })

  it('reads the chosen metric and hour, scaled to 0-1', () => {
    expect(heatmapWeightExpression('wind', 12)).toEqual(['/', ['get', 'wind12'], 4])
  })

  it('doubles the radius with each zoom level up to a cap', () => {
    const [, , , , r0, , r9] = heatmapRadiusExpression(20_000, 0)
    expect(r0).toBeCloseTo((20_000 * 1.5) / (40_075_016.686 / 512))
    expect(r9 / r0).toBe(512)
  })

  it('widens the radius at higher latitudes, where pixels cover less ground', () => {
    const equator = heatmapRadiusExpression(20_000, 0)[4]
    const north = heatmapRadiusExpression(20_000, 60)[4]
    expect(north / equator).toBeCloseTo(2)
  })

  it('averages latitude', () => {
    expect(averageLatitude(corridor.points)).toBe(40.5)
    expect(averageLatitude([])).toBe(0)
  })
})
