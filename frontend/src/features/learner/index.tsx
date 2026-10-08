import { ArrowRight, CalendarClock, Check, CheckCheck, ClipboardCheck, Flame, Lock, Mail } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { useHome, useMarkRead, useNotifications, usePathway, usePathwayStep, useGeneratePathway, useRsvp } from '@/api/learner'
import type { PathwayItem, Wave } from '@/api/types'
import { FadeIn, Stagger } from '@/components/motion'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, ButtonLink, Card, Dialog, EmptyState, Eyebrow, Field, Notice, PageHeader, Panel, ProgressBar, SectionTitle,
  SkeletonPage, Textarea,
} from '@/components/ui'
import { cn, fmt } from '@/lib/utils'

function greetingKey() {
  const hour = new Date().getHours()
  return hour < 12 ? 'home.greeting_morning' : hour < 17 ? 'home.greeting_afternoon' : 'home.greeting_evening'
}

// ---- L-01 Home ---------------------------------------------------------------------------
export function HomePage() {
  const { t } = useTranslation()
  const { data, isLoading, error, refetch } = useHome()
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <div className="mx-auto max-w-2xl space-y-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="text-[26px] sm:text-3xl">{t(greetingKey(), { name: data.first_name })}</h1>
              {data.level_label && <p className="text-sm text-ink-600">{data.level_label}</p>}
            </div>
            {data.streak_days > 0 && (
              <Badge tone="gold" className="px-3 py-1 text-sm"><Flame className="size-4" />{t('home.streak', { count: data.streak_days })}</Badge>
            )}
          </div>

          <FadeIn>
            <Panel>
              <Eyebrow>{t('home.nextStep')}</Eyebrow>
              <h2 className="mt-2 font-sans text-xl font-bold text-white sm:text-2xl">{data.next_step.title}</h2>
              <p className={cn('mt-2 text-white/75', data.next_step.is_overdue && 'text-gold-100')}>
                {data.next_step.is_overdue && <b className="mr-1 text-gold-500">Overdue ·</b>}{data.next_step.detail}
              </p>
              <ButtonLink to={data.next_step.href} variant="gold" size="lg" block className="mt-5">
                {data.next_step.action_label} <ArrowRight className="size-4" />
              </ButtonLink>
            </Panel>
          </FadeIn>

          {data.pathway_progress_pct !== null && (
            <section>
              <SectionTitle action={<Link to="/path" className="text-sm font-semibold text-forest-700">{t('common.seeAll')}</Link>}>{t('home.myPathway')}</SectionTitle>
              <Card>
                {data.pathway_status === 'pending_approval'
                  ? <p className="text-sm text-ink-600">Waiting for your manager to approve your pathway.</p>
                  : <ProgressBar value={data.pathway_progress_pct} label={data.pathway_wave ? t('home.waveDone', { pct: data.pathway_progress_pct, wave: data.pathway_wave }) : `${data.pathway_progress_pct}% done`} />}
              </Card>
            </section>
          )}

          <section>
            <SectionTitle>{t('home.comingUp')}</SectionTitle>
            {data.coming_up.length === 0 ? (
              <Card className="text-sm text-ink-600">{t('home.nothingComing')}</Card>
            ) : (
              <Stagger className="space-y-2.5">
                {data.coming_up.map((item) => (
                  <Link key={item.href + item.title} to={item.href} className="flex items-center gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4 transition-colors hover:border-forest-700">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-forest-100 text-forest-700">
                      {item.kind === 'session' ? <CalendarClock className="size-5" /> : item.kind === 'skill_check' ? <ClipboardCheck className="size-5" /> : <ArrowRight className="size-5" />}
                    </span>
                    <span className="min-w-0">
                      <b className="block truncate text-[15px]">{item.title}</b>
                      <span className="text-[13px] text-ink-600">{item.detail}</span>
                    </span>
                  </Link>
                ))}
              </Stagger>
            )}
          </section>
        </div>
      )}
    </QueryState>
  )
}

