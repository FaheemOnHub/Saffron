import { CalendarClock } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  QUARTER_HOURS,
  formatClockTime,
  formatDepartureLabel,
  joinLocalDateTime,
  splitLocalDateTime,
} from '@/format'
import { cn } from '@/lib/utils'

// Matches the backend's rule: departures within the next 7 days.
const MAX_DAYS_AHEAD = 7

function startOfToday() {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return today
}

export default function DepartureTimePicker({ id, value, onChange, invalid, describedBy }) {
  const [isOpen, setIsOpen] = useState(false)
  const { date, time } = splitLocalDateTime(value)
  const today = startOfToday()
  const lastDay = new Date(today)
  lastDay.setDate(today.getDate() + MAX_DAYS_AHEAD)

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          className={cn(
            'h-11 w-full justify-start gap-2 rounded-lg bg-card px-3 text-[0.9375rem] font-normal',
            invalid && 'border-destructive',
          )}
        >
          <CalendarClock className="size-4 text-muted-foreground" aria-hidden="true" />
          <span className="truncate">{formatDepartureLabel(value)}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0">
        <Calendar
          mode="single"
          selected={date}
          defaultMonth={date}
          onSelect={(picked) => picked && onChange(joinLocalDateTime(picked, time))}
          disabled={{ before: today, after: lastDay }}
        />
        <div className="flex items-center gap-3 border-t px-3 py-3">
          <span className="text-sm font-medium text-muted-foreground">Time</span>
          <Select value={time} onValueChange={(picked) => onChange(joinLocalDateTime(date, picked))}>
            <SelectTrigger className="h-9 flex-1" aria-label="Departure time">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="max-h-64">
              {QUARTER_HOURS.map((quarter) => (
                <SelectItem key={quarter} value={quarter}>{formatClockTime(quarter)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="button" size="sm" onClick={() => setIsOpen(false)}>Done</Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
