import { Plus, Search, Star } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useAsk, useKAction, useKBulk, useKHome, useKMyItems, useKRevisionDecision, useKSearch, useLibrary } from '@/api/knowledge'
import { usePeople } from '@/api/admin'
import type { KItem, KMyItems } from '@/api/types'
import { Stagger } from '@/components/motion'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, ButtonLink, Card, Dialog, EmptyState, Field, Input, Notice, PageHeader, SectionTitle, Select, SkeletonPage, Stat, StatusPill, Textarea,
} from '@/components/ui'
import { useSession } from '@/lib/session'
import { STATUS_LABEL, cn, fmt } from '@/lib/utils'

export function KStatus({ status }: { status: string }) {
  return <StatusPill status={status} label={STATUS_LABEL[status]} />
}

// ---- K-01 Home ------------------------------------------------------------------------------
export function KnowledgeHomePage() {
  const { data, isLoading, error, refetch } = useKHome()
  const [q, setQ] = useState('')
  const [submitted, setSubmitted] = useState('')
  const search = useKSearch(submitted)
  const ask = useAsk()
  const navigate = useNavigate()
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="min-w-0 space-y-6">
            <form className="flex flex-col gap-2 rounded-2xl border-2 border-forest-700 bg-surface p-2 sm:flex-row"
              onSubmit={(e) => { e.preventDefault(); setSubmitted(q); ask.reset() }}>
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-ink-400" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search or ask: how do I process a refund?" aria-label="Search or ask"
                  className="h-12 w-full rounded-xl bg-transparent pl-11 pr-3 text-[16px] outline-none" />
              </div>
              <div className="flex gap-2">
                <Button type="submit" variant="outline" className="flex-1 sm:flex-none" disabled={q.trim().length < 2}>Search</Button>
                <Button type="button" className="flex-1 sm:flex-none" disabled={q.trim().length < 3} loading={ask.isPending}
                  onClick={() => { setSubmitted(''); ask.mutate(q) }}>Ask</Button>
              </div>
            </form>

            {ask.data && (
              <Card className="border-forest-700/40 bg-forest-50">
                <p className="text-[12px] font-bold uppercase tracking-wider text-forest-700">Answer from the Knowledge Hub</p>
                <p className="mt-2 leading-relaxed">{ask.data.answer}</p>
                {ask.data.sources.length > 0 && (
                  <p className="mt-3 text-sm">Sources: {ask.data.sources.map((s, i) => <Link key={s.id} to={`/knowledge/items/${s.id}`} className="font-semibold text-forest-700 underline">{i ? ', ' : ''}{s.title}</Link>)}</p>
                )}
                <p className="mt-2 text-[12px] text-ink-600">Answers use only verified, up-to-date items. Always check the source.</p>
              </Card>
            )}
            {submitted && (
              <Card>
                <SectionTitle>Results for “{submitted}”</SectionTitle>
                {search.isLoading && <p className="text-sm text-ink-600">Searching…</p>}
                {search.data?.length === 0 && <p className="text-sm text-ink-600">Nothing found. Try other words, or ask the owner of the topic.</p>}
                <ul className="divide-y divide-line">
                  {search.data?.map((h) => (
                    <li key={h.item.id}><Link to={`/knowledge/items/${h.item.id}`} className="block py-3 hover:text-forest-700">
                      <span className="flex items-center gap-2"><b>{h.item.title}</b><Badge tone="neutral">{h.item.kind_label}</Badge><KStatus status={h.item.status} /></span>
                      <span className="mt-1 block text-sm text-ink-600">{h.snippet}</span></Link></li>
                  ))}
                </ul>
              </Card>
            )}

            <section>
              <p className="mb-2 text-sm font-semibold text-ink-600">Find by type</p>
              <div className="flex flex-wrap gap-2">
                {data.types.map((t) => (
                  <Link key={t.kind} to={`/knowledge/library?kind=${t.kind}`} className="rounded-full bg-forest-100 px-4 py-1.5 text-sm font-semibold text-forest-800 hover:bg-forest-200">{t.label}s <span className="text-forest-700/60">{t.count}</span></Link>
                ))}
              </div>
            </section>
            <section>
              <SectionTitle action={<ButtonLink to="/knowledge/add" size="sm"><Plus className="size-4" />Add knowledge</ButtonLink>}>Spaces</SectionTitle>
              <Stagger className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {data.spaces.map((s) => (
                  <Link key={s.id} to={`/knowledge/library?category_id=${s.id}`} className="block rounded-card border border-line bg-surface p-4 hover:border-forest-700">
                    <b>{s.name}</b><p className="text-[13px] text-ink-600">{fmt.plural(s.item_count, 'item')}</p>
                  </Link>
                ))}
              </Stagger>
            </section>
          </div>
          <aside className="min-w-0 space-y-5 lg:sticky lg:top-24 lg:self-start">
            <MyItemsCard mine={data.my_items} onOpen={() => navigate('/knowledge/my-items')} />
            <Card>
              <SectionTitle>Must know (critical)</SectionTitle>
              <ul className="scroll-panel max-h-72 space-y-2.5 pr-1">{data.critical.map((i) => (
                <li key={i.id}><Link to={`/knowledge/items/${i.id}`} className="flex items-center gap-2 text-sm hover:text-forest-700"><Star className="size-4 shrink-0 fill-gold-500 text-gold-500" />{i.title}</Link></li>
              ))}</ul>
            </Card>
            <Card>
              <SectionTitle>Recently verified</SectionTitle>
              <ul className="scroll-panel max-h-72 space-y-2.5 pr-1">{data.recently_verified.map((i) => (
                <li key={i.id} className="flex items-center justify-between gap-2"><Link to={`/knowledge/items/${i.id}`} className="truncate text-sm hover:text-forest-700">{i.title}</Link><Badge tone="ok">Verified</Badge></li>
              ))}</ul>
            </Card>
          </aside>
        </div>
      )}
    </QueryState>
  )
}

