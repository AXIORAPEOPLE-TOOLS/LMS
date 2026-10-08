import { ArrowRight, BarChart3, CalendarPlus, ClipboardCheck, FileUp, GraduationCap, Upload, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  useAdminHome, useAdminTests, useAssign, useAssignPreview, useCampaignPreview, useCommitUpload, useJobRoles, usePreviewUpload,
  useRoleDetail, useSendCampaign, useSkillRanking, useSkills, type UploadRow,
} from '@/api/admin'
import { useCourses } from '@/api/learner'
import type { Audience } from '@/api/types'
import { Stagger } from '@/components/motion'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, Card, Dialog, EmptyState, Field, Input, LevelDots, Notice, PageHeader, SectionTitle, Select, SkeletonPage, Stat, Toggle,
} from '@/components/ui'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { audienceChosen, useUndoToast } from './audience'
import { AudiencePicker } from './shared'

// ---- A-01 Admin home ----------------------------------------------------------------------
export function AdminHomePage() {
  const { data, isLoading, error, refetch } = useAdminHome()
  const navigate = useNavigate()
  const [assignOpen, setAssignOpen] = useState(false)
  const actions = [
    { title: 'Assign training', sub: 'to people or a role', icon: UserPlus, onClick: () => setAssignOpen(true), primary: true },
    { title: 'Schedule a session', sub: 'and send invitations', icon: CalendarPlus, onClick: () => navigate('/admin/courses?tab=sessions') },
    { title: 'Draft a course', sub: 'from an SOP or document', icon: GraduationCap, onClick: () => navigate('/admin/courses/new') },
    { title: 'Run a skill test', sub: 'for a role or team', icon: ClipboardCheck, onClick: () => navigate('/admin/skills') },
    { title: 'Download a report', sub: 'Excel, CSV or PDF', icon: BarChart3, onClick: () => navigate('/admin/reports') },
  ]
  return (
    <>
      <PageHeader title="What do you want to do?" />
      <Stagger className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {actions.map((a) => (
          <button key={a.title} onClick={a.onClick}
            className={cn('flex h-full flex-col rounded-[var(--radius-card)] border p-4 text-left transition-colors',
              a.primary ? 'on-dark border-transparent bg-forest-700 text-white hover:bg-forest-800' : 'border-line bg-surface hover:border-forest-700')}>
            <a.icon className={cn('size-5', a.primary ? 'text-gold-500' : 'text-forest-700')} />
            <b className="mt-3">{a.title}</b>
            <span className={cn('mt-1 text-[13px]', a.primary ? 'text-white/75' : 'text-ink-600')}>{a.sub}</span>
          </button>
        ))}
      </Stagger>
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && (
          <>
            <SectionTitle className="mt-8" action={<Badge tone="bad"><span className="size-1.5 animate-pulse rounded-full bg-bad-600" /> Live</Badge>}>Live today</SectionTitle>
            <Stagger className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              {data.metrics.map((m) => (
                <Stat key={m.key} label={m.label} change={m.key === 'overdue' ? null : m.change} tone="forest"
                  value={/^\d+$/.test(m.value) ? Number(m.value) : m.value} />
              ))}
            </Stagger>
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <Card>
                <SectionTitle>Needs attention</SectionTitle>
                {data.attention.length === 0 ? <p className="text-sm text-ink-600">Nothing urgent. Good work.</p> : (
                  <ul className="space-y-2.5">
                    {data.attention.map((a) => <li key={a.text}><Link to={a.href} className="flex items-center justify-between gap-2 text-sm hover:text-forest-700">• {a.text}<ArrowRight className="size-4 shrink-0" /></Link></li>)}
                  </ul>
                )}
              </Card>
              <Card>
                <SectionTitle>Content to create next</SectionTitle>
                {data.content_gaps.length === 0 ? <p className="text-sm text-ink-600">Every skill gap has a course.</p> : (
                  <ul className="space-y-2.5 text-sm">{data.content_gaps.map((g) => <li key={g.skill_id}>• {g.text}</li>)}</ul>
                )}
                <Button variant="outline" className="mt-4" onClick={() => navigate('/admin/courses/new')}><FileUp className="size-4" />Draft from a document</Button>
              </Card>
            </div>
          </>
        )}
      </QueryState>
      <AssignTrainingDialog open={assignOpen} onOpenChange={setAssignOpen} />
    </>
  )
}

