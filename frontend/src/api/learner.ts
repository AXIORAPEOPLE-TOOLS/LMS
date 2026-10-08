import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useApiMutation } from './client'
import type {
  Assignment, Attempt, AttemptResult, Badges, Board, CareerDetail, CareerMap, Certificate, Challenge,
  CourseDetail, CourseSummary, Home, Me, MySkill, MyTest, Notification, Pathway, Profile, Session, TestInfo, UUID,
} from './types'

export const keys = {
  me: ['me'] as const,
  home: ['me', 'home'] as const,
  pathway: ['me', 'pathway'] as const,
  assignments: ['me', 'assignments'] as const,
  tests: ['me', 'tests'] as const,
  skills: ['me', 'skills'] as const,
  certificates: ['me', 'certificates'] as const,
  career: ['me', 'career'] as const,
  profile: ['me', 'profile'] as const,
  badges: ['me', 'badges'] as const,
  challenges: ['challenges'] as const,
  notifications: ['me', 'notifications'] as const,
  sessions: ['me', 'sessions'] as const,
  courses: ['courses'] as const,
  course: (id: UUID) => ['courses', id] as const,
  board: (board: string, params: object) => ['boards', board, params] as const,
}

export const useMe = (enabled = true) => useQuery({ queryKey: keys.me, queryFn: () => api.get<Me>('/me'), enabled, staleTime: 5 * 60_000 })
export const useHome = () => useQuery({ queryKey: keys.home, queryFn: () => api.get<Home>('/me/home') })
export const usePathway = () => useQuery({ queryKey: keys.pathway, queryFn: () => api.get<Pathway | null>('/me/pathway') })
export const useAssignments = () => useQuery({ queryKey: keys.assignments, queryFn: () => api.get<Assignment[]>('/me/assignments') })
export const useMyTests = () => useQuery({ queryKey: keys.tests, queryFn: () => api.get<MyTest[]>('/me/tests') })
export const useMySkills = () => useQuery({ queryKey: keys.skills, queryFn: () => api.get<MySkill[]>('/me/skills') })
export const useCertificates = () => useQuery({ queryKey: keys.certificates, queryFn: () => api.get<Certificate[]>('/me/certificates') })
export const useCareer = () => useQuery({ queryKey: keys.career, queryFn: () => api.get<CareerMap>('/me/career') })
export const useCareerDetail = (roleId?: UUID) =>
  useQuery({ queryKey: ['me', 'career', roleId], queryFn: () => api.get<CareerDetail>(`/me/career/${roleId}`), enabled: !!roleId })
export const useProfile = () => useQuery({ queryKey: keys.profile, queryFn: () => api.get<Profile>('/me/profile') })
export const useBadges = () => useQuery({ queryKey: keys.badges, queryFn: () => api.get<Badges>('/me/badges') })
export const useChallenges = () => useQuery({ queryKey: keys.challenges, queryFn: () => api.get<Challenge[]>('/challenges') })
export const useSessions = () => useQuery({ queryKey: keys.sessions, queryFn: () => api.get<Session[]>('/me/sessions') })
export const useNotifications = () =>
  useQuery({ queryKey: keys.notifications, queryFn: () => api.get<{ items: Notification[]; unread: number }>('/me/notifications'), refetchInterval: 60_000 })
export const useCourses = (q?: string, skillId?: string) =>
  useQuery({ queryKey: [...keys.courses, q, skillId], queryFn: () => api.get<CourseSummary[]>('/courses', { q, skill_id: skillId }) })
export const useCourse = (id?: UUID) => useQuery({ queryKey: keys.course(id ?? ''), queryFn: () => api.get<CourseDetail>(`/courses/${id}`), enabled: !!id })
export const useTestInfo = (id?: UUID) => useQuery({ queryKey: ['tests', id], queryFn: () => api.get<TestInfo>(`/tests/${id}`), enabled: !!id })
export const useAttempt = (id?: UUID) => useQuery({ queryKey: ['attempts', id], queryFn: () => api.get<Attempt>(`/attempts/${id}`), enabled: !!id, staleTime: 0 })
export const useAttemptResult = (id?: UUID) =>
  useQuery({ queryKey: ['attempts', id, 'result'], queryFn: () => api.get<AttemptResult>(`/attempts/${id}/result`), enabled: !!id })
export const useBoard = (board: string, params: { scope?: string; period?: string; skill_id?: string }) =>
  useQuery({ queryKey: keys.board(board, params), queryFn: () => api.get<Board>(`/leaderboards/${board}`, params), refetchInterval: 15_000 })
export const useCompliance = () =>
  useQuery({ queryKey: ['boards', 'compliance'], queryFn: () => api.get<{ rows: { department: string; on_time_pct: number; assigned: number }[] }>('/leaderboards/compliance') })