function MyItemsCard({ mine, onOpen }: { mine: KMyItems; onOpen: () => void }) {
  const items = mine.items.filter((i) => i.reason === 'overdue' || i.reason === 'due_soon').slice(0, 4)
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl">My items</h2>
        <span className="flex gap-1.5">{mine.overdue > 0 && <Badge tone="bad">{mine.overdue} overdue</Badge>}{mine.due_soon > 0 && <Badge tone="warn">{mine.due_soon} due soon</Badge>}</span>
      </div>
      {items.length === 0 ? <p className="mt-3 text-sm text-ink-600">Nothing needs you right now.</p> : (
        <ul className="mt-4 space-y-4">{items.map((m) => <QuickVerify key={m.item.id} item={m.item} detail={m.detail} />)}</ul>
      )}
      <Button size="lg" block className="mt-5" onClick={onOpen}>Open My items</Button>
    </Card>
  )
}

function QuickVerify({ item, detail }: { item: KItem; detail: string }) {
  const act = useKAction(item.id)
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="min-w-0"><Link to={`/knowledge/items/${item.id}`} className="block truncate font-semibold hover:text-forest-700">{item.title}</Link>
        <span className={cn('text-[13px]', item.status === 'overdue' ? 'text-bad-600' : 'text-ink-600')}>{detail}</span></span>
      <Button size="sm" variant="outline" loading={act.isPending} onClick={() => act.mutate({ action: 'verify' })}>Still correct</Button>
    </li>
  )
}

