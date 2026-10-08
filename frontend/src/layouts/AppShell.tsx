/** Learning app shell: bottom tabs on phones, left rail on desktop, role-aware sections (slide 3). */
import {
  Activity, BarChart3, BookOpenText, ClipboardCheck, FileText, GitBranch, GraduationCap, Home, LayoutDashboard, Route, Settings2,
  ShieldCheck, Trophy, UserCheck, Users, Workflow,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useLocation } from 'react-router'
import { BrandMark } from '@/components/SplashScreen'
import { DegradedBanner, ErrorBoundary } from '@/components/SystemStatus'
import { PageTransition } from '@/components/motion'
import { useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { AppSwitcher, NotificationBell, UserMenu } from './common'

interface NavItem { to: string; label: string; icon: ComponentType<{ className?: string }>; end?: boolean }

function useSections() {
  const { t } = useTranslation()
  const { has } = useSession()
  const learner: NavItem[] = [
    { to: '/', label: t('nav.home'), icon: Home, end: true },
    { to: '/path', label: t('nav.path'), icon: Route },
    { to: '/learn', label: t('nav.learn'), icon: GraduationCap },
    { to: '/rank', label: t('nav.rank'), icon: Trophy },
    { to: '/knowledge', label: t('nav.knowledge'), icon: BookOpenText },
  ]
  const sections: { title: string; items: NavItem[] }[] = [{ title: t('app.learning'), items: learner }]
  if (has('manager', 'admin')) {
    sections.push({
      title: 'My team',
      items: [
        { to: '/team', label: t('nav.team'), icon: Users, end: true },
        { to: '/team/skills', label: t('nav.skills'), icon: GitBranch },
        { to: '/team/approvals', label: t('nav.approvals'), icon: UserCheck },
        { to: '/team/reports', label: 'Reports', icon: FileText },
      ],
    })
  }
  if (has('admin', 'reviewer', 'expert')) {
    const admin: NavItem[] = []
    if (has('admin')) {
      admin.push(
        { to: '/admin', label: t('nav.adminHome'), icon: LayoutDashboard, end: true },
        { to: '/admin/people', label: t('nav.people'), icon: Users },
        { to: '/admin/skills', label: t('nav.skillsTests'), icon: ClipboardCheck },
      )
    }
    if (has('admin', 'expert')) admin.push({ to: '/admin/courses', label: t('nav.courses'), icon: GraduationCap })
    if (has('admin')) {
      admin.push(
        { to: '/admin/workflows', label: t('nav.workflows'), icon: Workflow },
        { to: '/admin/reports', label: t('nav.reports'), icon: BarChart3 },
      )
    }
    if (has('admin', 'reviewer')) admin.push({ to: '/admin/proctoring', label: t('nav.proctoring'), icon: ShieldCheck })
    if (has('admin')) {
      admin.push({ to: '/admin/monitoring', label: 'Monitoring', icon: Activity }, { to: '/admin/settings', label: 'Settings', icon: Settings2 })
    }
    sections.push({ title: 'Admin', items: admin })
  }
  return { learner, sections }
}

function RailLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) => cn('flex items-center gap-3 rounded-[10px] px-3 py-2 text-[14.5px] font-medium transition-colors',
        isActive ? 'bg-forest-600 text-white' : 'text-white/80 hover:bg-white/10 hover:text-white')}
    >
      <Icon className="size-[18px]" />
      {item.label}
    </NavLink>
  )
}

export function AppShell() {
  const { learner, sections } = useSections()
  const location = useLocation()
  return (
    <div className="min-h-dvh lg:pl-64">
      {/* Desktop rail */}
      <aside className="on-dark fixed inset-y-0 left-0 z-30 hidden w-64 flex-col overflow-y-auto bg-forest-900 px-3 py-5 lg:flex">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <BrandMark className="size-8" />
          <span className="font-serif text-lg font-bold text-white">Learning</span>
        </div>
        <nav className="space-y-6" aria-label="Main">
          {sections.map((section) => (
            <div key={section.title}>
              <p className="mb-1.5 px-3 text-[11px] font-bold uppercase tracking-[0.16em] text-white/45">{section.title}</p>
              <div className="space-y-0.5">{section.items.map((item) => <RailLink key={item.to} item={item} />)}</div>
            </div>
          ))}
        </nav>
      </aside>

      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4">
          <div className="flex items-center gap-2 lg:hidden">
            <BrandMark className="size-7" />
            <span className="font-serif font-bold">Learning</span>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <AppSwitcher current="learning" />
            <NotificationBell />
            <UserMenu />
          </div>
        </div>
        <DegradedBanner />
        {/* Phone: team/admin sections as a scrollable strip */}
        {sections.length > 1 && (
          <nav className="flex gap-1 overflow-x-auto border-t border-line px-3 py-2 lg:hidden" aria-label="Sections">
            {sections.slice(1).flatMap((s) => s.items).map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end}
                className={({ isActive }) => cn('whitespace-nowrap rounded-full px-3 py-1 text-[13px] font-semibold', isActive ? 'bg-forest-700 text-white' : 'bg-forest-100 text-forest-800')}>
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-28 pt-5 sm:pt-7 lg:pb-12">
        <ErrorBoundary key={location.pathname}>
          <PageTransition key={location.pathname}>
            <Outlet />
          </PageTransition>
        </ErrorBoundary>
      </main>

      {/* Phone: 5 learner tabs */}
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface lg:hidden" aria-label="Main">
        <div className="mx-auto grid max-w-lg grid-cols-5">
          {learner.map((item) => {
            const Icon = item.icon
            return (
              <NavLink key={item.to} to={item.to} end={item.end}
                className={({ isActive }) => cn('flex flex-col items-center gap-0.5 py-2 text-[11px] font-semibold', isActive ? 'text-forest-700' : 'text-ink-400')}>
                {({ isActive }) => (
                  <>
                    <span className={cn('rounded-full px-4 py-1 transition-colors', isActive && 'bg-forest-100')}><Icon className="size-5" /></span>
                    {item.label}
                  </>
                )}
              </NavLink>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
