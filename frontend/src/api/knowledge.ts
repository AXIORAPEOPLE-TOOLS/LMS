import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useApiMutation } from './client'
import type {
  KAccess, KCompare, KFunctionDashboard, KHistoryEntry, KHome, KItem, KItemDetail, KLeaderDashboard, KLibrary, KMyItems,
  KSuggestion, UUID,
} from './types'

const k = {
  home: ['k', 'home'] as const,
  library: (f: object) => ['k', 'library', f] as const,
  item: (id: UUID) => ['k', 'item', id] as const,
  myItems: ['k', 'my-items'] as const,
}
const ALL = [['k']] as const

export const useKHome = () => useQuery({ queryKey: k.home, queryFn: () => api.get<KHome>('/knowledge/home') })
export const useLibrary = (filters: Record<string, string | undefined>) =>
  useQuery({ queryKey: k.library(filters), queryFn: () => api.get<KLibrary>('/knowledge/library', filters), placeholderData: (prev) => prev })
export const useKItem = (id?: UUID) => useQuery({ queryKey: k.item(id ?? ''), enabled: !!id, queryFn: () => api.get<KItemDetail>(`/knowledge/items/${id}`) })
export const useKMyItems = () => useQuery({ queryKey: k.myItems, queryFn: () => api.get<KMyItems>('/knowledge/my-items') })
export const useKSearch = (q: string) =>
  useQuery({ queryKey: ['k', 'search', q], enabled: q.trim().length > 1, queryFn: () => api.get<{ item: KItem; snippet: string }[]>('/knowledge/search', { q }) })
export const useKHistory = (id?: UUID) => useQuery({ queryKey: ['k', 'history', id], enabled: !!id, queryFn: () => api.get<KHistoryEntry[]>(`/knowledge/items/${id}/history`) })
export const useKCompare = (id?: UUID, from?: string, to?: string) =>
  useQuery({ queryKey: ['k', 'compare', id, from, to], enabled: !!id && !!from && !!to && from !== to,
    queryFn: () => api.get<KCompare>(`/knowledge/items/${id}/compare`, { from_version: from, to_version: to }) })
export const useKAccess = (id?: UUID) => useQuery({ queryKey: ['k', 'access', id], enabled: !!id, queryFn: () => api.get<KAccess>(`/knowledge/items/${id}/access`) })
export const useKRows = (id?: UUID, filters: Record<string, string | undefined> = {}) =>
  useQuery({ queryKey: ['k', 'rows', id, filters], enabled: !!id, queryFn: () => api.get<{ columns: string[]; rows: { id: UUID; data: Record<string, string> }[] }>(`/knowledge/items/${id}/rows`, filters) })
export const useKDashboard = () => useQuery({ queryKey: ['k', 'dashboard'], queryFn: () => api.get<KLeaderDashboard>('/knowledge/dashboard') })
export const useKFunction = (id?: UUID) => useQuery({ queryKey: ['k', 'dashboard', id], enabled: !!id, queryFn: () => api.get<KFunctionDashboard>(`/knowledge/dashboard/${id}`) })
export const useKWithoutOwner = () => useQuery({ queryKey: ['k', 'without-owner'], queryFn: () => api.get<KItem[]>('/knowledge/without-owner') })
export const useKRequests = () => useQuery({ queryKey: ['k', 'requests'], queryFn: () => api.get<KAccess['requests']>('/knowledge/access-requests') })

export const useAsk = () => useApiMutation((question: string) => api.post<{ answer: string; sources: KItem[] }>('/knowledge/ask', { question }))
export const useKUpload = () =>
  useApiMutation((file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload<{ id: UUID; filename: string; size_bytes: number; has_text: boolean }>('/knowledge/uploads', form)
  })
