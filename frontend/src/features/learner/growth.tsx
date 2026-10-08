import { fetchEventSource } from '@microsoft/fetch-event-source'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowUp, ArrowRight, Check, Flame, Lock, Medal, Star } from 'lucide-react'
import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import {
  keys, useBadges, useBoard, useCareer, useCareerAction, useCareerDetail, useChallenges, useCompliance, useJoinChallenge, useMe,
  useMySkills, useProfile, useUpdatePreferences,
} from '@/api/learner'
import type { Board, Me } from '@/api/types'
import { Stagger } from '@/components/motion'
import { EASE } from '@/lib/motion-tokens'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, Card, Field, Input, Notice, PageHeader, Panel, ProgressBar, Segmented, Select, SkeletonPage, Toggle,
} from '@/components/ui'
import { getToken } from '@/lib/auth'
import { cn, initials } from '@/lib/utils'

// ---- L-08 Leaderboards (live) ----------------------------------------------------------------
const BOARDS = [
  { value: 'skill_champions', label: 'Skill champions' },
  { value: 'learning_hours', label: 'Learning hours' },
  { value: 'pathway_progress', label: 'Pathway progress' },
  { value: 'most_improved', label: 'Most improved' },
] as const

/** Pushes new board versions into the query cache. If the stream fails, the 15 s poll keeps working. */
function useLiveBoard(board: string, params: Record<string, string | undefined>, onLive: (live: boolean) => void) {
  const client = useQueryClient()
  useEffect(() => {
    const controller = new AbortController()
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString()
    void fetchEventSource(`/api/leaderboards/${board}/stream?${query}`, {
      signal: controller.signal,
      headers: { Authorization: `Bearer ${getToken() ?? ''}` },
      openWhenHidden: false,
      onopen: async (r) => onLive(r.ok),
      onmessage: (event) => {
        if (event.event === 'board') client.setQueryData(keys.board(board, params), JSON.parse(event.data) as Board)
        if (event.event === 'degraded') onLive(false)
      },
      onerror: () => {
        onLive(false)
        return 15_000 // retry later, polling covers the gap
      },
    })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board, JSON.stringify(params)])
}

