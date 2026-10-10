import { ArrowLeft, Check, FileText, Link2, Lock, Paperclip, PenLine, Plus, Upload } from 'lucide-react'
import { motion } from 'motion/react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import {
  useKAction, useKCompare, useKCreate, useKHistory, useKImportRows, useKItem, useKRequestAccess, useKRow, useKRows, useKSuggest,
  useKUpdate, useKUpload, useLibrary,
} from '@/api/knowledge'
import { useDepartments, usePeople } from '@/api/admin'
import type { KItemDetail, KSuggestion } from '@/api/types'
import { Stagger } from '@/components/motion'
import { EASE } from '@/lib/motion-tokens'
import { QueryState } from '@/components/SystemStatus'
import {
  Badge, Button, Card, Dialog, Field, Input, Notice, PageHeader, SectionTitle, Select, SkeletonPage, Textarea, Toggle,
} from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import { useSession } from '@/lib/session'
import { cn, fmt } from '@/lib/utils'
import { ItemActions, KStatus } from './index'

const KINDS = [['sop', 'SOP / procedure'], ['policy', 'Policy'], ['template', 'Template'], ['checklist', 'Checklist'], ['playbook', 'Playbook'],
  ['faq', 'FAQ'], ['file', 'File'], ['link', 'Link'], ['list', 'List (table)'], ['meeting_notes', 'Meeting notes'], ['contact_list', 'Contact list']] as const
const TEMPLATES: Record<string, string> = {
  SOP: '1. \n2. \n3. ', Policy: 'Purpose:\n\nWho it applies to:\n\nThe rules:\n', FAQ: 'Q: \nA: \n', Checklist: '☐ \n☐ \n☐ ',
  Playbook: 'When to use this:\n\nSteps:\n1. ', 'Meeting notes': 'Date:\nPeople:\nDecisions:\nActions:', 'Contact list': '', 'Register (table)': '',
}