export function AssignTrainingDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const courses = useCourses()
  const [courseId, setCourseId] = useState('')
  const [audience, setAudience] = useState<Audience>({})
  const [due, setDue] = useState('')
  const [mandatory, setMandatory] = useState(false)
  const preview = useAssignPreview()
  const assign = useAssign()
  const undoToast = useUndoToast()
  const body = { course_id: courseId, audience, due_on: due || undefined, is_mandatory: mandatory }
  const ready = !!courseId && audienceChosen(audience)
  const close = () => { onOpenChange(false); preview.reset() }
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(o) : close())} title="Assign training" description="You will see a preview before anything is sent."
      footer={preview.data ? (
        <>
          <Button variant="outline" onClick={() => preview.reset()}>Back</Button>
          <Button loading={assign.isPending} disabled={preview.data.new_people === 0}
            onClick={() => assign.mutate(body, { onSuccess: (r) => { undoToast(r, `Assigned "${preview.data!.course_title}"`); close() } })}>
            Send to {preview.data.new_people} people
          </Button>
        </>
      ) : <Button disabled={!ready} loading={preview.isPending} onClick={() => preview.mutate(body)}>Preview</Button>}>
      {preview.data ? (
        <div className="space-y-3">
          <Notice>
            <b>{preview.data.course_title}</b> → {preview.data.audience_label}<br />
            {preview.data.new_people} new{preview.data.already_assigned > 0 && ` · ${preview.data.already_assigned} already have it`}
          </Notice>
          {preview.data.sample_names.length > 0 && <p className="text-sm text-ink-600">Including {preview.data.sample_names.join(', ')}</p>}
          <Card className="bg-canvas text-sm"><p className="text-[12px] font-semibold text-ink-600">Message preview</p>{preview.data.message_preview}</Card>
        </div>
      ) : (
        <div className="space-y-4">
          <Field label="Course">
            <Select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">Choose a course</option>
              {courses.data?.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </Select>
          </Field>
          <AudiencePicker value={audience} onChange={setAudience} />
          <Field label="Due date (optional)"><Input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
          <Toggle checked={mandatory} onChange={setMandatory} label="Mandatory" hint="Shows in compliance reports." />
        </div>
      )}
    </Dialog>
  )
}

// ---- A-02/A-03/A-04 People, roles, ranking ----------------------------------------------------
export function PeoplePage() {
  return (
    <>
      <PageHeader title="People, roles and ranking" subtitle="Upload people, map each to a role, and see the ranking skill by skill." />
      <div className="grid gap-5 lg:grid-cols-3">
        <UploadCard />
        <RoleCard />
        <RankingCard />
      </div>
    </>
  )
}

function UploadCard() {
  const preview = usePreviewUpload()
  const commit = useCommitUpload()
  const roles = useJobRoles()
  const [choices, setChoices] = useState<Record<number, string>>({})
  const rows = preview.data?.rows ?? []
  const roleFor = (r: UploadRow) => r.job_role_id ?? choices[r.row] ?? r.suggested_role_id
  const ready = rows.filter((r) => r.status !== 'error' && roleFor(r))
  return (
    <Card className="flex flex-col">
      <SectionTitle>1. Upload employees</SectionTitle>
      <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-forest-700 bg-forest-50 px-4 py-8 text-center hover:bg-forest-100">
        <Upload className="size-6 text-forest-700" />
        <b className="mt-2 text-sm">Drop your file here or choose a file</b>
        <span className="text-[12px] text-ink-600">.xlsx or .csv</span>
        <input type="file" accept=".csv,.xlsx" className="sr-only" onChange={(e) => e.target.files?.[0] && preview.mutate(e.target.files[0])} />
      </label>
      <button className="mt-2 text-left text-sm font-semibold text-forest-700" onClick={() => api.download('/users/upload/template', undefined, 'employees-template.csv')}>Download template</button>
      {preview.data && (
        <>
          <p className="mt-4 font-semibold">Check: {preview.data.ready} ready · {preview.data.needs_role} need a role{preview.data.errors > 0 && ` · ${preview.data.errors} with problems`}</p>
          <div className="mt-2 max-h-72 space-y-2 overflow-y-auto">
            {rows.filter((r) => r.status !== 'ready').map((r) => (
              <div key={r.row} className={cn('rounded-xl p-3 text-sm', r.status === 'error' ? 'bg-bad-50' : 'bg-warn-50')}>
                <b className={r.status === 'error' ? 'text-bad-600' : 'text-warn-600'}>Row {r.row} · “{r.job_title || r.full_name}”</b>
                {r.status === 'error' ? <p className="text-bad-600">{r.message}</p> : (
                  <Select className="mt-2 py-1.5 text-sm" value={roleFor(r) ?? ''} onChange={(e) => setChoices({ ...choices, [r.row]: e.target.value })} aria-label={`Role for row ${r.row}`}>
                    <option value="">Choose a role</option>
                    {roles.data?.map((role) => <option key={role.id} value={role.id}>{role.name}{role.id === r.suggested_role_id ? ' (suggested)' : ''}</option>)}
                  </Select>
                )}
              </div>
            ))}
          </div>
        </>
      )}
      <Button size="lg" block className="mt-auto" disabled={ready.length === 0} loading={commit.isPending}
        onClick={() => commit.mutate(ready.map((r) => ({ full_name: r.full_name, email: r.email, job_role_id: roleFor(r)!, department: r.department })), { onSuccess: () => preview.reset() })}>
        {preview.data ? `Upload ${ready.length} employees` : 'Upload employees'}
      </Button>
    </Card>
  )
}

