import { formatDuration, formatMiles, formatTime } from '../format'
import { riskColor } from '../risk'
import RiskStrip from './RiskStrip'

// Only levels a driver needs to act on get a line; Low/Moderate stay in the strip.
const CALLOUT_LEVELS = ['no_travel', 'severe', 'high']

function RiskCallouts({ summary, levelLabels }) {
  const callouts = CALLOUT_LEVELS
    .filter((level) => summary.miles_by_level[level] > 0)
    .map((level) => ({ level, miles: summary.miles_by_level[level] }))

  return (
    <ul className="risk-callouts">
      {callouts.length === 0 && <li>No High or Severe weather forecast</li>}
      {callouts.map(({ level, miles }) => (
        <li key={level}>
          <span className="swatch" style={{ backgroundColor: riskColor(level) }} aria-hidden="true" />
          {formatMiles(miles)} {levelLabels[level]}
        </li>
      ))}
      {summary.gust_warning_count > 0 && (
        <li>Strong gusts at {summary.gust_warning_count} checkpoint{summary.gust_warning_count > 1 ? 's' : ''}</li>
      )}
      {summary.unknown_miles > 0 && <li>{formatMiles(summary.unknown_miles)} beyond the forecast range</li>}
    </ul>
  )
}

function RouteCard({ route, isSelected, onSelect, levelLabels }) {
  return (
    <li>
      <button
        type="button"
        className={isSelected ? 'route-card is-selected' : 'route-card'}
        aria-pressed={isSelected}
        onClick={() => onSelect(route.id)}
      >
        <span className="route-heading">
          <span className="route-name">Route {route.rank}</span>
          {route.is_recommended && <span className="badge">Recommended</span>}
          {route.is_detour && <span className="tag">Forced detour</span>}
        </span>

        <span className="route-stats">
          <span><strong>{formatDuration(route.duration_s)}</strong> driving</span>
          <span>{formatMiles(route.distance_miles)}</span>
          <span>Arrive {formatTime(route.arrival_time)}</span>
        </span>

        <RiskStrip checkpoints={route.checkpoints} levelLabels={levelLabels} />
        <RiskCallouts summary={route.risk_summary} levelLabels={levelLabels} />

        {route.is_recommended && <span className="reason">{route.recommendation_reason}</span>}
      </button>
    </li>
  )
}

export default function RouteList({ plan, selectedRouteId, onSelectRoute }) {
  const levelLabels = Object.fromEntries(plan.risk_levels.map((level) => [level.key, level.label]))

  return (
    <section className="route-list" aria-labelledby="route-list-heading">
      <h2 id="route-list-heading">
        {plan.origin.label} to {plan.destination.label}
      </h2>
      {plan.routes.length < 3 && (
        <p className="note">
          Only {plan.routes.length} distinct truck route{plan.routes.length > 1 ? 's' : ''} found
          between these places.
        </p>
      )}
      <ol>
        {plan.routes.map((route) => (
          <RouteCard
            key={route.id}
            route={route}
            isSelected={route.id === selectedRouteId}
            onSelect={onSelectRoute}
            levelLabels={levelLabels}
          />
        ))}
      </ol>
      <ul className="legend" aria-label="Risk levels">
        {plan.risk_levels.map((level) => (
          <li key={level.key}>
            <span className="swatch" style={{ backgroundColor: riskColor(level.key) }} aria-hidden="true" />
            {level.label}
          </li>
        ))}
      </ul>
    </section>
  )
}