export function RankPage() {
  const [board, setBoard] = useState<string>('skill_champions')
  const [scope, setScope] = useState('team')
  const [period, setPeriod] = useState('quarter')
  const [skill, setSkill] = useState<string>('')
  const [live, setLive] = useState(false)
  const skills = useMySkills()
  const params = { scope, period, skill_id: board === 'skill_champions' ? skill || undefined : undefined }
  const { data, isLoading, error, refetch } = useBoard(board, params)
  const compliance = useCompliance()
  useLiveBoard(board, params, setLive)
  const tested = skills.data?.filter((s) => s.score !== null) ?? []

  return (
    <>
      <PageHeader title="Leaderboards" subtitle="Points only for real learning. Anyone can hide their name."
        actions={<Badge tone={live ? 'bad' : 'neutral'} className="px-3 py-1">{live ? <><span className="size-2 animate-pulse rounded-full bg-bad-600" /> Live</> : 'Updating every 15 s'}</Badge>} />
      <Segmented className="mb-3" value={board} onChange={setBoard} options={BOARDS.map((b) => ({ value: b.value, label: b.label }))} />
      <div className="mb-4 flex flex-wrap gap-2">
        {board === 'skill_champions' && tested.length > 0 && (
          <Select className="w-auto min-w-48" value={skill} onChange={(e) => setSkill(e.target.value)} aria-label="Skill">
            <option value="">My first tested skill</option>
            {tested.map((s) => <option key={s.skill_id} value={s.skill_id}>{s.skill_name}</option>)}
          </Select>
        )}
        <Select className="w-auto" value={scope} onChange={(e) => setScope(e.target.value)} aria-label="Who"><option value="team">My team</option><option value="company">Whole company</option></Select>
        <Select className="w-auto" value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="When"><option value="week">This week</option><option value="month">This month</option><option value="quarter">This quarter</option></Select>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
          <Card className="p-2 sm:p-3">
            {data?.rows.length === 0 && <p className="p-6 text-center text-ink-600">No one on this board yet. Finish a lesson to appear here.</p>}
            <LayoutGroup>
              <ol className="space-y-1.5">
                <AnimatePresence initial={false}>
                  {data?.rows.map((row) => {
                    const top = Math.max(...(data.rows.map((r) => r.value) ?? [1]), 1)
                    return (
                      <motion.li layout key={row.user_id ?? row.name + row.rank} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        transition={{ layout: { duration: 0.45, ease: EASE } }}
                        className={cn('grid grid-cols-[36px_1fr_auto] items-center gap-3 rounded-xl border px-3 py-2.5 sm:grid-cols-[36px_1.2fr_1fr_1fr_auto]',
                          row.is_me ? 'border-forest-700 bg-forest-50' : 'border-line bg-surface')}>
                        <span className={cn('flex size-8 items-center justify-center rounded-full text-sm font-bold', row.rank <= 3 ? 'bg-gold-500 text-white' : 'bg-canvas text-ink-600')}>{row.rank}</span>
                        <span className="min-w-0"><b className="block truncate">{row.name}</b><span className="text-[12px] text-ink-600 sm:hidden">{row.department}</span></span>
                        <span className="hidden truncate text-sm text-ink-600 sm:block">{row.department}</span>
                        <span className="hidden items-center gap-2 sm:flex"><ProgressBar className="flex-1" size="sm" tone="forest" value={(row.value / top) * 100} /></span>
                        <span className="flex items-center gap-3 text-right">
                          <b className="tabular">{row.display}</b>
                          {row.change ? <span className={cn('w-8 text-xs font-bold', row.change > 0 ? 'text-ok-600' : 'text-bad-600')}>{row.change > 0 ? '▲' : '▼'} {Math.abs(row.change)}</span> : <span className="w-8 text-xs text-ink-400">—</span>}
                        </span>
                      </motion.li>
                    )
                  })}
                </AnimatePresence>
              </ol>
            </LayoutGroup>
            {data?.rows.some((r) => r.name === 'A colleague') && <p className="px-2 pt-3 text-[13px] italic text-ink-600">“A colleague” chose to hide their name. They still count in team totals.</p>}
          </Card>
        </QueryState>
        <Card>
          <h2 className="text-lg">Mandatory training on time</h2>
          <p className="text-[13px] text-ink-600">By department. No individual names.</p>
          <Stagger className="mt-4 space-y-3">
            {compliance.data?.rows.map((r) => (
              <div key={r.department}>
                <div className="mb-1 flex justify-between text-sm"><span>{r.department}</span><b className="tabular">{r.on_time_pct}%</b></div>
                <ProgressBar size="sm" tone={r.on_time_pct >= 85 ? 'ok' : 'bad'} value={r.on_time_pct} />
              </div>
            ))}
          </Stagger>
          {compliance.data?.rows.length === 0 && <p className="mt-4 text-sm text-ink-600">No mandatory training due yet.</p>}
        </Card>
      </div>
    </>
  )
}

