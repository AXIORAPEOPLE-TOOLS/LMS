import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useApiMutation } from './client'
import { keys } from './learner'
import type {
  AdminHome, Audience, BulkResult, CourseDetail, CourseSummary, Department, JobRole, ReportResult, ReviewCase,
  ReviewQueueItem, Session, Skill, Team, TestInfo, UserRow, UUID, Workflow, WorkflowRun,
} from './types'

// ---- manager --------------------------------------------------------------------------
export const useTeam = () => useQuery({ queryKey: ['team'], queryFn: () => api.get<Team>('/team') })
export const useNudge = () =>
  useApiMutation((body: { user_id: UUID; item?: string }) => api.post('/team/nudge', body), { success: 'Nudge sent', invalidate: [['team']] })
export const useApprovePathway = () =>
  useApiMutation((id: UUID) => api.post(`/pathways/${id}/approve`), { success: 'Pathway approved', invalidate: [['team']] })
export const useSignOff = () =>
  useApiMutation(({ id, approve }: { id: UUID; approve: boolean }) => api.post(`/pathway-items/${id}/sign-off`, { approve }),
    { success: (_, v) => (v.approve ? 'Signed off' : 'Sent back for more practice'), invalidate: [['team']] })

// ---- catalogue data ---------------------------------------------------------------------
export const useDepartments = () => useQuery({ queryKey: ['departments'], queryFn: () => api.get<Department[]>('/departments'), staleTime: 10 * 60_000 })
export const useJobRoles = () => useQuery({ queryKey: ['job-roles'], queryFn: () => api.get<JobRole[]>('/job-roles'), staleTime: 10 * 60_000 })
export const useSkills = () => useQuery({ queryKey: ['skills'], queryFn: () => api.get<Skill[]>('/skills'), staleTime: 10 * 60_000 })
/** Name + department directory, available to everyone (pickers). */
export const usePeople = () =>
  useQuery({ queryKey: ['people'], queryFn: () => api.get<{ id: UUID; full_name: string; department_id: UUID | null }[]>('/people'), staleTime: 5 * 60_000 })
export const useUsers = (q?: string) => useQuery({ queryKey: ['users', q], queryFn: () => api.get<UserRow[]>('/users', { q }) })
export const useRoleDetail = (id?: UUID) =>
  useQuery({ queryKey: ['job-roles', id], enabled: !!id, queryFn: () => api.get<{ id: UUID; name: string; people_count: number; skills: { skill_id: UUID; skill_name: string; required_level: number }[] }>(`/job-roles/${id}`) })
export const useSkillRanking = (skillId?: UUID) =>
  useQuery({ queryKey: ['ranking', skillId], enabled: !!skillId, queryFn: () => api.get<{ skill_name: string; rows: { rank: number; name: string; score: number; level: number; department: string | null }[] }>(`/skills/${skillId}/ranking`) })

// ---- admin home -------------------------------------------------------------------------
export const useAdminHome = () => useQuery({ queryKey: ['admin', 'home'], queryFn: () => api.get<AdminHome>('/admin/home'), refetchInterval: 30_000 })

// ---- people upload (A-02) ---------------------------------------------------------------
export interface UploadRow { row: number; full_name: string; email: string; job_title: string; department: string | null; status: 'ready' | 'needs_role' | 'error'; job_role_id: UUID | null; suggested_role_id: UUID | null; suggested_role_name: string | null; message: string | null }
export const usePreviewUpload = () =>
  useApiMutation((file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload<{ rows: UploadRow[]; ready: number; needs_role: number; errors: number }>('/users/upload/preview', form)
  })
export const useCommitUpload = () =>
  useApiMutation((rows: { full_name: string; email: string; job_role_id: UUID; department?: string | null }[]) =>
    api.post<{ created: number; skipped: number }>('/users/upload/commit', { rows }),
    { invalidate: [['users']], success: (d) => `${d.created} people added` })

