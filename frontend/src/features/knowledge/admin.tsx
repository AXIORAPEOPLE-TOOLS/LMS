import { ArrowLeft, Lock, MoreHorizontal, Plus } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  useKAccess, useKAccessDecision, useKAssignOwner, useKBulk, useKCategory, useKDashboard, useKFunction, useKGrant, useKRequests, useKWithoutOwner,
  useLibrary,
} from '@/api/knowledge'
import { useDepartments, usePeople } from '@/api/admin'
import { CountUp, Stagger } from '@/components/motion'
import { QueryState } from '@/components/SystemStatus'
import { Badge, Button, Card, Dialog, EmptyState, Field, Input, Notice, PageHeader, Panel, ProgressBar, SectionTitle, Select, SkeletonPage, Stat } from '@/components/ui'
import { cn } from '@/lib/utils'

// ---- K-05 Access and owners -----------------------------------------------------------------
export function AccessPage() {
  const { id } = useParams()
  const { data, isLoading, error, refetch } = useKAccess(id)
  const decide = useKAccessDecision()
  const grant = useKGrant(id!)
  const people = usePeople()
  const departments = useDepartments()
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ principal_type: 'user', principal_id: '', role: 'viewer' })
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <div className="mx-auto max-w-3xl">
          <Link to={`/knowledge/items/${data.item_id}`} className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-forest-700"><ArrowLeft className="size-4" />Back to the page</Link>
          <PageHeader title={`${data.item_title}: who can do what`} actions={data.can_change && <Button size="sm" onClick={() => setAdding(true)}><Plus className="size-4" />Give access</Button>} />
          <Card>
            <Stagger className="space-y-3">
              {data.entries.map((e) => (
                <div key={`${e.principal_type}-${e.principal_id}`} className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-full bg-forest-100 text-sm font-bold text-forest-800">{e.initials}</span>
                  <span className="min-w-0 flex-1"><b className="block">{e.name}</b><span className="text-[13px] text-ink-600">{e.rights}</span></span>
                  <Badge className="px-4 py-1">{e.role}</Badge>
                </div>
              ))}
            </Stagger>
            <Notice tone="warn" className="mt-5 flex items-center gap-2 font-semibold"><Lock className="size-4" />Only the owner and knowledge admins can change access.</Notice>
          </Card>
          {data.requests.length > 0 && (
            <Card className="mt-4">
              <SectionTitle>Access requests ({data.requests.length})</SectionTitle>
              {data.requests.map((r) => (
                <div key={r.id} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <span>{r.requester_name} asks to {r.role === 'viewer' ? 'view' : 'edit'}{r.reason && <span className="block text-[13px] text-ink-600">“{r.reason}”</span>}</span>
                  {data.can_change && <span className="flex gap-2"><Button size="sm" onClick={() => decide.mutate({ id: r.id, approve: true })}>Approve</Button><Button size="sm" variant="outline" onClick={() => decide.mutate({ id: r.id, approve: false })}>Decline</Button></span>}
                </div>
              ))}
            </Card>
          )}
          <Card className="mt-4">
            <SectionTitle>Who can do what</SectionTitle>
            <table className="w-full text-center text-sm">
              <thead><tr className="text-[12px] text-ink-600"><th className="text-left" />{['Read', 'Edit', 'Publish', 'Verify', 'Access'].map((h) => <th key={h} className="py-1">{h}</th>)}</tr></thead>
              <tbody>
                {[['Viewer', 1, 0, 0, 0, 0], ['Editor', 1, 1, 0, 0, 0], ['Backup owner', 1, 1, 0, 1, 0], ['Owner', 1, 1, 1, 1, 1], ['Admin', 1, 1, 1, 1, 1]].map(([role, ...cells]) => (
                  <tr key={role as string} className="border-t border-line"><td className="py-2 text-left font-semibold">{role}</td>
                    {cells.map((c, i) => <td key={i} className={c ? 'font-bold text-ok-600' : 'text-ink-400'}>{c ? '✓' : '–'}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Dialog open={adding} onOpenChange={setAdding} title="Give access"
            footer={<Button disabled={!form.principal_id} loading={grant.isPending} onClick={() => grant.mutate(form, { onSuccess: () => setAdding(false) })}>Save</Button>}>
            <div className="space-y-3">
              <Field label="Who">
                <Select value={form.principal_type} onChange={(e) => setForm({ ...form, principal_type: e.target.value, principal_id: '' })}><option value="user">A person</option><option value="department">A team</option></Select>
              </Field>
              <Select value={form.principal_id} onChange={(e) => setForm({ ...form, principal_id: e.target.value })} aria-label="Choose">
                <option value="">Choose</option>
                {(form.principal_type === 'user' ? people.data?.map((u) => ({ id: u.id, name: u.full_name })) : departments.data)?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
              <Field label="Role"><Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="viewer">Viewer: read and comment</option><option value="editor">Editor: edit drafts</option></Select></Field>
            </div>
          </Dialog>
        </div>
      )}
    </QueryState>
  )
}

// ---- K-11 Leader dashboard --------------------------------------------------------------------------
export function LeaderDashboardPage() {
  const { data, isLoading, error, refetch } = useKDashboard()
  const navigate = useNavigate()
  return (
    <>
      <PageHeader title="Knowledge health" subtitle="One score, a few tiles and a league table by function. Click any number to see the list behind it." />
      <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
        {data && (
          <div className="space-y-5">
            <div className="grid gap-4 lg:grid-cols-[280px_1fr_1fr]">
              <Panel>
                <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/60">Knowledge health</p>
                <p className="mt-2 font-serif text-7xl font-bold text-white"><CountUp value={data.company.score} /><span className="ml-2 align-middle text-lg font-normal text-white/60">of 100</span></p>
                {data.change_since_last_month !== null && <p className="mt-2 font-semibold text-gold-500">{data.change_since_last_month >= 0 ? '▲' : '▼'} {Math.abs(data.change_since_last_month)} since last month</p>}
              </Panel>
              <Card>
                <b className="text-sm">Health score trend</b>
                <ResponsiveContainer width="100%" height={170}>
                  <LineChart data={data.trend} margin={{ top: 10, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid stroke="#eef1f0" vertical={false} />
                    <XAxis dataKey="month" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis domain={[50, 100]} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip />
                    <Line type="monotone" dataKey="score" stroke="#1F5C4E" strokeWidth={3} dot={{ r: 4, fill: '#1F5C4E' }} />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
              <div className="grid grid-cols-2 gap-3">
                <button className="text-left" onClick={() => navigate('/knowledge/library')}><Stat value={data.company.items} label={`Items · ${data.functions_count} functions`} /></button>
                <button className="text-left" onClick={() => navigate('/knowledge/library')}><Stat value={`${data.company.on_time_pct}%`} label={`Current on time · target ${data.target_on_time_pct}%`} tone={data.company.on_time_pct >= data.target_on_time_pct ? 'ok' : 'warn'} /></button>
                <button className="text-left" onClick={() => navigate('/knowledge/library?status=overdue')}><Stat value={data.company.overdue} label={`Overdue · ${data.company.due_soon} more due soon`} tone="bad" /></button>
                <button className="text-left" onClick={() => navigate('/knowledge/admin')}><Stat value={data.company.no_owner} label={`No owner · ${data.company.no_backup} without backup`} tone="bad" /></button>
              </div>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <b className="text-sm">Health score by function</b>
                <ResponsiveContainer width="100%" height={Math.max(180, data.by_function.length * 34)}>
                  <BarChart layout="vertical" data={data.by_function} margin={{ top: 8, right: 30, left: 30, bottom: 0 }}
                    onClick={(state) => {
                      const index = Number((state as { activeIndex?: number | string } | undefined)?.activeIndex)
                      const id = Number.isFinite(index) ? data.by_function[index]?.category_id : undefined
                      if (id) navigate(`/knowledge/dashboard/${id}`)
                    }}>
                    <XAxis type="number" domain={[0, 100]} hide />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 13 }} width={110} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: '#f1f6f3' }} />
                    <Bar dataKey="score" fill="#1F5C4E" radius={[0, 6, 6, 0]} label={{ position: 'right', fontSize: 12 }} className="cursor-pointer" />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
              <Card>
                <SectionTitle>Needs a leader’s attention</SectionTitle>
                {data.attention.length === 0 ? <p className="text-sm text-ink-600">Nothing urgent.</p> : (
                  <ul className="space-y-3">{data.attention.map((a) => (
                    <li key={a.text} className="flex items-center justify-between gap-3 text-sm"><span>• {a.text}</span><Button size="sm" variant="outline" onClick={() => navigate(a.href)}>{a.action}</Button></li>
                  ))}</ul>
                )}
              </Card>
            </div>
          </div>
        )}
      </QueryState>
    </>
  )
}

