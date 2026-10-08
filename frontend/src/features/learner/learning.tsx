import { ArrowLeft, Award, CalendarClock, Captions, Check, CheckCircle2, ClipboardCheck, MapPin, Pause, Play, Search, Video, XCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import {
  useAssignments, useCompleteLesson, useCourse, useCourses, useMyTests, useRsvp, useSessions, useSimulation, useSubmitQuiz,
} from '@/api/learner'
import type { CourseDetail, Lesson, Question } from '@/api/types'
import { api } from '@/lib/api'
import { Stagger } from '@/components/motion'
import { EASE } from '@/lib/motion-tokens'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, ButtonLink, Card, EmptyState, Input, Notice, PageHeader, ProgressBar, Segmented, SkeletonPage, StatusPill,
} from '@/components/ui'
import { cn, fmt } from '@/lib/utils'

type Tab = 'mine' | 'catalogue' | 'tests' | 'sessions'

export function LearnPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) ?? 'mine'
  return (
    <>
      <PageHeader title="Learn" subtitle="Your courses, skill checks and live sessions."
        actions={<ButtonLink to="/learn/certificates" variant="outline" size="sm"><Award className="size-4" />My certificates</ButtonLink>} />
      <Segmented<Tab> className="mb-5" value={tab} onChange={(t) => setParams({ tab: t }, { replace: true })}
        options={[{ value: 'mine', label: 'My learning' }, { value: 'tests', label: 'Skill checks' }, { value: 'sessions', label: 'Sessions' }, { value: 'catalogue', label: 'Catalogue' }]} />
      {tab === 'mine' && <MyLearning />}
      {tab === 'catalogue' && <Catalogue skill={params.get('skill') ?? undefined} />}
      {tab === 'tests' && <SkillChecks />}
      {tab === 'sessions' && <Sessions />}
    </>
  )
}

function MyLearning() {
  const { data, isLoading, error, refetch } = useAssignments()
  const open = data?.filter((a) => a.status !== 'completed') ?? []
  const done = data?.filter((a) => a.status === 'completed') ?? []
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {open.length === 0 && <EmptyState title="Nothing assigned right now" body="Pick a short course from the catalogue." action={<ButtonLink to="/learn?tab=catalogue">Browse courses</ButtonLink>} />}
      <Stagger className="grid gap-3 sm:grid-cols-2">
        {open.map((a) => (
          <Link key={a.id} to={`/learn/courses/${a.course_id}`} className="block rounded-[var(--radius-card)] border border-line bg-surface p-4 transition-colors hover:border-forest-700">
            <div className="flex items-start justify-between gap-2">
              <b>{a.course_title}</b>
              {a.is_overdue ? <StatusPill status="overdue" /> : a.is_mandatory ? <Badge tone="info">Mandatory</Badge> : null}
            </div>
            <p className="mt-1 text-[13px] text-ink-600">{a.duration_minutes} minutes{a.due_on && ` · due ${fmt.shortDate(a.due_on)}`}</p>
            <ProgressBar className="mt-3" size="sm" value={a.progress_pct} label={`${a.progress_pct}% done`} />
          </Link>
        ))}
      </Stagger>
      {done.length > 0 && (
        <details className="mt-6">
          <summary className="cursor-pointer text-sm font-semibold text-forest-700">Completed ({done.length})</summary>
          <ul className="mt-3 space-y-2">
            {done.map((a) => <li key={a.id} className="flex items-center gap-2 text-sm"><CheckCircle2 className="size-4 text-ok-600" />{a.course_title}</li>)}
          </ul>
        </details>
      )}
    </QueryState>
  )
}

