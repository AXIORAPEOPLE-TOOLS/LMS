import { Check, FileText, Loader2, Plus, Upload } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import {
  useAdminCourse, useAdminCourses, useAdminSessions, useCreateSession, useDraftCourse, useReminderPreview, useReminderRules,
  useReviewCourse, useSendInvitations, useSendReminders, useSkills, useSubmitCourse, useUsers,
} from '@/api/admin'
import type { Audience } from '@/api/types'
import { Stagger } from '@/components/motion'
import { EASE } from '@/lib/motion-tokens'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, ButtonLink, Card, Dialog, EmptyState, Field, Input, Notice, PageHeader, SectionTitle, Segmented, Select,
  SkeletonPage, StatusPill, Textarea, Toggle,
} from '@/components/ui'
import { useSession } from '@/lib/session'
import { cn, fmt } from '@/lib/utils'
import { audienceChosen, useUndoToast } from './audience'
import { AudiencePicker } from './shared'

type Tab = 'courses' | 'sessions' | 'reminders'

export function CoursesPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) ?? 'courses'
  const { has } = useSession()
  return (
    <>
      <PageHeader title="Courses & sessions"
        actions={has('admin') && <ButtonLink to="/admin/courses/new"><Plus className="size-4" />Draft a course</ButtonLink>} />
      <Segmented<Tab> className="mb-5" value={tab} onChange={(t) => setParams({ tab: t }, { replace: true })}
        options={[{ value: 'courses', label: 'Courses' }, { value: 'sessions', label: 'Sessions' }, { value: 'reminders', label: 'Reminders' }]} />
      {tab === 'courses' && <CourseList />}
      {tab === 'sessions' && <SessionsPage embedded />}
      {tab === 'reminders' && <RemindersPanel />}
    </>
  )
}