// ---- L-02 My pathway ---------------------------------------------------------------------
const STEPS = ['learn', 'practise', 'connect', 'prove'] as const
const STEP_LABEL = { learn: 'Learn', practise: 'Practise', connect: 'Connect', prove: 'Prove' }

function StepChips({ item }: { item: PathwayItem }) {
  const current = item.step === 'done' ? 4 : STEPS.indexOf(item.step as (typeof STEPS)[number])
  return (
    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {STEPS.map((step, i) => {
        const state = i < current ? 'done' : i === current ? 'now' : 'later'
        return (
          <span key={step} className={cn('flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-semibold',
            state === 'done' && 'bg-ok-50 text-ok-600', state === 'now' && 'bg-forest-100 text-forest-800 ring-1 ring-forest-700/30', state === 'later' && 'bg-canvas text-ink-400')}>
            {state === 'done' ? <Check className="size-4" /> : <span className={cn('size-2 rounded-full', state === 'now' ? 'bg-forest-700' : 'border border-ink-400')} />}
            {STEP_LABEL[step]}
          </span>
        )
      })}
    </div>
  )
}

function WaveCard({ wave }: { wave: Wave }) {
  return (
    <Card className={cn(wave.status === 'locked' && 'bg-canvas')}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xl">Wave {wave.number}</h3>
        <span className="text-sm text-ink-600">About {wave.hours} hours · {fmt.plural(wave.weeks, 'week')}</span>
      </div>
      {wave.status === 'locked' ? (
        <p className="mt-2 flex items-center gap-2 text-sm text-ink-600"><Lock className="size-4" />Locked: {wave.items.map((i) => i.skill_name).join(', ')}</p>
      ) : (
        <>
          <ProgressBar className="mt-3" value={wave.progress_pct} />
          <div className="mt-4 space-y-3">
            {wave.items.map((item) => (
              <div key={item.id} className="rounded-xl border border-line p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <b>{item.skill_name}</b>
                  {item.step === 'done' && <Badge tone="ok">Done</Badge>}
                </div>
                <p className="text-[13px] text-ink-600">
                  Level {item.from_level} to {item.to_level}{item.certificate_on_pass ? ' · Certificate on passing' : ' · Level confirmed by re-test'}
                </p>
                <StepChips item={item} />
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  )
}

export function PathwayPage() {
  const { data, isLoading, error, refetch } = usePathway()
  const generate = useGeneratePathway()
  const step = usePathwayStep()
  const navigate = useNavigate()
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null)
  const [evidence, setEvidence] = useState('')

  if (!isLoading && !error && !data) {
    return (
      <div className="mx-auto max-w-xl">
        <PageHeader title="My pathway" subtitle="Gaps become waves of three skills. Each skill has four steps: learn, practise, connect, prove." />
        <EmptyState title="Your pathway is not built yet" body="Finish your skill checks first, then build your plan. It takes one tap."
          action={<Button onClick={() => generate.mutate(undefined)} loading={generate.isPending}>Build my pathway</Button>} />
      </div>
    )
  }

  const next = data?.next_step
  const onNext = () => {
    if (!next) return
    if (next.step === 'practise' && next.action_label !== 'See status') setEvidenceFor(next.item_id)
    else if (next.step === 'connect') step.mutate({ itemId: next.item_id, action: 'connected' })
    else if (next.href) navigate(next.href)
  }

  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <>
          <PageHeader
            title={data.current_wave ? `Wave ${data.current_wave} of ${data.total_waves}` : 'My pathway'}
            subtitle={`${data.hours_per_week} hours a week${data.target_role_name ? ` · towards ${data.target_role_name}` : ''}`}
            tag={data.status === 'active' ? <Badge className="mb-2">{data.approved_by_name ? 'Manager approved' : 'Active'}</Badge>
              : data.status === 'pending_approval' ? <Badge tone="warn" className="mb-2">Waiting for manager approval</Badge> : <Badge tone="ok" className="mb-2">Completed</Badge>}
          />
          <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
            <Stagger className="order-2 space-y-4 lg:order-1">
              {data.waves.map((wave) => <WaveCard key={wave.number} wave={wave} />)}
            </Stagger>
            <div className="order-1 lg:order-2">
              <Panel className="lg:sticky lg:top-20">
                <Eyebrow>Your next step</Eyebrow>
                {next ? (
                  <>
                    <h2 className="mt-2 font-serif text-2xl text-white">{next.title}</h2>
                    <p className="mt-3 text-white/75">{next.description}</p>
                    <Button variant="gold" size="lg" block className="mt-6" onClick={onNext} loading={step.isPending}
                      disabled={next.action_label === 'See status'}>{next.action_label}</Button>
                  </>
                ) : (
                  <p className="mt-2 text-white/80">{data.status === 'pending_approval' ? 'Your manager will approve your plan soon.' : 'All done. Great work!'}</p>
                )}
                {data.total_waves > 1 && <p className="mt-6 text-sm italic text-white/60">Later waves open when this wave is done.</p>}
              </Panel>
            </div>
          </div>
          <Dialog open={!!evidenceFor} onOpenChange={(o) => !o && setEvidenceFor(null)} title="What did you do?"
            description="Write a few lines about using it on a real task. Your manager signs it off."
            footer={<>
              <Button variant="outline" onClick={() => setEvidenceFor(null)}>Cancel</Button>
              <Button loading={step.isPending} disabled={evidence.trim().length < 10}
                onClick={() => step.mutate({ itemId: evidenceFor!, action: 'evidence', evidence }, { onSuccess: () => { setEvidenceFor(null); setEvidence('') } })}>
                Send to my manager
              </Button>
            </>}>
            <Field label="Your practice" hint="At least 10 characters.">
              <Textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="I used the checklist on a parent call about fees…" />
            </Field>
          </Dialog>
        </>
      )}
    </QueryState>
  )
}

// ---- Messages ------------------------------------------------------------------------------
export function MessagesPage() {
  const { data, isLoading, error, refetch } = useNotifications()
  const markRead = useMarkRead()
  const rsvp = useRsvp()
  const navigate = useNavigate()
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Messages" subtitle="Reminders, invitations and updates."
        actions={data?.unread ? <Button variant="outline" size="sm" onClick={() => markRead.mutate('all')}><CheckCheck className="size-4" />Mark all read</Button> : null} />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data?.items.length === 0 && <EmptyState icon={<Mail className="size-8" />} title="No messages yet" body="Reminders and invitations will appear here." />}
        <Stagger className="space-y-2.5">
          {data?.items.map((n) => (
            <Card key={n.id} className={cn('relative', !n.read_at && 'border-forest-700/40 bg-forest-50')}>
              {!n.read_at && <span className="absolute right-4 top-4 size-2 rounded-full bg-gold-500" aria-label="Unread" />}
              <p className="text-[12px] text-ink-400">{fmt.ago(n.created_at)}</p>
              <b className="mt-0.5 block pr-6">{n.title}</b>
              {n.body && <p className="mt-1 whitespace-pre-line text-sm text-ink-700">{n.body}</p>}
              <div className="mt-3 flex flex-wrap gap-2">
                {n.actions.map((a) => (
                  <Button key={a.label} size="sm" variant={a.label === 'Accept' || a.label === 'Start now' ? 'primary' : 'outline'}
                    onClick={() => {
                      markRead.mutate(n.id)
                      if (a.action === 'rsvp_accept' || a.action === 'rsvp_decline') rsvp.mutate({ sessionId: a.session_id!, accept: a.action === 'rsvp_accept' })
                      else if (a.href) navigate(a.href)
                    }}>
                    {a.label}
                  </Button>
                ))}
                {n.actions.length === 0 && n.link && <Button size="sm" variant="ghost" onClick={() => { markRead.mutate(n.id); navigate(n.link!) }}>Open</Button>}
              </div>
            </Card>
          ))}
        </Stagger>
        {data && data.items.length > 0 && <Notice className="mt-6" tone="neutral">One short message a day at most, only inside your chosen time. Change it in <Link className="font-semibold underline" to="/me/reminders">My reminders</Link>.</Notice>}
      </QueryState>
    </div>
  )
}