// ---- L-07 Career map -------------------------------------------------------------------------
export function CareerPage() {
  const { data, isLoading, error, refetch } = useCareer()
  const [selected, setSelected] = useState<string | undefined>()
  const chosen = selected ?? data?.options.find((o) => o.direction === 'up' && !o.needs_more_tests)?.role_id ?? data?.options[0]?.role_id
  const detail = useCareerDetail(chosen)
  const action = useCareerAction()
  const up = data?.options.filter((o) => o.direction === 'up') ?? []
  const side = data?.options.filter((o) => o.direction === 'side') ?? []

  const Option = ({ o }: { o: (typeof up)[number] }) => (
    <button onClick={() => setSelected(o.role_id)}
      className={cn('w-full rounded-[var(--radius-card)] border bg-surface p-4 text-left transition-colors', chosen === o.role_id ? 'border-2 border-forest-700 bg-forest-50' : 'border-line hover:border-forest-700/50')}>
      <b className="block">{o.role_name}</b>
      <div className="mt-2 flex items-center gap-3">
        <Badge tone={o.direction === 'up' ? 'ok' : 'info'}>{o.direction === 'up' ? <><ArrowUp className="size-3" />Up</> : <><ArrowRight className="size-3" />Side</>}</Badge>
        {o.readiness_pct !== null ? <><ProgressBar className="flex-1" size="sm" tone="gold" value={o.readiness_pct} /><b className="text-sm tabular">{o.readiness_pct}%</b></>
          : <span className="text-[13px] italic text-ink-600">needs more tests first</span>}
      </div>
    </button>
  )

  return (
    <>
      <PageHeader title="Where can I grow?" subtitle="Up and sideways, with how ready you are and what to learn." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && (
          <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
            <div className="space-y-3">
              {up.length > 0 && <Stagger className="space-y-3">{[...up].reverse().map((o) => <Option key={o.role_id} o={o} />)}</Stagger>}
              <Panel>
                <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/60">You are here</p>
                <h2 className="mt-1 font-sans text-xl font-bold text-white">{data.current_role_name ?? 'No role yet'}</h2>
                <p className="mt-1 text-sm text-white/70">Role-ready in {data.role_ready_skills} of {data.core_skills} core skills</p>
              </Panel>
              {side.length > 0 && <div className="grid gap-3 sm:grid-cols-2">{side.map((o) => <Option key={o.role_id} o={o} />)}</div>}
              <p className="text-[13px] italic text-ink-600">Readiness uses only skills you have been tested on, so untested skills never count against you.</p>
            </div>
            {detail.data && (
              <Card className="lg:sticky lg:top-20 lg:self-start">
                <h2 className="text-2xl">{detail.data.role_name}</h2>
                <p className="text-sm text-ink-600">Readiness {detail.data.readiness_pct}% from {detail.data.tested} of {detail.data.total} skills tested</p>
                {detail.data.skills_to_close.length > 0 && (
                  <><b className="mt-5 block">Skills to close</b>
                    <ul className="mt-2 space-y-1.5 text-sm">{detail.data.skills_to_close.map((g) => <li key={g.skill_id}>• {g.skill_name}: +{g.levels_to_go} level{g.levels_to_go > 1 ? 's' : ''}</li>)}</ul></>
                )}
                {detail.data.test_next.length > 0 && <><b className="mt-5 block">Test these next</b><p className="mt-1 text-sm">{detail.data.test_next.join(', ')}</p></>}
                <p className="mt-5 text-sm text-ink-600">About {detail.data.weeks} weeks at {detail.data.hours_per_week} hours a week</p>
                <Button size="lg" block className="mt-5" loading={action.isPending} onClick={() => action.mutate({ roleId: detail.data!.role_id, action: 'add-to-pathway' })}>Add to my pathway</Button>
                <Button variant="ghost" block className="mt-2" onClick={() => action.mutate({ roleId: detail.data!.role_id, action: 'talk-to-manager' })}>Talk to my manager about this</Button>
              </Card>
            )}
          </div>
        )}
      </QueryState>
    </>
  )
}

// ---- L-09 Points, badges, challenge ------------------------------------------------------------
export function ProfilePage() {
  const profile = useProfile()
  const badges = useBadges()
  const challenges = useChallenges()
  const join = useJoinChallenge()
  const me = useMe()
  const prefs = useUpdatePreferences()
  const p = profile.data
  return (
    <QueryState isLoading={profile.isLoading} error={profile.error} hasData={!!p} skeleton={<SkeletonPage />} onRetry={profile.refetch}>
      {p && (
        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="text-center">
            <span className="mx-auto flex size-20 items-center justify-center rounded-full bg-forest-100 font-serif text-2xl font-bold text-forest-800">{p.initials || initials(p.full_name)}</span>
            <h1 className="mt-3 font-sans text-xl font-bold">{p.full_name}</h1>
            <p className="text-sm text-ink-600">{p.level_name}{p.skill_level_name && ` · ${p.skill_level_name}`}</p>
            <ProgressBar className="mt-4" tone="gold" value={p.level_progress_pct}
              label={p.next_level_name ? `${new Intl.NumberFormat('en-IN').format(p.points)} points · ${p.points_to_next} to ${p.next_level_name}` : `${p.points} points · top level`} />
            <div className="mt-4 grid grid-cols-3 gap-2">
              {[[<Flame key="f" className="size-5 text-gold-500" />, `${p.streak_days} day streak`], [<Star key="s" className="size-5 text-gold-500" />, `${p.levels_gained} levels gained`], [<Check key="c" className="size-5 text-forest-700" />, `${p.certificates} certificates`]].map(([icon, label]) => (
                <div key={String(label)} className="rounded-xl bg-forest-50 p-3 text-[12px] font-semibold">{icon}<span className="mt-1 block">{label}</span></div>
              ))}
            </div>
            <p className="mt-4 text-left text-sm"><b>This week</b><br /><span className="text-ink-600">+{p.week_points} points · {p.week_lessons} lessons · {p.week_tests} tests</span></p>
            {me.data && (
              <div className="mt-3 border-t border-line pt-2 text-left">
                <Toggle checked={me.data.show_name_on_boards} onChange={(v) => prefs.mutate({ show_name_on_boards: v })} label="Show my name on boards" hint="Off shows you as “A colleague”." />
              </div>
            )}
          </Card>
          <Card>
            <h2 className="font-sans text-lg font-bold">My badges · {badges.data?.earned ?? 0} of {badges.data?.total ?? 0}</h2>
            <Stagger className="mt-4 grid grid-cols-3 gap-3">
              {badges.data?.badges.map((b) => (
                <div key={b.code} className="text-center" title={b.description}>
                  <span className={cn('mx-auto flex size-14 items-center justify-center rounded-full', b.earned ? 'bg-gold-500 text-white' : 'bg-canvas text-ink-400')}>
                    {b.earned ? <Medal className="size-6" /> : <Lock className="size-5" />}
                  </span>
                  <span className={cn('mt-1 block text-[12px] font-semibold', !b.earned && 'text-ink-400')}>{b.name}</span>
                </div>
              ))}
            </Stagger>
          </Card>
          <div className="space-y-4">
            {challenges.data?.map((c) => (
              <div key={c.id} className="space-y-3">
                <Panel>
                  <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/60">Team challenge</p>
                  <h2 className="mt-2 font-sans text-lg font-bold text-white">{c.title}</h2>
                  <ProgressBar className="mt-4" tone="gold" value={c.team_pct} label={<span className="text-white/75">Team at {c.team_pct}% · {c.days_left} days left</span>} />
                </Panel>
                {c.my_part[0] && <Card><b className="text-sm">Your part</b><p className="mt-1 text-sm">{c.my_part[0]}</p></Card>}
                <p className="text-sm text-ink-600">Reward: team badge and {c.reward_points} points each</p>
                <Notice>Joining is optional. Show my name on boards: {me.data?.show_name_on_boards ? 'On' : 'Off'}</Notice>
                <Button variant="gold" size="lg" block disabled={c.joined} loading={join.isPending} onClick={() => join.mutate(c.id)}>{c.joined ? 'You joined' : 'Join challenge'}</Button>
              </div>
            ))}
            {challenges.data?.length === 0 && <Card className="text-sm text-ink-600">No team challenge right now.</Card>}
          </div>
        </div>
      )}
    </QueryState>
  )
}

