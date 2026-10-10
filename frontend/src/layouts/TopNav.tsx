/** One top navigation for every screen in both apps: links in a row, grouped sections as menus, a drawer on phones. */
import { Check, ChevronDown, Menu, X } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { useState, type ComponentType, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router'
import { cn } from '@/lib/utils'

export interface NavItem {
  to: string
  label: string
  icon?: ComponentType<{ className?: string }>
  end?: boolean
  count?: number
}
export interface NavGroup { title: string; items: NavItem[]; count?: number }

const link = 'flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[14.5px] font-semibold transition-colors'
const linkOn = 'bg-forest-700 text-white shadow-sm'
const linkOff = 'text-ink-700 hover:bg-forest-100 hover:text-forest-800'

function Count({ n }: { n?: number }) {
  return n ? <span className="rounded-full bg-gold-500 px-1.5 text-[11px] font-bold leading-4 text-white">{n}</span> : null
}

function GroupMenu({ group }: { group: NavGroup }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const isOn = (i: NavItem) => (i.end ? pathname === i.to : pathname.startsWith(i.to))
  const active = group.items.some(isOn)
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className={cn(link, 'outline-none', active ? linkOn : linkOff)}>
        {group.title}<Count n={group.count} />
        <ChevronDown className="size-4" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={8} className="z-50 min-w-56 rounded-xl border border-line bg-surface p-1.5 shadow-lg">
          {group.items.map((item) => {
            const Icon = item.icon
            const on = isOn(item)
            return (
              <DropdownMenu.Item key={item.to} onSelect={() => navigate(item.to)} aria-current={on ? 'page' : undefined}
                className={cn('flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium outline-none data-[highlighted]:bg-forest-100',
                  on && 'bg-forest-100 font-bold text-forest-800')}>
                {Icon && <Icon className="size-4 text-forest-700" />}
                {item.label}<Count n={item.count} />
                {on && <Check className="ml-auto size-4 text-forest-700" />}
              </DropdownMenu.Item>
            )
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

export function TopNav({ brand, items, groups = [], right }: { brand: ReactNode; items: NavItem[]; groups?: NavGroup[]; right: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-350 items-center gap-4 px-4 sm:px-8">
        <div className="flex shrink-0 items-center gap-2.5">{brand}</div>
        <nav className="ml-4 hidden items-center gap-1 lg:flex" aria-label="Main">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => cn(link, isActive ? linkOn : linkOff)}>
              {item.label}<Count n={item.count} />
            </NavLink>
          ))}
          {groups.map((g) => <GroupMenu key={g.title} group={g} />)}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          {right}
          <button className="rounded-lg p-2 text-ink-700 hover:bg-forest-100 lg:hidden" onClick={() => setOpen((o) => !o)} aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open}>
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>
      {open && (
        <nav onClick={(e) => (e.target as HTMLElement).closest('a') && setOpen(false)} className="max-h-[calc(100dvh-4rem)] overflow-y-auto border-t border-line bg-surface px-4 pb-5 pt-3 lg:hidden" aria-label="Menu">
          <div className="grid gap-1">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => cn(link, 'rounded-xl py-2.5', isActive ? linkOn : linkOff)}>
                {item.label}<Count n={item.count} />
              </NavLink>
            ))}
          </div>
          {groups.map((g) => (
            <div key={g.title} className="mt-4">
              <p className="mb-1 px-3.5 text-[11px] font-bold uppercase tracking-[0.16em] text-ink-400">{g.title}<Count n={g.count} /></p>
              <div className="grid gap-1">
                {g.items.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => cn(link, 'rounded-xl py-2.5', isActive ? linkOn : linkOff)}>
                    {item.label}<Count n={item.count} />
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
      )}
    </header>
  )
}
