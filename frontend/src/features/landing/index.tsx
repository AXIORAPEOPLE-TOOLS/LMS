/** Public landing page at "/". Signed-in people get a direct way to their home. */
import {
  ArrowRight, BookOpenCheck, BookOpenText, ClipboardCheck, FileSearch, ListChecks, ShieldCheck, Target, UserRound, Users,
} from 'lucide-react'
import { motion } from 'motion/react'
import type { ComponentType, ReactNode } from 'react'
import { Link } from 'react-router'
import { BrandMark } from '@/components/SplashScreen'
import { ButtonLink } from '@/components/ui'
import { EASE } from '@/lib/motion-tokens'
import { useSession } from '@/lib/session'

type Icon = ComponentType<{ className?: string }>

const EMPLOYEE_STEPS: { icon: Icon; title: string; body: string }[] = [
  { icon: UserRound, title: 'Pick your job role', body: 'The skills your role needs appear on your profile straight away.' },
  { icon: BookOpenCheck, title: 'Learn what HR assigns', body: 'Short courses and lessons. Stop any time, carry on where you left off.' },
  { icon: ClipboardCheck, title: 'Take the test, see your result', body: 'Your score, what you got right and your progress, recorded for you.' },
]

const HR_FEATURES: { icon: Icon; title: string; body: string }[] = [
  { icon: Target, title: 'Assign by skill or by name', body: 'Pick a skill and everyone whose role needs it is found for you. Add anyone else by name. Check the list, then send.' },
  { icon: ListChecks, title: 'See who is where', body: 'Not started, learning, course done, passed, failed, overdue. Per course, per person, ready to download.' },
  { icon: Users, title: 'Only the right people are told', body: 'Nobody outside the list gets a message. Repeating an assignment never creates doubles.' },
]

const HUB_FEATURES: { icon: Icon; title: string; body: string }[] = [
  { icon: BookOpenText, title: 'One home for company know-how', body: 'SOPs, policies, guides and templates, each with an owner and a category.' },
  { icon: FileSearch, title: 'Find it in one search', body: 'Search by words, type or department. People only see what they are allowed to.' },
  { icon: ShieldCheck, title: 'Always the current version', body: 'Every change keeps its history. Owners get a reminder when a review is due.' },
]

function FeatureGrid({ items }: { items: { icon: Icon; title: string; body: string }[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {items.map((f, i) => (
        <motion.div key={f.title} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.4, delay: i * 0.06, ease: EASE }} className="rounded-2xl border border-line bg-surface p-6">
          <span className="flex size-11 items-center justify-center rounded-xl bg-forest-100 text-forest-700"><f.icon className="size-5" /></span>
          <h3 className="mt-4 font-sans text-lg font-bold">{f.title}</h3>
          <p className="mt-1.5 text-[15px] leading-relaxed text-ink-600">{f.body}</p>
        </motion.div>
      ))}
    </div>
  )
}

function Section({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:px-8 sm:py-20">
      <p className="text-[12px] font-bold uppercase tracking-[0.2em] text-gold-600">{eyebrow}</p>
      <h2 className="mt-2 max-w-2xl text-3xl sm:text-4xl">{title}</h2>
      <div className="mt-8">{children}</div>
    </section>
  )
}

