import { Columns3, Wind } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { routeName } from '@/compare'
import { formatDuration, formatMiles, formatTime } from '@/format'
import { cn } from '@/lib/utils'
import { riskColor } from '@/risk'
import CompareDialog from './CompareDialog'
import RiskStrip from './RiskStrip'

// Only levels a driver needs to act on get a line; Low/Moderate stay in the strip.
const CALLOUT_LEVELS = ['no_travel', 'severe', 'high']

function RiskCallouts({ summary, levelLabels }) {
  const callouts = CALLOUT_LEVELS
    .filter((level) => summary.miles_by_level[level] > 0)
    .map((level) => ({ level, miles: summary.miles_by_level[level] }))

  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[0.8125rem] text-muted-foreground">
      {callouts.length === 0 && <li>No High or Severe weather forecast</li>}
      {callouts.map(({ level, miles }) => (
        <li key={level} className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <span className="size-2.5 rounded-[3px]" style={{ backgroundColor: riskColor(level) }} aria-hidden="true" />
          {formatMiles(miles)} {levelLabels[level]}
        </li>
      ))}
      {summary.gust_warning_count > 0 && (
        <li className="inline-flex items-center gap-1">
          <Wind className="size-3.5" aria-hidden="true" />
          Gusts at {summary.gust_warning_count} checkpoint{summary.gust_warning_count > 1 ? 's' : ''}
        </li>
      )}
      {summary.unknown_miles > 0 && <li>{formatMiles(summary.unknown_miles)} beyond the forecast range</li>}
    </ul>
  )
}

function RouteCard({ route, isSelected, onSelect, levelLabels, destinationTimezone }) {
  return (
    <li>
      <button
        type="button"
        aria-pressed={isSelected}
        onClick={() => onSelect(route.id)}
        className={cn(
          'grid w-full gap-2.5 rounded-xl border bg-card p-4 text-left shadow-xs transition-[border-color,box-shadow]',
          'hover:border-brand-blue/50 hover:shadow-sm',
          isSelected && 'border-brand-blue ring-[3px] ring-brand-blue/15',
        )}
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-[1.0625rem] font-extrabold tracking-tight">
            <span className="text-muted-foreground">{route.rank}.</span> {routeName(route)}
          </span>
          {route.is_recommended && <Badge className="bg-brand-blue">Recommended</Badge>}
          {route.is_detour && <Badge variant="outline">Forced detour</Badge>}
        </span>

        <span className="flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-muted-foreground tabular-nums">
          <span><strong className="font-bold text-foreground">{formatDuration(route.duration_s)}</strong> driving</span>
          <span>{formatMiles(route.distance_miles)}</span>
          <span>Arrive {formatTime(route.arrival_time, destinationTimezone)}</span>
        </span>

        <RiskStrip checkpoints={route.checkpoints} levelLabels={levelLabels} />
        <RiskCallouts summary={route.risk_summary} levelLabels={levelLabels} />

        {route.is_recommended && (
          <span className="border-t pt-2.5 text-[0.8125rem] font-semibold text-brand-navy">
            {route.recommendation_reason}
          </span>
        )}
      </button>
    </li>
  )
}

export default function RouteList({ plan, selectedRouteId, onSelectRoute }) {
  const levelLabels = Object.fromEntries(plan.risk_levels.map((level) => [level.key, level.label]))
  const [isComparing, setIsComparing] = useState(false)
  const routeCount = plan.routes.length

  return (
    <section aria-labelledby="route-list-heading" className="grid gap-3">
      <div className="flex items-center gap-3">
        <h2 id="route-list-heading" className="flex-1 text-base font-bold">
          {routeCount} {routeCount === 1 ? 'route' : 'routes'}, best first
        </h2>
        {routeCount > 1 && (
          <Button type="button" variant="outline" size="sm" onClick={() => setIsComparing(true)}>
            <Columns3 className="size-3.5" aria-hidden="true" /> Compare
          </Button>
        )}
      </div>
      {routeCount < 3 && (
        <p className="text-sm text-muted-foreground">
          Only {routeCount} distinct truck route{routeCount > 1 ? 's' : ''} found between these places.
        </p>
      )}

      <ol className="grid gap-3">
        {plan.routes.map((route) => (
          <RouteCard
            key={route.id}
            route={route}
            isSelected={route.id === selectedRouteId}
            onSelect={onSelectRoute}
            levelLabels={levelLabels}
            destinationTimezone={plan.destination.timezone}
          />
        ))}
      </ol>

      <CompareDialog plan={plan} isOpen={isComparing} onClose={() => setIsComparing(false)} levelLabels={levelLabels} />

      <ul className="flex flex-wrap gap-x-3 gap-y-1 pt-1 text-xs text-muted-foreground" aria-label="Risk levels">
        {plan.risk_levels.map((level) => (
          <li key={level.key} className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[3px]" style={{ backgroundColor: riskColor(level.key) }} aria-hidden="true" />
            {level.label}
          </li>
        ))}
      </ul>
    </section>
  )
}