// ---- K-02 Add knowledge in three clicks -------------------------------------------------------
export function AddKnowledgePage() {
  const [mode, setMode] = useState<'write' | 'upload' | 'link'>('upload')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [link, setLink] = useState('')
  const [uploadId, setUploadId] = useState<string>()
  const [fileName, setFileName] = useState<string>()
  const [s, setS] = useState<KSuggestion | null>(null)
  const [accepted, setAccepted] = useState(false)
  const [asVersion, setAsVersion] = useState(false)
  const upload = useKUpload()
  const suggest = useKSuggest()
  const create = useKCreate()
  const navigate = useNavigate()
  const people = usePeople()
  const departments = useDepartments()
  const lib = useLibrary({})

  const getSuggestions = (extra: Partial<{ upload_id: string; title: string; text: string; link_url: string }>) =>
    suggest.mutate(extra, { onSuccess: (data) => { setS(data); setAccepted(false); setAsVersion(false); if (!title) setTitle(data.title) } })

  const onFile = (file: File) => upload.mutate(file, {
    onSuccess: (u) => { setUploadId(u.id); setFileName(`${u.filename} · ${(u.size_bytes / 1e6).toFixed(1)} MB${u.has_text ? ' · text read for search' : ''}`); getSuggestions({ upload_id: u.id }) },
  })
  const supportTeam = s?.visibility === 'team' ? departments.data?.find((d) => s.visibility_label.startsWith(d.name))?.id : undefined
  const save = () => {
    if (!s) return
    create.mutate({
      title: title || s.title, kind: mode === 'link' ? 'link' : s.kind, category_id: s.category_id, owner_id: s.owner_id, backup_owner_id: s.backup_owner_id,
      visibility: supportTeam ? 'team' : 'company', team_department_id: supportTeam ?? null, body, link_url: link || null, upload_id: uploadId ?? null,
      review_months: 12, add_as_version_of: asVersion ? s.similar_item_id : null,
      list_columns: s.kind === 'list' ? ['Name', 'Owner', 'Status'] : [],
    }, { onSuccess: (item) => navigate(`/knowledge/items/${item.id}`) })
  }

  const cards = [
    { key: 'write', title: 'Write', sub: 'A page from a template', icon: PenLine },
    { key: 'upload', title: 'Upload', sub: 'A file or folder', icon: Upload },
    { key: 'link', title: 'Link', sub: 'A web or drive link', icon: Link2 },
  ] as const
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_400px]">
      <div className="min-w-0 space-y-5">
        <h1 className="text-3xl">What do you want to add?</h1>
        <div className="grid grid-cols-3 gap-3">
          {cards.map((c) => (
            <button key={c.key} onClick={() => { setMode(c.key); setS(null) }}
              className={cn('rounded-card border bg-surface p-4 text-center transition-colors', mode === c.key ? 'border-2 border-forest-700 bg-forest-50' : 'border-line hover:border-forest-700/50')}>
              <c.icon className="mx-auto size-6 text-forest-700" /><b className="mt-2 block">{c.title}</b><span className="text-[12px] text-ink-600">{c.sub}</span>
            </button>
          ))}
        </div>
        {mode === 'upload' && (
          <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface p-4 hover:border-forest-700">
            {fileName ? <FileText className="size-5 text-forest-700" /> : <Upload className="size-5 text-forest-700" />}
            <span className="text-sm">{upload.isPending ? 'Uploading…' : fileName ?? 'Choose a file (PDF, Word, text, images, spreadsheets)'}</span>
            <input type="file" className="sr-only" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
          </label>
        )}
        {mode === 'link' && (
          <div className="flex gap-2">
            <Input placeholder="https://drive.example.com/…" value={link} onChange={(e) => setLink(e.target.value)} aria-label="Link" />
            <Button variant="outline" disabled={!link.startsWith('http')} onClick={() => getSuggestions({ link_url: link, title })}>Next</Button>
          </div>
        )}
        {mode === 'write' && (
          <div className="space-y-3">
            <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <Field label="Content"><Textarea className="min-h-48" value={body} onChange={(e) => setBody(e.target.value)} /></Field>
            <Button variant="outline" disabled={title.length < 2} onClick={() => getSuggestions({ title, text: body })}>Next</Button>
          </div>
        )}
        <section>
          <p className="mb-2 font-semibold">Or start from a template</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.keys(TEMPLATES).map((t) => (
              <button key={t} onClick={() => { setMode('write'); setBody(TEMPLATES[t]); setS(null) }} className="rounded-xl border border-line bg-surface px-3 py-3 text-sm hover:border-forest-700">{t}</button>
            ))}
          </div>
        </section>
        {s?.similar_item_id && (
          <Notice tone="warn" className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <b>Similar item found: “{s.similar_item_title}” v{s.similar_item_version}. Add as a new version instead?</b>
            <Button size="sm" variant={asVersion ? 'primary' : 'outline'} onClick={() => setAsVersion(!asVersion)}>{asVersion ? <><Check className="size-4" />New version</> : 'Yes, new version'}</Button>
          </Notice>
        )}
      </div>

      <Card className="bg-forest-50 lg:sticky lg:top-20 lg:self-start">
        <b className="text-forest-800">Suggestions</b>
        <p className="text-[13px] text-ink-600">Nothing is saved until you accept.</p>
        {!s ? <p className="mt-6 text-sm text-ink-600">{suggest.isPending ? 'Reading it…' : 'Add a file, a link or some text to see suggestions.'}</p> : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ease: EASE }} className="mt-4 space-y-2.5">
            {[
              ['Title', <Input key="t" value={title || s.title} onChange={(e) => setTitle(e.target.value)} />],
              ['Kind', <Select key="k" value={s.kind} onChange={(e) => setS({ ...s, kind: e.target.value })}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>],
              ['Category', <Select key="c" value={s.category_id ?? ''} onChange={(e) => setS({ ...s, category_id: e.target.value || null })}>
                <option value="">Choose</option>{lib.data?.categories.map((c) => <option key={c.id} value={c.id}>{c.path}</option>)}</Select>],
              ['Owner', <Select key="o" value={s.owner_id ?? ''} onChange={(e) => setS({ ...s, owner_id: e.target.value || null })}>{people.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</Select>],
              ['Backup owner', <Select key="b" value={s.backup_owner_id ?? ''} onChange={(e) => setS({ ...s, backup_owner_id: e.target.value || null })}>
                <option value="">None</option>{people.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</Select>],
              ['Review date', <div key="r" className="rounded-[10px] border border-line bg-surface px-3.5 py-2.5 text-sm">{s.review_label}</div>],
              ['Who can see', <div key="v" className="rounded-[10px] border border-line bg-surface px-3.5 py-2.5 text-sm">{s.visibility_label}</div>],
            ].map(([label, control]) => (
              <div key={String(label)} className="grid grid-cols-[100px_1fr] items-center gap-2"><span className="text-[13px] text-ink-600">{label}</span>{control}</div>
            ))}
            <div className="grid grid-cols-2 gap-2 pt-3">
              <Button variant="outline" onClick={() => setAccepted(true)}>{accepted ? <><Check className="size-4" />Accepted</> : 'Accept all'}</Button>
              <Button loading={create.isPending} onClick={save}>Save and publish</Button>
            </div>
          </motion.div>
        )}
      </Card>
    </div>
  )
}

