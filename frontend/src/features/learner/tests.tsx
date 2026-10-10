import { Award, Camera, CameraOff, Check, CheckCircle2, Download, Share2, ShieldCheck } from 'lucide-react'
import { motion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  useAnswer, useAppeal, useAttempt, useAttemptResult, useBookInPerson, useCertificates, useStartAttempt, useSubmitAttempt, useTestInfo,
} from '@/api/learner'
import type { Attempt } from '@/api/types'
import { Stagger } from '@/components/motion'
import { EASE } from '@/lib/motion-tokens'
import { QueryState } from '@/components/SystemStatus'
import {
  Button, ButtonLink, Card, Dialog, EmptyState, Field, Input, Notice, PageHeader, Panel, ProgressBar, SkeletonPage, StatusPill, Textarea,
} from '@/components/ui'
import { api } from '@/lib/api'
import { cn, fmt } from '@/lib/utils'

// ---- intro (L-04 / L-06) ---------------------------------------------------------------------
export function TestIntroPage() {
  const { id } = useParams()
  const { data: test, isLoading, error, refetch } = useTestInfo(id)
  const start = useStartAttempt()
  const navigate = useNavigate()
  const [consent, setConsent] = useState(false)
  const [cameraOk, setCameraOk] = useState<boolean | null>(null)
  const [inPerson, setInPerson] = useState(false)
  const [dates, setDates] = useState('')
  const book = useBookInPerson()
  const supervised = test?.proctoring === 'camera'

  const checkCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true })
      stream.getTracks().forEach((t) => t.stop())
      setCameraOk(true)
    } catch {
      setCameraOk(false)
    }
  }

  const begin = () => start.mutate({ testId: id!, consent }, { onSuccess: (attempt) => navigate(`/learn/tests/attempts/${attempt.id}`) })

  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!test} skeleton={<SkeletonPage />} onRetry={refetch}>
      {test && (
        <div className="mx-auto max-w-xl">
          <p className="text-sm text-ink-600">{supervised ? 'Mandatory test' : 'Skill check'}</p>
          <h1 className="text-3xl">{test.title}</h1>
          <Stagger className="mt-6 space-y-4">
            {[
              [`${test.question_count} questions`, `about ${test.duration_minutes} minutes`],
              test.pass_mark ? [`Pass mark ${test.pass_mark}%`, 'you get a certificate when you pass'] : ['No pass or fail', 'it shows your level'],
              ['You can pause', supervised ? 'your answers are saved as you go' : 'between skills'],
            ].map(([title, sub], i) => (
              <div key={title} className="flex items-center gap-4">
                <span className="flex size-10 items-center justify-center rounded-full bg-forest-100 font-bold text-forest-800">{i + 1}</span>
                <span><b className="block">{title}</b><span className="text-sm text-ink-600">{sub}</span></span>
              </div>
            ))}
          </Stagger>

          {supervised ? (
            <div className="mt-7 space-y-4">
              <Notice tone="forest">
                <b className="block">How this test is supervised</b>
                Your camera takes a picture about every 45 seconds to check that it is you taking the test. Only a trained reviewer sees flags.
                Nothing is failed automatically. Pictures are deleted after 30 days.
              </Notice>
              <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span className="flex items-center gap-2 font-semibold">
                  {cameraOk ? <Camera className="size-5 text-ok-600" /> : <CameraOff className="size-5 text-ink-400" />}
                  {cameraOk === null ? 'Camera check' : cameraOk ? 'Camera works' : 'We could not use your camera'}
                </span>
                <Button variant="outline" size="sm" onClick={checkCamera}>Check camera</Button>
              </Card>
              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line bg-surface p-4">
                <input type="checkbox" className="mt-1 size-5 accent-[#1F5C4E]" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                <span>I understand how the test is supervised and I agree.</span>
              </label>
              <p className="text-sm text-ink-600">Prefer not to use a camera? <button className="font-semibold text-forest-700 underline" onClick={() => setInPerson(true)}>Book an in-person test</button></p>
              <Button size="lg" block disabled={!consent || cameraOk === false} loading={start.isPending} onClick={begin}>I agree, start the test</Button>
            </div>
          ) : (
            <>
              <Notice className="mt-7">{test.instructions}</Notice>
              <Button size="lg" block className="mt-6" loading={start.isPending} onClick={begin}>Start test</Button>
            </>
          )}

          <Dialog open={inPerson} onOpenChange={setInPerson} title="Book an in-person test" description="HR will confirm a date and room with you."
            footer={<Button loading={book.isPending} onClick={() => book.mutate({ testId: id!, dates }, { onSuccess: () => setInPerson(false) })}>Send request</Button>}>
            <Field label="Days or times that suit you" hint="For example: Monday or Tuesday morning">
              <Input value={dates} onChange={(e) => setDates(e.target.value)} />
            </Field>
          </Dialog>
        </div>
      )}
    </QueryState>
  )
}

