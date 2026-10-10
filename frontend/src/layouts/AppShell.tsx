/** Learning app shell: one top navigation on every screen; team and admin sections are menus in the same bar. */
import {
  Activity, BarChart3, BookOpenText, Home, LayoutDashboard as KDashboard, ListChecks, ClipboardCheck, FileText, GitBranch, GraduationCap, LayoutDashboard, Settings2,
  ClipboardList, Mail, PenLine, ShieldCheck, UserCheck, UserPlus, Users, Workflow,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation } from 'react-router'
import { BrandMark } from '@/components/SplashScreen'
import { DegradedBanner, ErrorBoundary } from '@/components/SystemStatus'
import { PageTransition } from '@/components/motion'
import { useSession } from '@/lib/session'
import { useKMyItems } from '@/api/knowledge'
import { NotificationBell, UserMenu } from './common'
import { TopNav, type NavGroup, type NavItem } from './TopNav'

function useNav() {
  const { t } = useTranslation()
  const { has, me } = useSession()
  const items: NavItem[] = [
    { to: '/home', label: t('nav.home'), end: true },
    { to: '/path', label: t('nav.path') },
    { to: '/learn', label: t('nav.learn') },
    { to: '/rank', label: t('nav.rank') },
  ]
  const { data: mine } = useKMyItems(!!me?.can_open_knowledge)
  const waiting = mine ? mine.overdue + mine.due_soon + mine.waiting_for_me : 0
  const groups: NavGroup[] = []
  if (me?.can_open_knowledge) groups.push({
    title: t('nav.knowledge'),
    count: waiting,
    items: [
      { to: '/knowledge', label: 'Overview', icon: Home, end: true },
      { to: '/knowledge/library', label: t('nav.library'), icon: BookOpenText },
      { to: '/knowledge/my-items', label: t('nav.myItems'), icon: ListChecks, count: waiting },
      { to: '/knowledge/dashboard', label: t('nav.dashboard'), icon: KDashboard },
      ...(has('knowledge_admin', 'admin') ? [{ to: '/knowledge/admin', label: t('nav.admin'), icon: Settings2 }] : []),
    ],
  })
  if (has('manager', 'admin')) {
    groups.push({
      title: 'My team',
      items: [
        { to: '/team', label: t('nav.team'), icon: Users, end: true },
        { to: '/team/skills', label: t('nav.skills'), icon: GitBranch },
        { to: '/team/approvals', label: t('nav.approvals'), icon: UserCheck },
        ...(has('admin') ? [] : [{ to: '/admin/training', label: 'Training tracker', icon: ListChecks }]),
        { to: '/team/reports', label: 'Reports', icon: FileText },
      ],
    })
  }
  if (has('admin', 'reviewer', 'expert')) {
    const admin: NavItem[] = []
    if (has('admin')) {
      admin.push(
        { to: '/admin', label: t('nav.adminHome'), icon: LayoutDashboard, end: true },
        { to: '/admin/assign', label: 'Assign training', icon: UserPlus },
        { to: '/admin/helpers', label: 'Helpers', icon: ClipboardList },
        { to: '/admin/training', label: 'Training tracker', icon: ListChecks },
        { to: '/admin/people', label: t('nav.people'), icon: Users },
        { to: '/admin/skills', label: t('nav.skillsTests'), icon: ClipboardCheck },
      )
    }
    if (has('admin', 'expert')) {
      admin.push(
        { to: '/admin/courses', label: t('nav.courses'), icon: GraduationCap },
        { to: '/admin/answers', label: 'Answers to check', icon: PenLine },
      )
    }
    if (has('admin')) {
      admin.push(
        { to: '/admin/workflows', label: t('nav.workflows'), icon: Workflow },
        { to: '/admin/reports', label: t('nav.reports'), icon: BarChart3 },
      )
    }
    if (has('admin', 'reviewer')) admin.push({ to: '/admin/proctoring', label: t('nav.proctoring'), icon: ShieldCheck })
    if (has('admin')) {
      admin.push(
        { to: '/admin/messages', label: 'Message log', icon: Mail },
        { to: '/admin/monitoring', label: 'Monitoring', icon: Activity },
        { to: '/admin/settings', label: 'Settings', icon: Settings2 },
      )
    }
    groups.push({ title: 'Admin', items: admin })
  }
  return { items, groups }
}

export function AppShell() {
  const { items, groups } = useNav()
  const location = useLocation()
  return (
    <div className="min-h-dvh">
      <TopNav
        brand={<Link to="/home" className="flex items-center gap-2.5"><BrandMark className="size-8" /><span className="font-serif text-lg font-bold">Learning</span></Link>}
        items={items}
        groups={groups}
        right={<><NotificationBell /><UserMenu /></>}
      />
      <DegradedBanner />
      <main className="mx-auto max-w-350 px-4 pb-14 pt-6 sm:px-8 sm:pt-8">
        <ErrorBoundary key={location.pathname}>
          <PageTransition key={location.pathname}>
            <Outlet />
          </PageTransition>
        </ErrorBoundary>
      </main>
    </div>
  )
}
