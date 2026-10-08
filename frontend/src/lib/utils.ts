import { clsx, type ClassValue } from 'clsx'
import { format, formatDistanceToNowStrict, parseISO } from 'date-fns'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const toDate = (value: string | Date) => (typeof value === 'string' ? parseISO(value) : value)

export const fmt = {
  date: (value?: string | null) => (value ? format(toDate(value), 'd MMM yyyy') : '–'),
  shortDate: (value?: string | null) => (value ? format(toDate(value), 'd MMM') : '–'),
  dayTime: (value?: string | null) => (value ? format(toDate(value), 'EEE d MMM · HH:mm') : '–'),
  time: (value?: string | null) => (value ? format(toDate(value), 'HH:mm') : '–'),
  ago: (value?: string | null) => (value ? `${formatDistanceToNowStrict(toDate(value))} ago` : '–'),
  number: (value: number) => new Intl.NumberFormat('en-IN').format(value),
  plural: (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`,
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export const STATUS_LABEL: Record<string, string> = {
  verified: 'Verified',
  due_soon: 'Due soon',
  overdue: 'Overdue',
  in_review: 'In review',
  draft: 'Draft',
  archived: 'Archived',
}

export const LEVEL_NAMES = ['None', 'Awareness', 'Working', 'Proficient', 'Advanced', 'Expert']
