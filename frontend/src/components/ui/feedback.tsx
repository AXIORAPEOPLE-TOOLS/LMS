import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { CountUp } from '../motion'

type Tone = 'neutral' | 'forest' | 'ok' | 'warn' | 'bad' | 'info' | 'gold'

const TONES: Record<Tone, string> = {
  neutral: 'bg-canvas text-ink-600 border-line',
  forest: 'bg-forest-100 text-forest-800 border-transparent',
  ok: 'bg-ok-50 text-ok-600 border-transparent',
  warn: 'bg-warn-50 text-warn-600 border-transparent',
  bad: 'bg-bad-50 text-bad-600 border-transparent',
  info: 'bg-info-50 text-info-600 border-transparent',
  gold: 'bg-gold-100 text-gold-600 border-transparent',
}

export function Badge({ tone = 'forest', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold', TONES[tone], className)}>
      {children}
    </span>
  )
}

const STATUS_TONE: Record<string, Tone> = {
  verified: 'ok', valid: 'ok', completed: 'ok', done: 'ok', accepted: 'ok', active: 'ok', on_track: 'ok',
  due_soon: 'warn', pending: 'warn', in_progress: 'info', in_review: 'info', waiting: 'warn', medium: 'warn',
  overdue: 'bad', expired: 'bad', revoked: 'bad', declined: 'neutral', high: 'bad', failed: 'bad', invalid: 'bad',
  draft: 'neutral', archived: 'neutral', low: 'neutral', locked: 'neutral', not_started: 'neutral',
}

export function StatusPill({ status, label }: { status: string; label?: string }) {
  const text = label ?? status.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  return <Badge tone={STATUS_TONE[status] ?? 'neutral'}>{text}</Badge>
}

export function ProgressBar({ value, tone = 'ok', label, className, size = 'md' }: {
  value: number; tone?: 'ok' | 'forest' | 'gold' | 'bad' | 'warn'; label?: ReactNode; className?: string; size?: 'sm' | 'md'
}) {
  const reduce = useReducedMotion()
  const color = { ok: 'bg-ok-600', forest: 'bg-forest-700', gold: 'bg-gold-500', bad: 'bg-bad-600', warn: 'bg-warn-600' }[tone]
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <div className={className}>
      <div
        className={cn('w-full overflow-hidden rounded-full bg-[#e6eae8]', size === 'sm' ? 'h-1.5' : 'h-2.5')}
        role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}
      >
        <motion.div
          className={cn('h-full rounded-full', color)}
          initial={{ width: reduce ? `${clamped}%` : 0 }}
          animate={{ width: `${clamped}%` }}
          transition={{ duration: reduce ? 0 : 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
      {label && <p className="mt-1.5 text-[13px] text-ink-600">{label}</p>}
    </div>
  )
}

export function Stat({ value, label, tone = 'ink', change, suffix, className }: {
  value: number | string; label: ReactNode; tone?: 'ink' | 'ok' | 'warn' | 'bad' | 'info' | 'forest'; change?: number | null; suffix?: string; className?: string
}) {
  const color = { ink: 'text-ink-900', ok: 'text-ok-600', warn: 'text-warn-600', bad: 'text-bad-600', info: 'text-info-600', forest: 'text-forest-700' }[tone]
  return (
    <div className={cn('rounded-card border border-line bg-surface p-4', className)}>
      <div className="flex items-start justify-between gap-2">
        <p className={cn('font-serif text-[30px] font-bold leading-none tabular sm:text-[34px]', color)}>
          {typeof value === 'number' ? <CountUp value={value} /> : value}
          {suffix}
        </p>
        {change != null && change !== 0 && (
          <span className={cn('text-xs font-bold', change > 0 ? 'text-ok-600' : 'text-bad-600')}>
            {change > 0 ? '▲' : '▼'} {Math.abs(change)}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm text-ink-600">{label}</p>
    </div>
  )
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-card border border-dashed border-line bg-surface px-6 py-10 text-center">
      {icon && <div className="mb-3 text-forest-700">{icon}</div>}
      <p className="font-semibold">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-ink-600">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-[#e7ecea]', className)} />
}

export function SkeletonPage() {
  return (
    <div className="space-y-4" aria-busy aria-label="Loading">
      <Skeleton className="h-9 w-2/3 max-w-sm" />
      <Skeleton className="h-36 w-full" />
      <div className="grid gap-3 sm:grid-cols-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    </div>
  )
}

export function Notice({ tone = 'forest', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <div className={cn('rounded-xl px-4 py-3 text-sm', TONES[tone], className)}>{children}</div>
}

export function LevelDots({ level, max = 5, required }: { level: number | null; max?: number; required?: number | null }) {
  return (
    <span className="inline-flex gap-1" aria-label={`Level ${level ?? 0} of ${max}`}>
      {Array.from({ length: max }, (_, i) => (
        <span
          key={i}
          className={cn('size-3 rounded-full', i < (level ?? 0) ? 'bg-forest-700' : 'bg-[#e3e7ea]', required != null && i === required - 1 && 'ring-2 ring-gold-500 ring-offset-1')}
        />
      ))}
    </span>
  )
}