// ---- proctoring (snapshots + tab switches) ------------------------------------------------------
function useProctoring(attempt: Attempt | undefined) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const startedAt = useRef(0)
  const [active, setActive] = useState(false)
  const send = useCallback((kind: string, image?: string) => {
    if (!attempt) return
    const at = Math.round((Date.now() - startedAt.current) / 1000)
    void api.post(`/attempts/${attempt.id}/proctor-events`, { kind, at_seconds: at, image_base64: image }).catch(() => undefined)
  }, [attempt])

  useEffect(() => {
    if (!attempt || attempt.proctoring !== 'camera' || attempt.status !== 'in_progress') return
    startedAt.current = Date.now()
    let stream: MediaStream | null = null
    let timer = 0
    const canvas = document.createElement('canvas')
    canvas.width = 320
    canvas.height = 240
    const snap = () => {
      const video = videoRef.current
      if (!video || video.readyState < 2) return
      canvas.getContext('2d')?.drawImage(video, 0, 0, 320, 240)
      send('snapshot', canvas.toDataURL('image/jpeg', 0.6))
    }
    navigator.mediaDevices?.getUserMedia({ video: { width: 320, height: 240 } }).then((s) => {
      stream = s
      if (videoRef.current) videoRef.current.srcObject = s
      setActive(true)
      s.getVideoTracks()[0]?.addEventListener('ended', () => send('camera_off'))
      timer = window.setInterval(snap, attempt.snapshot_seconds * 1000)
    }).catch(() => send('camera_off'))
    const onVisibility = () => document.visibilityState === 'hidden' && send('tab_switch')
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [attempt, send])
  return { videoRef, active }
}

// ---- one question per screen ---------------------------------------------------------------
export function AttemptPage() {
  const { id } = useParams()
  const { data: attempt, isLoading, error, refetch } = useAttempt(id)
  const navigate = useNavigate()
  useEffect(() => {
    if (attempt && attempt.status !== 'in_progress') navigate(`/learn/tests/attempts/${attempt.id}/result`, { replace: true })
  }, [attempt, navigate])
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!attempt} skeleton={<SkeletonPage />} onRetry={refetch}>
      {attempt && <AttemptRunner key={attempt.id} attempt={attempt} />}
    </QueryState>
  )
}

