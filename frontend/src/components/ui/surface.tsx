import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-card border border-line bg-surface p-4 sm:p-5', className)} {...props} />
}

/** Dark forest panel used for "Your next step" and other single important actions. */
export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('on-dark rounded-card bg-linear-to-br from-forest-700 via-forest-600 to-[#5aa58a] p-5 text-white shadow-sm sm:p-6', className)} {...props} />
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn('text-[11px] font-bold uppercase tracking-[0.18em] text-gold-500', className)}>{children}</p>
}

export function SectionTitle({ children, action, className }: { children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn('mb-3 flex items-center justify-between gap-3', className)}>
      <h2 className="font-sans text-[17px] font-bold">{children}</h2>
      {action}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions, tag }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; tag?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-col gap-3 sm:mb-7 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {tag}
        <h1 className="text-[26px] leading-tight sm:text-[32px]">{title}</h1>
        {subtitle && <p className="mt-1 text-ink-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  )
}

export function Divider({ className }: { className?: string }) {
  return <hr className={cn('border-line', className)} />
}
