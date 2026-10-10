import { ArrowRight, CalendarClock, Check, CheckCheck, ClipboardCheck, Clock, Flame, Mail } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { useHome, useMySkills, useMarkRead, useNotifications, usePathway, usePathwayStep, useGeneratePathway, useRsvp } from '@/api/learner'
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
        <div className="space-y-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="text-[26px] sm:text-3xl">{t(greetingKey(), { name: data.first_name })}</h1>
              {data.level_label && <p className="text-sm text-ink-600">{data.level_label}</p>}
            </div>
            {data.streak_days > 0 && (
              <Badge tone="gold" className="px-3 py-1 text-sm"><Flame className="size-4" />{t('home.streak', { count: data.streak_days })}</Badge>
            )}
          </div>

          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="space-y-6">
          <FadeIn>
            <Panel>
              <Eyebrow>{t('home.nextStep')}</Eyebrow>
              <h2 className="mt-2 font-sans text-xl font-bold text-white sm:text-2xl">{data.next_step.title}</h2>
              <p className={cn('mt-2 text-white/75', data.next_step.is_overdue && 'text-gold-100')}>
                {data.next_step.is_overdue && <b className="mr-1 text-gold-500">Overdue ·</b>}{data.next_step.detail}
              </p>
              <ButtonLink to={data.next_step.href} variant="gold" size="lg" className="mt-5">
                {data.next_step.action_label} <ArrowRight className="size-4" />
              </ButtonLink>
            </Panel>
          </FadeIn>

          {data.pathway_progress_pct !== null && (
            <section>
              <SectionTitle action={<Link to="/path" className="text-sm font-semibold text-forest-700">{t('common.seeAll')}</Link>}>{t('home.myPathway')}</SectionTitle>
              <Card>
                {data.pathway_status === 'pending_approval'
                  ? <p className="text-sm text-ink-600">Waiting for your manager to approve your plan.</p>
                  : <ProgressBar value={data.pathway_progress_pct} label={data.pathway_wave ? t('home.waveDone', { pct: data.pathway_progress_pct, wave: data.pathway_wave }) : `${data.pathway_progress_pct}% done`} />}
              </Card>
            </section>
          )}
          <RoleSkillsSummary />
          </div>

          <section>
            <SectionTitle>{t('home.comingUp')}</SectionTitle>
            {data.coming_up.length === 0 ? (
              <Card className="text-sm text-ink-600">{t('home.nothingComing')}</Card>
            ) : (
              <Stagger className="scroll-panel space-y-2.5 pr-1">
                {data.coming_up.map((item) => (
                  <Link key={item.href + item.title} to={item.href} className="flex items-center gap-3 rounded-card border border-line bg-surface p-4 transition-colors hover:border-forest-700">
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
        </div>
      )}
    </QueryState>
  )
}

/** Short version of "Skills for my role" (full list on the profile). */
function RoleSkillsSummary() {
  const { data } = useMySkills()
  const needed = (data ?? []).filter((s) => s.required_by_role)
  if (!needed.length) return null
  const proven = needed.filter((s) => s.proven).length
  const gaps = needed.filter((s) => !s.proven).slice(0, 3)
  return (
    <section>
      <SectionTitle action={<Link to="/me/profile" className="text-sm font-semibold text-forest-700">See all</Link>}>Skills for my role</SectionTitle>
      <Card>
        <ProgressBar value={(proven / needed.length) * 100} label={`${proven} of ${needed.length} skills at the level your role needs`} />
        {gaps.length > 0 && (
          <ul className="mt-4 space-y-2 text-sm">
            {gaps.map((s) => (
              <li key={s.skill_id} className="flex items-center justify-between gap-3">
                <span className="truncate">{s.skill_name}</span>
                <span className="shrink-0 text-[13px] text-ink-600">{s.current_level == null ? 'Not tested yet' : `Level ${s.current_level} of ${s.required_level}`}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  )
}

// ---- L-02 My learning plan ------------------------------------------------------------------
// Internal step keys stay learn/practise/connect/prove; people see plain words.
const STEPS = ['learn', 'practise', 'connect', 'prove'] as const
const STEP_LABEL = { learn: 'Take the course', practise: 'Use it at work', connect: 'Talk to an expert', prove: 'Pass the test' }

function stepIndex(item: PathwayItem) {
  return item.step === 'done' ? 4 : STEPS.indexOf(item.step as (typeof STEPS)[number])
}

function StepTracker({ item }: { item: PathwayItem }) {
  const current = stepIndex(item)
  return (
    <ol className="mt-4 grid grid-cols-4 gap-1" aria-label={`${item.skill_name} steps`}>
      {STEPS.map((step, i) => {
        const state = i < current ? 'done' : i === current ? 'now' : 'later'
        return (
          <li key={step} className="relative flex flex-col items-center text-center">
            {i > 0 && <span className={cn('absolute right-1/2 top-3.5 h-0.5 w-full -translate-y-1/2', i <= current ? 'bg-ok-600' : 'bg-line')} aria-hidden />}
            <span className={cn('relative z-10 flex size-7 items-center justify-center rounded-full text-[12px] font-bold',
              state === 'done' && 'bg-ok-600 text-white', state === 'now' && 'bg-forest-700 text-white ring-4 ring-forest-100', state === 'later' && 'border-2 border-line bg-surface text-ink-400')}>
              {state === 'done' ? <Check className="size-4" /> : i + 1}
            </span>
            <span className={cn('mt-1.5 text-[12px] leading-tight', state === 'now' ? 'font-bold text-forest-800' : state === 'done' ? 'text-ok-600' : 'text-ink-400')}>{STEP_LABEL[step]}</span>
          </li>
        )
      })}
    </ol>
  )
}

function SkillRow({ item }: { item: PathwayItem }) {
  const current = stepIndex(item)
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <b className="block">{item.skill_name}</b>
          <p className="text-[13px] text-ink-600">Level {item.from_level} → {item.to_level}{item.certificate_on_pass && ' · certificate when you pass'}</p>
        </div>
        {item.step === 'done' ? <Badge tone="ok">Done</Badge>
          : item.waiting_for_signoff ? <Badge tone="warn">Waiting for your manager</Badge>
          : <Badge>Step {current + 1} of 4</Badge>}
      </div>
      <StepTracker item={item} />
    </div>
  )
}

function StageCard({ wave, previous }: { wave: Wave; previous?: number }) {
  const left = wave.items.filter((i) => i.step !== 'done').length
  if (wave.status === 'locked') {
    return (
      <Card className="border-dashed bg-surface/60">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg">Stage {wave.number}</h3>
          <span className="flex items-center gap-1.5 text-sm text-ink-600"><Clock className="size-4" />Starts after Stage {previous}</span>
        </div>
        <p className="mt-1 text-sm text-ink-600">About {wave.hours} hours over {fmt.plural(wave.weeks, 'week')}</p>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {wave.items.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-2 rounded-lg bg-canvas px-3 py-2 text-sm">
              <span className="truncate">{i.skill_name}</span>
              <span className="shrink-0 text-[12px] text-ink-600">Level {i.from_level} → {i.to_level}</span>
            </li>
          ))}
        </ul>
      </Card>
    )
  }
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-xl">Stage {wave.number}</h3>
          {wave.status === 'done' ? <Badge tone="ok">Done</Badge> : <Badge>In progress</Badge>}
        </div>
        <span className="text-sm text-ink-600">{wave.status === 'done' ? `${wave.items.length} skills done` : `${left} of ${wave.items.length} skills left`} · about {wave.hours} hours</span>
      </div>
      <ProgressBar className="mt-3" value={wave.progress_pct} label={`${wave.progress_pct}% of this stage done`} />
      <div className="mt-4 space-y-3">
        {wave.items.map((item) => <SkillRow key={item.id} item={item} />)}
      </div>
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
        <PageHeader title="My learning plan" subtitle="Built from your test results: the skills your role needs, in small stages." />
        <EmptyState title="Your plan is not ready yet" body="Finish your tests first, then build your plan. It takes one tap."
          action={<Button onClick={() => generate.mutate(undefined)} loading={generate.isPending}>Build my plan</Button>} />
      </div>
    )
  }

  const next = data?.next_step
  const waiting = next?.action_label === 'Waiting for sign-off'
  const onNext = () => {
    if (!next || waiting) return
    if (next.step === 'practise') setEvidenceFor(next.item_id)
    else if (next.step === 'connect') step.mutate({ itemId: next.item_id, action: 'connected' })
    else if (next.href) navigate(next.href)
  }
  const items = data?.waves.flatMap((w) => w.items) ?? []
  const skillsDone = items.filter((i) => i.step === 'done').length
  const hoursLeft = Math.round(items.filter((i) => i.step !== 'done').reduce((sum, i) => sum + i.estimated_hours, 0))

  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <>
          <PageHeader
            title="My learning plan"
            subtitle={`${skillsDone} of ${items.length} skills done · about ${hoursLeft} hours left · ${data.hours_per_week} hours a week${data.target_role_name ? ` · towards ${data.target_role_name}` : ''}`}
            tag={data.status === 'active' ? <Badge className="mb-2">{data.approved_by_name ? 'Approved by your manager' : 'Active'}</Badge>
              : data.status === 'pending_approval' ? <Badge tone="warn" className="mb-2">Waiting for your manager to approve</Badge> : <Badge tone="ok" className="mb-2">Completed</Badge>}
          />
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
            <Stagger className="order-2 space-y-4 lg:order-1">
              {data.waves.map((wave, i) => <StageCard key={wave.number} wave={wave} previous={data.waves[i - 1]?.number} />)}
            </Stagger>
            <div className="order-1 lg:order-2">
              <Panel className="lg:sticky lg:top-24">
                <Eyebrow>Do this next</Eyebrow>
                {next ? (
                  <>
                    <h2 className="mt-2 font-serif text-2xl text-white">{next.title}</h2>
                    <p className="mt-3 text-white/80">{next.description}</p>
                    <Button variant="gold" size="lg" block className="mt-6" onClick={onNext} loading={step.isPending} disabled={waiting}>{next.action_label}</Button>
                  </>
                ) : (
                  <p className="mt-2 text-white/85">{data.status === 'pending_approval' ? 'Your manager will approve your plan soon.' : 'All done. Great work!'}</p>
                )}
                <div className="mt-6 border-t border-white/20 pt-4 text-sm text-white/85">
                  <p className="font-semibold text-white">How each skill works</p>
                  <ol className="mt-2 space-y-1">{STEPS.map((s, i) => <li key={s}>{i + 1}. {STEP_LABEL[s]}</li>)}</ol>
                </div>
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
            <Field label="What you did" hint="At least 10 characters.">
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
    <div className="mx-auto max-w-4xl">
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
