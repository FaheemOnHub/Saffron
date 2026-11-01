import { useState } from 'react'
import { nextQuarterHourLocal } from '../format'

const CHECKPOINT_INTERVAL_OPTIONS = [10, 25, 50]

function FieldError({ id, message }) {
  if (!message) return null
  return <p id={id} className="field-error">{message}</p>
}

export default function TripForm({ onPlan, isPlanning, fieldErrors }) {
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [departureTime, setDepartureTime] = useState(() => nextQuarterHourLocal())
  const [loadWeightLb, setLoadWeightLb] = useState('')
  const [checkpointIntervalMiles, setCheckpointIntervalMiles] = useState(25)

  function handleSubmit(event) {
    event.preventDefault()
    onPlan({ origin, destination, departureTime, loadWeightLb, checkpointIntervalMiles })
  }

  // Each field gets its error linked for screen readers.
  const errorProps = (field) => fieldErrors[field]
    ? { 'aria-invalid': true, 'aria-describedby': `${field}-error` }
    : {}

  return (
    <form className="trip-form" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label htmlFor="origin">From</label>
        <input
          id="origin" value={origin} onChange={(e) => setOrigin(e.target.value)}
          placeholder="City or address" autoComplete="off" required {...errorProps('origin')}
        />
        <FieldError id="origin-error" message={fieldErrors.origin} />
      </div>

      <div className="field">
        <label htmlFor="destination">To</label>
        <input
          id="destination" value={destination} onChange={(e) => setDestination(e.target.value)}
          placeholder="City or address" autoComplete="off" required {...errorProps('destination')}
        />
        <FieldError id="destination-error" message={fieldErrors.destination} />
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="departure_time">Departure</label>
          <input
            id="departure_time" type="datetime-local" value={departureTime}
            onChange={(e) => setDepartureTime(e.target.value)} required {...errorProps('departure_time')}
          />
          <FieldError id="departure_time-error" message={fieldErrors.departure_time} />
        </div>

        <div className="field field-narrow">
          <label htmlFor="load_weight_lb">Load (lb)</label>
          <input
            id="load_weight_lb" type="number" inputMode="numeric" min="0" max="80000" step="100"
            value={loadWeightLb} onChange={(e) => setLoadWeightLb(e.target.value)}
            placeholder="42000" required {...errorProps('load_weight_lb')}
          />
          <FieldError id="load_weight_lb-error" message={fieldErrors.load_weight_lb} />
        </div>
      </div>

      <fieldset className="field interval-picker">
        <legend>Check weather every</legend>
        <div className="segmented">
          {CHECKPOINT_INTERVAL_OPTIONS.map((miles) => (
            <label key={miles} className={miles === checkpointIntervalMiles ? 'is-selected' : ''}>
              <input
                type="radio" name="checkpoint_interval_miles" value={miles}
                checked={miles === checkpointIntervalMiles}
                onChange={() => setCheckpointIntervalMiles(miles)}
              />
              {miles} mi
            </label>
          ))}
        </div>
        <FieldError id="checkpoint_interval_miles-error" message={fieldErrors.checkpoint_interval_miles} />
      </fieldset>

      <button type="submit" className="plan-button" disabled={isPlanning}>
        {isPlanning ? 'Checking routes…' : 'Compare routes'}
      </button>
    </form>
  )
}
