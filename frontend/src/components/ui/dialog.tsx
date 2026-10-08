import { Dialog as RDialog } from 'radix-ui'
import { X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Dialog({ open, onOpenChange, title, description, children, footer, wide }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: ReactNode; description?: ReactNode; children?: ReactNode; footer?: ReactNode; wide?: boolean
}) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <RDialog.Portal forceMount>
            <RDialog.Overlay asChild>
              <motion.div className="fixed inset-0 z-50 bg-ink-900/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </RDialog.Overlay>
            <RDialog.Content asChild aria-describedby={description ? undefined : undefined}>
              <motion.div
                initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 24 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                className={cn('fixed inset-x-0 bottom-0 z-50 max-h-[90vh] overflow-y-auto rounded-t-2xl bg-surface p-5 shadow-xl sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:p-6',
                  wide ? 'sm:w-[min(760px,92vw)]' : 'sm:w-[min(480px,92vw)]')}
              >
                <div className="mb-4 flex items-start justify-between gap-4">
                  <div>
                    <RDialog.Title className="font-serif text-xl font-bold">{title}</RDialog.Title>
                    {description && <RDialog.Description className="mt-1 text-sm text-ink-600">{description}</RDialog.Description>}
                  </div>
                  <RDialog.Close className="rounded-lg p-1.5 text-ink-600 hover:bg-canvas" aria-label="Close">
                    <X className="size-5" />
                  </RDialog.Close>
                </div>
                {children}
                {footer && <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">{footer}</div>}
              </motion.div>
            </RDialog.Content>
          </RDialog.Portal>
        )}
      </AnimatePresence>
    </RDialog.Root>
  )
}
