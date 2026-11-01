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
