/**
 * Helpers for the HR steps (LMS.pdf): build a course from a brief, write a quick check, assign from a request.
 * Each run shows every step and what it did; people approve before anything is published or sent.
 */
import { Check, CircleDashed, Clock, Loader2, Minus, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import {
  useAdminCourses, useAssignPreview, useBuildCourse, useCancelRun, useCheckWritten, useConfirmAssign, useDepartments,
  useHelperRun, useHelperRuns, useJobRoles, usePlanAssign, useSkills, useUndo, useUsers, useWriteQuiz, useWrittenAnswers,
} from '@/api/admin'
import type { Audience, HelperRun, HelperRunSummary, HelperStep, WrittenReview } from '@/api/types'
import { QueryState } from '@/components/SystemStatus'
import { Badge, Button, ButtonLink, Card, EmptyState, Field, Input, Notice, PageHeader, Segmented, Select, SkeletonPage, StatusPill, Textarea, Toggle } from '@/components/ui'
import { cn, fmt } from '@/lib/utils'

type Tab = 'course' | 'quiz' | 'assign'

const RUN_STATUS: Record<HelperRunSummary['status'], { pill: string; label: string }> = {
  queued: { pill: 'not_started', label: 'Starting' },
  running: { pill: 'in_progress', label: 'Working' },
  waiting: { pill: 'waiting', label: 'Needs a person' },
  done: { pill: 'done', label: 'Done' },
  failed: { pill: 'failed', label: 'Stopped' },
  cancelled: { pill: 'declined', label: 'Cancelled' },
}
const KIND_LABEL: Record<HelperRunSummary['kind'], string> = { course: 'Course', quiz: 'Quick check', assign: 'Assignment' }

function RunStatus({ status }: { status: HelperRunSummary['status'] }) {
  return <StatusPill status={RUN_STATUS[status].pill} label={RUN_STATUS[status].label} />
}

export function HelpersPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'course'
  const runs = useHelperRuns()
  const answers = useWrittenAnswers()
  return (
    <div>
      <PageHeader title="Helpers"
        subtitle="Give the brief and the helper does the steps, showing each one. Nothing is published or sent until a person approves it." />
      {(answers.data?.length ?? 0) > 0 && (
        <Notice tone="warn" className="mb-5">
          {fmt.plural(answers.data!.length, 'set')} of written answers {answers.data!.length === 1 ? 'is' : 'are'} waiting for a person to check. <Link to="/admin/answers" className="font-semibold underline">Check them</Link>
        </Notice>
      )}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div>
          <Segmented<Tab> className="mb-4" value={tab} onChange={(v) => setParams({ tab: v })}
            options={[{ value: 'course', label: 'Build a course' }, { value: 'quiz', label: 'Write a quick check' }, { value: 'assign', label: 'Assign from a request' }]} />
          {tab === 'course' && <CourseBriefForm />}
          {tab === 'quiz' && <QuizBriefForm initialCourse={params.get('course') ?? ''} />}
          {tab === 'assign' && <AssignRequestForm />}
        </div>
        <aside className="lg:sticky lg:top-24">
          <Card>
            <h2 className="font-sans text-lg font-bold">Recent runs</h2>
            <QueryState isLoading={runs.isLoading} error={runs.error} hasData={!!runs.data} onRetry={runs.refetch}>
              {runs.data?.length === 0 && <p className="mt-2 text-sm text-ink-600">Nothing yet. Runs you start show here.</p>}
              {!!runs.data?.length && (
                <ul className="scroll-panel mt-3 max-h-[60vh] divide-y divide-line">
                  {runs.data.map((r) => (
                    <li key={r.id}>
                      <Link to={`/admin/helpers/${r.id}`} className="flex items-start justify-between gap-3 py-2.5 hover:bg-canvas">
                        <span className="min-w-0">
                          <b className="block truncate text-sm">{r.title}</b>
                          <span className="text-[12px] text-ink-600">{KIND_LABEL[r.kind]} · {fmt.ago(r.created_at)} · step {r.step_done} of {r.step_total}</span>
                        </span>
                        <RunStatus status={r.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </QueryState>
          </Card>
        </aside>
      </div>
    </div>
  )
}

function CourseBriefForm() {
  const navigate = useNavigate()
  const build = useBuildCourse()
  const skills = useSkills()
  const users = useUsers()
  const [form, setForm] = useState({ topic: '', audience: '', goal: '', duration: 30, skill: '', expert: '', links: '' })
  const [useKnowledge, setUseKnowledge] = useState(true)
  const [writeQuiz, setWriteQuiz] = useState(true)
  const [certification, setCertification] = useState(false)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value })
  const ready = form.topic.trim().length >= 3 && form.audience.trim().length >= 2 && form.goal.trim().length >= 5
  const submit = () => build.mutate({
    topic: form.topic, audience: form.audience, goal: form.goal, duration_minutes: Number(form.duration) || 30,
    skill_id: form.skill || null, approver_id: form.expert || null,
    links: form.links.split('\n').map((l) => l.trim()).filter(Boolean),
    use_knowledge: useKnowledge, write_quiz: writeQuiz, certification,
  }, { onSuccess: (run) => navigate(`/admin/helpers/${run.id}`) })
  return (
    <Card className="space-y-4">
      <p className="text-sm text-ink-600">The helper plans the modules, writes each one with an example, adds your links, writes the quick check, checks it all, and sends it to the expert.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Topic"><Input value={form.topic} onChange={set('topic')} placeholder="Handling refund requests" /></Field>
        <Field label="Who is it for?"><Input value={form.audience} onChange={set('audience')} placeholder="Customer support staff" /></Field>
      </div>
      <Field label="What should they be able to do afterwards?">
        <Textarea rows={3} value={form.goal} onChange={set('goal')} placeholder="Log, check and close a refund request correctly, the same day" />
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Length (minutes)"><Input type="number" min={5} max={240} value={form.duration} onChange={set('duration')} /></Field>
        <Field label="Skill it teaches (optional)">
          <Select value={form.skill} onChange={set('skill')}>
            <option value="">No skill</option>
            {skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
        <Field label="Expert who approves (optional)">
          <Select value={form.expert} onChange={set('expert')}>
            <option value="">Choose later</option>
            {users.data?.filter((u) => u.system_roles.includes('expert')).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Slides, videos or documents (optional)" hint="One link per line. Each goes into the module it fits best.">
        <Textarea rows={2} value={form.links} onChange={set('links')} placeholder="https://..." />
      </Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <Toggle checked={useKnowledge} onChange={setUseKnowledge} label="Use company material" hint="Published Knowledge Hub items open to everyone." />
        <Toggle checked={writeQuiz} onChange={setWriteQuiz} label="Write the quick check" hint="Multiple choice and short written cases." />
        <Toggle checked={certification} onChange={setCertification} label="Certification" hint="Pass mark 80 and a certificate." />
      </div>
      <Button size="lg" disabled={!ready} loading={build.isPending} onClick={submit}>Build the course</Button>
    </Card>
  )
}

function QuizBriefForm({ initialCourse }: { initialCourse: string }) {
  const navigate = useNavigate()
  const write = useWriteQuiz()
  const courses = useAdminCourses()
  const [course, setCourse] = useState(initialCourse)
  const [choice, setChoice] = useState('')
  const [written, setWritten] = useState('')
  const [passMark, setPassMark] = useState('')
  const [minutes, setMinutes] = useState('')
  const usable = (courses.data ?? []).filter((c) => c.lesson_count > 0 && !['drafting', 'archived'].includes(c.status))
  const num = (v: string) => (v === '' ? null : Number(v))
  return (
    <Card className="space-y-4">
      <p className="text-sm text-ink-600">The helper reads the lessons, drafts questions with answers, sets the pass mark and time, removes broken or repeated questions, saves them and tries the quick check once. The expert approves before learners see it.</p>
      <Field label="Course">
        <Select value={course} onChange={(e) => setCourse(e.target.value)}>
          <option value="">Choose a course</option>
          {usable.map((c) => <option key={c.id} value={c.id}>{c.title} · {c.status.replace('_', ' ')}</option>)}
        </Select>
      </Field>
      <div className="grid gap-4 sm:grid-cols-4">
        <Field label="Multiple choice"><Input type="number" min={0} max={30} placeholder="8" value={choice} onChange={(e) => setChoice(e.target.value)} /></Field>
        <Field label="Written cases"><Input type="number" min={0} max={10} placeholder="2" value={written} onChange={(e) => setWritten(e.target.value)} /></Field>
        <Field label="Pass mark"><Input type="number" min={1} max={100} placeholder="60" value={passMark} onChange={(e) => setPassMark(e.target.value)} /></Field>
        <Field label="Minutes"><Input type="number" min={1} max={180} placeholder="Auto" value={minutes} onChange={(e) => setMinutes(e.target.value)} /></Field>
      </div>
      <p className="text-[13px] text-ink-600">Leave a box empty to use the usual setting. Saving replaces the course's current questions.</p>
      <Button size="lg" disabled={!course} loading={write.isPending}
        onClick={() => write.mutate({ course_id: course, choice_count: num(choice), written_count: num(written), pass_mark: num(passMark), time_limit_minutes: num(minutes) },
          { onSuccess: (run) => navigate(`/admin/helpers/${run.id}`) })}>
        Write the quick check
      </Button>
    </Card>
  )
}

function AssignRequestForm() {
  const navigate = useNavigate()
  const plan = usePlanAssign()
  const [text, setText] = useState('')
  return (
    <Card className="space-y-4">
      <p className="text-sm text-ink-600">Write what you want in your own words. The helper finds the course, the people and the date, and shows you the full list. Nothing is sent until you press Assign.</p>
      <Field label="Your request">
        <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Assign Data privacy basics to the Sales department by 30 Nov" />
      </Field>
      <Button size="lg" disabled={text.trim().length < 3} loading={plan.isPending}
        onClick={() => plan.mutate(text, { onSuccess: (run) => navigate(`/admin/helpers/${run.id}`) })}>
        Read my request
      </Button>
    </Card>
  )
}

const STEP_ICON: Record<HelperStep['status'], { icon: typeof Check; className: string }> = {
  pending: { icon: CircleDashed, className: 'text-ink-400' },
  running: { icon: Loader2, className: 'animate-spin text-forest-700' },
  done: { icon: Check, className: 'text-ok-600' },
  skipped: { icon: Minus, className: 'text-ink-400' },
  waiting: { icon: Clock, className: 'text-warn-600' },
  failed: { icon: X, className: 'text-bad-600' },
}

export function HelperRunPage() {
  const { id } = useParams()
  const run = useHelperRun(id)
  const data = run.data
  return (
    <QueryState isLoading={run.isLoading} error={run.error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={run.refetch}>
      {data && (
        <div>
          <PageHeader title={data.title} subtitle={`${KIND_LABEL[data.kind]} · started ${fmt.ago(data.created_at)}`}
            actions={<ButtonLink variant="ghost" to="/admin/helpers">All helpers</ButtonLink>} />
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
            <Card>
              <div className="mb-4 flex items-center justify-between gap-3">
                <h2 className="font-sans text-lg font-bold">Steps</h2>
                <RunStatus status={data.status} />
              </div>
              <ol className="space-y-1">
                {data.steps.map((step, i) => {
                  const { icon: Icon, className } = STEP_ICON[step.status]
                  return (
                    <li key={step.key} className={cn('flex gap-3 rounded-xl p-3', step.status === 'waiting' && 'bg-warn-50', step.status === 'failed' && 'bg-bad-50')}>
                      <Icon className={cn('mt-0.5 size-5 shrink-0', className)} aria-hidden />
                      <div className="min-w-0">
                        <p className={cn('font-semibold', step.status === 'pending' && 'text-ink-500')}>{i + 1}. {step.label}</p>
                        {step.detail && <p className="mt-0.5 whitespace-pre-line text-sm text-ink-600">{step.detail}</p>}
                      </div>
                    </li>
                  )
                })}
              </ol>
            </Card>
            <aside className="lg:sticky lg:top-24">
              {data.kind === 'assign' ? <AssignOutcome run={data} /> : <CourseOutcome run={data} />}
            </aside>
          </div>
        </div>
      )}
    </QueryState>
  )
}

function CourseOutcome({ run }: { run: HelperRun }) {
  const working = run.status === 'queued' || run.status === 'running'
  return (
    <Card className="space-y-3">
      <h2 className="font-sans text-lg font-bold">{working ? 'Working on it' : run.status === 'failed' ? 'It stopped' : 'The result'}</h2>
      {working && <p className="text-sm text-ink-600">This page updates by itself. You can leave it; you get a message when it is ready.</p>}
      {run.status === 'failed' && (
        <>
          <Notice tone="bad">One step could not finish. Nothing was published.</Notice>
          <ButtonLink to={`/admin/helpers?tab=${run.kind}`} block>Start again</ButtonLink>
        </>
      )}
      {run.course_id && !working && (
        <>
          <p className="text-sm">Course: <StatusPill status={run.course_status ?? 'draft'} /></p>
          {run.status === 'waiting' && <p className="text-sm text-ink-600">Open the course, read it, and change anything you want. It goes live only after the expert approves it.</p>}
          {run.status === 'done' && <Notice tone="ok">Approved and live. You can assign it now.</Notice>}
          <ButtonLink to={`/admin/courses/${run.course_id}`} size="lg" block>Open the course</ButtonLink>
          {run.status === 'done' && <ButtonLink to="/admin/helpers?tab=assign" variant="ghost" block>Assign it</ButtonLink>}
        </>
      )}
    </Card>
  )
}

function AssignOutcome({ run }: { run: HelperRun }) {
  if (run.status === 'waiting' && run.plan) return <AssignConfirm run={run} />
  return <AssignDone run={run} />
}

function AssignConfirm({ run }: { run: HelperRun }) {
  const plan = run.plan!
  const courses = useAdminCourses()
  const departments = useDepartments()
  const roles = useJobRoles()
  const preview = useAssignPreview()
  const confirm = useConfirmAssign(run.id)
  const cancel = useCancelRun(run.id)
  const start = plan.audience ?? {}
  const [course, setCourse] = useState(plan.course_id ?? '')
  const [who, setWho] = useState<string>(start.everyone ? 'everyone' : start.department_id ? `d:${start.department_id}` : start.job_role_id ? `r:${start.job_role_id}` : '')
  const [due, setDue] = useState(plan.due_on ?? '')
  const [mandatory, setMandatory] = useState(false)
  const audience: Audience | null = who === 'everyone' ? { everyone: true } : who.startsWith('d:') ? { department_id: who.slice(2) } : who.startsWith('r:') ? { job_role_id: who.slice(2) } : null
  const unchanged = course === plan.course_id && JSON.stringify(audience) === JSON.stringify(plan.audience) && due === (plan.due_on ?? '')
  const shown = preview.data ?? (unchanged ? plan.preview : null)
  const body = audience && course ? { course_id: course, audience, due_on: due || null, is_mandatory: mandatory } : null
  const change = <T,>(fn: (v: T) => void) => (v: T) => { preview.reset(); fn(v) }
  return (
    <Card className="space-y-4">
      <h2 className="font-sans text-lg font-bold">Check before sending</h2>
      {plan.missing.length > 0 && <Notice tone="warn">The request did not say {plan.missing.map((m) => (m === 'who' ? 'who' : 'which course')).join(' or ')}. Choose below.</Notice>}
      <Field label="Course">
        <Select value={course} onChange={(e) => change(setCourse)(e.target.value)}>
          <option value="">Choose a course</option>
          {courses.data?.filter((c) => c.status === 'published').map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </Select>
      </Field>
      <Field label="Who">
        <Select value={who} onChange={(e) => change(setWho)(e.target.value)}>
          <option value="">Choose who</option>
          <option value="everyone">Everyone</option>
          <optgroup label="Department">{departments.data?.map((d) => <option key={d.id} value={`d:${d.id}`}>{d.name}</option>)}</optgroup>
          <optgroup label="Job role">{roles.data?.map((r) => <option key={r.id} value={`r:${r.id}`}>{r.name}</option>)}</optgroup>
        </Select>
      </Field>
      <Field label="Due date" hint={plan.due_from_request ? undefined : 'The request gave no date, so the usual period is filled in.'}>
        <Input type="date" value={due} onChange={(e) => change(setDue)(e.target.value)} />
      </Field>
      <Toggle checked={mandatory} onChange={setMandatory} label="Mandatory" hint="Shows in compliance reports." />
      {shown ? (
        <>
          <Notice>{shown.new_people} {shown.new_people === 1 ? 'person gets' : 'people get'} it{shown.already_assigned > 0 && ` · ${shown.already_assigned} already have it (skipped)`}</Notice>
          <ul className="scroll-panel max-h-56 divide-y divide-line rounded-xl border border-line text-sm">
            {shown.people.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 px-3 py-2">
                <span className="min-w-0"><b className="block truncate">{p.name}</b><span className="text-[12px] text-ink-600">{[p.job_role, p.department].filter(Boolean).join(' · ')}</span></span>
                {p.already_assigned ? <Badge tone="neutral">Has it</Badge> : <Badge tone="ok">New</Badge>}
              </li>
            ))}
          </ul>
          <Button size="lg" block disabled={!body || shown.new_people === 0} loading={confirm.isPending} onClick={() => body && confirm.mutate(body)}>
            Assign to {shown.new_people} {shown.new_people === 1 ? 'person' : 'people'}
          </Button>
        </>
      ) : (
        <Button size="lg" block disabled={!body} loading={preview.isPending} onClick={() => body && preview.mutate({ ...body, due_on: body.due_on ?? undefined })}>See who gets it</Button>
      )}
      <Button variant="ghost" block loading={cancel.isPending} onClick={() => cancel.mutate()}>Cancel this request</Button>
    </Card>
  )
}

function AssignDone({ run }: { run: HelperRun }) {
  const undo = useUndo()
  const result = run.result as { count?: number; bulk_action_id?: string; undo_until?: string; course_id?: string }
  const [openedAt] = useState(() => Date.now())
  const canUndo = !!result.undo_until && new Date(result.undo_until).getTime() > openedAt
  if (run.status === 'cancelled') return <Card><EmptyState title="Cancelled" body="Nothing was sent." /></Card>
  return (
    <Card className="space-y-3">
      <h2 className="font-sans text-lg font-bold">Assigned</h2>
      <Notice tone="ok">{fmt.plural(result.count ?? 0, 'person', 'people')} got it, with a message and the link.</Notice>
      {result.course_id && <ButtonLink to={`/admin/training/${result.course_id}`} size="lg" block>Follow progress</ButtonLink>}
      {canUndo && result.bulk_action_id && (
        <Button variant="ghost" block loading={undo.isPending} disabled={undo.isSuccess} onClick={() => undo.mutate(result.bulk_action_id!)}>
          {undo.isSuccess ? 'Undone' : `Undo (until ${new Date(result.undo_until!).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})`}
        </Button>
      )}
    </Card>
  )
}

// ---- written answers a person checks -----------------------------------------------------
export function WrittenAnswersPage() {
  const query = useWrittenAnswers()
  return (
    <div>
      <PageHeader title="Written answers to check"
        subtitle="When the suggested marks are unsure, a person decides. The learner gets the result as soon as you confirm." />
      <QueryState isLoading={query.isLoading} error={query.error} hasData={!!query.data} skeleton={<SkeletonPage />} onRetry={query.refetch}>
        {query.data?.length === 0 && <EmptyState title="Nothing to check" body="New written answers that need a person show up here." />}
        <div className="space-y-5">{query.data?.map((r) => <WrittenCard key={r.attempt_id} review={r} />)}</div>
      </QueryState>
    </div>
  )
}

function WrittenCard({ review }: { review: WrittenReview }) {
  const check = useCheckWritten()
  const [marks, setMarks] = useState<Record<string, { marks: number; feedback: string }>>(
    Object.fromEntries(review.answers.map((a) => [a.question_id, { marks: a.marks, feedback: a.feedback }])),
  )
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-sans text-lg font-bold">{review.person}</h2>
          <p className="text-sm text-ink-600">{review.course_title} · try {review.attempt_no} · {fmt.ago(review.submitted_at)}</p>
        </div>
        <Badge tone="neutral">Score so far {review.provisional_score} · pass mark {review.pass_mark}</Badge>
      </div>
      <div className="mt-4 space-y-4">
        {review.answers.map((a) => (
          <div key={a.question_id} className="grid gap-4 rounded-xl border border-line p-4 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="space-y-2 text-sm">
              <p className="font-semibold">{a.question}</p>
              <blockquote className="rounded-lg bg-canvas p-3 italic">{a.answer || 'No answer given.'}</blockquote>
              <p className="text-ink-600"><b>Look for:</b></p>
              <ul className="list-disc pl-5 text-ink-600">{a.rubric.map((r, i) => <li key={i}>{r.point} ({fmt.plural(r.marks, 'mark')})</li>)}</ul>
              {a.model_answer && <p className="text-ink-600"><b>Model answer:</b> {a.model_answer}</p>}
            </div>
            <div className="space-y-3">
              <Field label={`Marks (out of ${a.max_marks})`} hint={`Suggested ${a.marks}; ${a.confidence >= 0.5 ? 'fairly sure' : 'unsure'}.`}>
                <Input type="number" min={0} max={a.max_marks} value={marks[a.question_id].marks}
                  onChange={(e) => setMarks({ ...marks, [a.question_id]: { ...marks[a.question_id], marks: Math.max(0, Math.min(a.max_marks, Number(e.target.value))) } })} />
              </Field>
              <Field label="Note to the learner (optional)">
                <Textarea rows={3} value={marks[a.question_id].feedback} onChange={(e) => setMarks({ ...marks, [a.question_id]: { ...marks[a.question_id], feedback: e.target.value } })} />
              </Field>
            </div>
          </div>
        ))}
      </div>
      <Button size="lg" className="mt-4" loading={check.isPending}
        onClick={() => check.mutate({ attemptId: review.attempt_id, marks: Object.entries(marks).map(([question_id, m]) => ({ question_id, marks: m.marks, feedback: m.feedback })) })}>
        Confirm marks
      </Button>
    </Card>
  )
}