function Catalogue({ skill }: { skill?: string }) {
  const [q, setQ] = useState('')
  const { data, isLoading, error, refetch } = useCourses(q || undefined, skill)
  return (
    <>
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
        <Input className="pl-9" placeholder="Search courses" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search courses" />
      </div>
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data?.length === 0 && <EmptyState title="No courses match" body="Try a shorter word." />}
        <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data?.map((c) => (
            <Link key={c.id} to={`/learn/courses/${c.id}`} className="flex h-full flex-col rounded-[var(--radius-card)] border border-line bg-surface p-4 transition-colors hover:border-forest-700">
              <div className="flex flex-wrap gap-1.5">
                {c.kind === 'certification' && <Badge tone="gold">Certificate</Badge>}
                {c.is_mandatory && <Badge tone="info">Mandatory</Badge>}
                {c.has_simulation && <Badge tone="neutral">Practice</Badge>}
              </div>
              <b className="mt-2">{c.title}</b>
              {c.skill_name && <p className="text-[13px] text-ink-600">{c.skill_name} · level {c.from_level} to {c.to_level}</p>}
              <p className="mt-auto pt-3 text-[13px] text-ink-600">{c.duration_minutes} min · {fmt.plural(c.lesson_count, 'lesson')}{c.languages.includes('hi') && ' · हिंदी'}</p>
            </Link>
          ))}
        </Stagger>
      </QueryState>
    </>
  )
}

function SkillChecks() {
  const { data, isLoading, error, refetch } = useMyTests()
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data?.length === 0 && <EmptyState icon={<ClipboardCheck className="size-8" />} title="No skill checks waiting" body="When your role needs a check, it shows up here." />}
      <Stagger className="space-y-2.5">
        {data?.map((t) => (
          <Card key={t.invite_id ?? t.test.id} className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <b>{t.test.title}</b>
              <p className="text-[13px] text-ink-600">
                {t.test.question_count} questions · about {t.test.duration_minutes} minutes{t.due_on && ` · by ${fmt.shortDate(t.due_on)}`}
                {t.test.proctoring === 'camera' && ' · supervised'}
              </p>
            </div>
            {t.status === 'done' ? (
              <span className="flex items-center gap-2 text-sm"><StatusPill status="done" />{t.last_level != null && `Level ${t.last_level}`}</span>
            ) : t.status === 'in_progress' && t.attempt_id ? (
              <ButtonLink to={`/learn/tests/attempts/${t.attempt_id}`}>Continue</ButtonLink>
            ) : (
              <ButtonLink to={`/learn/tests/${t.test.id}`}>Start</ButtonLink>
            )}
          </Card>
        ))}
      </Stagger>
    </QueryState>
  )
}

function Sessions() {
  const { data, isLoading, error, refetch } = useSessions()
  const rsvp = useRsvp()
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data?.length === 0 && <EmptyState icon={<CalendarClock className="size-8" />} title="No live sessions coming up" />}
      <Stagger className="space-y-2.5">
        {data?.map((s) => (
          <Card key={s.id}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <b>{s.title}</b>
                <p className="text-[13px] text-ink-600">{fmt.dayTime(s.starts_at)}{s.trainer_name && ` · with ${s.trainer_name}`}</p>
                {s.location && <p className="flex items-center gap-1 text-[13px] text-ink-600"><MapPin className="size-3.5" />{s.location}</p>}
              </div>
              {s.my_status && <StatusPill status={s.my_status} label={s.my_status === 'pending' ? 'Please reply' : undefined} />}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {s.my_status !== 'accepted' && <Button size="sm" onClick={() => rsvp.mutate({ sessionId: s.id, accept: true })}>Accept</Button>}
              {s.my_status !== 'declined' && <Button size="sm" variant="outline" onClick={() => rsvp.mutate({ sessionId: s.id, accept: false })}>Decline</Button>}
              {s.meeting_link && s.my_status === 'accepted' && <a className="inline-flex h-9 items-center px-3 text-sm font-semibold text-forest-700 underline" href={s.meeting_link} target="_blank" rel="noreferrer">Join link</a>}
            </div>
          </Card>
        ))}
      </Stagger>
    </QueryState>
  )
}

