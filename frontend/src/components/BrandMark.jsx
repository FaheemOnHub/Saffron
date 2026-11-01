import { useEffect, useState } from 'react'

// Four renders of the logo with the lane dashes a step further along each time.
// Shown in turn they make the road roll forward.
const ROAD_FRAMES = ['/brand/road-1.webp', '/brand/road-2.webp', '/brand/road-3.webp', '/brand/road-4.webp']
const FRAME_MS = 140

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

// The logo mark. With `animated`, it cycles the frames (a still frame when the
// viewer has asked for reduced motion). All frames stay mounted and only the
// visible one changes, so there's no flicker while images load.
export default function BrandMark({ animated = false, className = 'size-10' }) {
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    if (!animated || prefersReducedMotion()) return undefined
    const timer = setInterval(() => setFrame((current) => (current + 1) % ROAD_FRAMES.length), FRAME_MS)
    return () => clearInterval(timer)
  }, [animated])

  return (
    <span className={`relative inline-block shrink-0 ${className}`} aria-hidden="true">
      {ROAD_FRAMES.map((src, index) => (
        <img
          key={src}
          src={src}
          alt=""
          width="192"
          height="192"
          className="absolute inset-0 size-full object-contain"
          style={{ opacity: index === (animated ? frame : 0) ? 1 : 0 }}
        />
      ))}
    </span>
  )
}
