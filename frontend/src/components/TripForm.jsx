import { ArrowDownUp, Loader2, Route } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { nextQuarterHourLocal } from '@/format'
import { cn } from '@/lib/utils'
import DepartureTimePicker from './DepartureTimePicker'
import PlaceCombobox from './PlaceCombobox'

const CHECKPOINT_INTERVAL_OPTIONS = [10, 25, 50]

function FieldError({ id, message }) {
  if (!message) return null
  return <p id={id} className="text-[0.8125rem] font-medium text-destructive">{message}</p>
}

export default function TripForm({ onPlan, isPlanning, fieldErrors, hidden }) {
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [departureTime, setDepartureTime] = useState(() => nextQuarterHourLocal())
  const [loadWeightLb, setLoadWeightLb] = useState('')
  const [checkpointIntervalMiles, setCheckpointIntervalMiles] = useState(25)

  function handleSubmit(event) {
    event.preventDefault()
    onPlan({ origin, destination, departureTime, loadWeightLb, checkpointIntervalMiles })
  }

  function swapPlaces() {
    setOrigin(destination)
    setDestination(origin)
  }

  // Links each field to its error for screen readers.
  const errorFor = (field) => (fieldErrors[field]
    ? { invalid: true, describedBy: `${field}-error` }
    : { invalid: false, describedBy: undefined })

  return (
    <form className="grid gap-4" onSubmit={handleSubmit} noValidate hidden={hidden}>
      <div className="relative grid gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="origin">From</Label>
          <PlaceCombobox id="origin" value={origin} onChange={setOrigin} placeholder="City or address" {...errorFor('origin')} />
          <FieldError id="origin-error" message={fieldErrors.origin} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="destination">To</Label>
          <PlaceCombobox
            id="destination" value={destination} onChange={setDestination}
            placeholder="City or address" {...errorFor('destination')}
          />
          <FieldError id="destination-error" message={fieldErrors.destination} />
        </div>
        <Button
          type="button" variant="outline" size="icon" onClick={swapPlaces}
          aria-label="Swap From and To"
          className="absolute top-[4.6rem] right-0 z-10 size-8 rounded-full bg-card shadow-sm"
        >
          <ArrowDownUp className="size-3.5" aria-hidden="true" />
        </Button>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_8.5rem] items-start gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="departure_time">Departure</Label>
          <DepartureTimePicker
            id="departure_time" value={departureTime} onChange={setDepartureTime} {...errorFor('departure_time')}
          />
          <FieldError id="departure_time-error" message={fieldErrors.departure_time} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="load_weight_lb">Load</Label>
          <div className="relative">
            <Input
              id="load_weight_lb" type="number" inputMode="numeric" min="0" max="80000" step="100"
              value={loadWeightLb} onChange={(event) => setLoadWeightLb(event.target.value)}
              placeholder="42000"
              aria-invalid={fieldErrors.load_weight_lb ? true : undefined}
              aria-describedby={fieldErrors.load_weight_lb ? 'load_weight_lb-error' : undefined}
              className="h-11 rounded-lg bg-card pr-9 tabular-nums"
            />
            <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm text-muted-foreground">lb</span>
          </div>
          <FieldError id="load_weight_lb-error" message={fieldErrors.load_weight_lb} />
        </div>
      </div>

      <div className="grid gap-1.5">
        <Label id="interval-label">Check weather every</Label>
        <ToggleGroup
          type="single"
          variant="outline"
          value={String(checkpointIntervalMiles)}
          onValueChange={(picked) => picked && setCheckpointIntervalMiles(Number(picked))}
          aria-labelledby="interval-label"
          className="w-full"
        >
          {CHECKPOINT_INTERVAL_OPTIONS.map((miles) => (
            <ToggleGroupItem
              key={miles}
              value={String(miles)}
              className={cn(
                'h-10 flex-1 bg-card font-semibold',
                'data-[state=on]:bg-primary data-[state=on]:text-primary-foreground',
              )}
            >
              {miles} mi
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <FieldError id="checkpoint_interval_miles-error" message={fieldErrors.checkpoint_interval_miles} />
      </div>

      <Button type="submit" size="lg" disabled={isPlanning} className="mt-1 h-12 rounded-lg text-base font-bold">
        {isPlanning
          ? <><Loader2 className="size-4 animate-spin" aria-hidden="true" /> Checking routes</>
          : <><Route className="size-4" aria-hidden="true" /> Compare routes</>}
      </Button>
    </form>
  )
}