// ---- L-03 Course player -------------------------------------------------------------------------
export function CoursePage() {
  const { id } = useParams()
  const { data, isLoading, error, refetch } = useCourse(id)
  const [current, setCurrent] = useState<string | null>(null)
  const [showQuiz, setShowQuiz] = useState(false)
  const lesson = useMemo(() => {
    if (!data) return null
    const chosen = data.lessons.find((l) => l.id === current)
    return chosen ?? data.lessons.find((l) => l.id === data.my_progress?.next_lesson_id) ?? null
  }, [data, current])
  const allLessonsDone = data ? data.lessons.every((l) => l.completed) : false
  const quizMode = showQuiz || (allLessonsDone && (data?.question_count ?? 0) > 0 && data?.my_progress?.status !== 'completed')

  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
          <div className="min-w-0">
            <Link to="/learn" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-forest-700"><ArrowLeft className="size-4" />Learn</Link>
            {data.my_progress?.status === 'completed' && !current && !showQuiz ? (
              <CompletedCard course={data} />
            ) : quizMode && !current ? (
              <Quiz course={data} />
            ) : lesson ? (
              <LessonView key={lesson.id} course={data} lesson={lesson} onNext={(nextId) => (nextId ? setCurrent(nextId) : setShowQuiz(true))} />
            ) : (
              <CompletedCard course={data} />
            )}
          </div>
          <aside>
            <Card>
              <b className="block">{data.title}</b>
              <ProgressBar className="mt-3" value={data.my_progress?.progress_pct ?? 0} label={`${data.my_progress?.progress_pct ?? 0}% done`} />
              <ol className="mt-4 space-y-1">
                {data.lessons.map((l) => (
                  <li key={l.id}>
                    <button onClick={() => { setCurrent(l.id); setShowQuiz(false) }}
                      className={cn('flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-canvas', lesson?.id === l.id && !quizMode && 'bg-forest-50 font-semibold')}>
                      {l.completed ? <CheckCircle2 className="size-4 shrink-0 text-ok-600" /> : <span className="size-4 shrink-0 rounded-full border-2 border-line" />}
                      <span className="truncate">{l.title}</span>
                    </button>
                  </li>
                ))}
                {data.question_count > 0 && (
                  <li><button onClick={() => { setShowQuiz(true); setCurrent(null) }} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-canvas">
                    <ClipboardCheck className="size-4 text-forest-700" />Quick check: {data.question_count} questions</button></li>
                )}
              </ol>
            </Card>
          </aside>
        </div>
      )}
    </QueryState>
  )
}

function CompletedCard({ course }: { course: CourseDetail }) {
  return (
    <Card className="py-10 text-center">
      <CheckCircle2 className="mx-auto size-12 text-ok-600" />
      <h1 className="mt-3 text-2xl">You finished “{course.title}”</h1>
      <p className="mt-1 text-ink-600">{course.kind === 'certification' ? 'Your certificate is ready.' : 'Nice work. Your next step is on the home screen.'}</p>
      <div className="mt-5 flex justify-center gap-2">
        <ButtonLink to="/">Back to home</ButtonLink>
        {course.kind === 'certification' && <ButtonLink to="/learn/certificates" variant="outline">My certificates</ButtonLink>}
      </div>
    </Card>
  )
}

function LessonView({ course, lesson, onNext }: { course: CourseDetail; lesson: Lesson; onNext: (nextId: string | null) => void }) {
  const complete = useCompleteLesson(course.id)
  const index = course.lessons.findIndex((l) => l.id === lesson.id)
  const finish = () => complete.mutate(lesson.id, { onSuccess: (r) => onNext(r.next_lesson_id) })
  return (
    <div>
      {lesson.kind === 'simulation' && lesson.scenario ? (
        <Simulation lesson={lesson} onDone={() => onNext(course.lessons[index + 1]?.id ?? null)} />
      ) : (
        <>
          {lesson.kind === 'video' && <CaptionedPlayer lesson={lesson} />}
          <h1 className="mt-5 text-2xl sm:text-3xl">{lesson.title}</h1>
          <p className="text-[13px] text-ink-600">Lesson {index + 1} of {course.lessons.length}{lesson.source_ref && ` · ${lesson.source_ref}`}</p>
          <div className="mt-4 whitespace-pre-line leading-relaxed text-ink-700">{lesson.body || lesson.summary}</div>
          {course.question_count > 0 && index === course.lessons.length - 1 && (
            <Notice className="mt-5">Quick check at the end: {course.question_count} questions.</Notice>
          )}
          <Button size="lg" block className="mt-6" onClick={finish} loading={complete.isPending}>{lesson.completed ? 'Next' : 'Done, next'}</Button>
        </>
      )}
    </div>
  )
}

