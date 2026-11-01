export function formatDuration(totalSeconds) {
  const totalMinutes = Math.round(totalSeconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes}m`
  return `${hours}h ${String(minutes).padStart(2, '0')}m`
}

export function formatMiles(miles) {
  return `${Math.round(miles).toLocaleString('en-US')} mi`
}

// Times show in the viewer's timezone, with the zone named so a driver
// crossing zones isn't misled.
const timeFormatter = new Intl.DateTimeFormat('en-US', {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

export function formatTime(isoString) {
  return timeFormatter.format(new Date(isoString))
}

// Default departure: the next quarter hour, in the format datetime-local expects.
export function nextQuarterHourLocal(now = new Date()) {
  const rounded = new Date(now)
  rounded.setSeconds(0, 0)
  rounded.setMinutes(Math.ceil((rounded.getMinutes() + 1) / 15) * 15)
  const pad = (value) => String(value).padStart(2, '0')
  return `${rounded.getFullYear()}-${pad(rounded.getMonth() + 1)}-${pad(rounded.getDate())}` +
    `T${pad(rounded.getHours())}:${pad(rounded.getMinutes())}`
}

const pad = (value) => String(value).padStart(2, '0')

// The form keeps departure as a local "YYYY-MM-DDTHH:mm" string (what
// buildTripPlanQuery expects); the picker edits the date and time parts separately.
export function splitLocalDateTime(value) {
  const [datePart, timePart = '00:00'] = value.split('T')
  const [year, month, day] = datePart.split('-').map(Number)
  return { date: new Date(year, month - 1, day), time: timePart.slice(0, 5) }
}

export function joinLocalDateTime(date, time) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${time}`
}

// Every quarter hour of the day, as "HH:mm".
export const QUARTER_HOURS = Array.from({ length: 96 }, (_, index) =>
  `${pad(Math.floor(index / 4))}:${pad((index % 4) * 15)}`)

export function formatClockTime(time) {
  const [hours, minutes] = time.split(':').map(Number)
  const suffix = hours < 12 ? 'AM' : 'PM'
  return `${hours % 12 || 12}:${pad(minutes)} ${suffix}`
}

const departureFormatter = new Intl.DateTimeFormat('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

export function formatDepartureLabel(value) {
  const { date, time } = splitLocalDateTime(value)
  return `${departureFormatter.format(date)} at ${formatClockTime(time)}`
}
