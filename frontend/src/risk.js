// Display colors per risk level key from the API. Ordered green -> purple so
// worse always reads darker/hotter, and No Travel stands apart from Severe red.
export const RISK_COLORS = {
  low: '#3E9B5F',
  moderate: '#E2B33C',
  high: '#E57A2E',
  severe: '#C9312C',
  no_travel: '#5E1F6E',
}

export const UNKNOWN_RISK_COLOR = '#9AA6AE'

export function riskColor(levelKey) {
  return RISK_COLORS[levelKey] ?? UNKNOWN_RISK_COLOR
}

// Contiguous runs of the same level along a route, so a strip of 40
// checkpoints draws as a handful of segments rather than 40 slivers.
export function riskSegments(checkpoints) {
  const segments = []
  for (const checkpoint of checkpoints) {
    const level = checkpoint.risk?.level ?? 'unknown'
    const last = segments[segments.length - 1]
    if (last && last.level === level) {
      last.miles += checkpoint.coverage_miles
    } else {
      segments.push({ level, miles: checkpoint.coverage_miles })
    }
  }
  return segments
}
