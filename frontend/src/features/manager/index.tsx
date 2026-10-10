import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router'
import { useApprovePathway, useNudge, useSignOff, useTeam } from '@/api/admin'
import type { Pathway, Team } from '@/api/types'
import { Stagger } from '@/components/motion'
import { QueryState } from '@/components/SystemStatus'
import { Badge, Button, Card, EmptyState, PageHeader, ProgressBar, SectionTitle, SkeletonPage, Stat } from '@/components/ui'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const LEVEL_COLOURS = ['bg-[#f1f3f4] text-ink-600', 'bg-[#fadbd8]', 'bg-[#fde3c4]', 'bg-[#e4efc9]', 'bg-[#c4e3cf]', 'bg-[#9fd3b4]']

export function Heatmap({ heatmap, onPerson }: { heatmap: Team['heatmap']; onPerson?: (id: string) => void }) {
  if (heatmap.rows.length === 0) return <EmptyState title="No one in your team yet" />
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-separate border-spacing-1.5 text-sm">
        <thead>
          <tr>
            <th className="w-32" />
            {heatmap.skills.map((s) => <th key={s.id} className="px-1 pb-1 text-center text-[12px] font-semibold text-ink-600">{s.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {heatmap.rows.map((row) => (
            <tr key={row.user_id}>
              <td className="pr-2">
                <button className="text-left font-medium hover:text-forest-700 hover:underline" onClick={() => onPerson?.(row.user_id)}>{row.name}</button>
              </td>
              {row.levels.map((level, i) => {
                const short = level !== null && row.required[i] !== null && level < (row.required[i] ?? 0)
                return (
                  <td key={i} title={row.required[i] != null ? `Needs level ${row.required[i]}` : undefined}
                    className={cn('h-10 rounded-lg text-center font-bold', level === null ? 'bg-canvas text-ink-400' : LEVEL_COLOURS[level], short && 'ring-1 ring-bad-600/40')}>
                    {level ?? '–'}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[13px] italic text-ink-600">Colour = level 0 to 5. A red edge means below what the role needs. Click a person to see their pathway.</p>
    </div>
  )
}

export function TeamPage() {
  const { data, isLoading, error, refetch } = useTeam()
  const nudge = useNudge()
  const navigate = useNavigate()
  return (
    <>
      <PageHeader title="My team at a glance" subtitle="Who is on track, who needs a nudge, and where the skill gaps are." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && (
          <div className="space-y-5">
            <Stagger className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat value={data.counts.on_track} label="On track" tone="ok" className="bg-ok-50 border-transparent" />
              <Stat value={data.counts.due_soon} label="Due soon" tone="warn" className="bg-warn-50 border-transparent" />
              <Stat value={data.counts.overdue} label="Overdue" tone="bad" className="bg-bad-50 border-transparent" />
              <Stat value={data.counts.to_approve} label="To approve" tone="info" className="bg-info-50 border-transparent" />
            </Stagger>
            <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
              <Card className="min-w-0">
                <SectionTitle>Skills heatmap: level by person</SectionTitle>
                <Heatmap heatmap={data.heatmap} onPerson={(id) => navigate(`/team/people/${id}`)} />
              </Card>
              <Card className="min-w-0">
                <SectionTitle>Needs your attention</SectionTitle>
                {data.attention.length === 0 && <p className="text-sm text-ink-600">Everyone is on track.</p>}
                <ul className="space-y-3">
                  {data.attention.map((a) => (
                    <li key={a.user_id + a.item} className="flex items-center justify-between gap-3">
                      <span className="min-w-0"><b className="block">{a.name}</b><span className={cn('text-[13px]', a.overdue_days ? 'text-bad-600' : 'text-ink-600')}>{a.detail}</span></span>
                      <Button variant="outline" size="sm" onClick={() => nudge.mutate({ user_id: a.user_id, item: a.item })}>Nudge</Button>
                    </li>
                  ))}
                </ul>
                {data.approvals.length > 0 && (
                  <>
                    <SectionTitle className="mt-6">To approve</SectionTitle>
                    <ApprovalList approvals={data.approvals.slice(0, 3)} />
                    {data.approvals.length > 3 && <Link to="/team/approvals" className="mt-2 block text-sm font-semibold text-forest-700">See all {data.approvals.length}</Link>}
                  </>
                )}
              </Card>
            </div>
          </div>
        )}
      </QueryState>
    </>
  )
}

function ApprovalList({ approvals }: { approvals: Team['approvals'] }) {
  const approvePathway = useApprovePathway()
  const signOff = useSignOff()
  return (
    <ul className="space-y-3">
      {approvals.map((a) => (
        <li key={a.id} className="flex items-start justify-between gap-3">
          <span className="min-w-0"><b className="block text-sm">{a.title}</b><span className="line-clamp-2 text-[13px] text-ink-600">{a.detail}</span></span>
          <span className="flex shrink-0 gap-1.5">
            {a.kind === 'practise' && <Button variant="ghost" size="sm" onClick={() => signOff.mutate({ id: a.id, approve: false })}>More practice</Button>}
            <Button size="sm" onClick={() => (a.kind === 'pathway' ? approvePathway.mutate(a.id) : signOff.mutate({ id: a.id, approve: true }))}>Approve</Button>
          </span>
        </li>
      ))}
    </ul>
  )
}

export function TeamSkillsPage() {
  const { data, isLoading, error, refetch } = useTeam()
  const navigate = useNavigate()
  return (
    <>
      <PageHeader title="Team skills" subtitle="Each person's level against what their role needs." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && <Card><Heatmap heatmap={data.heatmap} onPerson={(id) => navigate(`/team/people/${id}`)} /></Card>}
      </QueryState>
    </>
  )
}

export function ApprovalsPage() {
  const { data, isLoading, error, refetch } = useTeam()
  return (
    <div>
      <PageHeader title="Approvals" subtitle="Pathways and practise tasks waiting for you." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data?.approvals.length === 0 ? <EmptyState title="Nothing to approve" body="You are all caught up." /> : data && <Card><ApprovalList approvals={data.approvals} /></Card>}
      </QueryState>
    </div>
  )
}

export function PersonPage() {
  const { id } = useParams()
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['person-pathway', id], queryFn: () => api.get<Pathway | null>(`/users/${id}/pathway`) })
  return (
    <div>
      <Link to="/team" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-forest-700"><ArrowLeft className="size-4" />Team</Link>
      <QueryState isLoading={isLoading} error={error} hasData={data !== undefined} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data === null && <EmptyState title="No pathway yet" body="It is built once their skill checks are done." />}
        {data && (
          <>
            <PageHeader title="Pathway" subtitle={`${data.progress_pct}% done · ${data.total_waves} waves`} tag={<Badge className="mb-2">{data.status.replace('_', ' ')}</Badge>} />
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {data.waves.map((w) => (
                <Card key={w.number}>
                  <div className="flex justify-between"><b>Stage {w.number}</b><span className="text-sm text-ink-600">{w.status}</span></div>
                  <ProgressBar className="mt-2" size="sm" value={w.progress_pct} />
                  <ul className="mt-3 space-y-1 text-sm">
                    {w.items.map((i) => <li key={i.id} className="flex justify-between"><span>{i.skill_name}</span><span className="text-ink-600">{i.step}{i.waiting_for_signoff && ' · waiting for you'}</span></li>)}
                  </ul>
                </Card>
              ))}
            </div>
          </>
        )}
      </QueryState>
    </div>
  )
}