// ---- K-03 Knowledge page ----------------------------------------------------------------------------
export function ItemPage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const { data: item, isLoading, error, refetch } = useKItem(id)
  const forbidden = error instanceof ApiError && error.status === 403
  return forbidden ? <NoAccess itemId={id!} message={(error as ApiError).message} /> : (
    <QueryState isLoading={isLoading} error={error} hasData={!!item} skeleton={<SkeletonPage />} onRetry={refetch}>
      {item && (params.get('edit') ? <EditItem item={item} onDone={() => setParams({})} /> : <ItemView item={item} onEdit={() => setParams({ edit: '1' })} />)}
    </QueryState>
  )
}

function NoAccess({ itemId, message }: { itemId: string; message: string }) {
  const request = useKRequestAccess(itemId)
  const [reason, setReason] = useState('')
  return (
    <Card className="mx-auto mt-6 max-w-md text-center">
      <Lock className="mx-auto size-8 text-forest-700" />
      <h1 className="mt-3 text-2xl">You do not have access yet</h1>
      <p className="mt-1 text-sm text-ink-600">{message}</p>
      <Field label="Why do you need it? (optional)" className="mt-5 text-left"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <Button className="mt-4" block loading={request.isPending} disabled={request.isSuccess} onClick={() => request.mutate({ role: 'viewer', reason })}>
        {request.isSuccess ? 'Request sent' : 'Ask the owner for access'}</Button>
    </Card>
  )
}

function ItemView({ item, onEdit }: { item: KItemDetail; onEdit: () => void }) {
  const act = useKAction(item.id)
  const { has } = useSession()
  const navigate = useNavigate()
  const crumbs = item.category_path?.split(' › ') ?? []
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
      <article className="min-w-0">
        <p className="text-sm text-ink-600">{[...crumbs, item.title].join(' › ')}</p>
        <h1 className="mt-1 text-3xl sm:text-4xl">{item.title}</h1>
        <div className="mt-3 flex flex-wrap gap-2">
          <KStatus status={item.status} />
          {item.last_verified_at && <Badge tone="ok">✓ Verified {fmt.date(item.last_verified_at)}</Badge>}
          <Badge>Version {item.version}</Badge>
          {item.owner_name && <Badge>Owner: {item.owner_name}</Badge>}
          <Badge tone="neutral">Next review: {fmt.date(item.next_review_on)}</Badge>
          {item.visibility !== 'company' && <Badge tone="warn">{item.visibility === 'team' ? 'Team only' : 'Restricted'}</Badge>}
        </div>
        {item.pending_change && <Notice tone="info" className="mt-4">A change is waiting for the owner’s approval. <Link className="font-semibold underline" to={`/knowledge/items/${item.id}/history`}>See it</Link></Notice>}
        {item.kind === 'link' && item.link_url && <a href={item.link_url} target="_blank" rel="noreferrer" className="mt-5 inline-flex items-center gap-2 font-semibold text-forest-700 underline"><Link2 className="size-4" />Open the link</a>}
        {item.kind === 'list' ? <ListTable item={item} /> : <div className="mt-6 whitespace-pre-line text-[16px] leading-relaxed text-ink-700">{item.body}</div>}
        {item.attachments.length > 0 && (
          <div className="mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-4 text-sm">
            <Paperclip className="size-4 text-ink-600" />
            {item.attachments.map((a) => a.upload_id ? (
              <button key={a.name} className="font-semibold text-forest-700 underline" onClick={() => api.download(`/knowledge/items/${item.id}/files/${a.upload_id}`, undefined, a.name)}>{a.name}</button>
            ) : <span key={a.name}>{a.name}</span>)}
          </div>
        )}
      </article>
      <Card className="space-y-3 lg:sticky lg:top-20 lg:self-start">
        {item.can_verify && <Button size="lg" block loading={act.isPending} onClick={() => act.mutate({ action: 'verify' })}>Still correct (verify)</Button>}
        <div className="grid grid-cols-2 gap-2">
          {item.can_edit && <Button variant="outline" onClick={onEdit}>Update</Button>}
          {item.can_change_access && <Button variant="outline" onClick={() => navigate(`/knowledge/items/${item.id}/access`)}>Access</Button>}
        </div>
        {item.my_role === 'owner' && <div className="flex flex-wrap gap-2"><ItemActions item={item} handOver /></div>}
        <Button variant="outline" block onClick={() => navigate(`/knowledge/items/${item.id}/history`)}>View history ({item.version_count} versions)</Button>
        <div className="space-y-3 border-t border-line pt-3 text-sm">
          <p><b className="block">Owner and backup</b>{item.owner_name ?? 'No owner'}{item.backup_owner_name && ` (owner) · ${item.backup_owner_name} (backup)`}</p>
          <p><b className="block">Category</b>{item.category_path ?? '–'} · Kind: {item.kind_label}</p>
        </div>
        {has('admin') && item.kind !== 'list' && (
          <Button variant="ghost" block loading={act.isPending && act.variables?.action === 'course'} onClick={() => act.mutate({ action: 'course' })}>Turn into a course</Button>
        )}
        {item.linked_course_id && <Link to={`/learn/courses/${item.linked_course_id}`} className="block text-center text-sm font-semibold text-forest-700">Linked course →</Link>}
      </Card>
    </div>
  )
}