// ---- courses (A-05) -----------------------------------------------------------------------
export const useAdminCourses = () => useQuery({ queryKey: ['admin', 'courses'], queryFn: () => api.get<CourseSummary[]>('/admin/courses') })
export const useAdminCourse = (id?: UUID) =>
  useQuery({
    queryKey: ['admin', 'courses', id], enabled: !!id, queryFn: () => api.get<CourseDetail>(`/admin/courses/${id}`),
    refetchInterval: (query) => (query.state.data?.status === 'drafting' ? 2_000 : false),
  })
export const useDraftCourse = () =>
  useApiMutation(({ file, options }: { file: File; options: Record<string, unknown> }) => {
    const form = new FormData()
    form.append('file', file)
    form.append('options', JSON.stringify(options))
    return api.upload<CourseSummary>('/admin/courses/drafts', form)
  }, { invalidate: [['admin', 'courses']] })
export const useReplaceContent = (id: UUID) =>
  useApiMutation((body: { lessons: unknown[]; questions: unknown[] }) => api.put(`/admin/courses/${id}/content`, body),
    { invalidate: [['admin', 'courses', id]], success: 'Draft saved' })
export const useSubmitCourse = (id: UUID) =>
  useApiMutation((approverId: UUID) => api.post(`/admin/courses/${id}/submit`, { approver_id: approverId }),
    { invalidate: [['admin', 'courses']], success: 'Sent to the expert for approval' })
export const useReviewCourse = (id: UUID) =>
  useApiMutation((body: { approve: boolean; note: string }) => api.post(`/admin/courses/${id}/review`, body),
    { invalidate: [['admin', 'courses'], keys.courses], success: (_, v) => (v.approve ? 'Approved and published' : 'Sent back with notes') })

// ---- assignments, tests, sessions -----------------------------------------------------
export const useAssignPreview = () =>
  useApiMutation((body: { course_id: UUID; audience: Audience; due_on?: string; is_mandatory?: boolean }) =>
    api.post<{ course_title: string; audience_label: string; new_people: number; already_assigned: number; sample_names: string[]; message_preview: string }>('/admin/assignments/preview', body))
export const useAssign = () =>
  useApiMutation((body: { course_id: UUID; audience: Audience; due_on?: string; is_mandatory?: boolean }) => api.post<BulkResult>('/admin/assignments', body),
    { invalidate: [['admin', 'home']] })
export const useUndo = () =>
  useApiMutation((bulkId: UUID) => api.post<{ undone: number }>(`/admin/bulk/${bulkId}/undo`), { success: (d) => `Undone for ${d.undone} people` })
export const useAdminTests = () => useQuery({ queryKey: ['admin', 'tests'], queryFn: () => api.get<TestInfo[]>('/admin/tests') })
export const useCampaignPreview = () =>
  useApiMutation((body: { test_ids: UUID[]; audience: Audience; due_on?: string }) =>
    api.post<{ audience_label: string; people: number; tests: number; new_invites: number }>('/admin/tests/campaign/preview', body))
export const useSendCampaign = () =>
  useApiMutation((body: { test_ids: UUID[]; audience: Audience; due_on?: string }) => api.post<BulkResult>('/admin/tests/campaign', body))
export const useAdminSessions = () => useQuery({ queryKey: ['admin', 'sessions'], queryFn: () => api.get<Session[]>('/admin/sessions') })
export const useCreateSession = () =>
  useApiMutation((body: Record<string, unknown>) => api.post<Session>('/admin/sessions', body), { invalidate: [['admin', 'sessions']] })
export const useSendInvitations = () =>
  useApiMutation((id: UUID) => api.post<BulkResult>(`/admin/sessions/${id}/send`), { invalidate: [['admin', 'sessions']] })
export const useReminderPreview = () =>
  useQuery({ queryKey: ['admin', 'reminders'], queryFn: () => api.get<{ name: string; local_time: string; channels: string; items: string[] }[]>('/admin/reminders/preview') })
export const useReminderRules = () =>
  useQuery({ queryKey: ['admin', 'reminders', 'rules'], queryFn: () => api.get<{ quiet_start: string; quiet_end: string; allow_weekends: boolean; max_per_day: number; max_per_week: number; paused: boolean }>('/admin/reminders/rules') })
export const useSendReminders = () =>
  useApiMutation(() => api.post<{ created: number }>('/admin/reminders/send'), { invalidate: [['admin', 'reminders']], success: (d) => `${d.created} reminders scheduled` })

