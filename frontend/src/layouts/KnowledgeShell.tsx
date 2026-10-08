/** Knowledge Hub: a separate app with its own menu (slide 3, rule 8). */
import { BookOpenText, Home, LayoutDashboard, ListChecks, Settings2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useLocation } from 'react-router'
import { useKMyItems } from '@/api/knowledge'
import { DegradedBanner, ErrorBoundary } from '@/components/SystemStatus'
import { PageTransition } from '@/components/motion'
import { useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { AppSwitcher, NotificationBell, UserMenu } from './common'

export function KnowledgeShell() {
  const { t } = useTranslation()
  const { has } = useSession()
  const location = useLocation()
  const { data: mine } = useKMyItems()
  const waiting = mine ? mine.overdue + mine.due_soon + mine.waiting_for_me : 0
  const tabs = [
    { to: '/knowledge', label: t('nav.home'), icon: Home, end: true },
    { to: '/knowledge/library', label: t('nav.library'), icon: BookOpenText },
    { to: '/knowledge/my-items', label: t('nav.myItems'), icon: ListChecks, count: waiting },
    ...(has('knowledge_admin', 'admin', 'function_head', 'manager') ? [{ to: '/knowledge/dashboard', label: t('nav.dashboard'), icon: LayoutDashboard }] : []),
    ...(has('knowledge_admin', 'admin') ? [{ to: '/knowledge/admin', label: t('nav.admin'), icon: Settings2 }] : []),
  ]
  return (
    <div className="min-h-dvh">
      <header className="on-dark sticky top-0 z-20 bg-forest-900">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <NavLink to="/knowledge" className="font-serif text-lg font-bold text-white">Knowledge Hub</NavLink>
          <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label="Knowledge Hub">
            {tabs.map((tab) => (
              <NavLink key={tab.to} to={tab.to} end={tab.end}
                className={({ isActive }) => cn('rounded-[10px] px-4 py-1.5 text-sm font-semibold transition-colors', isActive ? 'bg-forest-600 text-white' : 'text-white/80 hover:bg-white/10')}>
                {tab.label}
                {'count' in tab && tab.count ? <span className="ml-1.5 text-gold-500">{tab.count}</span> : null}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <AppSwitcher current="knowledge" dark />
            <NotificationBell dark />
            <UserMenu dark />
          </div>
        </div>
      </header>
      <DegradedBanner />
      <main className="mx-auto max-w-6xl px-4 pb-28 pt-5 sm:pt-7 md:pb-12">
        <ErrorBoundary key={location.pathname}>
          <PageTransition key={location.pathname}>
            <Outlet />
          </PageTransition>
        </ErrorBoundary>
      </main>
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface md:hidden" aria-label="Knowledge Hub">
        <div className="mx-auto flex max-w-lg justify-around">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <NavLink key={tab.to} to={tab.to} end={tab.end}
                className={({ isActive }) => cn('relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-semibold', isActive ? 'text-forest-700' : 'text-ink-400')}>
                <Icon className="size-5" />
                {tab.label}
                {'count' in tab && tab.count ? <span className="absolute right-1/4 top-1 rounded-full bg-gold-500 px-1 text-[10px] text-white">{tab.count}</span> : null}
              </NavLink>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
