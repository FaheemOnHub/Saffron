import { useEffect, useState } from 'react'
import { formatTime } from '../format'
import { RISK_COLORS } from '../risk'

const LAYER_OPTIONS = [
  { key: 'risk', label: 'Risk' },
  { key: 'wind', label: 'Wind' },
  { key: 'rain', label: 'Rain' },
  { key: 'snow', label: 'Snow' },
  { key: 'off', label: 'Off' },
]

// What each step of the color scale means per layer. Mirrors the risk table in
// backend/planner/risk.py: each tick is where Moderate, High, Severe, No Travel start.
const SCALE_TICKS = {
  risk: ['Moderate', 'High', 'Severe', 'No Travel'],
  wind: ['25', '35', '45', '55 mph'],
  rain: ['0.10', '0.25', '0.50', '1.00 in/hr'],
  snow: ['0.5', '1', '2', '3 in/hr'],
}

const PLAY_STEP_MS = 450

export default function HeatmapControls({ hours, hour, onHourChange, layer, onLayerChange }) {
  const [isPlaying, setIsPlaying] = useState(false)
  const lastHour = hours.length - 1

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
  const isOff = layer === 'off'

  return (
    <section className="heatmap-controls" aria-label="Weather along the trip">
      <div className="heatmap-layers" role="radiogroup" aria-label="Weather layer">
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

      <div className="heatmap-time">
        <button
          type="button"
          className="play-button"
          onClick={togglePlay}
          disabled={isOff}
          aria-label={isPlaying ? 'Pause forecast' : 'Play forecast'}
        >
          {isPlaying ? '❚❚' : '▶'}
        </button>
        <input
          type="range"
          min="0"
          max={lastHour}
          step="1"
          value={hour}
          disabled={isOff}
          onChange={(event) => {
            setIsPlaying(false)
            onHourChange(Number(event.target.value))
          }}
          aria-label="Hours after departure"
          aria-valuetext={timeLabel}
        />
      </div>
      <p className="heatmap-time-label">
        <strong>{isOff ? 'Weather layer off' : timeLabel}</strong>
        {!isOff && hour === 0 && <span> (departure)</span>}
      </p>

      {!isOff && (
        <div className="heatmap-scale" aria-hidden="true">
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
