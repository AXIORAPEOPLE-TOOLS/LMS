import { ArrowLeft, ArrowRight, Award, Captions, Check, CheckCircle2, ClipboardCheck, MapPin, Pause, Play, Search, Video, XCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
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
  Badge, Button, ButtonLink, Card, EmptyState, Field, Input, Notice, PageHeader, ProgressBar, Segmented, SkeletonPage, StatusPill, Textarea,
} from '@/components/ui'
import { cn, fmt } from '@/lib/utils'

type Tab = 'todo' | 'browse' | 'done'

/** Learn: three plain tabs. "To do" holds everything assigned to me (courses, tests, live classes). */
export function LearnPage() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  // Old links (?tab=mine|tests|sessions|catalogue) still work.
  const tab: Tab = raw === 'browse' || raw === 'catalogue' ? 'browse' : raw === 'done' ? 'done' : 'todo'
  return (
    <>
      <PageHeader title="Learn" subtitle="What HR assigned to you, what you can pick yourself, and what you have finished." />
      <Segmented<Tab> className="mb-6" value={tab} onChange={(t) => setParams({ tab: t }, { replace: true })}
        options={[{ value: 'todo', label: 'To do' }, { value: 'browse', label: 'Browse courses' }, { value: 'done', label: 'Done' }]} />
      {tab === 'todo' && <ToDo />}
      {tab === 'browse' && <Catalogue skill={params.get('skill') ?? undefined} />}
      {tab === 'done' && <Done />}
    </>
  )
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  if (!count) return null
  return (
    <section className="mb-8">
      <h2 className="mb-3 font-sans text-[17px] font-bold">{title} <span className="font-normal text-ink-400">{count}</span></h2>
      {children}
    </section>
  )
}

function ToDo() {
  const assignments = useAssignments()
  const tests = useMyTests()
  const sessions = useSessions()
  const rsvp = useRsvp()
  const loading = assignments.isLoading || tests.isLoading || sessions.isLoading
  const open = assignments.data?.filter((a) => a.status !== 'completed') ?? []
  const openTests = tests.data?.filter((t) => t.status !== 'done') ?? []
  const upcoming = sessions.data?.filter((s) => s.my_status !== 'declined') ?? []
  if (loading) return <SkeletonPage />
  if (!open.length && !openTests.length && !upcoming.length) {
    return <EmptyState icon={<CheckCircle2 className="size-8" />} title="You are all caught up" body="Nothing is assigned right now. Pick a short course if you like."
      action={<ButtonLink to="/learn?tab=browse">Browse courses</ButtonLink>} />
  }
  return (
    <>
      <Section title="Courses" count={open.length}>
        <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {open.map((a) => (
            <Link key={a.id} to={`/learn/courses/${a.course_id}`} className="flex h-full flex-col rounded-card border border-line bg-surface p-5 transition-colors hover:border-forest-700">
              <div className="flex items-start justify-between gap-2">
                <b>{a.course_title}</b>
                {a.is_overdue ? <StatusPill status="overdue" /> : a.is_mandatory ? <Badge tone="info">Must do</Badge> : null}
              </div>
              <p className="mt-1 text-[13px] text-ink-600">{a.duration_minutes} minutes{a.due_on && ` · due ${fmt.shortDate(a.due_on)}`}</p>
              <div className="mt-auto pt-4">
                <ProgressBar size="sm" value={a.progress_pct} label={a.progress_pct ? `${a.progress_pct}% done` : 'Not started'} />
              </div>
            </Link>
          ))}
        </Stagger>
      </Section>
      <Section title="Tests" count={openTests.length}>
        <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {openTests.map((t) => (
            <Card key={t.invite_id ?? t.test.id} className="flex h-full flex-col gap-4">
              <div className="flex-1">
                <b>{t.test.title}</b>
                <p className="text-[13px] text-ink-600">
                  {t.test.question_count} questions · about {t.test.duration_minutes} minutes{t.due_on && ` · by ${fmt.shortDate(t.due_on)}`}
                  {t.test.proctoring === 'camera' && ' · camera on'}
                </p>
              </div>
              {t.status === 'in_progress' && t.attempt_id
                ? <ButtonLink to={`/learn/tests/attempts/${t.attempt_id}`} variant="outline" block>Continue test</ButtonLink>
                : <ButtonLink to={`/learn/tests/${t.test.id}`} variant="outline" block>Start test</ButtonLink>}
            </Card>
          ))}
        </Stagger>
      </Section>
      <Section title="Live classes" count={upcoming.length}>
        <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {upcoming.map((s) => (
            <Card key={s.id} className="flex h-full flex-col">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <b>{s.title}</b>
                {s.my_status === 'pending' ? <Badge tone="warn">Please reply</Badge> : s.my_status === 'accepted' ? <Badge tone="ok">Going</Badge> : null}
              </div>
              <p className="text-[13px] text-ink-600">{fmt.dayTime(s.starts_at)}{s.trainer_name && ` · with ${s.trainer_name}`}</p>
              {s.location && <p className="flex items-center gap-1 text-[13px] text-ink-600"><MapPin className="size-3.5" />{s.location}</p>}
              <div className="mt-auto flex flex-wrap gap-2 pt-4">
                {s.my_status !== 'accepted' && <Button size="sm" variant="outline" onClick={() => rsvp.mutate({ sessionId: s.id, accept: true })}>I will attend</Button>}
                {s.my_status === 'accepted' && s.meeting_link && <a className="inline-flex h-9 items-center px-1 text-sm font-semibold text-forest-700 underline" href={s.meeting_link} target="_blank" rel="noreferrer">Join link</a>}
                <Button size="sm" variant="ghost" onClick={() => rsvp.mutate({ sessionId: s.id, accept: false })}>Can't attend</Button>
              </div>
            </Card>
          ))}
        </Stagger>
      </Section>
    </>
  )
}

