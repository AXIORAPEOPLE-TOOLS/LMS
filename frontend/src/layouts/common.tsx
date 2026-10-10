import { Bell, BookOpenText, ChevronDown, GraduationCap, Languages, LogOut, User, AlarmClock } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { useNotifications, useUpdatePreferences } from '@/api/learner'
import { setLanguage } from '@/i18n'
import { useSession } from '@/lib/session'
import { cn, initials } from '@/lib/utils'

export function NotificationBell({ dark }: { dark?: boolean }) {
  const { data } = useNotifications()
  const unread = data?.unread ?? 0
  return (
    <Link to="/messages" className={cn('relative rounded-lg p-2', dark ? 'text-white hover:bg-white/10' : 'text-ink-700 hover:bg-forest-100')} aria-label={`Messages${unread ? `, ${unread} unread` : ''}`}>
      <Bell className="size-5" />
      {unread > 0 && (
        <span className="absolute right-1 top-1 flex min-w-4 items-center justify-center rounded-full bg-gold-500 px-1 text-[10px] font-bold text-white">
          {unread > 9 ? '9+' : unread}
        </span>
      )}
    </Link>
  )
}

export function AppSwitcher({ current, dark }: { current: 'learning' | 'knowledge'; dark?: boolean }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const item = 'flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm outline-none data-[highlighted]:bg-forest-100'
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className={cn('flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-semibold', dark ? 'text-white hover:bg-white/10' : 'text-ink-700 hover:bg-forest-100')}>
        <span className="grid grid-cols-2 gap-0.5" aria-hidden>{[0, 1, 2, 3].map((i) => <span key={i} className="size-1.5 rounded-xs bg-current" />)}</span>
        <span className="hidden sm:inline">{t('nav.switchApp')}</span>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className="z-50 w-60 rounded-xl border border-line bg-surface p-1.5 shadow-lg">
          <DropdownMenu.Item className={item} onSelect={() => navigate('/home')}>
            <GraduationCap className="size-5 text-forest-700" />
            <span><b className="block">{t('app.learning')}</b><span className="text-ink-600">Courses, skills, pathways</span></span>
            {current === 'learning' && <span className="ml-auto size-2 rounded-full bg-ok-600" />}
          </DropdownMenu.Item>
          <DropdownMenu.Item className={item} onSelect={() => navigate('/knowledge')}>
            <BookOpenText className="size-5 text-forest-700" />
            <span><b className="block">{t('app.knowledge')}</b><span className="text-ink-600">SOPs, policies, lists</span></span>
            {current === 'knowledge' && <span className="ml-auto size-2 rounded-full bg-ok-600" />}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

export function UserMenu({ dark }: { dark?: boolean }) {
  const { me, signOut } = useSession()
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const save = useUpdatePreferences()
  if (!me) return null
  const item = 'flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-forest-100'
  const toggleLanguage = () => {
    const next = i18n.language === 'hi' ? 'en' : 'hi'
    setLanguage(next)
    save.mutate({ locale: next })
  }
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className={cn('flex items-center gap-1.5 rounded-full p-0.5 pr-1.5', dark ? 'hover:bg-white/10' : 'hover:bg-forest-100')} aria-label="Your account">
        <span className="flex size-8 items-center justify-center rounded-full bg-forest-100 text-xs font-bold text-forest-800">{initials(me.full_name)}</span>
        <ChevronDown className={cn('size-4', dark ? 'text-white' : 'text-ink-600')} />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className="z-50 w-64 rounded-xl border border-line bg-surface p-1.5 shadow-lg">
          <div className="px-3 py-2">
            <p className="font-semibold">{me.full_name}</p>
            <p className="text-[13px] text-ink-600">{me.job_role_name ?? me.email}</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item className={item} onSelect={() => navigate('/me/profile')}><User className="size-4" />{t('nav.profile')}</DropdownMenu.Item>
          <DropdownMenu.Item className={item} onSelect={() => navigate('/me/reminders')}><AlarmClock className="size-4" />{t('nav.reminders')}</DropdownMenu.Item>
          <DropdownMenu.Item className={item} onSelect={toggleLanguage}><Languages className="size-4" />{i18n.language === 'hi' ? 'English' : 'हिंदी'}</DropdownMenu.Item>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item className={item} onSelect={signOut}><LogOut className="size-4" />{t('nav.signOut')}</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