// ---- K-12 Function dashboard ---------------------------------------------------------------------------
export function FunctionDashboardPage() {
  const { id } = useParams()
  const { data, isLoading, error, refetch } = useKFunction(id)
  const bulk = useKBulk()
  const lib = useLibrary({ category_id: id, status: 'overdue' })
  const navigate = useNavigate()
  return (
    <QueryState isLoading={isLoading} error={error} hasData={!!data} skeleton={<SkeletonPage />} onRetry={refetch}>
      {data && (
        <div className="space-y-5">
          <Link to="/knowledge/dashboard" className="inline-flex items-center gap-1 text-sm font-semibold text-forest-700"><ArrowLeft className="size-4" />All functions</Link>
          <h1 className="text-4xl">{data.name}</h1>
          <Stagger className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <Stat value={data.tile.score} label="Health" tone="forest" />
            <Stat value={data.tile.items} label="Items" />
            <Stat value={`${data.tile.on_time_pct}%`} label="Current on time" tone="warn" />
            <Stat value={data.tile.overdue} label="Overdue" tone="bad" />
            <Stat value={data.tile.due_soon} label="Due soon" tone="warn" />
            <Stat value={data.tile.no_backup} label="No backup" tone="bad" />
            <Stat value={data.tile.critical} label="Critical items" />
          </Stagger>
          <div className="grid gap-4 lg:grid-cols-[1fr_1fr_300px]">
            <Card>
              <SectionTitle>By category</SectionTitle>
              <ul className="space-y-3">{data.by_category.map((c) => (
                <li key={c.category_id} className="grid grid-cols-[1fr_24px_100px_80px] items-center gap-2 text-sm">
                  <button className="truncate text-left hover:text-forest-700" onClick={() => navigate(`/knowledge/library?category_id=${c.category_id}`)}>{c.name}</button>
                  <span className="text-right tabular">{c.items}</span>
                  <ProgressBar size="sm" tone={c.overdue ? 'warn' : 'ok'} value={c.ok_pct} />
                  <span className={cn('text-[12px] font-bold', c.overdue ? 'text-bad-600' : 'text-ok-600')}>{c.overdue ? `${c.overdue} overdue` : 'ok'}</span>
                </li>
              ))}</ul>
            </Card>
            <Card>
              <SectionTitle>By owner</SectionTitle>
              <ul className="space-y-3">{data.by_owner.map((o) => (
                <li key={o.owner_id} className="flex items-center justify-between gap-2 text-sm">
                  <b className="w-28 truncate">{o.name}</b><span className="text-ink-600">{o.items} items</span>
                  <span className={cn('font-bold', o.overdue ? 'text-bad-600' : 'text-ok-600')}>{o.overdue ? `${o.overdue} overdue` : 'all current'}</span>
                </li>
              ))}</ul>
            </Card>
            <Card className="space-y-2 bg-forest-50">
              <SectionTitle>Actions</SectionTitle>
              <Button block disabled={!lib.data?.items.length} loading={bulk.isPending}
                onClick={() => bulk.mutate({ item_ids: lib.data!.items.map((i) => i.id), action: 'remind_owners' })}>Remind {data.overdue_owner_count} overdue owners</Button>
              <Button block variant="outline" onClick={() => navigate(`/knowledge/library?category_id=${id}`)}>Assign {data.items_without_backup} backups</Button>
              <Button block variant="outline" onClick={() => navigate(`/knowledge/library?category_id=${id}`)}>Open the {data.name} list</Button>
              <p className="text-[13px] italic text-ink-600">Messages are combined: one per owner.</p>
            </Card>
          </div>
        </div>
      )}
    </QueryState>
  )
}

