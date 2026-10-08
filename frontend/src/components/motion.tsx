/** Motion helpers. Every animation respects prefers-reduced-motion (docs/frontend-ui-guide.md §5). */
import { animate, motion, useInView, useReducedMotion, type Variants } from 'motion/react'
import { Children, useEffect, useRef, useState, type ReactNode } from 'react'
import { EASE } from '@/lib/motion-tokens'


export function PageTransition({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      initial={{ opacity: 0, y: reduce ? 0 : 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: EASE }}
    >
      {children}
    </motion.div>
  )
}

const container: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.04 } } }
const item: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.22, ease: EASE } },
}

/** Staggers the first children in; long lists animate only the first 8 items. */
export function Stagger({ children, className, itemClassName, as = 'div' }: { children: ReactNode; className?: string; itemClassName?: string; as?: 'div' | 'ul' }) {
  const reduce = useReducedMotion()
  const Component = as === 'ul' ? motion.ul : motion.div
  if (reduce) {
    const Plain = as
    return <Plain className={className}>{children}</Plain>
  }
  return (
    <Component className={className} variants={container} initial="hidden" animate="show">
      {Children.toArray(children).map((child, index) =>
        index < 8 ? (
          <motion.div key={index} variants={item} className={itemClassName}>
            {child}
          </motion.div>
        ) : (
          child
        ),
      )}
    </Component>
  )
}

export function FadeIn({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion()
  return (
    <motion.div className={className} initial={{ opacity: 0, y: reduce ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, delay, ease: EASE }}>
      {children}
    </motion.div>
  )
}

/** Counts a number up when it scrolls into view (dashboards). */
export function CountUp({ value, duration = 0.8 }: { value: number; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const reduce = useReducedMotion()
  const [display, setDisplay] = useState(0)
  useEffect(() => {
    if (!inView || reduce) return
    const controls = animate(0, value, { duration, ease: EASE, onUpdate: (v) => setDisplay(Math.round(v)) })
    return () => controls.stop()
  }, [inView, value, duration, reduce])
  return <span ref={ref}>{new Intl.NumberFormat('en-IN').format(reduce ? value : display)}</span>
}
