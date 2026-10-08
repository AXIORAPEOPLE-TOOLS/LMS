import { Switch } from 'radix-ui'
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const control =
  'w-full rounded-[10px] border border-line bg-surface px-3.5 py-2.5 text-[15px] text-ink-900 placeholder:text-ink-400 focus:border-forest-700 focus:outline-none focus:ring-2 focus:ring-forest-700/20 disabled:bg-canvas'

export function Field({ label, hint, error, children, htmlFor, className }: {
  label: ReactNode; hint?: ReactNode; error?: string; children: ReactNode; htmlFor?: string; className?: string
}) {
  const message = error ? <p className="text-[13px] text-bad-600" role="alert">{error}</p> : hint ? <p className="text-[13px] text-ink-600">{hint}</p> : null
  if (!htmlFor) {
    // No id given: wrap the control in the label so it is always announced with its name.
    return (
      <div className={cn('space-y-1.5', className)}>
        <label className="block space-y-1.5">
          <span className="block text-sm font-semibold text-ink-700">{label}</span>
          {children}
        </label>
        {message}
      </div>
    )
  }
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="block text-sm font-semibold text-ink-700">{label}</label>
      {children}
      {message}
    </div>
  )
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn(control, className)} {...props} />
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn(control, 'min-h-28', className)} {...props} />
})

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...props }, ref) {
  return (
    <select ref={ref} className={cn(control, 'appearance-none bg-[length:16px] bg-[right_12px_center] bg-no-repeat pr-9', className)}
      style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235B6670' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }}
      {...props}>
      {children}
    </select>
  )
})

export function Toggle({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; hint?: ReactNode; disabled?: boolean }) {
  const id = useId()
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <label htmlFor={id} className="min-w-0">
        <span className="block font-medium">{label}</span>
        {hint && <span className="block text-[13px] text-ink-600">{hint}</span>}
      </label>
      <Switch.Root
        id={id} checked={checked} onCheckedChange={onChange} disabled={disabled}
        className="relative h-7 w-12 shrink-0 rounded-full bg-[#d5dade] transition-colors data-[state=checked]:bg-ok-600 disabled:opacity-50"
      >
        <Switch.Thumb className="block size-6 translate-x-0.5 rounded-full bg-white shadow transition-transform duration-200 data-[state=checked]:translate-x-[22px]" />
      </Switch.Root>
    </div>
  )
}

export function Segmented<T extends string>({ value, onChange, options, className }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; className?: string
}) {
  return (
    <div role="tablist" className={cn('inline-flex max-w-full gap-1 overflow-x-auto rounded-xl bg-canvas p-1', className)}>
      {options.map((option) => (
        <button
          key={option.value} role="tab" aria-selected={value === option.value} onClick={() => onChange(option.value)}
          className={cn('whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors',
            value === option.value ? 'bg-forest-700 text-white shadow-sm' : 'text-ink-600 hover:bg-white')}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