// ---- K-13 Categories + items without owner + requests ------------------------------------------------------
export function KnowledgeAdminPage() {
  const lib = useLibrary({})
  const without = useKWithoutOwner()
  const requests = useKRequests()
  const assign = useKAssignOwner()
  const decide = useKAccessDecision()
  const category = useKCategory()
  const people = usePeople()
  const [dialog, setDialog] = useState<null | { kind: 'add' | 'rename' | 'merge' | 'owner'; id?: string; name?: string }>(null)
  const [value, setValue] = useState('')
  const [parent, setParent] = useState('')
  const close = () => { setDialog(null); setValue(''); setParent('') }
  const submit = () => {
    if (!dialog) return
    if (dialog.kind === 'owner') assign.mutate({ id: dialog.id!, ownerId: value }, { onSuccess: close })
    else if (dialog.kind === 'add') category.mutate({ body: { name: value, parent_id: parent || null } }, { onSuccess: close })
    else if (dialog.kind === 'rename') category.mutate({ id: dialog.id, body: { name: value } }, { onSuccess: close })
    else category.mutate({ id: dialog.id, merge: true, body: { into_id: value } }, { onSuccess: close })
  }
  const categories = lib.data?.categories ?? []
  return (
    <>
      <PageHeader title="Knowledge admin" subtitle="Keep the category tree tidy, give every item an owner, and answer access requests." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <SectionTitle action={<Button size="sm" onClick={() => setDialog({ kind: 'add' })}><Plus className="size-4" />Add category</Button>}>Categories</SectionTitle>
          <ul className="space-y-1.5">
            {categories.map((c) => (
              <li key={c.id} className={cn('flex items-center justify-between rounded-lg border border-line px-3 py-2', c.parent_id && 'ml-5 bg-canvas')}>
                <span className={cn('text-sm', !c.parent_id && 'font-semibold')}>{c.name}</span>
                <span className="flex items-center gap-3 text-[13px] text-ink-600">{c.item_count} items
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger className="rounded p-1 hover:bg-forest-100" aria-label={`Options for ${c.name}`}><MoreHorizontal className="size-4" /></DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                      <DropdownMenu.Content align="end" className="z-50 w-40 rounded-xl border border-line bg-surface p-1 shadow-lg">
                        <DropdownMenu.Item className="cursor-pointer rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-forest-100" onSelect={() => { setDialog({ kind: 'rename', id: c.id, name: c.name }); setValue(c.name) }}>Rename</DropdownMenu.Item>
                        <DropdownMenu.Item className="cursor-pointer rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-forest-100" onSelect={() => setDialog({ kind: 'merge', id: c.id, name: c.name })}>Merge into…</DropdownMenu.Item>
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[13px] italic text-ink-600">Rename · Merge into · Move. Items and their history follow.</p>
        </Card>
        <div className="space-y-5">
          <Card>
            <SectionTitle><span className="text-bad-600">Items without an owner ({without.data?.length ?? 0})</span></SectionTitle>
            {without.data?.length === 0 && <EmptyState title="Every item has an owner" />}
            <ul className="space-y-2">{without.data?.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-3"><span><b className="block text-sm">{i.title}</b><span className="text-[12px] text-ink-600">{i.category_path}</span></span>
                <Button size="sm" onClick={() => setDialog({ kind: 'owner', id: i.id, name: i.title })}>Assign</Button></li>
            ))}</ul>
          </Card>
          <Card>
            <SectionTitle>Access requests ({requests.data?.length ?? 0})</SectionTitle>
            {requests.data?.length === 0 && <p className="text-sm text-ink-600">No open requests.</p>}
            <ul className="space-y-2">{requests.data?.map((r) => (
              <li key={r.id} className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><span className="text-sm">{r.requester_name} asks to view <b>{r.item_title}</b></span>
                <span className="flex gap-2"><Button size="sm" onClick={() => decide.mutate({ id: r.id, approve: true })}>Approve</Button><Button size="sm" variant="outline" onClick={() => decide.mutate({ id: r.id, approve: false })}>Decline</Button></span></li>
            ))}</ul>
          </Card>
        </div>
      </div>
      <Dialog open={!!dialog} onOpenChange={(o) => !o && close()}
        title={{ add: 'Add category', rename: `Rename “${dialog?.name}”`, merge: `Merge “${dialog?.name}” into…`, owner: `Owner for “${dialog?.name}”` }[dialog?.kind ?? 'add']}
        footer={<Button disabled={!value} loading={category.isPending || assign.isPending} onClick={submit}>Save</Button>}>
        {dialog?.kind === 'add' || dialog?.kind === 'rename' ? (
          <div className="space-y-3">
            <Field label="Name"><Input value={value} onChange={(e) => setValue(e.target.value)} /></Field>
            {dialog.kind === 'add' && <Field label="Inside (optional)"><Select value={parent} onChange={(e) => setParent(e.target.value)}><option value="">Top level</option>{categories.filter((c) => !c.parent_id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>}
          </div>
        ) : dialog?.kind === 'merge' ? (
          <Select value={value} onChange={(e) => setValue(e.target.value)} aria-label="Merge into"><option value="">Choose</option>{categories.filter((c) => c.id !== dialog.id).map((c) => <option key={c.id} value={c.id}>{c.path}</option>)}</Select>
        ) : (
          <Select value={value} onChange={(e) => setValue(e.target.value)} aria-label="Owner"><option value="">Choose</option>{people.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</Select>
        )}
      </Dialog>
    </>
  )
}