function RoleCard() {
  const roles = useJobRoles()
  const [roleId, setRoleId] = useState<string>()
  const chosen = roleId ?? roles.data?.[0]?.id
  const detail = useRoleDetail(chosen)
  return (
    <Card>
      <SectionTitle>2. Role and its skills</SectionTitle>
      <Select value={chosen ?? ''} onChange={(e) => setRoleId(e.target.value)} aria-label="Role">
        {roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
      </Select>
      <ul className="mt-4 space-y-2.5">
        {detail.data?.skills.map((s) => (
          <li key={s.skill_id} className="flex items-center justify-between gap-3 text-sm"><span>{s.skill_name}</span><LevelDots level={s.required_level} /></li>
        ))}
      </ul>
      <p className="mt-4 text-[13px] italic text-ink-600">Required level shown in dots. {detail.data && `${detail.data.people_count} people have this role.`}</p>
    </Card>
  )
}

function RankingCard() {
  const skills = useSkills()
  const [skillId, setSkillId] = useState<string>()
  const chosen = skillId ?? skills.data?.find((s) => s.code === 'CUST-COMM')?.id ?? skills.data?.[0]?.id
  const ranking = useSkillRanking(chosen)
  return (
    <Card className="flex flex-col">
      <SectionTitle>3. Ranking by skill</SectionTitle>
      <Select value={chosen ?? ''} onChange={(e) => setSkillId(e.target.value)} aria-label="Skill">
        {skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </Select>
      <table className="mt-3 w-full text-sm">
        <thead><tr className="text-left text-[12px] text-ink-600"><th className="py-1">Rank</th><th>Person</th><th>Score</th><th>Level</th></tr></thead>
        <tbody>
          {ranking.data?.rows.slice(0, 10).map((r) => (
            <tr key={r.rank + r.name} className="border-t border-line"><td className="py-2 font-bold">{r.rank}</td><td>{r.name}</td><td className="tabular">{r.score}</td><td><Badge tone="ok">L{r.level}</Badge></td></tr>
          ))}
        </tbody>
      </table>
      {ranking.data?.rows.length === 0 && <p className="mt-3 text-sm text-ink-600">No one tested yet.</p>}
      <Link to="/admin/skills" className="mt-auto pt-4 text-sm font-semibold text-forest-700">Send skill tests →</Link>
    </Card>
  )
}

// ---- Skills & tests: campaigns --------------------------------------------------------------------
export function SkillsTestsPage() {
  const tests = useAdminTests()
  const [selected, setSelected] = useState<string[]>([])
  const [audience, setAudience] = useState<Audience>({})
  const [due, setDue] = useState('')
  const preview = useCampaignPreview()
  const send = useSendCampaign()
  const undoToast = useUndoToast()
  const body = { test_ids: selected, audience, due_on: due || undefined }
  return (
    <>
      <PageHeader title="Skills & tests" subtitle="Send skill checks to a role or team. People see their level and rank band straight away." />
      <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <QueryState isLoading={tests.isLoading} error={tests.error} hasData={!!tests.data} skeleton={<SkeletonPage />} onRetry={tests.refetch}>
          <Card>
            <SectionTitle>Tests</SectionTitle>
            {tests.data?.length === 0 && <EmptyState title="No tests yet" />}
            <ul className="divide-y divide-line">
              {tests.data?.map((t) => (
                <li key={t.id} className="flex items-center gap-3 py-3">
                  <input type="checkbox" className="size-5 accent-[#1F5C4E]" checked={selected.includes(t.id)} aria-label={t.title}
                    onChange={(e) => setSelected(e.target.checked ? [...selected, t.id] : selected.filter((x) => x !== t.id))} />
                  <span className="flex-1"><b className="block text-sm">{t.title}</b>
                    <span className="text-[12px] text-ink-600">{t.question_count} questions · {t.duration_minutes} min{t.pass_mark ? ` · pass ${t.pass_mark}%` : ' · no pass or fail'}</span></span>
                  {t.proctoring === 'camera' && <Badge tone="info">Supervised</Badge>}
                </li>
              ))}
            </ul>
          </Card>
        </QueryState>
        <Card className="space-y-4 lg:self-start">
          <SectionTitle>Send skill tests</SectionTitle>
          <AudiencePicker value={audience} onChange={(a) => { setAudience(a); preview.reset() }} />
          <Field label="Finish by (optional)"><Input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
          {preview.data && <Notice>{preview.data.new_invites} new skill checks for {preview.data.audience_label}</Notice>}
          {preview.data ? (
            <Button size="lg" block loading={send.isPending} disabled={preview.data.new_invites === 0}
              onClick={() => send.mutate(body, { onSuccess: (r) => { undoToast(r, 'Skill tests sent'); preview.reset(); setSelected([]) } })}>Send skill tests</Button>
          ) : (
            <Button size="lg" block disabled={!selected.length || !audienceChosen(audience)} loading={preview.isPending} onClick={() => preview.mutate(body)}>Preview</Button>
          )}
        </Card>
      </div>
    </>
  )
}
