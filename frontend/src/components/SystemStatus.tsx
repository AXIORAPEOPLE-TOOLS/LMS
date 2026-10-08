/** Limited-mode banner (from /api/health) and an error boundary that never shows a stack trace. */
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CloudOff, RefreshCw } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { Component, useState, type ErrorInfo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Health } from '@/api/types'
import { Button } from './ui'

async function fetchHealth(): Promise<Health> {
  try {
    const response = await fetch('/api/health')
    if (!response.ok) throw new Error('down')
    return (await response.json()) as Health
  } catch {
    return { status: 'degraded', mode: 'offline', components: {}, degraded: [] }
  }
}

export function DegradedBanner() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { data } = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: (q) => (q.state.data?.mode === 'full' ? 60_000 : 15_000) })
  const show = data && data.mode !== 'full'
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          role="status" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
          className={data.mode === 'offline' ? 'bg-bad-50 text-bad-600' : 'bg-warn-50 text-warn-600'}
        >
          <div className="mx-auto flex max-w-6xl items-start gap-3 px-4 py-2.5 text-sm">
            {data.mode === 'offline' ? <CloudOff className="mt-0.5 size-4 shrink-0" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" />}
            <div className="flex-1">
              <p className="font-semibold">{data.mode === 'offline' ? t('degraded.offline') : t('degraded.limited')}</p>
              {open && data.degraded.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-ink-700">
                  {data.degraded.map((d) => <li key={d.name}><b>{d.label}:</b> {d.fallback}</li>)}
                </ul>
              )}
            </div>
            {data.degraded.length > 0 && (
              <button className="shrink-0 font-semibold underline" onClick={() => setOpen((v) => !v)}>{t('degraded.details')}</button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

interface BoundaryState { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Screen crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto mt-16 max-w-md px-4 text-center">
        <h2 className="text-2xl">This screen hit a problem</h2>
        <p className="mt-2 text-ink-600">Your work is safe. Reload the screen to try again.</p>
        <Button className="mt-5" onClick={() => window.location.reload()}>
          <RefreshCw className="size-4" /> Reload
        </Button>
      </div>
    )
  }
}

/** Standard loading / error wrapper for a query: degraded errors keep showing cached data. */
export function QueryState({ isLoading, error, hasData, children, skeleton, onRetry }: {
  isLoading: boolean; error: unknown; hasData: boolean; children: ReactNode; skeleton?: ReactNode; onRetry?: () => void
}) {
  if (hasData) return <>{children}</>
  if (isLoading) return <>{skeleton}</>
  if (error) {
    const message = error instanceof Error ? error.message : 'Something went wrong.'
    return (
      <div className="rounded-[var(--radius-card)] border border-line bg-surface p-6 text-center">
        <p className="font-semibold">We could not load this right now</p>
        <p className="mt-1 text-sm text-ink-600">{message}</p>
        {onRetry && <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}><RefreshCw className="size-4" /> Try again</Button>}
      </div>
    )
  }
  return <>{children}</>
}
