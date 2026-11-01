// Turns the API's trip plan into what Mapbox needs. Kept free of mapbox-gl so
// it can be unit tested. Note the API sends [lat, lng]; GeoJSON wants [lng, lat].
import { formatTime } from './format'
import { riskColor, riskSegments } from './risk'

const toLngLat = ([lat, lng]) => [lng, lat]

export function routeLinesGeoJson(routes) {
  return {
    type: 'FeatureCollection',
    features: routes.map((route) => ({
      type: 'Feature',
      properties: { id: route.id, rank: route.rank },
      geometry: { type: 'LineString', coordinates: route.path.map(toLngLat) },
    })),
  }
}

export function checkpointsGeoJson(route) {
  return {
    type: 'FeatureCollection',
    features: route.checkpoints.map((checkpoint) => ({
      type: 'Feature',
      properties: {
        sequence: checkpoint.sequence,
        color: riskColor(checkpoint.risk?.level),
      },
      geometry: { type: 'Point', coordinates: [checkpoint.lng, checkpoint.lat] },
    })),
  }
}

// A Mapbox 'step' expression over line-progress (0 at origin, 1 at destination)
// that paints each stretch of the line in its risk color.
export function riskGradientExpression(route) {
  const segments = riskSegments(route.checkpoints).filter((segment) => segment.miles > 0)
  const totalMiles = segments.reduce((sum, segment) => sum + segment.miles, 0)
  if (segments.length === 0 || totalMiles === 0) return riskColor(route.checkpoints[0]?.risk?.level)

  const expression = ['step', ['line-progress'], riskColor(segments[0].level)]
  let milesSoFar = 0
  for (let index = 1; index < segments.length; index += 1) {
    milesSoFar += segments[index - 1].miles
    // Stops must strictly increase; float rounding can't push us past 1.
    expression.push(Math.min(milesSoFar / totalMiles, 0.999999), riskColor(segments[index].level))
  }
  return expression
}

export function boundsOfRoutes(routes) {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity
  for (const route of routes) {
    for (const [lat, lng] of route.path) {
      west = Math.min(west, lng)
      east = Math.max(east, lng)
      south = Math.min(south, lat)
      north = Math.max(north, lat)
    }
  }
  return [[west, south], [east, north]]
}

const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (character) => `&#${character.charCodeAt(0)};`)

function drivingFactors(risk) {
  const factors = [
    ['wind', risk.wind_level],
    ['rain', risk.rain_level],
    ['snow', risk.snow_level],
  ].filter(([, level]) => level === risk.level).map(([name]) => name)
  return factors.join(' and ')
}

export function checkpointPopupHtml(checkpoint, levelLabels, loadWeightLb) {
  const heading = `Mile ${Math.round(checkpoint.distance_miles)}`
  const arrival = `Arrive ${formatTime(checkpoint.eta)}`
  if (!checkpoint.forecast_available) {
    return `<div class="popup"><strong>${heading}</strong><p>${arrival}</p>` +
      '<p>No forecast yet for this time.</p></div>'
  }

  const { weather, risk } = checkpoint
  const levelLabel = levelLabels[risk.level]
  const lines = [
    `Wind ${Math.round(weather.wind_mph)} mph, gusts ${Math.round(weather.wind_gust_mph)} mph`,
    `Rain ${weather.rain_in_per_hr.toFixed(2)} in/hr`,
    `Snow ${weather.snow_in_per_hr.toFixed(2)} in/hr`,
  ]
  const notes = []
  if (risk.level !== 'low') notes.push(`${levelLabel} because of ${drivingFactors(risk)}.`)
  if (risk.raised_by_load) {
    notes.push(`Wind risk raised for the ${loadWeightLb.toLocaleString('en-US')} lb load.`)
  }
  if (checkpoint.gust_warning) notes.push('Gusts reach the High wind band.')

  return `<div class="popup">` +
    `<strong>${heading}</strong>` +
    // Swatch plus dark text: white text on the amber/green levels isn't readable enough.
    `<span class="popup-level"><span class="swatch" style="background:${riskColor(risk.level)}"></span>` +
    `${escapeHtml(levelLabel)}</span>` +
    `<p>${arrival}</p>` +
    `<ul>${lines.map((line) => `<li>${line}</li>`).join('')}</ul>` +
    notes.map((note) => `<p class="popup-note">${escapeHtml(note)}</p>`).join('') +
    `</div>`
}