function EditItem({ item, onDone }: { item: KItemDetail; onDone: () => void }) {
  const update = useKUpdate(item.id)
  const [title, setTitle] = useState(item.title)
  const [body, setBody] = useState(item.body)
  const [note, setNote] = useState('')
  const [major, setMajor] = useState(false)
  const save = (publish: boolean) => update.mutate({ title, body, change_note: note, is_major: major, publish }, { onSuccess: () => publish && onDone() })
  return (
    <div className="mx-auto max-w-3xl">
      <button onClick={onDone} className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-forest-700"><ArrowLeft className="size-4" />Back to the page</button>
      <PageHeader title="Update" subtitle={item.can_publish ? 'Publishing makes a new version. Nothing is ever overwritten.' : 'Your change goes to the owner for approval.'} />
      <Card className="space-y-4">
        <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Content"><Textarea className="min-h-80 font-[inherit]" value={body} onChange={(e) => setBody(e.target.value)} /></Field>
        <Field label="What changed?" hint="Shown in the history, for example: Refund limit raised after the finance review."><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        {item.can_publish && <Toggle checked={major} onChange={setMajor} label="Major change" hint="Moves to the next whole version, for example 3.2 → 4.0" />}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={() => save(false)} loading={update.isPending && update.variables?.publish === false}>Save draft</Button>
          <Button onClick={() => save(true)} loading={update.isPending && update.variables?.publish !== false}>{item.can_publish ? 'Publish' : 'Send to the owner'}</Button>
        </div>
      </Card>
    </div>
  )
}