// ---- mutations --------------------------------------------------------------------------
export const useUpdatePreferences = () =>
  useApiMutation((body: Partial<Pick<Me, 'locale' | 'show_name_on_boards' | 'reminder_window' | 'reminder_channels' | 'hours_per_week'>>) =>
    api.patch<Me>('/me/preferences', body), { invalidate: [keys.me], success: 'Saved' })

export const useCompleteLesson = (courseId: UUID) =>
  useApiMutation((lessonId: UUID) => api.post<{ progress_pct: number; course_completed: boolean; next_lesson_id: UUID | null; quiz_pending: boolean }>(`/lessons/${lessonId}/complete`),
    { invalidate: [keys.course(courseId), keys.home, keys.assignments, keys.pathway, keys.profile] })

export const useSimulation = () =>
  useApiMutation(({ lessonId, order }: { lessonId: UUID; order: string[] }) =>
    api.post<{ correct: boolean; first_wrong_step: number | null; message: string; points: number }>(`/lessons/${lessonId}/simulation`, { order }))

export const useSubmitQuiz = (courseId: UUID) =>
  useApiMutation((answers: Record<UUID, number>) =>
    api.post<{ score: number; passed: boolean; pass_mark: number | null; results: { question_id: UUID; correct: boolean; right_index: number; reason: string }[]; course_completed: boolean }>(`/courses/${courseId}/quiz`, { answers }),
    { invalidate: [keys.course(courseId), keys.home, keys.assignments, keys.certificates, keys.profile] })

export const useStartAttempt = () =>
  useApiMutation(({ testId, consent }: { testId: UUID; consent: boolean }) => api.post<Attempt>(`/tests/${testId}/attempts`, { consent }))
export const useAnswer = (attemptId: UUID) =>
  useApiMutation(({ questionId, option }: { questionId: UUID; option: number }) => api.put(`/attempts/${attemptId}/answer`, { question_id: questionId, option_index: option }), { silentError: true })
export const useSubmitAttempt = () =>
  useApiMutation((attemptId: UUID) => api.post<AttemptResult>(`/attempts/${attemptId}/submit`),
    { invalidate: [keys.tests, keys.skills, keys.home, keys.pathway, keys.certificates, keys.profile] })
export const useBookInPerson = () =>
  useApiMutation(({ testId, dates }: { testId: UUID; dates: string }) => api.post(`/tests/${testId}/in-person`, { preferred_dates: dates }),
    { success: 'Request sent. HR will confirm a date with you.' })
export const useAppeal = () =>
  useApiMutation(({ attemptId, note }: { attemptId: UUID; note: string }) => api.post(`/attempts/${attemptId}/appeal`, { note }),
    { success: 'Appeal sent. A different reviewer will decide.' })

export const useGeneratePathway = () =>
  useApiMutation((targetRoleId?: UUID) => api.post<Pathway>('/me/pathway/generate', { target_role_id: targetRoleId ?? null }),
    { invalidate: [keys.pathway, keys.home], success: 'Your pathway is ready' })
export const usePathwayStep = () =>
  useApiMutation(({ itemId, action, evidence }: { itemId: UUID; action: 'learned' | 'connected' | 'evidence'; evidence?: string }) =>
    api.post(`/me/pathway/items/${itemId}/${action}`, action === 'evidence' ? { evidence } : {}),
    { invalidate: [keys.pathway, keys.home, keys.tests], success: (_, v) => (v.action === 'evidence' ? 'Sent to your manager to sign off' : 'Step done') })

export const useCareerAction = () =>
  useApiMutation(({ roleId, action }: { roleId: UUID; action: 'add-to-pathway' | 'talk-to-manager' }) => api.post(`/me/career/${roleId}/${action}`),
    { invalidate: [keys.pathway, keys.home], success: (_, v) => (v.action === 'add-to-pathway' ? 'Added to your pathway' : 'Your manager has been told') })

export const useJoinChallenge = () =>
  useApiMutation((id: UUID) => api.post<Challenge>(`/challenges/${id}/join`), { invalidate: [keys.challenges], success: 'You joined the challenge' })

export const useRsvp = () =>
  useApiMutation(({ sessionId, accept }: { sessionId: UUID; accept: boolean }) => api.post<Session>(`/sessions/${sessionId}/rsvp`, { accept }),
    { invalidate: [keys.sessions, keys.home, keys.notifications], success: (_, v) => (v.accept ? 'See you there' : 'Thanks for letting us know') })

export const useMarkRead = () =>
  useApiMutation((id: UUID | 'all') => (id === 'all' ? api.post('/me/notifications/read-all') : api.post(`/me/notifications/${id}/read`)),
    { invalidate: [keys.notifications], silentError: true })
