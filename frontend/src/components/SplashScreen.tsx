/** Branded splash on first open per session (≤1.4 s). Skipped on reduced motion and return visits. */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { EASE } from '@/lib/motion-tokens'

const KEY = 'lms.splash-shown'

function alreadyShown() {
  try {
    return sessionStorage.getItem(KEY) === '1'
  } catch {
    return true
  }
}

export function BrandMark({ className = 'size-12' }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden>
      <rect width="48" height="48" rx="12" fill="#1F5C4E" />
      <path d="M13 33V15h4v14h9v4H13Z" fill="#fff" />
      <path d="M27 15h8l-6 9 6 9h-8" fill="none" stroke="#B8860B" strokeWidth="3.2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export function SplashScreen() {
  const reduce = useReducedMotion()
  const [visible, setVisible] = useState(() => !reduce && !alreadyShown())

  useEffect(() => {
    if (!visible) return
    try {
      sessionStorage.setItem(KEY, '1')
    } catch {
      /* ignore */
    }
    const timer = window.setTimeout(() => setVisible(false), 1000)
    return () => window.clearTimeout(timer)
  }, [visible])

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="splash"
          className="fixed inset-0 z-100 flex flex-col items-center justify-center bg-linear-to-br from-[#eaf5ef] via-white to-[#fbf4e4]"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.4, ease: EASE } }}
          onClick={() => setVisible(false)}
          role="presentation"
        >
          <motion.p
            className="font-serif text-3xl font-bold text-forest-800 sm:text-4xl"
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: EASE }}
          >
            Learning &amp; Knowledge
          </motion.p>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