function ListTable({ item }: { item: KItemDetail }) {
  const [status, setStatus] = useState('')
  const rows = useKRows(item.id, { status: status || undefined })
  const save = useKRow(item.id)
  const importRows = useKImportRows(item.id)
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const columns = rows.data?.columns ?? item.list_columns
  return (
    <div className="mt-6">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {columns.includes('Status') && (
          <Select className="w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Status: all</option><option value="active">Active</option><option value="renew">Renew</option></Select>
        )}
        {item.can_edit && <>
          <Button size="sm" onClick={() => { setAdding(true); setDraft({}) }}><Plus className="size-4" />Add row</Button>
          <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-[10px] border border-forest-700 px-3 text-sm font-semibold text-forest-700">
            <Upload className="size-4" />Import from a spreadsheet<input type="file" accept=".csv,.xlsx" className="sr-only" onChange={(e) => e.target.files?.[0] && importRows.mutate(e.target.files[0])} />
          </label>
        </>}
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[480px] text-sm">
          <thead><tr className="text-left text-[12px] text-ink-600">{columns.map((c) => <th key={c} className="px-3 py-2.5">{c}</th>)}</tr></thead>
          <tbody>
            {rows.data?.rows.map((r) => (
              <tr key={r.id} className="border-t border-line">
                {columns.map((c, i) => <td key={c} className={cn('px-3 py-2.5', i === 0 && 'font-semibold')}>
                  {c === 'Status' ? <Badge tone={String(r.data[c]).toLowerCase() === 'renew' ? 'warn' : 'ok'}>{r.data[c]}</Badge> : r.data[c]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="mt-2 text-[13px] italic text-ink-600">Import from a spreadsheet · filters · row history · review every {item.review_months} months</p>
      <Dialog open={adding} onOpenChange={setAdding} title="Add row" footer={<Button loading={save.isPending} onClick={() => save.mutate({ data: draft }, { onSuccess: () => setAdding(false) })}>Save</Button>}>
        <div className="space-y-3">{columns.map((c) => <Field key={c} label={c}><Input value={draft[c] ?? ''} onChange={(e) => setDraft({ ...draft, [c]: e.target.value })} /></Field>)}</div>
      </Dialog>
    </div>
  )
}

// ---- K-08 Versions, revisions, reviews -------------------------------------------------------------------
export function HistoryPage() {
  const { id } = useParams()
  const item = useKItem(id)
  const history = useKHistory(id)
  const versions = useMemo(() => history.data?.filter((h) => h.kind === 'version').map((h) => h.label.replace('Version ', '')) ?? [], [history.data])
  const [chosenPair, setPair] = useState<[string, string] | null>(null)
  const pair = chosenPair ?? (versions.length >= 2 ? ([versions[1], versions[0]] as [string, string]) : null)
  const compare = useKCompare(id, pair?.[0], pair?.[1])
  const act = useKAction(id!)
  const navigate = useNavigate()
  const dot = { version: 'bg-forest-700', revision: 'bg-info-600', review: 'bg-ok-600' }
  return (
    <QueryState isLoading={history.isLoading} error={history.error} hasData={!!history.data} skeleton={<SkeletonPage />} onRetry={history.refetch}>
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <h1 className="text-3xl">{item.data?.title}: history</h1>
        <div className="flex flex-wrap gap-2 text-[12px] font-semibold">
          <span className="rounded-lg bg-info-50 px-3 py-1.5 text-info-600">Revision: every save</span>
          <span className="rounded-lg bg-forest-100 px-3 py-1.5 text-forest-800">Version: a published change</span>
          <span className="rounded-lg bg-ok-50 px-3 py-1.5 text-ok-600">Review: owner confirms it is right</span>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Stagger className="space-y-2">
          {history.data?.map((h) => {
            const label = h.label.replace('Version ', '')
            const active = h.kind === 'version' && pair?.[1] === label
            return (
              <button key={h.id} disabled={h.kind !== 'version'} onClick={() => { const i = versions.indexOf(label); setPair([versions[i + 1] ?? label, label]) }}
                className={cn('flex w-full items-start gap-3 rounded-xl border bg-surface p-3.5 text-left', active ? 'border-2 border-forest-700 bg-forest-50' : 'border-line')}>
                <span className={cn('mt-1 size-6 shrink-0 rounded-full', dot[h.kind])} />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap justify-between gap-x-3"><b className={h.kind === 'revision' ? 'text-info-600' : h.kind === 'review' ? 'text-ok-600' : 'text-forest-800'}>{h.label}</b>
                    <span className="text-[12px] text-ink-600">{fmt.date(h.at)}{h.by_name && ` · ${h.by_name}`}</span></span>
                  <span className="mt-0.5 flex flex-wrap justify-between gap-x-3 text-sm"><span>{h.summary}</span>{h.approved_by_name && <span className="text-[12px] text-ink-600">Approved by {h.approved_by_name}</span>}</span>
                </span>
              </button>
            )
          })}
        </Stagger>
        <div className="lg:sticky lg:top-20 lg:self-start">
          <SectionTitle>{pair ? `Compare: version ${pair[0]} and version ${pair[1]}` : 'Compare versions'}</SectionTitle>
          <Card className="space-y-1.5 text-sm">
            {!compare.data && <p className="text-ink-600">{versions.length < 2 ? 'Only one version so far.' : 'Choose a version on the left.'}</p>}
            {compare.data?.lines.map((l, i) => (
              <p key={i} className={cn('rounded-md px-3 py-1.5', l.op === 'add' && 'bg-ok-50 font-semibold text-ok-600', l.op === 'remove' && 'bg-bad-50 text-bad-600', l.op === 'same' && 'text-ink-600')}>
                {l.op === 'add' ? '+ ' : l.op === 'remove' ? '− ' : ''}{l.text}
              </p>
            ))}
            {compare.data?.change_note && <p className="pt-2 italic">Change note: “{compare.data.change_note}”</p>}
          </Card>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {item.data?.can_publish && pair && <Button variant="outline" loading={act.isPending} onClick={() => act.mutate({ action: `restore/${pair[0]}` }, { onSuccess: () => navigate(`/knowledge/items/${id}`) })}>Restore version {pair[0]}</Button>}
            <Button onClick={() => navigate(`/knowledge/items/${id}`)}>Back to the page</Button>
          </div>
          <p className="mt-2 text-[13px] italic text-ink-600">Restoring makes a new version. Nothing is ever overwritten.</p>
        </div>
      </div>
    </QueryState>
  )
}
