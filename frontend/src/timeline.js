// Time math for the trip timeline and the truck marker. No React or Mapbox here,
// so it can be unit tested.

const HOUR_MS = 3_600_000
const EARTH_RADIUS_M = 6_371_000

const toMs = (iso) => new Date(iso).getTime()

// Each route as stretches of time on the timeline axis, colored by risk.
// A checkpoint's weather stands for the time halfway back to the previous
// checkpoint and halfway on to the next (the time version of coverage_miles).
// Returns [{ level, start, end }] with start/end as 0-1 fractions of the axis.
export function timelineSegments(route, axisStartMs, axisHours) {
  const spanMs = axisHours * HOUR_MS
  const etas = route.checkpoints.map((checkpoint) => toMs(checkpoint.eta))
  const clamp = (ms) => Math.min(Math.max((ms - axisStartMs) / spanMs, 0), 1)

  const segments = []
  route.checkpoints.forEach((checkpoint, index) => {
    const startMs = index === 0 ? etas[0] : (etas[index - 1] + etas[index]) / 2
    const endMs = index === etas.length - 1 ? etas[index] : (etas[index] + etas[index + 1]) / 2
    const level = checkpoint.risk?.level ?? 'unknown'
    const start = clamp(startMs)
    const end = clamp(endMs)
    if (end <= start) return
    const last = segments[segments.length - 1]
    if (last && last.level === level && Math.abs(last.end - start) < 1e-9) {
      last.end = end
    } else {
      segments.push({ level, start, end })
    }
  })
  return segments
}

// Where the truck is at a moment, in miles along the route, from checkpoint ETAs.
export function truckProgress(route, momentMs) {
  const { checkpoints } = route
  const first = checkpoints[0]
  const last = checkpoints[checkpoints.length - 1]
  if (momentMs <= toMs(first.eta)) return { status: 'waiting', miles: 0 }
  if (momentMs >= toMs(last.eta)) return { status: 'arrived', miles: last.distance_miles }

  for (let index = 1; index < checkpoints.length; index += 1) {
    const before = checkpoints[index - 1]
    const after = checkpoints[index]
    const beforeMs = toMs(before.eta)
    const afterMs = toMs(after.eta)
    if (momentMs <= afterMs) {
      const share = afterMs === beforeMs ? 0 : (momentMs - beforeMs) / (afterMs - beforeMs)
      return { status: 'driving', miles: before.distance_miles + share * (after.distance_miles - before.distance_miles) }
    }
  }
  return { status: 'arrived', miles: last.distance_miles }
}

function haversineM([latA, lngA], [latB, lngB]) {
  const toRad = (degrees) => (degrees * Math.PI) / 180
  const a = Math.sin(toRad(latB - latA) / 2) ** 2 +
    Math.cos(toRad(latA)) * Math.cos(toRad(latB)) * Math.sin(toRad(lngB - lngA) / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a))
}

// Running distance along a [lat, lng] path; computed once per route.
export function cumulativeDistances(path) {
  const distances = [0]
  for (let index = 1; index < path.length; index += 1) {
    distances.push(distances[index - 1] + haversineM(path[index - 1], path[index]))
  }
  return distances
}

// The [lat, lng] a given share (0-1) of the way along the path, so the marker
// stays on the road instead of cutting straight between checkpoints.
export function pointAlongPath(path, distances, share) {
  const total = distances[distances.length - 1]
  const target = Math.min(Math.max(share, 0), 1) * total
  let low = 0
  let high = distances.length - 1
  while (high - low > 1) {
    const middle = (low + high) >> 1
    if (distances[middle] < target) low = middle
    else high = middle
  }
  const gap = distances[high] - distances[low]
  const t = gap === 0 ? 0 : (target - distances[low]) / gap
  return [
    path[low][0] + t * (path[high][0] - path[low][0]),
    path[low][1] + t * (path[high][1] - path[low][1]),
  ]
}