// ---- workflows (A-07) ------------------------------------------------------------------------
export const useWorkflows = () => useQuery({ queryKey: ['admin', 'workflows'], queryFn: () => api.get<{ paused: boolean; workflows: Workflow[]; pending_runs: number }>('/admin/workflows') })
export const useWorkflowRuns = (status?: string) => useQuery({ queryKey: ['admin', 'workflows', 'runs', status], queryFn: () => api.get<WorkflowRun[]>('/admin/workflows/runs', { status }) })
export const useSetMode = () =>
  useApiMutation(({ id, mode }: { id: UUID; mode: string }) => api.put(`/admin/workflows/${id}/mode`, { mode }), { invalidate: [['admin', 'workflows']] })
export const useSetEnabled = () =>
  useApiMutation(({ id, enabled }: { id: UUID; enabled: boolean }) => api.put(`/admin/workflows/${id}/enabled`, { enabled }), { invalidate: [['admin', 'workflows']], success: (_, v) => (v.enabled ? 'Turned on' : 'Turned off') })
export const usePauseAll = () =>
  useApiMutation((paused: boolean) => api.put('/admin/workflows/pause', { paused }), { invalidate: [['admin', 'workflows']], success: (_, p) => (p ? 'All automatic sends stopped' : 'Automatic sends are back on') })
export const useWorkflowPreview = () =>
  useApiMutation((id: UUID) => api.post<{ lines: string[]; people: number }>(`/admin/workflows/${id}/preview`, { context: { since_days: 30 } }))
export const useRunWorkflow = () =>
  useApiMutation((id: UUID) => api.post<WorkflowRun>(`/admin/workflows/${id}/run`, { context: { since_days: 30 } }), { invalidate: [['admin', 'workflows']], success: 'Done' })
export const useDecideRun = () =>
  useApiMutation(({ id, approve }: { id: UUID; approve: boolean }) => api.post<WorkflowRun>(`/admin/workflows/runs/${id}/decision`, { approve }),
    { invalidate: [['admin', 'workflows']], success: (_, v) => (v.approve ? 'Approved and sent' : 'Cancelled') })

// ---- reports (A-08) ----------------------------------------------------------------------------
export const useReportCatalogue = () =>
  useQuery({ queryKey: ['reports'], queryFn: () => api.get<{ group: string; reports: { id: string; name: string; description: string }[] }[]>('/reports') })
export const useReport = (id?: string, filters: Record<string, string> = {}) =>
  useQuery({ queryKey: ['reports', id, filters], enabled: !!id, queryFn: () => api.get<ReportResult>(`/reports/${id}`, filters) })
export const useScheduleReport = () =>
  useApiMutation(({ id, frequency, format }: { id: string; frequency: string; format: string }) => api.post(`/reports/${id}/schedule`, { frequency, format }),
    { success: 'Scheduled. You will get it in your messages.' })

// ---- proctoring (A-09) -----------------------------------------------------------------------
export const useReviewQueue = () => useQuery({ queryKey: ['proctoring'], queryFn: () => api.get<ReviewQueueItem[]>('/proctoring/queue') })
export const useReviewCase = (id?: UUID) =>
  useQuery({ queryKey: ['proctoring', id], enabled: !!id, queryFn: () => api.get<ReviewCase>(`/proctoring/attempts/${id}`) })
export const useDecide = () =>
  useApiMutation(({ id, decision, note }: { id: UUID; decision: string; note: string }) => api.post(`/proctoring/attempts/${id}/decision`, { decision, note }),
    { invalidate: [['proctoring']], success: 'Decision saved' })

// ---- settings ---------------------------------------------------------------------------------
export const useSettings = () =>
  useQuery({ queryKey: ['settings'], queryFn: () => api.get<{ key: string; value: unknown; default: unknown; description: string; is_overridden: boolean }[]>('/settings') })
export const useSaveSetting = () =>
  useApiMutation(({ key, value }: { key: string; value: unknown }) => api.put(`/settings/${key}`, { value }), { invalidate: [['settings']], success: 'Setting saved' })