function Done() {
  const assignments = useAssignments()
  const tests = useMyTests()
  if (assignments.isLoading || tests.isLoading) return <SkeletonPage />
  const courses = assignments.data?.filter((a) => a.status === 'completed') ?? []
  const passedTests = tests.data?.filter((t) => t.status === 'done') ?? []
  return (
    <>
      <Link to="/learn/certificates" className="mb-8 flex items-center gap-4 rounded-card border border-gold-500/40 bg-linear-to-r from-gold-100/70 to-surface p-5 hover:border-gold-500">
        <span className="flex size-11 items-center justify-center rounded-xl bg-gold-500 text-white"><Award className="size-5" /></span>
        <span className="flex-1"><b className="block">My certificates</b><span className="text-sm text-ink-600">Download or share them.</span></span>
        <ArrowRight className="size-5 text-ink-400" />
      </Link>
      {!courses.length && !passedTests.length && <EmptyState title="Nothing finished yet" body="Finished courses and tests show here." />}
      <Section title="Finished courses" count={courses.length}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {courses.map((a) => (
            <Link key={a.id} to={`/learn/courses/${a.course_id}`} className="flex items-center gap-3 rounded-card border border-line bg-surface p-4 text-sm hover:border-forest-700">
              <CheckCircle2 className="size-5 shrink-0 text-ok-600" /><b className="truncate">{a.course_title}</b>
            </Link>
          ))}
        </div>
      </Section>
      <Section title="Tests taken" count={passedTests.length}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {passedTests.map((t) => (
            <div key={t.invite_id ?? t.test.id} className="flex items-center gap-3 rounded-card border border-line bg-surface p-4 text-sm">
              <ClipboardCheck className="size-5 shrink-0 text-forest-700" />
              <b className="min-w-0 flex-1 truncate">{t.test.title}</b>
              {t.last_level != null && <Badge tone="ok">Level {t.last_level}</Badge>}
            </div>
          ))}
        </div>
      </Section>
    </>
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
            <Link key={c.id} to={`/learn/courses/${c.id}`} className="flex h-full flex-col rounded-card border border-line bg-surface p-4 transition-colors hover:border-forest-700">
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
        <ButtonLink to="/home">Back to home</ButtonLink>
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
      <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-card bg-ink-900">
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
      <div className={cn('relative mt-4 aspect-4/3 overflow-hidden rounded-card', mode === 'ar' ? 'bg-[#b8c6c0]' : 'bg-[#dde5e1]')}>
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
  const [answers, setAnswers] = useState<Record<string, number | string>>({})
  const [index, setIndex] = useState(0)
  const { data: full } = useCourseQuestions(course)
  const questions = full ?? []
  const result = submit.data
  if (!questions.length) return <SkeletonPage />
  if (result?.under_review) {
    return (
      <Card className="mx-auto max-w-xl text-center">
        <h1 className="text-2xl">Thanks, your answers are in</h1>
        <p className="mt-3 text-ink-600">A person is checking your written answers. You will get a message with your result, usually within a day.</p>
        <ButtonLink to="/learn" size="lg" block className="mt-6">Back to Learn</ButtonLink>
      </Card>
    )
  }
  if (result) {
    const restart = () => { submit.reset(); setAnswers({}); setIndex(0) }
    const feedback = result.results.filter((r) => r.feedback)
    return (
      <Card className="mx-auto max-w-xl text-center">
        <h1 className="text-2xl">{result.passed ? 'You passed' : 'Not quite yet'}</h1>
        <p className="mt-3 font-serif text-5xl font-bold text-forest-800 tabular">{result.score}<span className="text-2xl text-ink-400"> / 100</span></p>
        <p className="mt-2 text-ink-600">{result.correct_count} of {result.total} right · pass mark {result.pass_mark}</p>
        {!result.passed && result.attempts_left !== null && (
          <p className="mt-1 text-sm text-ink-600">{result.attempts_left > 0 ? `${fmt.plural(result.attempts_left, 'try', 'tries')} left` : 'No tries left. Ask your manager to reopen it.'}</p>
        )}
        {feedback.length > 0 && (
          <ul className="mt-4 space-y-2 text-left text-sm">
            {feedback.map((r) => <li key={r.question_id} className="rounded-xl bg-canvas p-3"><b>{r.marks} of {r.max_marks} marks.</b> {r.feedback}</li>)}
          </ul>
        )}
        {result.passed ? (
          <Button size="lg" block className="mt-6" onClick={() => navigate('/home')}>Back to home</Button>
        ) : result.can_retake ? (
          <Button size="lg" block className="mt-6" onClick={restart}>Restart quiz</Button>
        ) : (
          <ButtonLink to="/learn" size="lg" block className="mt-6">Back to Learn</ButtonLink>
        )}
      </Card>
    )
  }
  const q = questions[index]
  const last = index === questions.length - 1
  const written = q.kind === 'written'
  const answered = written ? String(answers[q.id] ?? '').trim().length >= 3 : answers[q.id] !== undefined
  return (
    <Card>
      <p className="text-sm text-ink-600">
        Question {index + 1} of {questions.length}
        {course.quiz_time_limit_minutes ? ` · take about ${course.quiz_time_limit_minutes} minutes in all` : ''}
      </p>
      <ProgressBar className="mt-2" size="sm" tone="forest" value={((index + 1) / questions.length) * 100} />
      <h2 className="mt-5 font-sans text-lg font-bold">{q.text}</h2>
      {written ? (
        <Field label="Your answer" hint="A few lines in your own words. Spelling does not matter." className="mt-4">
          <Textarea rows={5} value={String(answers[q.id] ?? '')} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} />
        </Field>
      ) : (
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
      )}
      <div className="mt-6 flex gap-2">
        {index > 0 && <Button variant="ghost" size="lg" onClick={() => setIndex(index - 1)}>Back</Button>}
        <Button size="lg" block disabled={!answered} loading={submit.isPending}
          onClick={() => (last ? submit.mutate(answers) : setIndex(index + 1))}>{last ? 'See my result' : 'Next'}</Button>
      </div>
    </Card>
  )
}

function useCourseQuestions(course: CourseDetail) {
  return useQuery({ queryKey: ['courses', course.id, 'quiz'], queryFn: () => api.get<Question[]>(`/courses/${course.id}/quiz`) })
}
