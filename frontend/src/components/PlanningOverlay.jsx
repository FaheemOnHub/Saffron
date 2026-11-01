import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import BrandMark from './BrandMark'

// The steps the backend runs for every plan, shown in turn while waiting.
// They are not live progress: the request is a single call.
const PLANNING_STEPS = [
  'Finding truck routes',
  'Placing weather checkpoints',
  'Checking forecasts along each route',
  'Ranking routes by risk and time',
]
const STEP_MS = 1400

function StepCaption() {
  const [step, setStep] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setStep((current) => Math.min(current + 1, PLANNING_STEPS.length - 1)), STEP_MS)
    return () => clearInterval(timer)
  }, [])

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.p
        key={step}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.2 }}
        className="text-sm text-muted-foreground"
      >
        {PLANNING_STEPS[step]}
      </motion.p>
    </AnimatePresence>
  )
}

// Covers the map while a plan is loading, with the logo's road rolling.
export default function PlanningOverlay({ isPlanning }) {
  return (
    <AnimatePresence>
      {isPlanning && (
        <motion.div
          key="planning"
          role="status"
          aria-live="polite"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="absolute inset-0 z-20 grid place-items-center bg-background/70 backdrop-blur-[2px]"
        >
          <motion.div
            initial={{ scale: 0.96, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 260, damping: 22 }}
            className="flex w-64 flex-col items-center gap-3 rounded-2xl border bg-card px-6 py-6 text-center shadow-xl"
          >
            <BrandMark animated className="size-24" />
            <p className="text-base font-bold text-brand-navy">Planning your trip</p>
            <StepCaption />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
