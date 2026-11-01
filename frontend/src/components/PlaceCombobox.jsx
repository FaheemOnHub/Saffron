import { Loader2, MapPin } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { fetchPlaceSuggestions } from '@/api'
import { cn } from '@/lib/utils'

const SUGGEST_DELAY_MS = 250
const MIN_QUERY_LENGTH = 2

// A text field with place suggestions underneath, following the WAI-ARIA
// combobox pattern: arrow keys move through suggestions, Enter picks one,
// Escape closes the list. HERE does the matching on the backend.
export default function PlaceCombobox({ id, value, onChange, placeholder, invalid, describedBy }) {
  const [suggestions, setSuggestions] = useState([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  // The label the driver last picked; no need to look it up again.
  const pickedLabel = useRef('')
  const listboxId = `${id}-suggestions`

  useEffect(() => {
    const query = value.trim()
    if (query.length < MIN_QUERY_LENGTH || query === pickedLabel.current) {
      setSuggestions([])
      setIsLoading(false)
      return undefined
    }
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setIsLoading(true)
      try {
        setSuggestions(await fetchPlaceSuggestions(query, { signal: controller.signal }))
        setActiveIndex(-1)
        setIsLoading(false)
      } catch {
        // Aborted by newer typing; that request's results arrive instead.
      }
    }, SUGGEST_DELAY_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [value])

  const showList = isOpen && suggestions.length > 0

  function pick(label) {
    pickedLabel.current = label
    onChange(label)
    setIsOpen(false)
    setActiveIndex(-1)
  }

  function handleKeyDown(event) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (suggestions.length === 0) return
      event.preventDefault()
      setIsOpen(true)
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((current) => (current + step + suggestions.length) % suggestions.length)
    } else if (event.key === 'Enter' && showList && activeIndex >= 0) {
      // Picking a suggestion shouldn't also submit the form.
      event.preventDefault()
      pick(suggestions[activeIndex].label)
    } else if (event.key === 'Escape' && showList) {
      event.preventDefault()
      setIsOpen(false)
    }
  }

  return (
    <div className="relative">
      <div
        className={cn(
          'flex h-11 items-center gap-2 rounded-lg border bg-card px-3 shadow-xs transition-[box-shadow,border-color]',
          'focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/25',
          invalid && 'border-destructive focus-within:ring-destructive/20',
        )}
      >
        <MapPin className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <input
          id={id}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={showList}
          aria-controls={listboxId}
          aria-activedescendant={showList && activeIndex >= 0 ? `${id}-option-${activeIndex}` : undefined}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          autoComplete="off"
          spellCheck={false}
          value={value}
          placeholder={placeholder}
          onChange={(event) => {
            onChange(event.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          onBlur={() => setIsOpen(false)}
          onKeyDown={handleKeyDown}
          className="h-full w-full min-w-0 bg-transparent text-[0.9375rem] outline-none placeholder:text-muted-foreground"
        />
        {isLoading && <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />}
      </div>

      <ul
        id={listboxId}
        role="listbox"
        aria-label="Suggested places"
        hidden={!showList}
        // Keep focus in the field while a suggestion is clicked.
        onMouseDown={(event) => event.preventDefault()}
        className="absolute top-full z-30 mt-1.5 max-h-72 w-full overflow-y-auto rounded-lg border bg-popover p-1 shadow-lg"
      >
        {suggestions.map((suggestion, index) => (
          <li
            key={suggestion.id}
            id={`${id}-option-${index}`}
            role="option"
            aria-selected={index === activeIndex}
            onClick={() => pick(suggestion.label)}
            onMouseMove={() => setActiveIndex(index)}
            className={cn(
              'flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm',
              index === activeIndex && 'bg-accent text-accent-foreground',
            )}
          >
            <MapPin className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="truncate">{suggestion.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
