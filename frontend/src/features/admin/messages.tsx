/** Message log: every message on every channel. Email and WhatsApp are simulated until a provider is connected. */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Mail, MessageCircle, Play, Search, Smartphone } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { QueryState } from '@/components/SystemStatus'
import { Badge, Button, Card, Input, Notice, PageHeader, SkeletonPage } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { cn, fmt } from '@/lib/utils'

interface Row {
  id: string; created_at: string; person: string; channel: string; to_address: string | null; subject: string; text: string
  status: string; reason: string; kind: string; is_automatic: boolean
}
interface Log { rows: Row[]; counts: Record<string, number>; simulated_channels: string[] }

const CHANNELS = [
  { key: '', label: 'All' },
  { key: 'in_app', label: 'In app', icon: Smartphone },
  { key: 'email', label: 'Email', icon: Mail },
  { key: 'whatsapp', label: 'WhatsApp', icon: MessageCircle },
]
const STATUS_TONE: Record<string, 'ok' | 'info' | 'neutral' | 'warn' | 'bad'> = { sent: 'ok', simulated: 'info', skipped: 'neutral', paused: 'warn', failed: 'bad' }
const STATUS_LABEL: Record<string, string> = { sent: 'Delivered', simulated: 'Simulated', skipped: 'Not sent', paused: 'Paused', failed: 'Failed' }

export function MessageLogPage() {
  const client = useQueryClient()
  const [channel, setChannel] = useState('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['message-log', channel, q],
    queryFn: () => api.get<Log>('/admin/message-log', { channel: channel || undefined, q: q || undefined }),
    refetchInterval: 15_000,
  })
  const runNow = async () => {
    setRunning(true)
    try {
      await api.post('/admin/scheduler/workflows.daily/run')
      toast.success('Daily automations ran. New messages appear below as they are delivered.')
      await client.invalidateQueries({ queryKey: ['message-log'] })
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setRunning(false)
    }
  }
  return (
    <div>
      <PageHeader title="Message log" subtitle="Every reminder, invitation and result, on every channel. Refreshes every 15 seconds."
        actions={<Button variant="outline" loading={running} onClick={runNow}><Play className="size-4" />Run today's automations now</Button>} />
      {data && data.simulated_channels.length > 0 && (
        <Notice className="mb-5">
          {data.simulated_channels.map((c) => (c === 'whatsapp' ? 'WhatsApp' : c === 'email' ? 'Email' : c)).join(' and ')} {data.simulated_channels.length > 1 ? 'are' : 'is'} not connected yet.
          Messages are written here exactly as they would be sent, and nothing leaves the system. In-app messages are delivered for real.
        </Notice>
      )}
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        {CHANNELS.slice(1).map((c) => (
          <Card key={c.key} className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-xl bg-forest-100 text-forest-700">{c.icon && <c.icon className="size-5" />}</span>
            <span><span className="block text-[13px] text-ink-600">{c.label} today</span><b className="font-serif text-2xl tabular">{data?.counts[c.key] ?? 0}</b></span>
          </Card>
        ))}
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {CHANNELS.map((c) => (
          <button key={c.key} onClick={() => setChannel(c.key)}
            className={cn('rounded-full border px-3.5 py-1.5 text-[13px] font-semibold', channel === c.key ? 'border-forest-700 bg-forest-700 text-white' : 'border-line bg-surface hover:border-forest-700')}>
            {c.label}
          </button>
        ))}
        <div className="relative ml-auto w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
          <Input className="pl-9" placeholder="Search person, subject or address" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search messages" />
        </div>
      </div>
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        <Card className="p-0 sm:p-0">
          {data?.rows.length === 0 && <p className="p-8 text-center text-ink-600">No messages yet. Run today's automations, or assign some training.</p>}
          <ul className="divide-y divide-line">
            {data?.rows.map((r) => (
              <li key={r.id}>
                <button onClick={() => setOpen(open === r.id ? null : r.id)} className="grid w-full gap-1 px-4 py-3 text-left hover:bg-canvas sm:grid-cols-[150px_180px_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
                  <span className="text-[13px] text-ink-600 tabular">{fmt.ago(r.created_at)}</span>
                  <span className="min-w-0"><b className="block truncate text-sm">{r.person}</b><span className="block truncate text-[12px] text-ink-600">{CHANNELS.find((c) => c.key === r.channel)?.label} · {r.to_address ?? '—'}</span></span>
                  <span className="min-w-0 truncate text-sm">{r.subject}{r.is_automatic && <span className="ml-2 text-[12px] text-ink-400">automatic</span>}</span>
                  <span><Badge tone={STATUS_TONE[r.status] ?? 'neutral'}>{STATUS_LABEL[r.status] ?? r.status}</Badge></span>
                </button>
                {open === r.id && (
                  <div className="border-t border-line bg-canvas px-4 py-3 text-sm">
                    {r.reason && <p className="mb-2 text-[13px] text-ink-600">{r.reason}</p>}
                    <pre className="whitespace-pre-wrap font-sans text-ink-700">{r.text || r.subject}</pre>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </QueryState>
    </div>
  )
}
