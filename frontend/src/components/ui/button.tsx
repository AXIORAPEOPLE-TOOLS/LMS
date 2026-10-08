import type { VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { motion } from 'motion/react'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router'
import { cn } from '@/lib/utils'
import { buttonStyles } from './button-styles'

type Variants = VariantProps<typeof buttonStyles>

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, Variants {
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, block, loading, children, disabled, ...props },
  ref,
) {
  return (
    <motion.button
      ref={ref}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.15 }}
      className={cn(buttonStyles({ variant, size, block }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...(props as object)}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </motion.button>
  )
})

export function ButtonLink({ className, variant, size, block, ...props }: LinkProps & Variants) {
  return <Link className={cn(buttonStyles({ variant, size, block }), className)} {...props} />
}
