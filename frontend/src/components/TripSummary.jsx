import { ArrowDown, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatDepartureLabel, timezoneAbbreviation } from '@/format'

// The planned trip in a few lines, shown in place of the form so the results
// start near the top of the panel.
export default function TripSummary({ plan, trip, onEdit }) {
  return (
    <section aria-label="Planned trip" className="grid gap-3 rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex items-start gap-3">
        <div className="grid min-w-0 flex-1 gap-0.5 text-[0.9375rem] font-semibold leading-snug">
          <span className="truncate" title={plan.origin.label}>{plan.origin.label}</span>
          <ArrowDown className="size-3.5 text-muted-foreground" aria-label="to" />
          <span className="truncate" title={plan.destination.label}>{plan.destination.label}</span>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onEdit}>
          <Pencil className="size-3.5" aria-hidden="true" /> Edit trip
        </Button>
      </div>
      <ul className="flex flex-wrap gap-1.5 text-[0.8125rem] text-muted-foreground">
        <li className="rounded-full bg-muted px-2.5 py-1">
          Departs {formatDepartureLabel(trip.departureTime)}{' '}
          {timezoneAbbreviation(plan.origin.timezone, new Date(plan.routes[0].departure_time))}
        </li>
        <li className="rounded-full bg-muted px-2.5 py-1">{plan.load_weight_lb.toLocaleString('en-US')} lb</li>
        <li className="rounded-full bg-muted px-2.5 py-1">Weather every {plan.checkpoint_interval_miles} mi</li>
      </ul>
    </section>
  )
}