export const useKSuggest = () => useApiMutation((body: { title?: string; text?: string; upload_id?: UUID; link_url?: string }) => api.post<KSuggestion>('/knowledge/suggest', body))
export const useKCreate = () => useApiMutation((body: Record<string, unknown>) => api.post<KItemDetail>('/knowledge/items', body), { invalidate: [...ALL], success: 'Saved' })
export const useKUpdate = (id: UUID) =>
  useApiMutation((body: { title?: string; body?: string; change_note?: string; is_major?: boolean; publish?: boolean }) => api.put<KItemDetail>(`/knowledge/items/${id}`, body),
    { invalidate: [...ALL], success: (d, v) => (v.publish === false ? 'Draft saved' : d.pending_change ? 'Sent to the owner for approval' : `Published version ${d.version}`) })
export const useKAction = (id: UUID) =>
  useApiMutation(({ action, body }: { action: 'verify' | 'snooze' | 'hand-over' | 'archive' | `restore/${string}` | 'course'; body?: unknown }) =>
    api.post<KItemDetail>(`/knowledge/items/${id}/${action}`, body ?? {}), {
    invalidate: [...ALL],
    success: (_, v) => ({ verify: 'Thanks — marked as still correct', snooze: 'Snoozed for 7 days', 'hand-over': 'Handed over', archive: 'Archived', course: 'A course draft is being prepared' } as Record<string, string>)[v.action] ?? 'Restored as a new version',
  })
export const useKSettings = (id: UUID) => useApiMutation((body: Record<string, unknown>) => api.patch<KItemDetail>(`/knowledge/items/${id}/settings`, body), { invalidate: [...ALL], success: 'Saved' })
export const useKRevisionDecision = () =>
  useApiMutation(({ id, approve }: { id: UUID; approve: boolean }) => api.post(`/knowledge/revisions/${id}/decision`, { approve }), { invalidate: [...ALL], success: (_, v) => (v.approve ? 'Change published' : 'Change declined') })
export const useKRequestAccess = (id: UUID) =>
  useApiMutation((body: { role: string; reason: string }) => api.post(`/knowledge/items/${id}/access-requests`, body), { success: 'Request sent to the owner' })
export const useKAccessDecision = () =>
  useApiMutation(({ id, approve }: { id: UUID; approve: boolean }) => api.post(`/knowledge/access-requests/${id}/decision`, { approve }), { invalidate: [...ALL], success: (_, v) => (v.approve ? 'Access given' : 'Declined') })
export const useKGrant = (id: UUID) =>
  useApiMutation((body: { principal_type: string; principal_id: UUID; role: string }) => api.post(`/knowledge/items/${id}/access`, body), { invalidate: [...ALL], success: 'Access updated' })
export const useKAssignOwner = () =>
  useApiMutation(({ id, ownerId }: { id: UUID; ownerId: UUID }) => api.post(`/knowledge/items/${id}/owner`, { owner_id: ownerId }), { invalidate: [...ALL], success: 'Owner assigned' })
export const useKBulk = () =>
  useApiMutation((body: { item_ids: UUID[]; action: string; owner_id?: UUID; review_on?: string; category_id?: UUID }) => api.post<{ count: number }>('/knowledge/bulk', body),
    { invalidate: [...ALL], success: (d) => `Done for ${d.count} items` })
export const useKCategory = () =>
  useApiMutation(({ id, body, merge }: { id?: UUID; body: Record<string, unknown>; merge?: boolean }) =>
    merge ? api.post(`/knowledge/categories/${id}/merge`, body) : id ? api.patch(`/knowledge/categories/${id}`, body) : api.post('/knowledge/categories', body),
    { invalidate: [...ALL], success: 'Categories updated' })
export const useKRow = (itemId: UUID) =>
  useApiMutation(({ rowId, data }: { rowId?: UUID; data: Record<string, string> }) =>
    rowId ? api.patch(`/knowledge/items/${itemId}/rows/${rowId}`, { data }) : api.post(`/knowledge/items/${itemId}/rows`, { data }),
    { invalidate: [['k', 'rows', itemId]], success: 'Saved' })
export const useKImportRows = (itemId: UUID) =>
  useApiMutation((file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload<{ count: number }>(`/knowledge/items/${itemId}/rows/import`, form)
  }, { invalidate: [['k']], success: (d) => `${d.count} rows imported` })