function CourseList() {
  const { data, isLoading, error, refetch } = useAdminCourses()
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      <Card className="p-0">
        <ul className="divide-y divide-line">
          {data?.map((c) => (
            <li key={c.id}>
              <Link to={`/admin/courses/${c.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-canvas">
                <FileText className="size-5 shrink-0 text-forest-700" />
                <span className="min-w-0 flex-1"><b className="block truncate">{c.title}</b><span className="text-[13px] text-ink-600">{c.skill_name ?? 'No skill'} · {fmt.plural(c.lesson_count, 'lesson')} · {c.duration_minutes} min</span></span>
                <StatusPill status={c.status === 'published' ? 'active' : c.status} label={{ published: 'Published', in_review: 'Waiting for expert', draft: 'Draft', drafting: 'Preparing…', archived: 'Archived' }[c.status]} />
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </QueryState>
  )
}

// ---- A-05 Course builder ---------------------------------------------------------------------
function Steps({ step }: { step: 1 | 2 | 3 }) {
  const labels = ['What to teach', 'Check the draft', 'Approve and publish']
  return (
    <ol className="mb-6 flex flex-wrap gap-x-8 gap-y-2">
      {labels.map((label, i) => (
        <li key={label} className="flex items-center gap-2.5">
          <span className={cn('flex size-8 items-center justify-center rounded-full text-sm font-bold',
            i + 1 < step ? 'bg-ok-600 text-white' : i + 1 === step ? 'bg-forest-700 text-white' : 'bg-[#e3e7ea] text-ink-400')}>
            {i + 1 < step ? <Check className="size-4" /> : i + 1}
          </span>
          <span className={cn('text-sm', i + 1 === step ? 'font-bold' : 'text-ink-600')}>{label}</span>
        </li>
      ))}
    </ol>
  )
}

export function CourseBuilderPage() {
  const skills = useSkills()
  const draft = useDraftCourse()
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [skillId, setSkillId] = useState('')
  const [levels, setLevels] = useState('2-3')
  const [video, setVideo] = useState(true)
  const [simulation, setSimulation] = useState(true)
  const [certification, setCertification] = useState(false)
  const [from, to] = levels.split('-').map(Number)
  const start = () => file && draft.mutate(
    { file, options: { skill_id: skillId || null, from_level: from, to_level: to, narrated_video: video, simulation, certification, quiz_size: 12, languages: ['en', 'hi'] } },
    { onSuccess: (course) => navigate(`/admin/courses/${course.id}`) },
  )
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Draft a course" subtitle="Three steps: choose what to teach, check the draft, approve. Nothing is published until an expert approves." />
      <Steps step={1} />
      <Card className="space-y-5">
        <label className={cn('flex cursor-pointer items-center gap-3 rounded-xl border border-dashed p-4', file ? 'border-forest-700 bg-forest-50' : 'border-line hover:border-forest-700')}>
          {file ? <FileText className="size-6 text-forest-700" /> : <Upload className="size-6 text-forest-700" />}
          <span className="flex-1">
            <b className="block text-sm">{file ? file.name : 'Choose an SOP or document'}</b>
            <span className="text-[13px] text-ink-600">{file ? `${(file.size / 1e6).toFixed(1)} MB` : 'PDF, Word (.docx) or text'}</span>
          </span>
          <input type="file" accept=".pdf,.docx,.txt,.md" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Skill it builds">
            <Select value={skillId} onChange={(e) => setSkillId(e.target.value)}>
              <option value="">Choose a skill</option>
              {skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Level">
            <Select value={levels} onChange={(e) => setLevels(e.target.value)}>
              {['0-2', '1-2', '2-3', '3-4', '4-5'].map((l) => <option key={l} value={l}>Level {l.replace('-', ' to ')}</option>)}
            </Select>
          </Field>
        </div>
        <div className="divide-y divide-line">
          <Toggle checked={video} onChange={setVideo} label="Narrated video with captions" hint="English + Hindi" />
          <Toggle checked={simulation} onChange={setSimulation} label="Practice simulation" hint="Interactive everywhere; AR where the phone supports it" />
          <Toggle checked={certification} onChange={setCertification} label="Certification course" hint="Pass mark and a certificate" />
        </div>
        <p className="text-[13px] italic text-ink-600">Time to draft: about 5 minutes.</p>
        <Button size="lg" block disabled={!file} loading={draft.isPending} onClick={start}>Draft the course</Button>
      </Card>
    </div>
  )
}

export function CourseReviewPage() {
  const { id } = useParams()
  const { data, isLoading, error, refetch } = useAdminCourse(id)
  const { me, has } = useSession()
  const experts = useUsers()
  const submit = useSubmitCourse(id!)
  const review = useReviewCourse(id!)
  const [approver, setApprover] = useState('')
  const [note, setNote] = useState('')
  const [decision, setDecision] = useState<null | boolean>(null)
  const step = !data ? 1 : data.status === 'drafting' ? 1 : data.status === 'draft' ? 2 : 3
  const isApprover = data && (data.approver_id === me?.id || has('admin'))
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <div className="mx-auto max-w-5xl">
          <Link to="/admin/courses" className="text-sm font-semibold text-forest-700">← Courses</Link>
          <PageHeader title={data.title} subtitle={data.source_filename ? `From ${data.source_filename}` : undefined}
            tag={<StatusPill status={data.status === 'published' ? 'active' : data.status} label={{ published: 'Published', in_review: 'Waiting for expert', draft: 'Draft', drafting: 'Preparing…', archived: 'Archived' }[data.status]} />} />
          <Steps step={step as 1 | 2 | 3} />
          {data.status === 'drafting' ? (
            <Card className="flex items-center gap-4 py-10">
              <Loader2 className="size-6 animate-spin text-forest-700" />
              <div><b>Preparing the draft…</b><p className="text-sm text-ink-600">Reading the document and building lessons and a quiz. You can leave this page; we will send you a message.</p></div>
            </Card>
          ) : (
            <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
              <Card>
                <SectionTitle>Draft outline</SectionTitle>
                <Stagger className="space-y-2">
                  {data.lessons.map((l) => (
                    <div key={l.id} className={cn('flex items-center justify-between gap-3 rounded-xl border border-line px-4 py-3', l.kind === 'simulation' && 'bg-forest-50')}>
                      <span className="min-w-0"><b className="block">{l.position}. {l.title}</b><span className="line-clamp-1 text-[13px] text-ink-600">{l.summary}</span></span>
                      <span className="shrink-0 text-[12px] text-ink-600">{l.kind === 'simulation' ? 'Simulation' : l.source_ref}</span>
                    </div>
                  ))}
                </Stagger>
                <p className="mt-4 text-sm">Quiz: {fmt.plural(data.questions?.length ?? data.question_count, 'question')} with answers and reasons</p>
                {data.questions && data.questions.length > 0 && (
                  <details className="mt-2"><summary className="cursor-pointer text-sm font-semibold text-forest-700">See questions</summary>
                    <ol className="mt-2 space-y-2 text-sm">{data.questions.map((q) => (
                      <li key={q.id} className="rounded-lg bg-canvas p-3"><b>{q.text}</b><br />Answer: {q.options[q.answer_index ?? 0]}<br /><span className="text-ink-600">{q.reason}</span></li>
                    ))}</ol>
                  </details>
                )}
              </Card>
              <div className="space-y-3">
                {data.review_note && <Notice tone="warn"><b>Expert note:</b> {data.review_note}</Notice>}
                {data.status === 'draft' && has('admin') && (
                  <Card className="space-y-3">
                    <b>Send for approval</b>
                    <Notice tone="bad">Needs expert approval before it can be published.</Notice>
                    <Field label="Subject expert">
                      <Select value={approver} onChange={(e) => setApprover(e.target.value)}>
                        <option value="">Choose an expert</option>
                        {experts.data?.filter((u) => u.system_roles.includes('expert')).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                      </Select>
                    </Field>
                    <Button block disabled={!approver} loading={submit.isPending} onClick={() => submit.mutate(approver)}>Send to expert</Button>
                  </Card>
                )}
                {data.status === 'in_review' && isApprover && (
                  <Card className="space-y-3">
                    <b>Your decision</b>
                    <Button block onClick={() => setDecision(true)}>Approve and publish</Button>
                    <Button block variant="outline" onClick={() => setDecision(false)}>Send back with notes</Button>
                  </Card>
                )}
                {data.status === 'in_review' && !isApprover && <Notice>Waiting for the expert to approve.</Notice>}
                {data.status === 'published' && <Notice tone="ok"><Check className="mr-1 inline size-4" />Published. People can find it in the catalogue.</Notice>}
              </div>
            </div>
          )}
          <Dialog open={decision !== null} onOpenChange={() => setDecision(null)} title={decision ? 'Approve and publish' : 'Send back with notes'}
            footer={<Button loading={review.isPending} disabled={decision === false && note.trim().length < 3}
              onClick={() => review.mutate({ approve: !!decision, note }, { onSuccess: () => setDecision(null) })}>{decision ? 'Publish' : 'Send back'}</Button>}>
            <Field label={decision ? 'Note (optional)' : 'What should change?'}><Textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          </Dialog>
        </div>
      )}
    </QueryState>
  )
}

// ---- A-06 Sessions & invitations ------------------------------------------------------------------
export function SessionsPage({ embedded }: { embedded?: boolean }) {
  const sessions = useAdminSessions()
  const create = useCreateSession()
  const send = useSendInvitations()
  const users = useUsers()
  const undoToast = useUndoToast()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ title: '', date: '', start: '11:00', end: '12:00', trainer_id: '', meeting_link: '' })
  const [audience, setAudience] = useState<Audience>({})
  const save = () => {
    const starts = new Date(`${form.date}T${form.start}`)
    const ends = new Date(`${form.date}T${form.end}`)
    create.mutate({ title: form.title, trainer_id: form.trainer_id || null, meeting_link: form.meeting_link || null, starts_at: starts.toISOString(), ends_at: ends.toISOString(), audience },
      { onSuccess: () => setOpen(false) })
  }
  return (
    <>
      {!embedded && <PageHeader title="Sessions & invitations" />}
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-ink-600">Scheduled sessions send an invitation. Self-paced items only get completion reminders.</p>
        <Button onClick={() => setOpen(true)}><Plus className="size-4" />Schedule a session</Button>
      </div>
      <QueryState isLoading={sessions.isLoading} error={sessions.error} hasData={!!sessions.data} skeleton={<SkeletonPage />} onRetry={sessions.refetch}>
        {sessions.data?.length === 0 && <EmptyState title="No sessions scheduled" />}
        <Stagger className="space-y-3">
          {sessions.data?.map((s) => (
            <Card key={s.id} className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <b>{s.title}</b>
                <p className="text-[13px] text-ink-600">{fmt.dayTime(s.starts_at)} – {fmt.time(s.ends_at)}{s.trainer_name && ` · ${s.trainer_name}`} · {s.audience_label}</p>
                <p className="mt-1 text-[13px]"><b className="text-ok-600">Accepted {s.accepted}</b> · Declined {s.declined} · Waiting {s.waiting}</p>
              </div>
              {s.invitations_sent_at && s.waiting === 0 ? <Badge tone="ok">Invitations sent</Badge> : (
                <Button loading={send.isPending} onClick={() => send.mutate(s.id, { onSuccess: (r) => undoToast(r, 'Invitations sent') })}>Send invitations</Button>
              )}
            </Card>
          ))}
        </Stagger>
      </QueryState>
      <Dialog open={open} onOpenChange={setOpen} title="Schedule a session" wide
        footer={<Button disabled={!form.title || !form.date || !audienceChosen(audience)} loading={create.isPending} onClick={save}>Save (send after preview)</Button>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Title" className="sm:col-span-2"><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Objection handling for counsellors" /></Field>
          <Field label="Date"><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="From"><Input type="time" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
            <Field label="To"><Input type="time" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
          </div>
          <Field label="Trainer">
            <Select value={form.trainer_id} onChange={(e) => setForm({ ...form, trainer_id: e.target.value })}>
              <option value="">Choose</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select>
          </Field>
          <Field label="Meeting link"><Input value={form.meeting_link} onChange={(e) => setForm({ ...form, meeting_link: e.target.value })} placeholder="https://" /></Field>
          <div className="sm:col-span-2"><b className="mb-2 block text-sm">Who</b><AudiencePicker value={audience} onChange={setAudience} /></div>
        </div>
        {form.title && form.date && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ease: EASE }} className="mt-4 rounded-xl bg-[#dcf5c8] p-4 text-sm">
            <p className="text-[12px] font-semibold text-ink-600">Invitation preview</p>
            Hi {'{first name}'}, you are invited to “{form.title}” on {form.date && fmt.dayTime(`${form.date}T${form.start}`)}. Can you join?
            <div className="mt-2 flex gap-2"><span className="rounded-lg bg-forest-700 px-3 py-1 text-white">Accept</span><span className="rounded-lg border border-forest-700 px-3 py-1 text-forest-700">Decline</span></div>
          </motion.div>
        )}
      </Dialog>
    </>
  )
}

function RemindersPanel() {
  const rules = useReminderRules()
  const preview = useReminderPreview()
  const send = useSendReminders()
  const r = rules.data
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <h2 className="text-xl">Self-paced course: reminders only</h2>
        <Notice tone="bad" className="mt-3 font-semibold">No invitation is sent for self-paced items.</Notice>
        <b className="mt-5 block">How reminders work</b>
        <ul className="mt-2 space-y-2 text-sm">
          {['Sent inside each person’s best time window', `At most ${r?.max_per_day ?? 1} a day and ${r?.max_per_week ?? 3} a week`,
            `No messages before ${r?.quiet_start ?? '09:00'}, after ${r?.quiet_end ?? '19:00'}, weekends or holidays`, 'Stop the moment the item is complete',
            'After the due date: the manager gets one list'].map((t) => (
            <li key={t} className="flex items-start gap-2"><span className="mt-0.5 flex size-5 items-center justify-center rounded-full bg-ok-600 text-white"><Check className="size-3" /></span>{t}</li>
          ))}
        </ul>
        {r?.paused && <Notice tone="warn" className="mt-4">All automatic sends are stopped. Reminders sent by hand still go out.</Notice>}
      </Card>
      <Card>
        <SectionTitle>Today’s reminders (preview)</SectionTitle>
        {preview.data?.length === 0 && <p className="text-sm text-ink-600">No reminders are due today.</p>}
        <table className="w-full text-sm">
          <tbody>
            {preview.data?.slice(0, 12).map((p) => (
              <tr key={p.name} className="border-b border-line last:border-0"><td className="py-2">{p.name}</td><td className="font-bold text-forest-700 tabular">{p.local_time}</td><td className="text-ink-600">{p.channels}</td></tr>
            ))}
          </tbody>
        </table>
        <Button variant="outline" className="mt-4" loading={send.isPending} disabled={!preview.data?.length} onClick={() => send.mutate(undefined)}>Send reminders now</Button>
      </Card>
    </div>
  )
}