/** A light video stand-in: plays timed captions (EN / हिंदी) when no media file is attached. */
function CaptionedPlayer({ lesson }: { lesson: Lesson }) {
  const languages = Object.keys(lesson.captions ?? {})
  const [lang, setLang] = useState(languages[0] ?? 'en')
  const [playing, setPlaying] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const total = lesson.duration_minutes * 60
  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => setSeconds((s) => Math.min(total, s + 1)), 1000)
    return () => window.clearInterval(timer)
  }, [playing, total])
  const lines = lesson.captions?.[lang] ?? []
  const caption = [...lines].reverse().find((c) => c.at <= seconds)?.text ?? lines[0]?.text ?? lesson.summary
  return (
    <div>
      <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-[var(--radius-card)] bg-ink-900">
        {lesson.media_url ? (
          <video src={lesson.media_url} controls className="h-full w-full" />
        ) : (
          <>
            <button onClick={() => setPlaying((p) => !p)} className="flex size-16 items-center justify-center rounded-full bg-white/10 text-white backdrop-blur hover:bg-white/20" aria-label={playing ? 'Pause' : 'Play'}>
              {playing ? <Pause className="size-7" /> : <Play className="size-7 translate-x-0.5" />}
            </button>
            <Video className="absolute left-4 top-4 size-5 text-white/40" aria-hidden />
            <AnimatePresence mode="wait">
              <motion.p key={caption} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
                className="absolute inset-x-6 bottom-5 rounded-md bg-black/80 px-3 py-2 text-center text-sm text-white">{caption}</motion.p>
            </AnimatePresence>
          </>
        )}
      </div>
      <ProgressBar className="mt-3" size="sm" tone="forest" value={(seconds / total) * 100} />
      <div className="mt-1.5 flex items-center justify-between text-[12px] text-ink-600">
        <span className="tabular">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} of {lesson.duration_minutes}:00</span>
        <span className="flex items-center gap-2"><Captions className="size-3.5" />
          {languages.map((l) => (
            <button key={l} onClick={() => setLang(l)} className={cn('font-semibold', lang === l ? 'text-forest-700' : 'text-ink-400')}>{l === 'hi' ? 'हिंदी' : 'EN'}</button>
          ))}
        </span>
      </div>
    </div>
  )
}

/** Simulation: AR mode where supported, a simple photo-with-tap-points mode everywhere. */
function Simulation({ lesson, onDone }: { lesson: Lesson; onDone: () => void }) {
  const scenario = lesson.scenario!
  const [order, setOrder] = useState<string[]>([])
  const [mode, setMode] = useState<'simple' | 'ar'>('simple')
  const check = useSimulation()
  const result = check.data
  const arAvailable = scenario.ar_supported && typeof navigator !== 'undefined' && 'xr' in navigator
  const tap = (id: string) => {
    if (order.includes(id) || result?.correct) return
    const next = [...order, id]
    setOrder(next)
    if (next.length === scenario.steps.length) check.mutate({ lessonId: lesson.id, order: next })
  }
  const reset = () => { setOrder([]); check.reset() }
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl">{lesson.title}</h1>
        {scenario.ar_supported && (
          <Segmented value={mode} onChange={setMode} options={[{ value: 'simple', label: 'Simple mode' }, { value: 'ar', label: 'AR mode' }]} />
        )}
      </div>
      <p className="mt-1 text-ink-600">Step {Math.min(order.length + 1, scenario.steps.length)} of {scenario.steps.length}: tap the steps in the right order.</p>
      {mode === 'ar' && !arAvailable && <Notice tone="warn" className="mt-3">This phone does not support AR. Simple mode works the same way.</Notice>}
      <div className={cn('relative mt-4 aspect-[4/3] overflow-hidden rounded-[var(--radius-card)]', mode === 'ar' ? 'bg-[#b8c6c0]' : 'bg-[#dde5e1]')}>
        {scenario.image && <img src={scenario.image} alt="" className="absolute inset-0 h-full w-full object-cover" />}
        <div className="absolute inset-[18%] rounded-xl bg-[#b0bfb8]" aria-hidden />
        {scenario.steps.map((step, i) => {
          const position = order.indexOf(step.id)
          return (
            <motion.button
              key={step.id} onClick={() => tap(step.id)} whileTap={{ scale: 0.92 }}
              initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: i * 0.06, ease: EASE }}
              className={cn('absolute flex min-h-11 -translate-x-1/2 -translate-y-1/2 items-center gap-2 rounded-full px-3 py-2 text-sm font-semibold shadow-md',
                position >= 0 ? 'bg-forest-700 text-white' : 'bg-white text-ink-900 hover:ring-2 hover:ring-gold-500')}
              style={{ left: `${step.x ?? 20 + i * 20}%`, top: `${step.y ?? 50}%` }}
            >
              <span className={cn('flex size-6 items-center justify-center rounded-full text-xs', position >= 0 ? 'bg-gold-500' : 'bg-forest-100 text-forest-800')}>
                {position >= 0 ? position + 1 : '?'}
              </span>
              {step.label}
            </motion.button>
          )
        })}
      </div>
      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className={cn('mt-4 rounded-xl p-4', result.correct ? 'bg-ok-50 text-ok-600' : 'bg-bad-50 text-bad-600')}>
            <p className="flex items-center gap-2 font-bold">{result.correct ? <Check className="size-5" /> : <XCircle className="size-5" />}{result.message}{result.points > 0 && ` +${result.points} points`}</p>
            {scenario.feedback && <p className="mt-1 text-sm">{scenario.feedback}</p>}
          </motion.div>
        )}
      </AnimatePresence>
      {result?.correct ? (
        <Button size="lg" block className="mt-5" onClick={onDone}>Next step</Button>
      ) : order.length > 0 ? (
        <Button size="lg" variant="outline" block className="mt-5" onClick={reset}>Start again</Button>
      ) : null}
    </div>
  )
}

