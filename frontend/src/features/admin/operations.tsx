import { CalendarClock, Download, Power, RotateCcw } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  useDecide, useDecideRun, usePauseAll, useReport, useReportCatalogue, useReviewCase, useReviewQueue, useRunWorkflow, useSaveSetting,
  useScheduleReport, useSetMode, useSettings, useWorkflowPreview, useWorkflowRuns, useWorkflows,
} from '@/api/admin'
import type { ReportResult, Workflow } from '@/api/types'
import { Stagger } from '@/components/motion'
import { EASE } from '@/lib/motion-tokens'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, Card, Dialog, EmptyState, Field, Input, Notice, PageHeader, ProgressBar, SectionTitle, Select, SkeletonPage,
  StatusPill, Textarea,
} from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useSession } from '@/lib/session'
import { cn, fmt } from '@/lib/utils'

// ---- A-07 Workflows -------------------------------------------------------------------------
const MODES = [{ value: 'manual', label: 'Manual' }, { value: 'hybrid', label: 'Hybrid' }, { value: 'auto', label: 'Auto' }] as const

export function WorkflowsPage() {
  const { data, isLoading, error, refetch } = useWorkflows()
  const runs = useWorkflowRuns('pending_approval')
  const setMode = useSetMode()
  const pause = usePauseAll()
  const preview = useWorkflowPreview()
  const run = useRunWorkflow()
  const decide = useDecideRun()
  const [selectedId, setSelectedId] = useState<string>()
  const selected = data?.workflows.find((w) => w.id === selectedId) ?? data?.workflows[0]
  const [confirmRun, setConfirmRun] = useState(false)

  return (
    <>
      <PageHeader title="Workflows" subtitle="Turn ready-made workflows on, choose how much to automate, or run any of them by hand."
        actions={data && (
          <Button variant={data.paused ? 'primary' : 'danger'} onClick={() => pause.mutate(!data.paused)} loading={pause.isPending}>
            <Power className="size-4" />{data.paused ? 'Turn automatic sends back on' : 'Stop all automatic sends'}
          </Button>
        )} />
      {data?.paused && <Notice tone="warn" className="mb-4">All automatic sends are stopped. Automatic workflows wait for your approval instead.</Notice>}
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && selected && (
          <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
            <Stagger className="space-y-2">
              {data.workflows.map((w) => (
                <div key={w.id} onClick={() => setSelectedId(w.id)} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && setSelectedId(w.id)}
                  className={cn('flex cursor-pointer flex-col gap-2 rounded-card border bg-surface p-3 sm:flex-row sm:items-center sm:justify-between',
                    selected.id === w.id ? 'border-2 border-forest-700 bg-forest-50' : 'border-line')}>
                  <b className="text-[15px]">{w.name}</b>
                  <div className="inline-flex rounded-lg bg-canvas p-0.5" onClick={(e) => e.stopPropagation()}>
                    {MODES.map((m) => (
                      <button key={m.value} onClick={() => setMode.mutate({ id: w.id, mode: m.value })}
                        className={cn('rounded-md px-3 py-1 text-[12px] font-bold', w.mode === m.value ? 'bg-forest-700 text-white' : 'text-ink-600')}>{m.label}</button>
                    ))}
                  </div>
                </div>
              ))}
            </Stagger>
            <div className="space-y-4">
              <WorkflowDetail workflow={selected} onPreview={() => preview.mutate(selected.id)} onRun={() => setConfirmRun(true)} />
              {runs.data && runs.data.length > 0 && (
                <Card>
                  <SectionTitle>Waiting for your approval</SectionTitle>
                  <ul className="space-y-3">
                    {runs.data.map((r) => (
                      <li key={r.id} className="rounded-xl border border-line p-3">
                        <b className="text-sm">{data.workflows.find((w) => w.id === r.workflow_id)?.name}</b>
                        <ul className="mt-1 list-disc pl-5 text-[13px] text-ink-700">{r.preview.lines?.map((l) => <li key={l}>{l}</li>)}</ul>
                        <div className="mt-3 flex gap-2">
                          <Button size="sm" onClick={() => decide.mutate({ id: r.id, approve: true })}>Approve and send</Button>
                          <Button size="sm" variant="outline" onClick={() => decide.mutate({ id: r.id, approve: false })}>Cancel</Button>
                        </div>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>
          </div>
        )}
      </QueryState>
      <Dialog open={confirmRun} onOpenChange={setConfirmRun} title={`Run “${selected?.name}” now`} description="This is what will happen:"
        footer={<Button loading={run.isPending} onClick={() => run.mutate(selected!.id, { onSuccess: () => setConfirmRun(false) })}>Run now</Button>}>
        {preview.isPending ? <p className="text-sm text-ink-600">Preparing the preview…</p> : (
          <ul className="list-disc space-y-1 pl-5 text-sm">{preview.data?.lines.map((l) => <li key={l}>{l}</li>)}</ul>
        )}
      </Dialog>
    </>
  )
}

function WorkflowDetail({ workflow, onPreview, onRun }: { workflow: Workflow; onPreview: () => void; onRun: () => void }) {
  const rows = [
    { tag: 'WHEN', tone: 'bg-forest-700', text: workflow.trigger_label },
    { tag: 'IF', tone: 'bg-ink-600', text: workflow.condition_label },
    { tag: 'THEN', tone: 'bg-forest-700', text: workflow.action_labels.join(' · ') },
    { tag: 'APPROVAL', tone: 'bg-gold-500', text: workflow.approval_label },
  ]
  return (
    <Card>
      <div className="flex items-center gap-3"><h2 className="text-2xl">{workflow.name}</h2><Badge>{workflow.mode[0].toUpperCase() + workflow.mode.slice(1)}</Badge></div>
      <div className="mt-4 space-y-2">
        {rows.map((r, i) => (
          <motion.div key={r.tag} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06, ease: EASE }} className="flex gap-2">
            <span className={cn('flex w-24 shrink-0 items-center justify-center rounded-lg py-3 text-[12px] font-bold text-white', r.tone)}>{r.tag}</span>
            <span className="flex flex-1 items-center rounded-lg border border-line bg-canvas px-3 text-sm">{r.text}</span>
          </motion.div>
        ))}
      </div>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        <Button variant="outline" className="flex-1" onClick={() => { onPreview(); onRun() }}>Run now (preview first)</Button>
      </div>
    </Card>
  )
}

// ---- A-08 Reports ---------------------------------------------------------------------------------
export function ReportsPage() {
  const catalogue = useReportCatalogue()
  const [params, setParams] = useSearchParams()
  const reportId = params.get('report') ?? catalogue.data?.find((g) => g.reports.length)?.reports[0]?.id
  const filters = Object.fromEntries([...params.entries()].filter(([k]) => k !== 'report'))
  const report = useReport(reportId, filters)
  const schedule = useScheduleReport()
  const [drill, setDrill] = useState<{ row: string; column: string; rows: Record<string, string>[] } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const exportAs = async (format: string) => {
    setBusy(format)
    try {
      await api.download(`/reports/${reportId}/export`, { ...filters, format })
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const openDrill = async (row: string, column: string) => {
    try {
      const rows = await api.get<Record<string, string>[]>(`/reports/${reportId}/drill`, { ...filters, row, column })
      setDrill({ row, column, rows })
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader title="Reports" subtitle="Pick one, set filters, and download to Excel, CSV or PDF." />
      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        <Card className="p-2 lg:self-start">
          {catalogue.data?.map((g) => (
            <div key={g.group} className="mb-2">
              <p className="px-3 pt-2 text-[11px] font-bold uppercase tracking-wider text-ink-400">{g.group} ({g.reports.length})</p>
              {g.reports.map((r) => (
                <button key={r.id} onClick={() => setParams({ report: r.id })}
                  className={cn('block w-full rounded-lg px-3 py-2 text-left text-sm', r.id === reportId ? 'bg-forest-100 font-semibold text-forest-800' : 'hover:bg-canvas')}>{r.name}</button>
              ))}
            </div>
          ))}
        </Card>
        <div className="min-w-0">
          <QueryState isLoading={report.isLoading} error={report.error} hasData={!!report.data} skeleton={<SkeletonPage />} onRetry={report.refetch}>
            {report.data && (
              <Card>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div><h2 className="text-2xl">{report.data.name}</h2>{report.data.description && <p className="text-sm text-ink-600">{report.data.description}</p>}</div>
                  <div className="flex flex-wrap gap-2">
                    {['xlsx', 'csv', 'pdf'].map((f, i) => (
                      <Button key={f} size="sm" variant={i === 0 ? 'primary' : 'outline'} loading={busy === f} onClick={() => exportAs(f)}>
                        <Download className="size-4" />{f === 'xlsx' ? 'Excel' : f.toUpperCase()}
                      </Button>
                    ))}
                    <Button size="sm" variant="outline" onClick={() => schedule.mutate({ id: reportId!, frequency: 'weekly', format: 'xlsx' })}><CalendarClock className="size-4" />Schedule weekly</Button>
                  </div>
                </div>
                {report.data.filters.includes('period') && (
                  <Select className="mt-4 w-auto" value={filters.period ?? 'quarter'} onChange={(e) => setFilter('period', e.target.value)} aria-label="Period">
                    <option value="week">This week</option><option value="month">This month</option><option value="quarter">This quarter</option><option value="year">This year</option>
                  </Select>
                )}
                <ReportTable report={report.data} onDrill={openDrill} />
                <p className="mt-3 text-[13px] italic text-ink-600">{report.data.columns.some((c) => c.drill) && 'Click any number to see the people behind it. '}Exports include who ran them, when and which filters.</p>
                <Notice className="mt-3">{report.data.scope === 'team' ? 'You see only your own team.' : 'Managers see only their own team.'} Exports with personal data are watermarked and logged.</Notice>
              </Card>
            )}
          </QueryState>
        </div>
      </div>
      <Dialog wide open={!!drill} onOpenChange={() => setDrill(null)} title={drill ? `${drill.row}: ${drill.column.replace('_', ' ')}` : ''}>
        {drill?.rows.length === 0 ? <p className="text-sm text-ink-600">No one here.</p> : (
          <table className="w-full text-sm"><tbody>
            {drill?.rows.map((r, i) => <tr key={i} className="border-b border-line">{Object.values(r).map((v, j) => <td key={j} className="py-2 pr-3">{String(v ?? '–')}</td>)}</tr>)}
          </tbody></table>
        )}
      </Dialog>
    </>
  )
}

function ReportTable({ report, onDrill }: { report: ReportResult; onDrill: (row: string, column: string) => void }) {
  if (report.rows.length === 0) return <EmptyState title="No data for these filters yet" />
  const firstKey = report.columns[0]?.key
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead><tr className="text-left text-[12px] text-ink-600">{report.columns.map((c) => <th key={c.key} className="px-2 py-2 font-semibold">{c.label}</th>)}</tr></thead>
        <tbody>
          {report.rows.slice(0, 300).map((row, i) => (
            <tr key={i} className="border-t border-line odd:bg-canvas/60">
              {report.columns.map((c) => {
                const value = row[c.key]
                if (c.kind === 'percent' && typeof value === 'number') {
                  return <td key={c.key} className="px-2 py-2.5"><span className="flex items-center gap-2"><ProgressBar className="w-24" size="sm" tone={value >= 85 ? 'ok' : 'bad'} value={value} /><b className="tabular">{value}%</b></span></td>
                }
                if (c.drill && typeof value === 'number' && value > 0) {
                  return <td key={c.key} className="px-2 py-2.5"><button className="font-semibold text-forest-700 underline tabular" onClick={() => onDrill(String(row[firstKey]), c.key)}>{value}</button></td>
                }
                return <td key={c.key} className={cn('px-2 py-2.5', c === report.columns[0] && 'font-semibold', c.kind === 'number' && 'tabular')}>{value ?? '–'}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {report.rows.length > 300 && <p className="mt-2 text-[13px] text-ink-600">Showing 300 of {report.rows.length}. Download for everything.</p>}
    </div>
  )
}

// ---- A-09 Proctoring review --------------------------------------------------------------------
export function ProctoringPage() {
  const queue = useReviewQueue()
  const [selected, setSelected] = useState<string>()
  const chosen = selected ?? queue.data?.[0]?.attempt_id
  const kase = useReviewCase(chosen)
  const decide = useDecide()
  const [decision, setDecision] = useState('valid')
  const [note, setNote] = useState('')
  const [images, setImages] = useState<Record<string, string>>({})
  const loadImage = async (flagId: string) => {
    try {
      const response = await fetch(`/api/proctoring/events/${flagId}/image`, { headers: { Authorization: `Bearer ${localStorage.getItem('lms.token')}` } })
      if (!response.ok) return
      const url = URL.createObjectURL(await response.blob())
      setImages((m) => ({ ...m, [flagId]: url }))
    } catch {
      /* ignore */
    }
  }
  const flagLabel: Record<string, string> = { second_face: 'Second face seen', tab_switch: 'Tab switched', no_face: 'No face seen', phone_seen: 'Phone seen', camera_off: 'Camera turned off', noise: 'Noise' }
  return (
    <>
      <PageHeader title="Proctoring review" subtitle="The system collects flags. A trained reviewer decides. Nobody is failed automatically." />
      <QueryState isLoading={queue.isLoading} error={queue.error} hasData={!!queue.data} skeleton={<SkeletonPage />} onRetry={queue.refetch}>
        {queue.data?.length === 0 ? <EmptyState title="Nothing to review" body="Flagged attempts will appear here." /> : (
          <div className="grid gap-5 lg:grid-cols-[280px_1fr_300px]">
            <Card className="p-2">
              <p className="px-2 py-1 font-semibold">Needs review ({queue.data?.length})</p>
              {queue.data?.map((q) => (
                <button key={q.attempt_id} onClick={() => { setSelected(q.attempt_id); setNote('') }}
                  className={cn('mt-1 flex w-full items-center justify-between rounded-xl border p-3 text-left', chosen === q.attempt_id ? 'border-forest-700 bg-forest-50' : 'border-line')}>
                  <span><b className="block text-sm">{q.test_title}</b><span className="text-[12px] text-ink-600">{fmt.plural(q.flags, 'flag')}{q.is_appeal && ' · appeal'}</span></span>
                  <StatusPill status={q.severity} />
                </button>
              ))}
            </Card>
            {kase.data && (
              <Card>
                <h2 className="text-2xl">{kase.data.test_title}</h2>
                <p className="text-sm text-ink-600">Employee {kase.data.employee_code ?? '–'} · {kase.data.question_count} questions · score {kase.data.score}% · {kase.data.minutes} minutes</p>
                {kase.data.appeal_note && <Notice tone="info" className="mt-3"><b>Appeal:</b> {kase.data.appeal_note}</Notice>}
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {kase.data.flags.map((f) => (
                    <div key={f.id} className="overflow-hidden rounded-xl border border-line">
                      <div className="flex aspect-video items-center justify-center bg-[#d3d7de] text-sm text-ink-600">
                        {images[f.id] ? <img src={images[f.id]} alt="Snapshot" className="h-full w-full object-cover" />
                          : f.has_image ? <Button size="sm" variant="ghost" onClick={() => loadImage(f.id)}>Show picture</Button> : 'No picture'}
                      </div>
                      <p className="bg-bad-50 px-3 py-2 text-sm font-semibold text-bad-600">{flagLabel[f.kind] ?? f.kind}{f.count > 1 && ` (${f.count}x)`} · {Math.floor(f.at_seconds / 60)}:{String(f.at_seconds % 60).padStart(2, '0')}</p>
                    </div>
                  ))}
                </div>
                <b className="mt-5 block text-sm">Timeline</b>
                <div className="relative mt-3 h-2 rounded-full bg-[#e3e7ea]">
                  {kase.data.flags.map((f) => (
                    <span key={f.id} title={flagLabel[f.kind]} className={cn('absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full', f.severity === 'high' ? 'bg-bad-600' : 'bg-warn-600')}
                      style={{ left: `${Math.min(100, (f.at_seconds / Math.max(kase.data!.duration_seconds, 1)) * 100)}%` }} />
                  ))}
                </div>
                <div className="mt-1 flex justify-between text-[11px] text-ink-400"><span>Start</span><span>End</span></div>
                <Notice className="mt-5">Pictures are deleted 30 days after the case closes. Every view of this evidence is logged.</Notice>
              </Card>
            )}
            {kase.data && (
              <Card className="space-y-2 lg:self-start">
                <b>Your decision</b>
                {[['valid', 'Attempt is valid'], ['retest', 'Needs a retest'], ['invalid', 'Not valid']].map(([v, label]) => (
                  <Button key={v} block variant={decision === v ? 'primary' : 'outline'} onClick={() => setDecision(v)}>{label}</Button>
                ))}
                <Field label="Add a note (required)"><Textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
                <Button block disabled={note.trim().length < 3} loading={decide.isPending}
                  onClick={() => decide.mutate({ id: chosen!, decision, note }, { onSuccess: () => { setSelected(undefined); setNote('') } })}>Save decision</Button>
                <p className="text-[13px] italic text-ink-600">The learner can appeal; a different reviewer decides.</p>
              </Card>
            )}
          </div>
        )}
      </QueryState>
    </>
  )
}

// ---- Settings --------------------------------------------------------------------------------------
export function SettingsPage() {
  const { data, isLoading, error, refetch } = useSettings()
  const save = useSaveSetting()
  const { has } = useSession()
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  if (!has('admin')) return null
  return (
    <>
      <PageHeader title="Settings" subtitle="Every number the product uses lives here. Change it without a release." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        <Card className="p-0">
          <ul className="divide-y divide-line">
            {data?.map((s) => (
              <li key={s.key} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <span className="min-w-0"><b className="block text-sm">{s.description}</b><code className="text-[12px] text-ink-400">{s.key}</code></span>
                {editing === s.key ? (
                  <span className="flex gap-2">
                    <Input className="w-64 font-mono text-sm" value={draft} onChange={(e) => setDraft(e.target.value)} />
                    <Button size="sm" onClick={() => {
                      try {
                        save.mutate({ key: s.key, value: JSON.parse(draft) }, { onSuccess: () => setEditing(null) })
                      } catch {
                        toast.error('That is not a valid value. Use the same shape as before.')
                      }
                    }}>Save</Button>
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <code className="max-w-xs truncate rounded bg-canvas px-2 py-1 text-[12px]">{JSON.stringify(s.value)}</code>
                    {s.is_overridden && <Badge tone="info">Changed</Badge>}
                    <Button size="sm" variant="ghost" onClick={() => { setEditing(s.key); setDraft(JSON.stringify(s.value)) }}>Edit</Button>
                    {s.is_overridden && <Button size="sm" variant="ghost" aria-label="Back to default" onClick={() => save.mutate({ key: s.key, value: s.default })}><RotateCcw className="size-4" /></Button>}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </QueryState>
    </>
  )
}