// ---- K-07 Library -------------------------------------------------------------------------------
export function LibraryPage() {
  const [params, setParams] = useSearchParams()
  const filters = Object.fromEntries(params.entries())
  const { data, isLoading, error, refetch } = useLibrary(filters)
  const { has } = useSession()
  const canBulk = has('knowledge_admin', 'admin', 'function_head')
  const [selected, setSelected] = useState<string[]>([])
  const [bulk, setBulk] = useState<null | 'change_owner' | 'set_review_date'>(null)
  const [value, setValue] = useState('')
  const run = useKBulk()
  const users = usePeople()
  const set = (key: string, v?: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(key, v)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  return (
    <>
      <PageHeader title="Library" subtitle="Every item you may see, with owner, version, status and next review."
        actions={<ButtonLink to="/knowledge/add"><Plus className="size-4" />Add knowledge</ButtonLink>} />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && (
          <div className="grid gap-5 lg:grid-cols-[250px_1fr]">
            <Card className="p-2 lg:self-start">
              <p className="px-3 py-2 font-semibold">Categories</p>
              <button onClick={() => set('category_id')} className={cn('flex w-full justify-between rounded-lg px-3 py-2 text-sm', !filters.category_id ? 'bg-forest-100 font-semibold' : 'hover:bg-canvas')}>
                <span>All knowledge</span><span className="text-ink-600">{data.total}</span>
              </button>
              {data.categories.map((c) => (
                <button key={c.id} onClick={() => set('category_id', c.id)}
                  className={cn('flex w-full justify-between rounded-lg px-3 py-2 text-left text-sm', filters.category_id === c.id ? 'bg-forest-100 font-semibold' : 'hover:bg-canvas', c.parent_id ? 'pl-7 text-ink-600' : 'font-semibold')}>
                  <span className="truncate">{c.name}</span><span className="text-ink-600">{c.item_count}</span>
                </button>
              ))}
            </Card>
            <div className="min-w-0">
              <div className="flex flex-wrap gap-2">
                <div className="relative min-w-56 flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
                  <Input className="pl-9" placeholder="Search in the Library" defaultValue={filters.q} onChange={(e) => set('q', e.target.value || undefined)} aria-label="Search in the Library" />
                </div>
                <Select className="w-auto" value={filters.status ?? ''} onChange={(e) => set('status', e.target.value || undefined)} aria-label="Status">
                  <option value="">Status: any</option><option value="overdue">Overdue</option><option value="due_soon">Due soon</option><option value="verified">Verified</option><option value="in_review">In review</option><option value="draft">Draft</option>
                </Select>
                <Select className="w-auto" value={filters.critical ?? ''} onChange={(e) => set('critical', e.target.value || undefined)} aria-label="Critical">
                  <option value="">Critical: any</option><option value="true">Critical only</option>
                </Select>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button onClick={() => set('kind')} className={cn('rounded-full border px-3 py-1 text-sm', !filters.kind ? 'border-forest-700 bg-forest-50 font-semibold' : 'border-line')}>All {data.total}</button>
                {data.kinds.map((k) => (
                  <button key={k.kind} onClick={() => set('kind', k.kind)} className={cn('rounded-full border px-3 py-1 text-sm', filters.kind === k.kind ? 'border-forest-700 bg-forest-50 font-semibold' : 'border-line bg-surface')}>{k.label} {k.count}</button>
                ))}
              </div>
              {data.items.length === 0 ? <div className="mt-4"><EmptyState title="Nothing matches" body="Try fewer filters." /></div> : (
                <Card className="mt-4 overflow-x-auto p-0">
                  <table className="w-full min-w-180 text-sm">
                    <thead><tr className="text-left text-[12px] text-ink-600">
                      {canBulk && <th className="w-10" />}<th className="px-3 py-2.5">Name</th><th>Kind</th><th>Category</th><th>Owner</th><th>Ver.</th><th>Status</th><th>Next review</th>
                    </tr></thead>
                    <tbody>
                      {data.items.map((i) => (
                        <tr key={i.id} className="border-t border-line hover:bg-canvas">
                          {canBulk && <td className="pl-3"><input type="checkbox" className="size-4 accent-[#1F5C4E]" checked={selected.includes(i.id)} onChange={() => toggle(i.id)} aria-label={`Select ${i.title}`} /></td>}
                          <td className="px-3 py-2.5"><Link to={`/knowledge/items/${i.id}`} className="font-semibold hover:text-forest-700">{i.is_critical && <Star className="mr-1 inline size-3.5 fill-gold-500 text-gold-500" />}{i.title}</Link></td>
                          <td>{i.kind_label}</td>
                          <td className="text-ink-600">{i.category_path}</td>
                          <td>{i.owner_name ?? <span className="text-bad-600">No owner</span>}</td>
                          <td className="tabular">{i.version}</td>
                          <td><KStatus status={i.status} /></td>
                          <td className={cn('tabular', i.status === 'overdue' && 'font-bold text-bad-600')}>{fmt.shortDate(i.next_review_on)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}
              {selected.length > 0 && (
                <div className="on-dark sticky bottom-20 mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-forest-900 p-3 text-white md:bottom-4">
                  <b className="mr-2">{selected.length} selected</b>
                  <Button size="sm" variant="soft" onClick={() => run.mutate({ item_ids: selected, action: 'remind_owners' })}>Remind owners</Button>
                  <Button size="sm" variant="soft" onClick={() => { setBulk('change_owner'); setValue('') }}>Change owner</Button>
                  <Button size="sm" variant="soft" onClick={() => { setBulk('set_review_date'); setValue('') }}>Set review date</Button>
                  <Button size="sm" variant="outline-light" onClick={() => setSelected([])}>Clear</Button>
                </div>
              )}
            </div>
          </div>
        )}
      </QueryState>
      <Dialog open={!!bulk} onOpenChange={() => setBulk(null)} title={bulk === 'change_owner' ? 'Change owner' : 'Set review date'}
        footer={<Button disabled={!value} loading={run.isPending} onClick={() => run.mutate(
          { item_ids: selected, action: bulk!, ...(bulk === 'change_owner' ? { owner_id: value } : { review_on: value }) },
          { onSuccess: () => { setBulk(null); setSelected([]) } })}>Apply to {selected.length} items</Button>}>
        {bulk === 'change_owner' ? (
          <Field label="New owner"><Select value={value} onChange={(e) => setValue(e.target.value)}><option value="">Choose</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</Select></Field>
        ) : <Field label="Review date"><Input type="date" value={value} onChange={(e) => setValue(e.target.value)} /></Field>}
      </Dialog>
    </>
  )
}

// ---- K-09 My items --------------------------------------------------------------------------------
export function MyItemsPage() {
  const { data, isLoading, error, refetch } = useKMyItems()
  const decide = useKRevisionDecision()
  const navigate = useNavigate()
  return (
    <>
      <PageHeader title="My items" subtitle="Everything that needs you, with one-click actions. The reminders point here." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-4">
              <Stagger className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat value={data.overdue} label="Overdue" tone="bad" className="border-transparent bg-bad-50" />
                <Stat value={data.due_soon} label="Due soon" tone="warn" className="border-transparent bg-warn-50" />
                <Stat value={data.waiting_for_me} label="Waiting for me" tone="info" className="border-transparent bg-info-50" />
                <Stat value={data.drafts} label="My drafts" className="border-transparent bg-[#eef1f2]" />
              </Stagger>
              {data.items.length === 0 && <EmptyState title="All caught up" body="Nothing needs you right now." />}
              <Stagger className="space-y-2">
                {data.items.map((m) => (
                  <Card key={m.item.id + m.reason} className="flex flex-col gap-3 p-3.5 sm:flex-row sm:items-center sm:justify-between">
                    <span className="min-w-0"><Link to={`/knowledge/items/${m.item.id}`} className="block font-semibold hover:text-forest-700">{m.item.title}</Link>
                      <span className={cn('text-[13px]', m.reason === 'overdue' ? 'text-bad-600' : 'text-ink-600')}>{m.detail}</span></span>
                    <span className="flex flex-wrap gap-2">
                      {m.reason === 'waiting_for_me' ? (
                        <>
                          <Button size="sm" onClick={() => navigate(`/knowledge/items/${m.item.id}/history`)}>Review</Button>
                          <Button size="sm" variant="outline" onClick={() => decide.mutate({ id: m.revision_id!, approve: true })}>Approve</Button>
                        </>
                      ) : m.reason === 'draft' ? (
                        <Button size="sm" onClick={() => navigate(`/knowledge/items/${m.item.id}?edit=1`)}>Continue</Button>
                      ) : <ItemActions item={m.item} canSnooze={m.can_snooze} handOver={m.reason === 'overdue'} />}
                    </span>
                  </Card>
                ))}
              </Stagger>
            </div>
            <Card className="bg-forest-50 lg:self-start">
              <h2 className="font-sans text-lg font-bold">Coming up for me</h2>
              <ul className="mt-3 space-y-3 text-sm">{data.coming_up.map((c) => <li key={c.text} className="grid grid-cols-[80px_1fr] gap-2"><b className="text-forest-700">{c.when}</b><span>{c.text}</span></li>)}</ul>
              {data.coming_up.length === 0 && <p className="mt-2 text-sm text-ink-600">No reviews due soon.</p>}
              {data.backup_note && <><b className="mt-6 block">My backup owner</b><p className="text-sm">{data.backup_note}</p></>}
              <p className="mt-6 text-[13px] italic text-ink-600">Snooze twice for 7 days, with a reason. After that the function head is told.</p>
            </Card>
          </div>
        )}
      </QueryState>
    </>
  )
}

export function ItemActions({ item, canSnooze = true, handOver }: { item: KItem; canSnooze?: boolean; handOver?: boolean }) {
  const act = useKAction(item.id)
  const navigate = useNavigate()
  const users = usePeople()
  const [dialog, setDialog] = useState<null | 'snooze' | 'hand-over'>(null)
  const [text, setText] = useState('')
  return (
    <>
      <Button size="sm" loading={act.isPending && act.variables?.action === 'verify'} onClick={() => act.mutate({ action: 'verify' })}>Still correct</Button>
      <Button size="sm" variant="outline" onClick={() => navigate(`/knowledge/items/${item.id}?edit=1`)}>Update</Button>
      {handOver || !canSnooze
        ? <Button size="sm" variant="outline" onClick={() => setDialog('hand-over')}>Hand over</Button>
        : <Button size="sm" variant="outline" onClick={() => setDialog('snooze')}>Snooze</Button>}
      <Dialog open={!!dialog} onOpenChange={() => setDialog(null)} title={dialog === 'snooze' ? 'Snooze for 7 days' : 'Hand over to someone else'}
        footer={<Button disabled={!text} loading={act.isPending}
          onClick={() => act.mutate(dialog === 'snooze' ? { action: 'snooze', body: { reason: text } } : { action: 'hand-over', body: { new_owner_id: text } }, { onSuccess: () => { setDialog(null); setText('') } })}>
          {dialog === 'snooze' ? 'Snooze' : 'Hand over'}</Button>}>
        {dialog === 'snooze' ? (
          <><Field label="Why do you need more time?"><Textarea value={text} onChange={(e) => setText(e.target.value)} /></Field><Notice className="mt-3">You can snooze twice. After that the function head is told.</Notice></>
        ) : (
          <Field label="New owner"><Select value={text} onChange={(e) => setText(e.target.value)}><option value="">Choose</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</Select></Field>
        )}
      </Dialog>
    </>
  )
}
