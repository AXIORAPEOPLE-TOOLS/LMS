import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, ShieldAlert } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router'
import { z } from 'zod'
import { BrandMark } from '@/components/SplashScreen'
import { EASE } from '@/lib/motion-tokens'
import { Button, Card, Field, Input, Notice, Skeleton } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useSession } from '@/lib/session'
import { fmt } from '@/lib/utils'

const schema = z.object({
  email: z.string().email('Enter your work email, for example asha@example.com.'),
  password: z.string().min(1, 'Enter your password.'),
})
type FormValues = z.infer<typeof schema>

const DEMO = [
  { email: 'asha@example.com', who: 'Learner (Asha)' },
  { email: 'manager@example.com', who: 'Manager' },
  { email: 'admin@example.com', who: 'Admin' },
  { email: 'meera@example.com', who: 'Knowledge owner' },
]

export function LoginPage() {
  const { t } = useTranslation()
  const { signIn, signedIn } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, setValue, formState } = useForm<FormValues>({ resolver: zodResolver(schema) })
  if (signedIn) return <Navigate to="/" replace />

  const onSubmit = handleSubmit(async (values) => {
    setError(null)
    try {
      await signIn(values.email, values.password)
      navigate((location.state as { from?: string } | null)?.from ?? '/', { replace: true })
    } catch (e) {
      setError(errorMessage(e))
    }
  })

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      <section className="on-dark relative hidden overflow-hidden bg-forest-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3"><BrandMark className="size-10" /><span className="font-serif text-xl font-bold">Learning &amp; Knowledge</span></div>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}>
          <p className="text-[11px] font-bold uppercase tracking-[0.3em] text-gold-500">Learning &amp; Knowledge Suite</p>
          <h1 className="mt-4 max-w-lg font-serif text-5xl font-bold leading-tight text-white">Simple, clear screens for everyone</h1>
          <p className="mt-5 max-w-md text-lg text-white/75">Know your next step, grow your skills, and find any company process in one search.</p>
        </motion.div>
        <p className="text-sm text-white/50">One main button on every screen. Plain words. Built for phones first.</p>
        <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-96 rounded-full border-[40px] border-white/5" />
      </section>

      <section className="flex items-center justify-center px-4 py-10">
        <motion.div className="w-full max-w-sm" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }}>
          <div className="mb-8 flex items-center gap-3 lg:hidden"><BrandMark className="size-9" /><span className="font-serif text-lg font-bold">Learning &amp; Knowledge</span></div>
          <h1 className="text-3xl">{t('login.title')}</h1>
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
          <Card className="mt-8 bg-forest-50">
            <p className="text-sm font-semibold">{t('login.demo')}</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DEMO.map((d) => (
                <button key={d.email} type="button"
                  onClick={() => { setValue('email', d.email); setValue('password', 'Demo@1234') }}
                  className="rounded-lg border border-line bg-surface px-3 py-2 text-left text-[13px] hover:border-forest-700">
                  <b className="block">{d.who}</b><span className="text-ink-600">{d.email}</span>
                </button>
              ))}
            </div>
          </Card>
        </motion.div>
      </section>
    </div>
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
