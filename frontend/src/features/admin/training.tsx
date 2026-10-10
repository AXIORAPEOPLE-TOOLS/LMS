/** HR training tracker (core flow): who has not started, is learning, finished the course, passed or failed. */
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import type { UUID } from '@/api/types'
import { Stagger } from '@/components/motion'
import { QueryState } from '@/components/SystemStatus'
import { Badge, Button, ButtonLink, Card, EmptyState, PageHeader, ProgressBar, SkeletonPage } from '@/components/ui'
import { api } from '@/lib/api'
import { useSession } from '@/lib/session'
import { cn, fmt } from '@/lib/utils'

type State = 'not_started' | 'in_progress' | 'course_done' | 'failed' | 'passed'
interface TrackerCourse { course_id: UUID; course_title: string; skill_name: string | null; total: number; counts: Record<State, number>; overdue: number }
interface TrackerPerson {
  user_id: UUID; name: string; department: string | null; state: State; state_label: string; overdue: boolean; due_on: string | null
  progress_pct: number; lessons_done: number; lessons_total: number; best_score: number | null; attempts: number; completed_at: string | null
}
interface Tracker extends TrackerCourse { has_test: boolean; pass_mark: number | null; people: TrackerPerson[] }

const STATES: { key: State; label: string; tone: 'neutral' | 'warn' | 'info' | 'bad' | 'ok' }[] = [
  { key: 'not_started', label: 'Not started', tone: 'neutral' },
  { key: 'in_progress', label: 'In progress', tone: 'warn' },
  { key: 'course_done', label: 'Course done, test not passed', tone: 'info' },
  { key: 'failed', label: 'Failed the test', tone: 'bad' },
  { key: 'passed', label: 'Passed', tone: 'ok' },
]
const TONE = Object.fromEntries(STATES.map((s) => [s.key, s.tone])) as Record<State, (typeof STATES)[number]['tone']>

function StateBar({ counts, total }: { counts: Record<State, number>; total: number }) {
  const colour: Record<State, string> = { not_started: 'bg-line', in_progress: 'bg-warn-600', course_done: 'bg-info-600', failed: 'bg-bad-600', passed: 'bg-ok-600' }
  return (
    <div className="flex h-2.5 overflow-hidden rounded-full bg-canvas" aria-hidden>
      {STATES.map((s) => counts[s.key] ? <span key={s.key} className={colour[s.key]} style={{ width: `${(counts[s.key] / Math.max(total, 1)) * 100}%` }} /> : null)}
    </div>
  )
}

export function TrainingOverviewPage() {
  const { has } = useSession()
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['training'], queryFn: () => api.get<TrackerCourse[]>('/admin/training') })
  return (
    <div>
      <PageHeader title="Training tracker" subtitle="Every course you assigned and where each person stands."
        actions={has('admin') && <ButtonLink to="/admin/assign"><UserPlus className="size-4" />Assign training</ButtonLink>} />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data?.length === 0 && <EmptyState title="No training assigned yet" body="Assign a course to see who has started, finished and passed."
          action={has('admin') ? <ButtonLink to="/admin/assign">Assign training</ButtonLink> : undefined} />}
        <Stagger className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data?.map((c) => (
            <Link key={c.course_id} to={`/admin/training/${c.course_id}`} className="flex flex-col rounded-card border border-line bg-surface p-5 transition-colors hover:border-forest-700">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0"><b className="block truncate">{c.course_title}</b><span className="text-[13px] text-ink-600">{c.skill_name ?? 'No skill set'} · {fmt.plural(c.total, 'person', 'people')}</span></div>
                {c.overdue > 0 && <Badge tone="bad">{c.overdue} overdue</Badge>}
              </div>
              <div className="mt-4"><StateBar counts={c.counts} total={c.total} /></div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-[12px]">
                <div><dt className="text-ink-600">Not started</dt><dd className="text-lg font-bold tabular">{c.counts.not_started}</dd></div>
                <div><dt className="text-ink-600">Learning</dt><dd className="text-lg font-bold tabular">{c.counts.in_progress + c.counts.course_done + c.counts.failed}</dd></div>
                <div><dt className="text-ink-600">Passed</dt><dd className="text-lg font-bold tabular text-ok-600">{c.counts.passed}</dd></div>
              </dl>
            </Link>
          ))}
        </Stagger>
      </QueryState>
    </div>
  )
}

export function TrainingCoursePage() {
  const { id } = useParams()
  const [filter, setFilter] = useState<State | 'overdue' | 'all'>('all')
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['training', id], queryFn: () => api.get<Tracker>(`/admin/training/${id}`) })
  const people = (data?.people ?? []).filter((p) => filter === 'all' || (filter === 'overdue' ? p.overdue : p.state === filter))
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <div>
          <Link to="/admin/training" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-forest-700"><ArrowLeft className="size-4" />Training tracker</Link>
          <PageHeader title={data.course_title}
            subtitle={`${data.skill_name ?? 'No skill set'} · ${fmt.plural(data.total, 'person', 'people')}${data.has_test ? ` · test pass mark ${data.pass_mark}` : ' · no test'}`}
            actions={<Button variant="outline" onClick={() => api.download(`/admin/training/${data.course_id}/export`, undefined, `${data.course_title}.csv`)}><Download className="size-4" />Download CSV</Button>} />
          <div className="mb-5 flex flex-wrap gap-2">
            {[{ key: 'all' as const, label: 'Everyone', n: data.total }, ...STATES.map((s) => ({ key: s.key, label: s.label, n: data.counts[s.key] })), { key: 'overdue' as const, label: 'Overdue', n: data.overdue }].map((f) => (
              <button key={f.key} onClick={() => setFilter(f.key)}
                className={cn('rounded-full border px-3.5 py-1.5 text-[13px] font-semibold transition-colors', filter === f.key ? 'border-forest-700 bg-forest-700 text-white' : 'border-line bg-surface hover:border-forest-700')}>
                {f.label} <span className="tabular opacity-70">{f.n}</span>
              </button>
            ))}
          </div>
          <Card className="overflow-x-auto p-0 sm:p-0">
            <table className="w-full min-w-180 text-sm">
              <thead className="border-b border-line bg-canvas text-left text-[12px] uppercase tracking-wide text-ink-600">
                <tr><th className="px-4 py-3">Person</th><th className="px-4 py-3">Where they are</th><th className="px-4 py-3">Lessons</th><th className="px-4 py-3">Test</th><th className="px-4 py-3">Due</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {people.map((p) => (
                  <tr key={p.user_id}>
                    <td className="px-4 py-3"><b className="block">{p.name}</b><span className="text-[12px] text-ink-600">{p.department ?? ''}</span></td>
                    <td className="px-4 py-3"><Badge tone={TONE[p.state]}>{p.state_label}</Badge></td>
                    <td className="px-4 py-3"><ProgressBar size="sm" value={p.lessons_total ? (p.lessons_done / p.lessons_total) * 100 : p.progress_pct} label={`${p.lessons_done} of ${p.lessons_total}`} /></td>
                    <td className="px-4 py-3 tabular">{data.has_test ? (p.attempts ? `Best ${p.best_score} · ${fmt.plural(p.attempts, 'try', 'tries')}` : 'Not taken') : '—'}</td>
                    <td className="px-4 py-3">{p.due_on ? <span className={cn(p.overdue && 'font-semibold text-bad-600')}>{fmt.shortDate(p.due_on)}{p.overdue && ' · overdue'}</span> : <span className="text-ink-400">No date</span>}</td>
                  </tr>
                ))}
                {people.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-ink-600">Nobody here.</td></tr>}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </QueryState>
  )
}
