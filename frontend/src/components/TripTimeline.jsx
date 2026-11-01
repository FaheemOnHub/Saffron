import { useEffect, useState } from 'react'
import { routeName } from '../compare'
import { formatMiles, formatTime } from '../format'
import { RISK_COLORS, riskColor } from '../risk'
import { timelineSegments, truckProgress } from '../timeline'

const LAYER_OPTIONS = [
  { key: 'risk', label: 'Risk' },
  { key: 'wind', label: 'Wind' },
  { key: 'rain', label: 'Rain' },
  { key: 'snow', label: 'Snow' },
  { key: 'off', label: 'Off' },
]

// What each step of the heatmap color scale means per layer. Mirrors the risk
// table in backend/planner/risk.py: each tick is where Moderate, High, Severe, No Travel start.
const SCALE_TICKS = {
  risk: ['Moderate', 'High', 'Severe', 'No Travel'],
  wind: ['25', '35', '45', '55 mph'],
  rain: ['0.10', '0.25', '0.50', '1.00 in/hr'],
  snow: ['0.5', '1', '2', '3 in/hr'],
}

const AXIS_TICK_HOURS = [0, 12, 24, 36, 48]
const PLAY_STEP_MS = 450

function truckStatus(route, momentMs) {
  if (!route) return ''
  const progress = truckProgress(route, momentMs)
  if (progress.status === 'waiting') return 'Not left yet'
  if (progress.status === 'arrived') return 'Arrived'
  const totalMiles = route.checkpoints[route.checkpoints.length - 1].distance_miles
  return `Truck at mile ${Math.round(progress.miles)} of ${formatMiles(totalMiles)}`
}

// One shared clock for the trip: each route is a bar from departure to arrival,
// colored by the risk the truck meets at that time. The same cursor drives the
// map heatmap and the truck marker.
export default function TripTimeline({ plan, selectedRouteId, onSelectRoute, hour, onHourChange, layer, onLayerChange }) {
  const [isPlaying, setIsPlaying] = useState(false)
  const hours = plan.corridor_forecast.hours
  const lastHour = hours.length - 1
  const axisStartMs = Date.parse(hours[0])
  const momentMs = Date.parse(hours[hour])
  const selected = plan.routes.find((route) => route.id === selectedRouteId)
  const cursorLeft = `${(hour / lastHour) * 100}%`

  // One timer per step: advance an hour, and stop on reaching the last one.
  useEffect(() => {
    if (!isPlaying) return undefined
    const timer = setTimeout(() => {
      const nextHour = Math.min(hour + 1, lastHour)
      onHourChange(nextHour)
      if (nextHour === lastHour) setIsPlaying(false)
    }, PLAY_STEP_MS)
    return () => clearTimeout(timer)
  }, [isPlaying, hour, lastHour, onHourChange])

  function togglePlay() {
    // Playing from the end starts over.
    if (!isPlaying && hour >= lastHour) onHourChange(0)
    setIsPlaying(!isPlaying)
  }

  const timeLabel = `+${hour} h, ${formatTime(hours[hour])}`

  return (
    <section className="trip-timeline" aria-label="Trip timeline">
      <div className="timeline-toolbar">
        <button
          type="button"
          className="play-button"
          onClick={togglePlay}
          aria-label={isPlaying ? 'Pause timeline' : 'Play timeline'}
        >
          {isPlaying ? '❚❚' : '▶'}
        </button>
        <p className="timeline-time" aria-live="polite">
          <strong>{timeLabel}</strong>
          <span>{truckStatus(selected, momentMs)}</span>
        </p>
        <div className="heatmap-layers" role="radiogroup" aria-label="Map weather layer">
          {LAYER_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={layer === option.key}
              className={layer === option.key ? 'is-selected' : ''}
              onClick={() => onLayerChange(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="timeline-grid">
        <span />
        <div className="timeline-axis" aria-hidden="true">
          {AXIS_TICK_HOURS.filter((tick) => tick <= lastHour).map((tick) => (
            <span key={tick} style={{ left: `${(tick / lastHour) * 100}%` }}>
              {tick === 0 ? 'Depart' : `+${tick} h`}
            </span>
          ))}
        </div>

        {plan.routes.map((route) => {
          const isSelected = route.id === selectedRouteId
          return (
            <div key={route.id} className="timeline-row">
              <button
                type="button"
                className={isSelected ? 'timeline-label is-selected' : 'timeline-label'}
                aria-pressed={isSelected}
                onClick={() => onSelectRoute(route.id)}
              >
                {/* Phones show only the main highway; the full name stays for screen readers. */}
                {route.rank}. {route.highways?.[0] ?? routeName(route)}
                {route.highways?.length > 1 && (
                  <span className="timeline-label-rest"> / {route.highways.slice(1).join(' / ')}</span>
                )}
              </button>
              <div className={isSelected ? 'timeline-track is-selected' : 'timeline-track'} aria-hidden="true">
                {timelineSegments(route, axisStartMs, lastHour).map((segment) => (
                  <span
                    key={`${segment.start}-${segment.level}`}
                    className={segment.level === 'unknown' ? 'timeline-band is-unknown' : 'timeline-band'}
                    style={{
                      left: `${segment.start * 100}%`,
                      width: `${(segment.end - segment.start) * 100}%`,
                      backgroundColor: riskColor(segment.level),
                    }}
                  />
                ))}
                <span className="timeline-cursor" style={{ left: cursorLeft }} />
              </div>
            </div>
          )
        })}

        <span />
        <input
          type="range"
          className="timeline-slider"
          min="0"
          max={lastHour}
          step="1"
          value={hour}
          onChange={(event) => {
            setIsPlaying(false)
            onHourChange(Number(event.target.value))
          }}
          aria-label="Hours after departure"
          aria-valuetext={timeLabel}
        />
      </div>

      {layer !== 'off' && (
        <div className="heatmap-scale" aria-hidden="true">
          <span className="heatmap-scale-label">Map shading</span>
          <span
            className="heatmap-ramp"
            style={{
              background: `linear-gradient(to right, transparent, ${RISK_COLORS.moderate} 25%, ` +
                `${RISK_COLORS.high} 50%, ${RISK_COLORS.severe} 75%, ${RISK_COLORS.no_travel})`,
            }}
          />
          <span className="heatmap-ticks">
            {SCALE_TICKS[layer].map((tick) => <span key={tick}>{tick}</span>)}
          </span>
        </div>
      )}
    </section>
  )
}