function Quiz({ course }: { course: CourseDetail }) {
  const submit = useSubmitQuiz(course.id)
  const navigate = useNavigate()
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [index, setIndex] = useState(0)
  const { data: full } = useCourseQuestions(course)
  const questions = full ?? []
  const result = submit.data
  if (!questions.length) return <SkeletonPage />
  if (result) {
    return (
      <Card>
        <h1 className="text-2xl">{result.passed ? 'You passed' : 'Not quite yet'}</h1>
        <p className="mt-1 text-ink-600">Score {result.score} of 100{result.pass_mark && ` · pass mark ${result.pass_mark}`}</p>
        <ul className="mt-5 space-y-3">
          {result.results.map((r, i) => (
            <li key={r.question_id} className="rounded-xl border border-line p-3 text-sm">
              <p className="flex items-start gap-2 font-semibold">{r.correct ? <Check className="mt-0.5 size-4 shrink-0 text-ok-600" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-bad-600" />}{questions[i]?.text}</p>
              {!r.correct && <p className="mt-1 pl-6 text-ink-600">Right answer: {questions[i]?.options[r.right_index]}. {r.reason}</p>}
            </li>
          ))}
        </ul>
        <Button size="lg" block className="mt-5" onClick={() => (result.passed ? navigate('/') : (submit.reset(), setAnswers({}), setIndex(0)))}>
          {result.passed ? 'Back to home' : 'Try again'}
        </Button>
      </Card>
    )
  }
  const q = questions[index]
  const last = index === questions.length - 1
  return (
    <Card>
      <p className="text-sm text-ink-600">Question {index + 1} of {questions.length}</p>
      <ProgressBar className="mt-2" size="sm" tone="forest" value={((index + 1) / questions.length) * 100} />
      <h2 className="mt-5 font-sans text-lg font-bold">{q.text}</h2>
      <div className="mt-4 space-y-2.5" role="radiogroup">
        {q.options.map((option, i) => (
          <button key={i} role="radio" aria-checked={answers[q.id] === i} onClick={() => setAnswers({ ...answers, [q.id]: i })}
            className={cn('flex w-full items-center gap-3 rounded-xl border p-3.5 text-left text-[15px] transition-colors',
              answers[q.id] === i ? 'border-forest-700 bg-forest-50' : 'border-line hover:border-forest-700/50')}>
            <span className={cn('size-5 shrink-0 rounded-full border-2', answers[q.id] === i ? 'border-forest-700 bg-forest-700 shadow-[inset_0_0_0_3px_white]' : 'border-line')} />
            {option}
          </button>
        ))}
      </div>
      <Button size="lg" block className="mt-6" disabled={answers[q.id] === undefined} loading={submit.isPending}
        onClick={() => (last ? submit.mutate(answers) : setIndex(index + 1))}>{last ? 'See my result' : 'Next'}</Button>
    </Card>
  )
}

function useCourseQuestions(course: CourseDetail) {
  return useQuery({ queryKey: ['courses', course.id, 'quiz'], queryFn: () => api.get<Question[]>(`/courses/${course.id}/quiz`) })
}
