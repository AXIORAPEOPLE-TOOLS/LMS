import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { BookOpenCheck, CheckCircle2, ClipboardCheck, ShieldAlert, UserRound } from 'lucide-react'
import { motion } from 'motion/react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router'
import { z } from 'zod'
import { BrandMark } from '@/components/SplashScreen'
import { EASE } from '@/lib/motion-tokens'
import { Button, Card, Field, Input, Notice, Select, Skeleton } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useSession } from '@/lib/session'
import { fmt } from '@/lib/utils'

const schema = z.object({
  email: z.string().email('Enter your work email, for example asha@example.com.'),
  password: z.string().min(1, 'Enter your password.'),
})
type FormValues = z.infer<typeof schema>

const DEMO = [
  { email: 'asha@example.com', who: 'Employee' },
  { email: 'manager@example.com', who: 'Manager' },
  { email: 'admin@example.com', who: 'HR admin' },
  { email: 'meera@example.com', who: 'Records owner' },
]

const STEPS = [
  { icon: UserRound, title: 'Pick your job role', body: 'The skills your role needs appear on your profile.' },
  { icon: BookOpenCheck, title: 'Learn what HR assigns', body: 'Short courses. Your place is saved.' },
  { icon: ClipboardCheck, title: 'Take the test, see your result', body: 'Your progress is recorded for you and HR.' },
]

/** Shared layout for sign-in and sign-up: a short "how it works" on the left, the form on the right. */
function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-10 sm:px-8">
      <div className="grid w-full max-w-5xl items-center gap-10 lg:grid-cols-[1fr_440px] lg:gap-16">
        <motion.section className="hidden lg:block" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: EASE }}>
          <div className="flex items-center gap-3"><BrandMark className="size-10" /><span className="font-serif text-xl font-bold">Learning &amp; Knowledge</span></div>
          <h1 className="mt-10 max-w-md font-serif text-[44px] font-bold leading-[1.1]">Learn what your role needs.</h1>
          <p className="mt-4 max-w-md text-lg text-ink-600">One place for your training, your tests and your company's know-how.</p>
          <ol className="mt-10 space-y-3">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex max-w-md items-start gap-4 rounded-2xl border border-line bg-surface/80 p-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-forest-100 text-forest-700"><step.icon className="size-5" /></span>
                <span><b className="block">{i + 1}. {step.title}</b><span className="text-sm text-ink-600">{step.body}</span></span>
              </li>
            ))}
          </ol>
        </motion.section>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }}>
          <div className="mb-6 flex items-center justify-center gap-3 lg:hidden"><BrandMark className="size-9" /><span className="font-serif text-lg font-bold">Learning &amp; Knowledge</span></div>
          <div className="rounded-3xl border border-line bg-surface p-6 shadow-[0_12px_40px_-20px_rgba(31,92,78,0.35)] sm:p-9">{children}</div>
        </motion.div>
      </div>
    </div>
  )
}

export function LoginPage() {
  const { t } = useTranslation()
  const { signIn, signedIn } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, setValue, formState } = useForm<FormValues>({ resolver: zodResolver(schema) })
  if (signedIn) return <Navigate to="/home" replace />

  const onSubmit = handleSubmit(async (values) => {
    setError(null)
    try {
      await signIn(values.email, values.password)
      navigate((location.state as { from?: string } | null)?.from ?? '/home', { replace: true })
    } catch (e) {
      setError(errorMessage(e))
    }
  })

  return (
    <AuthLayout>
      <h1 className="text-[28px]">{t('login.title')}</h1>
      <p className="mt-1 text-ink-600">{t('login.subtitle')}</p>
      <form className="mt-7 space-y-4" onSubmit={onSubmit} noValidate>
        <Field label={t('login.email')} htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="username" inputMode="email" {...register('email')} />
        </Field>
        <Field label={t('login.password')} htmlFor="password" error={formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" {...register('password')} />
        </Field>
        {error && <Notice tone="bad">{error}</Notice>}
        <Button type="submit" size="lg" block loading={formState.isSubmitting}>{t('login.submit')}</Button>
      </form>
      <p className="mt-5 text-center text-sm text-ink-600">New here? <Link to="/signup" className="font-semibold text-forest-700 underline underline-offset-2">Create your account</Link></p>
      <div className="mt-7 border-t border-line pt-5">
        <p className="text-[13px] font-semibold text-ink-600">{t('login.demo')}</p>
        <div className="mt-2.5 flex flex-wrap gap-2">
          {DEMO.map((d) => (
            <button key={d.email} type="button" title={d.email}
              onClick={() => { setValue('email', d.email); setValue('password', 'Demo@1234') }}
              className="rounded-full border border-line bg-canvas px-3.5 py-1.5 text-[13px] font-semibold text-ink-700 transition-colors hover:border-forest-700 hover:text-forest-800">
              {d.who}
            </button>
          ))}
        </div>
      </div>
    </AuthLayout>
  )
}

