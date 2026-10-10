/** HR assigns training (core flow): pick a skill → who (auto by role + by name) → preview everyone → confirm. */
import { useQuery } from '@tanstack/react-query'
import { Check, Search, UserPlus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useAssign, useAssignPreview, useDepartments, useJobRoles, useSkills, useUsers } from '@/api/admin'
import type { Audience, CourseSummary } from '@/api/types'
import { Badge, Button, Card, Field, Input, Notice, PageHeader, Select, Toggle } from '@/components/ui'
import { api } from '@/lib/api'
import { cn, fmt } from '@/lib/utils'
import { useUndoToast } from './audience'

function StepTitle({ n, title, hint }: { n: number; title: string; hint?: string }) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-forest-700 text-sm font-bold text-white">{n}</span>
      <div><h2 className="font-sans text-lg font-bold">{title}</h2>{hint && <p className="text-sm text-ink-600">{hint}</p>}</div>
    </div>
  )
}

export function AssignTrainingPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const skills = useSkills()
  const roles = useJobRoles()
  const departments = useDepartments()
  const users = useUsers()
  const preview = useAssignPreview()
  const assign = useAssign()
  const undoToast = useUndoToast()

  const [skillId, setSkillId] = useState(params.get('skill') ?? '')
  const [courseId, setCourseId] = useState('')
  const [bySkill, setBySkill] = useState(true)
  const [picked, setPicked] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [deptFilter, setDeptFilter] = useState('')
  const [due, setDue] = useState('')
  const [mandatory, setMandatory] = useState(false)

  const courses = useQuery({
    queryKey: ['admin', 'courses', 'by-skill', skillId],
    enabled: !!skillId,
    queryFn: () => api.get<CourseSummary[]>('/admin/courses', { skill_id: skillId }),
  })
  const published = (courses.data ?? []).filter((c) => c.status === 'published')
  const chosenCourse = courseId || (published.length === 1 ? published[0].id : '')

  const roleName = useMemo(() => new Map(roles.data?.map((r) => [r.id, r.name])), [roles.data])
  const deptName = useMemo(() => new Map(departments.data?.map((d) => [d.id, d.name])), [departments.data])
  const matches = (users.data ?? []).filter((u) => u.is_active
    && (!search || u.full_name.toLowerCase().includes(search.toLowerCase()) || u.email.toLowerCase().includes(search.toLowerCase()))
    && (!roleFilter || u.job_role_id === roleFilter) && (!deptFilter || u.department_id === deptFilter)).slice(0, 30)
  const toggle = (id: string) => { preview.reset(); setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id])) }

  const audience: Audience = { ...(bySkill && skillId ? { skill_id: skillId } : {}), ...(picked.length ? { user_ids: picked } : {}) }
  const body = { course_id: chosenCourse, audience, due_on: due || undefined, is_mandatory: mandatory }
  const ready = !!chosenCourse && (audience.skill_id || picked.length)
  const p = preview.data

  return (
    <div>
      <PageHeader title="Assign training" subtitle="Choose a skill, choose who learns it, check the list, then send. Only the people on the list are told." />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <Card>
            <StepTitle n={1} title="What should they learn?" hint="Pick the skill. Then pick the course that teaches it." />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Skill">
                <Select value={skillId} onChange={(e) => { setSkillId(e.target.value); setCourseId(''); preview.reset() }}>
                  <option value="">Choose a skill</option>
                  {skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </Select>
              </Field>
              <Field label="Course" hint={skillId && courses.isSuccess && published.length === 0 ? 'No published course teaches this skill yet.' : undefined}>
                <Select value={chosenCourse} disabled={!skillId || published.length === 0} onChange={(e) => { setCourseId(e.target.value); preview.reset() }}>
                  <option value="">{skillId ? 'Choose a course' : 'Pick a skill first'}</option>
                  {published.map((c) => <option key={c.id} value={c.id}>{c.title} · {c.duration_minutes} min</option>)}
                </Select>
              </Field>
            </div>
          </Card>

          <Card>
            <StepTitle n={2} title="Who should learn it?" hint="Use the automatic list, add people by name, or both." />
            <Toggle checked={bySkill} onChange={(v) => { setBySkill(v); preview.reset() }} label="Everyone whose job role needs this skill"
              hint="Found from the role library. You see the full list before sending." />
            <div className="mt-5 border-t border-line pt-5">
              <p className="mb-2 text-sm font-semibold">Add people by name</p>
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_180px_180px]">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
                  <Input className="pl-9" placeholder="Search by name or email" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search people" />
                </div>
                <Select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} aria-label="Filter by job role">
                  <option value="">Any job role</option>
                  {roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                </Select>
                <Select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)} aria-label="Filter by department">
                  <option value="">Any department</option>
                  {departments.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Select>
              </div>
              <ul className="mt-3 max-h-72 divide-y divide-line overflow-y-auto rounded-xl border border-line">
                {matches.map((u) => {
                  const on = picked.includes(u.id)
                  return (
                    <li key={u.id}>
                      <button type="button" onClick={() => toggle(u.id)} className={cn('flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm hover:bg-canvas', on && 'bg-forest-50')}>
                        <span className={cn('flex size-5 shrink-0 items-center justify-center rounded border-2', on ? 'border-forest-700 bg-forest-700 text-white' : 'border-line')}>{on && <Check className="size-3.5" />}</span>
                        <span className="min-w-0 flex-1"><b className="block truncate">{u.full_name}</b>
                          <span className="text-[12px] text-ink-600">{[u.job_role_id && roleName.get(u.job_role_id), u.department_id && deptName.get(u.department_id)].filter(Boolean).join(' · ') || u.email}</span></span>
                      </button>
                    </li>
                  )
                })}
                {matches.length === 0 && <li className="px-3 py-4 text-sm text-ink-600">Nobody matches.</li>}
              </ul>
              {picked.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {picked.map((id) => {
                    const u = users.data?.find((x) => x.id === id)
                    return <button key={id} type="button" onClick={() => toggle(id)} className="flex items-center gap-1 rounded-full bg-forest-100 px-3 py-1 text-[13px] font-semibold text-forest-800">{u?.full_name ?? 'Person'}<X className="size-3.5" /></button>
                  })}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <StepTitle n={3} title="When is it due?" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Due date (optional)"><Input type="date" value={due} onChange={(e) => { setDue(e.target.value); preview.reset() }} /></Field>
              <div className="sm:pt-6"><Toggle checked={mandatory} onChange={(v) => { setMandatory(v); preview.reset() }} label="Mandatory" hint="Shows in compliance reports." /></div>
            </div>
          </Card>
        </div>

        <aside className="lg:sticky lg:top-24">
          <Card>
            <h2 className="font-sans text-lg font-bold">Check before sending</h2>
            {!p ? (
              <>
                <p className="mt-1 text-sm text-ink-600">Nothing is sent until you confirm.</p>
                <Button size="lg" block className="mt-5" disabled={!ready} loading={preview.isPending} onClick={() => preview.mutate(body)}>
                  <UserPlus className="size-4" />See who gets it
                </Button>
              </>
            ) : (
              <>
                <dl className="mt-3 space-y-1.5 text-sm">
                  <div className="flex justify-between gap-3"><dt className="text-ink-600">Skill</dt><dd className="text-right font-semibold">{p.skill_name ?? '—'}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-ink-600">Course</dt><dd className="text-right font-semibold">{p.course_title}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-ink-600">Due</dt><dd className="text-right font-semibold">{p.due_on ? fmt.date(p.due_on) : 'No date'}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-ink-600">Test</dt><dd className="text-right font-semibold">{p.pass_mark ? `Pass mark ${p.pass_mark}` : 'Course test, default pass mark'}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-ink-600">Mandatory</dt><dd className="text-right font-semibold">{p.is_mandatory ? 'Yes' : 'No'}</dd></div>
                </dl>
                <Notice className="mt-4">{p.new_people} {p.new_people === 1 ? 'person gets' : 'people get'} it{p.already_assigned > 0 && ` · ${p.already_assigned} already have it (skipped)`}</Notice>
                <ul className="mt-3 max-h-64 divide-y divide-line overflow-y-auto rounded-xl border border-line text-sm">
                  {p.people.map((person) => (
                    <li key={person.id} className="flex items-center justify-between gap-2 px-3 py-2">
                      <span className="min-w-0"><b className="block truncate">{person.name}</b><span className="text-[12px] text-ink-600">{[person.job_role, person.department].filter(Boolean).join(' · ')}</span></span>
                      {person.already_assigned ? <Badge tone="neutral">Has it</Badge> : <Badge tone="ok">New</Badge>}
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[13px] text-ink-600">Message: {p.message_preview}</p>
                <Button size="lg" block className="mt-5" disabled={p.new_people === 0} loading={assign.isPending}
                  onClick={() => assign.mutate(body, { onSuccess: (r) => { undoToast(r, `Assigned "${p.course_title}"`); navigate(`/admin/training/${chosenCourse}`) } })}>
                  Send to {p.new_people} {p.new_people === 1 ? 'person' : 'people'}
                </Button>
                <Button variant="ghost" block className="mt-2" onClick={() => preview.reset()}>Change something</Button>
              </>
            )}
          </Card>
        </aside>
      </div>
    </div>
  )
}