/** Starts from the saved answers (resume after a pause). Keyed by attempt so state is fresh per attempt. */
function AttemptRunner({ attempt }: { attempt: Attempt }) {
  const id = attempt.id
  const answer = useAnswer(id)
  const submit = useSubmitAttempt()
  const navigate = useNavigate()
  const [index, setIndex] = useState(() => Math.max(0, attempt.questions.findIndex((q) => q.selected == null)))
  const [selected, setSelected] = useState<Record<string, number>>(() =>
    Object.fromEntries(attempt.questions.filter((q) => q.selected != null).map((q) => [q.id, q.selected!])))
  const [secondsLeft, setSecondsLeft] = useState<number | null>(attempt.seconds_left)
  const { videoRef, active } = useProctoring(attempt)

  const finish = useCallback(() => {
    submit.mutate(id, { onSuccess: () => navigate(`/learn/tests/attempts/${id}/result`, { replace: true }) })
  }, [id, navigate, submit])

  useEffect(() => {
    if (secondsLeft === null) return
    if (secondsLeft <= 0) {
      toast.info('Time is up. We saved your answers.')
      finish()
      return
    }
    const timer = window.setTimeout(() => setSecondsLeft((s) => (s ?? 1) - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [secondsLeft, finish])

  const q = attempt.questions[index]
  const choose = (option: number) => {
    if (!q) return
    setSelected({ ...selected, [q.id]: option })
    answer.mutate({ questionId: q.id, option })
  }
  const last = index === attempt.questions.length - 1

  return (
    <>
      {q && (
        <div className="mx-auto max-w-xl">
          <div className="flex items-center justify-between text-sm">
            <span className="text-ink-600">Question {index + 1} of {attempt.total}</span>
            {secondsLeft !== null && (
              <span className={cn('font-bold tabular', secondsLeft < 60 ? 'text-bad-600' : 'text-warn-600')} aria-live="polite">
                {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, '0')} left
              </span>
            )}
          </div>
          <ProgressBar className="mt-2" size="sm" tone="forest" value={((index + 1) / attempt.total) * 100} />
          {attempt.proctoring === 'camera' && (
            <div className="mt-3 flex items-center gap-2 text-[12px] text-ink-600">
              <video ref={videoRef} autoPlay muted playsInline className="h-12 w-16 rounded-md bg-ink-900 object-cover" />
              <ShieldCheck className={cn('size-4', active ? 'text-ok-600' : 'text-ink-400')} />{active ? 'Supervised · camera on' : 'Starting camera…'}
            </div>
          )}
          <motion.div key={q.id} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.22, ease: EASE }}>
            <h1 className="mt-6 font-sans text-xl font-bold leading-snug">{q.text}</h1>
            <div className="mt-5 space-y-2.5" role="radiogroup" aria-label="Choose one answer">
              {q.options.map((option, i) => (
                <button key={i} role="radio" aria-checked={selected[q.id] === i} onClick={() => choose(i)}
                  className={cn('flex w-full items-center gap-3 rounded-xl border p-4 text-left text-[15px] transition-colors',
                    selected[q.id] === i ? 'border-forest-700 bg-forest-50 ring-1 ring-forest-700' : 'border-line bg-surface hover:border-forest-700/50')}>
                  <span className={cn('size-5 shrink-0 rounded-full border-2', selected[q.id] === i ? 'border-forest-700 bg-forest-700 shadow-[inset_0_0_0_3px_white]' : 'border-line')} />
                  {option}
                </button>
              ))}
            </div>
          </motion.div>
          <div className="mt-6 flex gap-2">
            {index > 0 && <Button variant="outline" size="lg" onClick={() => setIndex(index - 1)}>Back</Button>}
            <Button size="lg" className="flex-1" disabled={selected[q.id] === undefined} loading={submit.isPending}
              onClick={() => (last ? finish() : setIndex(index + 1))}>{last ? 'Finish' : 'Next'}</Button>
          </div>
          <p className="mt-4 text-center text-[13px] text-ink-600">Need a break? <Link to="/learn?tab=tests" className="font-semibold text-forest-700">Pause</Link> — your answers are saved.</p>
        </div>
      )}
    </>
  )
}