interface SignupOptions { allowed: boolean; email_domains: string[]; roles: { id: string; name: string; group: string }[]; departments: { id: string; name: string }[] }

/** Employee sign-up: name, work email, password and job role. The role brings its skills. */
export function SignupPage() {
  const { signInWithToken, signedIn } = useSession()
  const navigate = useNavigate()
  const options = useQuery({ queryKey: ['signup-options'], queryFn: () => api.get<SignupOptions>('/auth/signup-options') })
  const [form, setForm] = useState({ full_name: '', email: '', password: '', job_role_id: '', department_id: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (signedIn) return <Navigate to="/home" replace />
  const groups = Object.entries((options.data?.roles ?? []).reduce<Record<string, { id: string; name: string }[]>>((acc, r) => {
    (acc[r.group || 'Other'] ??= []).push(r)
    return acc
  }, {}))
  const ready = form.full_name.trim().length > 1 && form.email.includes('@') && form.password.length >= 8 && !!form.job_role_id
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const { access_token } = await api.post<{ access_token: string }>('/auth/signup', { ...form, department_id: form.department_id || null })
      signInWithToken(access_token)
      navigate('/me/profile', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthLayout>
          <h1 className="text-[28px]">Create your account</h1>
          <p className="mt-1 text-ink-600">Pick your job role. We add the skills it needs to your profile.</p>
          {options.data && !options.data.allowed ? (
            <Notice tone="warn" className="mt-6">Sign-up is turned off. Ask HR to add you.</Notice>
          ) : (
            <form className="mt-6 space-y-4" onSubmit={submit} noValidate>
              <Field label="Full name" htmlFor="full_name"><Input id="full_name" autoComplete="name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
              <Field label="Work email" htmlFor="su_email" hint={options.data?.email_domains.length ? `Use your ${options.data.email_domains.join(' or ')} email.` : undefined}>
                <Input id="su_email" type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </Field>
              <Field label="Password" htmlFor="su_password" hint="At least 8 characters.">
                <Input id="su_password" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </Field>
              <Field label="Job role" htmlFor="job_role">
                <Select id="job_role" value={form.job_role_id} onChange={(e) => setForm({ ...form, job_role_id: e.target.value })}>
                  <option value="">Choose your job role</option>
                  {groups.map(([group, roles]) => (
                    <optgroup key={group} label={group}>{roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</optgroup>
                  ))}
                </Select>
              </Field>
              <Field label="Department (optional)" htmlFor="department">
                <Select id="department" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
                  <option value="">Choose your department</option>
                  {options.data?.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Select>
              </Field>
              {error && <Notice tone="bad">{error}</Notice>}
              <Button type="submit" size="lg" block loading={busy} disabled={!ready}>Create account</Button>
            </form>
          )}
          <p className="mt-6 text-center text-sm text-ink-600">Already have an account? <Link to="/login" className="font-semibold text-forest-700 underline">Sign in</Link></p>
    </AuthLayout>
  )
}

interface Verification { code: string; holder: string; title: string; issued_on: string; valid_until: string | null; status: 'valid' | 'expired' | 'revoked' }

/** Public page behind the certificate QR code. */
export function VerifyPage() {
  const { code } = useParams()
  const { data, isLoading, error } = useQuery({ queryKey: ['verify', code], queryFn: () => api.get<Verification>(`/certificates/verify/${code}`), retry: false })
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4">
      <Card className="w-full max-w-md border-gold-500 p-8 text-center">
        <p className="text-[11px] font-bold uppercase tracking-[0.25em] text-gold-500">Certificate check</p>
        {isLoading && <Skeleton className="mx-auto mt-6 h-24 w-3/4" />}
        {error && (
          <div className="mt-6"><ShieldAlert className="mx-auto size-10 text-bad-600" /><p className="mt-3 font-semibold">No certificate has this ID.</p><p className="text-sm text-ink-600">{code}</p></div>
        )}
        {data && (
          <div className="mt-5">
            {data.status === 'valid' ? <CheckCircle2 className="mx-auto size-12 text-ok-600" /> : <ShieldAlert className="mx-auto size-12 text-bad-600" />}
            <h1 className="mt-3 text-3xl">{data.holder}</h1>
            <p className="mt-1 text-ink-600">{data.title}</p>
            <p className="mt-4 text-sm">Issued {fmt.date(data.issued_on)}{data.valid_until && ` · valid until ${fmt.date(data.valid_until)}`}</p>
            <p className={`mt-4 inline-block rounded-full px-4 py-1 text-sm font-bold ${data.status === 'valid' ? 'bg-ok-50 text-ok-600' : 'bg-bad-50 text-bad-600'}`}>
              {data.status === 'valid' ? '✓ Valid' : data.status === 'expired' ? 'Expired' : 'Revoked'}
            </p>
            <p className="mt-4 text-xs text-ink-400">Certificate ID {data.code}</p>
          </div>
        )}
      </Card>
    </div>
  )
}
