import { cva } from 'class-variance-authority'

export const buttonStyles = cva(
  'inline-flex items-center justify-center gap-2 rounded-[10px] font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50 select-none',
  {
    variants: {
      variant: {
        primary: 'bg-forest-700 text-white hover:bg-forest-800 active:bg-forest-900',
        gold: 'bg-gold-500 text-white hover:bg-gold-600',
        outline: 'border border-forest-700 bg-surface text-forest-700 hover:bg-forest-50',
        ghost: 'text-forest-700 hover:bg-forest-100',
        soft: 'bg-forest-100 text-forest-800 hover:bg-forest-200',
        danger: 'bg-bad-600 text-white hover:brightness-95',
        'outline-light': 'border border-white/40 text-white hover:bg-white/10',
      },
      size: {
        sm: 'h-9 px-3 text-sm',
        md: 'h-11 px-5 text-[15px]',
        lg: 'h-12 px-6 text-base w-full sm:w-auto',
      },
      block: { true: 'w-full' },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)