// ---- L-10 My reminders ---------------------------------------------------------------------------
export function RemindersPage() {
  const { data: me } = useMe()
  return me ? <RemindersForm key={me.id} me={me} /> : <SkeletonPage />
}

function RemindersForm({ me }: { me: Me }) {
  const save = useUpdatePreferences()
  const [window_, setWindow] = useState<[string, string]>(me.reminder_window)
  const [channels, setChannels] = useState({ in_app: me.reminder_channels.in_app ?? true, email: !!me.reminder_channels.email, whatsapp: !!me.reminder_channels.whatsapp })
  const [hours, setHours] = useState(me.hours_per_week)
  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-5 text-3xl">My reminders</h1>
      <Card className="space-y-5">
        <div>
          <b className="mb-2 block">Best time to remind me</b>
          <div className="flex items-center gap-2">
            <Input type="time" value={window_[0]} onChange={(e) => setWindow([e.target.value, window_[1]])} aria-label="From" />
            <span className="text-ink-600">to</span>
            <Input type="time" value={window_[1]} onChange={(e) => setWindow([window_[0], e.target.value])} aria-label="To" />
          </div>
          <p className="mt-1 text-[13px] text-ink-600">Weekdays</p>
        </div>
        <div>
          <b className="block">Where</b>
          <Toggle checked={channels.in_app} onChange={(v) => setChannels({ ...channels, in_app: v })} label="In the app" />
          <Toggle checked={channels.email} onChange={(v) => setChannels({ ...channels, email: v })} label="Email" />
          <Toggle checked={channels.whatsapp} onChange={(v) => setChannels({ ...channels, whatsapp: v })} label="WhatsApp" />
        </div>
        <Field label="Learning time each week" hint="Used to plan your pathway.">
          <Select value={hours} onChange={(e) => setHours(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6, 8, 10].map((h) => <option key={h} value={h}>{h} hours</option>)}</Select>
        </Field>
        <p className="text-[13px] text-ink-600">No messages before 9 am, after 7 pm, on weekends or holidays. At most one a day.</p>
        <Button size="lg" block loading={save.isPending} onClick={() => save.mutate({ reminder_window: window_, reminder_channels: channels, hours_per_week: hours })}>Save</Button>
      </Card>
    </div>
  )
}