export function LandingPage() {
  const { signedIn, me } = useSession()
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5"><BrandMark className="size-8" /><span className="font-serif text-lg font-bold">Learning &amp; Knowledge</span></Link>
          <nav className="ml-auto flex items-center gap-2">
            {signedIn ? (
              <ButtonLink to="/home">Go to my home <ArrowRight className="size-4" /></ButtonLink>
            ) : (
              <>
                <Link to="/login" className="rounded-full px-4 py-2 text-sm font-semibold text-ink-700 hover:bg-forest-100">Sign in</Link>
                <ButtonLink to="/signup" className="hidden sm:inline-flex">Create account</ButtonLink>
              </>
            )}
          </nav>
        </div>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-10 pt-14 sm:px-8 sm:pt-20 lg:grid-cols-[1.1fr_1fr]">
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}>
          <h1 className="font-serif text-[40px] font-bold leading-[1.08] sm:text-[56px]">Learn what your role needs. Find what your company knows.</h1>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-600">
            Employees get the skills for their job, learn what HR assigns and see their results. HR sends training to exactly the right people and sees who is where.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {signedIn ? (
              <ButtonLink to="/home" size="lg">{me ? `Continue, ${me.full_name.split(' ')[0]}` : 'Go to my home'} <ArrowRight className="size-4" /></ButtonLink>
            ) : (
              <>
                <ButtonLink to="/signup" size="lg">Create your account <ArrowRight className="size-4" /></ButtonLink>
                <ButtonLink to="/login" size="lg" variant="outline">Sign in</ButtonLink>
              </>
            )}
          </div>
        </motion.div>

        {/* A calm preview of the employee home: next step + assigned training. */}
        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1, ease: EASE }}
          className="rounded-3xl border border-line bg-surface p-5 shadow-[0_24px_60px_-30px_rgba(31,92,78,0.45)] sm:p-6" aria-hidden>
          <div className="rounded-2xl bg-linear-to-br from-forest-700 via-forest-600 to-[#5aa58a] p-5 text-white">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-gold-100">Do this next</p>
            <p className="mt-2 text-xl font-bold">Take the course: Data privacy basics</p>
            <p className="mt-1 text-sm text-white/80">Assigned by HR · due 20 Oct</p>
            <span className="mt-4 inline-flex rounded-xl bg-gold-500 px-4 py-2 text-sm font-bold">Continue course</span>
          </div>
          <div className="mt-4 space-y-2.5">
            {[['Cybersecurity awareness', 'Course done · test passed', 'bg-ok-50 text-ok-600'], ['Customer communication', 'Lesson 2 of 4', 'bg-warn-50 text-warn-600'], ['POSH awareness', 'Assigned · not started', 'bg-canvas text-ink-600']].map(([title, state, tone]) => (
              <div key={title} className="flex items-center justify-between gap-3 rounded-xl border border-line px-4 py-3">
                <b className="text-sm">{title}</b>
                <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${tone}`}>{state}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </section>

      <Section eyebrow="For employees" title="Three steps, nothing else to figure out">
        <ol className="grid gap-4 md:grid-cols-3">
          {EMPLOYEE_STEPS.map((s, i) => (
            <li key={s.title} className="rounded-2xl border border-line bg-surface p-6">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-full bg-forest-700 text-sm font-bold text-white">{i + 1}</span>
                <s.icon className="size-5 text-forest-700" />
              </div>
              <h3 className="mt-4 font-sans text-lg font-bold">{s.title}</h3>
              <p className="mt-1.5 text-[15px] leading-relaxed text-ink-600">{s.body}</p>
            </li>
          ))}
        </ol>
      </Section>

      <div className="border-y border-line bg-surface/60">
        <Section eyebrow="For HR" title="Send training to exactly the people who need it">
          <FeatureGrid items={HR_FEATURES} />
        </Section>
      </div>

      <Section eyebrow="Knowledge Hub" title="Company knowledge, organised and current">
        <FeatureGrid items={HUB_FEATURES} />
      </Section>

      {!signedIn && (
        <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-8">
          <div className="flex flex-col items-start justify-between gap-6 rounded-3xl bg-linear-to-br from-forest-700 via-forest-600 to-[#5aa58a] p-8 text-white sm:flex-row sm:items-center sm:p-10">
            <div>
              <h2 className="text-3xl text-white">Ready to start?</h2>
              <p className="mt-2 text-white/85">Create your account and pick your job role. It takes a minute.</p>
            </div>
            <ButtonLink to="/signup" variant="gold" size="lg">Create your account <ArrowRight className="size-4" /></ButtonLink>
          </div>
        </section>
      )}

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-ink-600 sm:px-8">
          <span className="flex items-center gap-2"><BrandMark className="size-6" />Learning &amp; Knowledge</span>
          <span>Plain words. One clear next step. Works on phones.</span>
        </div>
      </footer>
    </div>
  )
}
