import { riskColor, riskSegments } from '../risk'

// A straight-line diagram of the route: each band's width is its share of the
// miles, its color the forecast risk there. Origin on the left.
export default function RiskStrip({ checkpoints, levelLabels }) {
  const segments = riskSegments(checkpoints)
  const description = segments
    .map((segment) => `${Math.round(segment.miles)} mi ${levelLabels[segment.level] ?? 'no forecast'}`)
    .join(', then ')

  return (
    <div className="risk-strip" role="img" aria-label={`Risk along route: ${description}`}>
      {segments.map((segment, index) => (
        <span
          key={index}
          className={segment.level === 'unknown' ? 'risk-band is-unknown' : 'risk-band'}
          style={{ flexGrow: segment.miles, backgroundColor: riskColor(segment.level) }}
        />
      ))}
    </div>
  )
}