// ---- result ------------------------------------------------------------------------------------
export function ResultPage() {
  const { id } = useParams()
  const { data: r, isLoading, error, refetch } = useAttemptResult(id)
  const appeal = useAppeal()
  const [appealOpen, setAppealOpen] = useState(false)
  const [note, setNote] = useState('')
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!r} skeleton={<SkeletonPage />} onRetry={refetch}>
      {r && (
        <div className="mx-auto max-w-xl space-y-3">
          <p className="text-sm text-ink-600">Your result</p>
          <Panel>
            {r.status === 'under_review' ? (
              <><h1 className="font-serif text-3xl text-white">Being checked</h1><p className="mt-2 text-white/75">{r.message}</p></>
            ) : r.level !== null ? (
              <>
                <motion.h1 initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ ease: EASE, duration: 0.4 }} className="font-serif text-5xl text-white">Level {r.level}</motion.h1>
                <p className="mt-2 text-white/80">{r.level_name}{r.level === 3 && ': role-ready'}</p>
                <p className="mt-3 text-sm text-white/70">Score {r.score} of 100</p>
              </>
            ) : (
              <>
                <h1 className="font-serif text-4xl text-white">{r.passed ? 'You passed' : `${r.score}%`}</h1>
                <p className="mt-2 text-white/75">Score {r.score} of 100{r.pass_mark && ` · pass mark ${r.pass_mark}%`}</p>
              </>
            )}
          </Panel>
          {r.top_percent != null && (
            <Card><p className="text-[13px] text-ink-600">Your rank band</p><b>Top {r.top_percent}% of {r.out_of} people tested</b></Card>
          )}
          {r.required_level != null && r.meets_requirement !== null && (
            <Notice tone={r.meets_requirement ? 'ok' : 'warn'}>
              {r.meets_requirement ? <><Check className="mr-1 inline size-4" />Your role needs Level {r.required_level}. You meet it.</>
                : <>Your role needs Level {r.required_level}. Your pathway will help you get there.</>}
            </Notice>
          )}
          <Notice tone="neutral">{r.message}</Notice>
          {r.certificate_id ? <ButtonLink to="/learn/certificates" size="lg" block><Award className="size-4" />See my certificate</ButtonLink>
            : r.skills_left_to_check > 0 ? <ButtonLink to="/learn?tab=tests" size="lg" block>Next skill</ButtonLink>
              : <ButtonLink to="/path" size="lg" block>See my pathway</ButtonLink>}
          {(r.status === 'invalid' || r.status === 'retest') && (
            <Button variant="outline" block onClick={() => setAppealOpen(true)}>Appeal this decision</Button>
          )}
          <Dialog open={appealOpen} onOpenChange={setAppealOpen} title="Appeal" description="A different reviewer will look at your attempt."
            footer={<Button disabled={note.trim().length < 10} loading={appeal.isPending} onClick={() => appeal.mutate({ attemptId: id!, note }, { onSuccess: () => setAppealOpen(false) })}>Send appeal</Button>}>
            <Field label="What happened?"><Textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          </Dialog>
        </div>
      )}
    </QueryState>
  )
}

// ---- certificates -----------------------------------------------------------------------------
export function CertificatesPage() {
  const { data, isLoading, error, refetch } = useCertificates()
  const share = async (code: string) => {
    const url = `${window.location.origin}/verify/${code}`
    try {
      if (navigator.share) await navigator.share({ title: 'My certificate', url })
      else {
        await navigator.clipboard.writeText(url)
        toast.success('Link copied')
      }
    } catch {
      /* cancelled */
    }
  }
  return (
    <div>
      <PageHeader title="My certificates" subtitle="Download, share or check when each one needs renewing." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data?.length === 0 && <EmptyState icon={<Award className="size-8" />} title="No certificates yet" body="Finish a certification course or a mandatory test to earn one." />}
        <Stagger className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {data?.map((c) => (
            <div key={c.id} className="flex flex-col">
              <div className="flex-1 rounded-card border-2 border-gold-500 bg-linear-to-b from-gold-100/60 to-surface p-6 text-center">
                <p className="text-[11px] font-bold uppercase tracking-[0.25em] text-gold-500">Certificate of completion</p>
                <h2 className="mt-2 text-2xl">{c.title}</h2>
                <p className="mt-1 text-sm text-ink-600">{fmt.date(c.issued_at)}{c.valid_until && ` · valid until ${fmt.date(c.valid_until)}`}</p>
                <div className="mt-4 flex items-center justify-center gap-3">
                  <span className="text-xs text-ink-600">ID {c.code}</span>
                  <StatusPill status={c.status} label={c.status === 'valid' ? '✓ Valid' : undefined} />
                </div>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button onClick={() => api.download(`/certificates/${c.id}/pdf`, undefined, `${c.code}.pdf`)}><Download className="size-4" />Download PDF</Button>
                <Button variant="outline" onClick={() => share(c.code)}><Share2 className="size-4" />Share</Button>
              </div>
            </div>
          ))}
        </Stagger>
        {data && data.length > 0 && <p className="mt-5 text-sm text-ink-600"><CheckCircle2 className="mr-1 inline size-4 text-ok-600" />Renewal reminders come 60, 30 and 7 days before expiry. Anyone can check a certificate with its QR code.</p>}
      </QueryState>
    </div>
  )
}
