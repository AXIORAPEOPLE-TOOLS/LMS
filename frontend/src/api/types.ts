/** Types mirroring the backend schemas (see /api/docs). */

export type UUID = string

export interface Me {
  id: UUID
  email: string
  full_name: string
  employee_code: string | null
  system_roles: string[]
  department_id: UUID | null
  department_name: string | null
  job_role_id: UUID | null
  job_role_name: string | null
  manager_id: UUID | null
  manager_name: string | null
  locale: 'en' | 'hi'
  show_name_on_boards: boolean
  reminder_window: [string, string]
  reminder_channels: { in_app?: boolean; email?: boolean; whatsapp?: boolean }
  hours_per_week: number
}

export interface Health {
  status: string
  mode: 'full' | 'limited' | 'offline'
  components: Record<string, string>
  degraded: { name: string; label: string; fallback: string }[]
}

export interface NextStep {
  kind: 'assignment' | 'pathway' | 'skill_check' | 'explore'
  title: string
  detail: string
  action_label: string
  href: string
  is_overdue: boolean
}

export interface ComingUp {
  kind: 'session' | 'skill_check' | 'assignment'
  title: string
  detail: string
  href: string
}

export interface Home {
  first_name: string
  level_label: string | null
  streak_days: number
  points: number
  next_step: NextStep
  pathway_progress_pct: number | null
  pathway_wave: number | null
  pathway_status: string | null
  coming_up: ComingUp[]
}

export interface PathwayItem {
  id: UUID
  wave: number
  position: number
  skill_id: UUID
  skill_name: string
  from_level: number
  to_level: number
  step: 'learn' | 'practise' | 'connect' | 'prove' | 'done'
  course_id: UUID | null
  course_title: string | null
  mentor_name: string | null
  practise_task: string
  practise_evidence: string | null
  waiting_for_signoff: boolean
  certificate_on_pass: boolean
  estimated_hours: number
}

export interface Wave {
  number: number
  status: 'active' | 'locked' | 'done'
  hours: number
  weeks: number
  progress_pct: number
  items: PathwayItem[]
}

export interface Pathway {
  id: UUID
  user_id: UUID
  status: 'pending_approval' | 'active' | 'completed'
  hours_per_week: number
  target_role_name: string | null
  approved_by_name: string | null
  current_wave: number | null
  total_waves: number
  progress_pct: number
  waves: Wave[]
  next_step: { item_id: UUID; step: string; title: string; description: string; action_label: string; href: string | null } | null
}

export interface CourseSummary {
  id: UUID
  title: string
  description: string
  skill_id: UUID | null
  skill_name: string | null
  from_level: number
  to_level: number
  kind: 'self_paced' | 'certification'
  status: string
  is_mandatory: boolean
  pass_mark: number | null
  duration_minutes: number
  languages: string[]
  has_video: boolean
  has_simulation: boolean
  lesson_count: number
}

export interface Scenario {
  title?: string
  image?: string | null
  ar_supported?: boolean
  steps: { id: string; label: string; x?: number; y?: number }[]
  correct_order: string[]
  feedback?: string
}

export interface Lesson {
  id: UUID
  position: number
  title: string
  kind: 'video' | 'reading' | 'simulation'
  summary: string
  body: string
  source_ref: string | null
  duration_minutes: number
  media_url: string | null
  captions: Record<string, { at: number; text: string }[]>
  scenario: Scenario | null
  completed: boolean
}

export interface Question {
  id: UUID
  position: number
  text: string
  options: string[]
  answer_index?: number
  reason?: string
}

export interface CourseDetail extends CourseSummary {
  lessons: Lesson[]
  question_count: number
  my_progress: {
    assignment_id: UUID | null
    status: string
    progress_pct: number
    due_on: string | null
    quiz_score: number | null
    completed_lessons: number
    next_lesson_id: UUID | null
  } | null
  source_filename: string | null
  approver_id: UUID | null
  review_note: string | null
  final_test_id: UUID | null
  questions?: Question[]
}

export interface Assignment {
  id: UUID
  course_id: UUID
  course_title: string
  course_kind: string
  duration_minutes: number
  due_on: string | null
  status: string
  is_mandatory: boolean
  progress_pct: number
  source: string
  is_overdue: boolean
}

export interface TestInfo {
  id: UUID
  skill_id: UUID | null
  skill_name: string | null
  title: string
  instructions: string
  duration_minutes: number
  proctoring: 'none' | 'camera'
  pass_mark: number | null
  is_mandatory: boolean
  question_count: number
}

export interface MyTest {
  invite_id: UUID | null
  test: TestInfo
  due_on: string | null
  status: 'pending' | 'in_progress' | 'done'
  attempt_id: UUID | null
  last_score: number | null
  last_level: number | null
}

export interface Attempt {
  id: UUID
  test_id: UUID
  test_title: string
  status: string
  proctoring: 'none' | 'camera'
  snapshot_seconds: number
  questions: { id: UUID; text: string; options: string[]; selected: number | null }[]
  answered: number
  total: number
  seconds_left: number
}

export interface AttemptResult {
  attempt_id: UUID
  status: string
  score: number
  level: number | null
  level_name: string | null
  passed: boolean | null
  pass_mark: number | null
  rank: number | null
  out_of: number | null
  top_percent: number | null
  required_level: number | null
  meets_requirement: boolean | null
  skills_left_to_check: number
  message: string
  certificate_id: UUID | null
}

export interface Certificate {
  id: UUID
  title: string
  code: string
  issued_at: string
  valid_until: string | null
  status: 'valid' | 'expired' | 'revoked'
  score: number | null
}

export interface MySkill {
  skill_id: UUID
  skill_name: string
  category: string
  required_level: number | null
  current_level: number | null
  score: number | null
  gap: number
  rank: number | null
  out_of: number | null
  top_percent: number | null
}

export interface CareerMap {
  current_role_id: UUID | null
  current_role_name: string | null
  role_ready_skills: number
  core_skills: number
  options: { role_id: UUID; role_name: string; direction: 'up' | 'side'; readiness_pct: number | null; needs_more_tests: boolean }[]
}

export interface CareerDetail {
  role_id: UUID
  role_name: string
  readiness_pct: number
  tested: number
  total: number
  skills_to_close: { skill_id: UUID; skill_name: string; levels_to_go: number }[]
  test_next: string[]
  weeks: number
  hours_per_week: number
  can_estimate: boolean
}

export interface Profile {
  full_name: string
  initials: string
  skill_level_name: string | null
  points: number
  level_name: string
  next_level_name: string | null
  points_to_next: number | null
  level_progress_pct: number
  streak_days: number
  levels_gained: number
  certificates: number
  week_points: number
  week_lessons: number
  week_tests: number
  show_name_on_boards: boolean
}

export interface Badges {
  earned: number
  total: number
  badges: { code: string; name: string; description: string; earned: boolean }[]
}

export interface Challenge {
  id: UUID
  title: string
  description: string
  goal_pct: number
  team_pct: number
  days_left: number
  reward_points: number
  joined: boolean
  members: number
  my_part: string[]
}

export interface Board {
  board: string
  title: string
  rows: { rank: number; user_id: UUID | null; name: string; department: string | null; value: number; display: string; change: number | null; is_me: boolean }[]
  version: string
}

export interface Notification {
  id: UUID
  kind: string
  title: string
  body: string
  link: string | null
  actions: { label: string; href?: string; action?: string; session_id?: string }[]
  created_at: string
  read_at: string | null
}

export interface Session {
  id: UUID
  title: string
  starts_at: string
  ends_at: string
  meeting_link: string | null
  location: string | null
  trainer_name: string | null
  audience_label: string
  invitations_sent_at: string | null
  accepted: number
  declined: number
  waiting: number
  my_status: string | null
}

export interface BulkResult {
  bulk_action_id: UUID
  count: number
  undo_until: string
  summary: string
}

export interface Audience {
  user_ids?: UUID[]
  job_role_id?: UUID | null
  department_id?: UUID | null
  everyone?: boolean
}

export interface Department { id: UUID; name: string }
export interface JobRole { id: UUID; code: string; name: string; family: string }
export interface Skill { id: UUID; code: string; name: string; category: string; is_mandatory: boolean }
export interface UserRow { id: UUID; email: string; full_name: string; system_roles: string[]; department_id: UUID | null; job_role_id: UUID | null; is_active: boolean; employee_code: string | null }

export interface Team {
  counts: { on_track: number; due_soon: number; overdue: number; to_approve: number; people: number }
  heatmap: { skills: { id: UUID; name: string }[]; rows: { user_id: UUID; name: string; levels: (number | null)[]; required: (number | null)[] }[] }
  attention: { user_id: UUID; name: string; item: string; detail: string; overdue_days: number | null }[]
  approvals: { kind: 'pathway' | 'practise'; id: UUID; title: string; detail: string }[]
}

export interface AdminHome {
  metrics: { key: string; label: string; value: string; change: number | null }[]
  attention: { text: string; href: string }[]
  content_gaps: { skill_id: UUID; skill_name: string; people: number; text: string }[]
}

export interface Workflow {
  id: UUID
  code: string
  name: string
  trigger_label: string
  condition_label: string
  action_labels: string[]
  approval_label: string
  mode: 'manual' | 'hybrid' | 'auto'
  is_enabled: boolean
}

export interface WorkflowRun {
  id: UUID
  workflow_id: UUID
  triggered_by: string
  status: string
  preview: { lines?: string[]; people?: number }
  result: { lines?: string[]; error?: string }
  created_at: string
}

export interface ReportColumn { key: string; label: string; kind: string; drill: boolean }
export interface ReportResult {
  id: string
  name: string
  group: string
  description: string
  filters: string[]
  columns: ReportColumn[]
  rows: Record<string, string | number | null>[]
  scope: 'team' | 'company'
}

export interface ReviewQueueItem { attempt_id: UUID; test_title: string; employee_code: string | null; flags: number; severity: 'low' | 'medium' | 'high'; is_appeal: boolean }
export interface ReviewCase {
  attempt_id: UUID
  test_title: string
  employee_code: string | null
  question_count: number
  score: number | null
  minutes: number
  duration_seconds: number
  flags: { id: UUID; kind: string; at_seconds: number; severity: string | null; count: number; has_image: boolean }[]
  status: string
  appeal_note: string | null
}

// ---- Knowledge Hub ----
export interface KItem {
  id: UUID
  title: string
  kind: string
  kind_label: string
  category_id: UUID | null
  category_path: string | null
  owner_id: UUID | null
  owner_name: string | null
  version: string
  status: 'verified' | 'due_soon' | 'overdue' | 'in_review' | 'draft' | 'archived'
  next_review_on: string | null
  is_critical: boolean
  visibility: string
  updated_at: string
}

export interface KItemDetail extends KItem {
  body: string
  link_url: string | null
  attachments: { name: string; upload_id?: string; size?: number }[]
  backup_owner_id: UUID | null
  backup_owner_name: string | null
  review_months: number
  last_verified_at: string | null
  snooze_count: number
  version_count: number
  list_columns: string[]
  linked_course_id: UUID | null
  my_role: string
  can_edit: boolean
  can_publish: boolean
  can_verify: boolean
  can_change_access: boolean
  pending_change: boolean
}

export interface KCategory { id: UUID; name: string; parent_id: UUID | null; head_id: UUID | null; item_count: number; path: string }

export interface KLibrary {
  total: number
  items: KItem[]
  kinds: { kind: string; label: string; count: number }[]
  categories: KCategory[]
}

export interface KMyItems {
  overdue: number
  due_soon: number
  waiting_for_me: number
  drafts: number
  items: { item: KItem; reason: 'overdue' | 'due_soon' | 'waiting_for_me' | 'draft'; detail: string; revision_id: UUID | null; can_snooze: boolean }[]
  coming_up: { when: string; text: string }[]
  backup_note: string | null
}

export interface KHome {
  types: { kind: string; label: string; count: number }[]
  spaces: KCategory[]
  recently_verified: KItem[]
  critical: KItem[]
  my_items: KMyItems
}

export interface KSuggestion {
  title: string
  kind: string
  kind_label: string
  category_id: UUID | null
  category_path: string | null
  owner_id: UUID | null
  owner_name: string | null
  backup_owner_id: UUID | null
  backup_owner_name: string | null
  review_on: string
  review_label: string
  visibility: string
  visibility_label: string
  similar_item_id: UUID | null
  similar_item_title: string | null
  similar_item_version: string | null
}

export interface KHistoryEntry { kind: 'version' | 'revision' | 'review'; id: UUID; label: string; summary: string; by_name: string | null; approved_by_name: string | null; at: string; status: string | null }
export interface KCompare { from_label: string; to_label: string; lines: { op: 'same' | 'add' | 'remove'; text: string }[]; change_note: string }
export interface KAccess {
  item_id: UUID
  item_title: string
  entries: { principal_type: string; principal_id: UUID | null; name: string; initials: string; role: string; rights: string }[]
  requests: { id: UUID; requester_name: string; role: string; reason: string; item_title: string }[]
  can_change: boolean
}

export interface KHealthTile { score: number; items: number; on_time_pct: number; overdue: number; due_soon: number; no_owner: number; no_backup: number; critical: number }
export interface KLeaderDashboard {
  company: KHealthTile
  change_since_last_month: number | null
  functions_count: number
  trend: { month: string; score: number }[]
  by_function: { category_id: UUID; name: string; score: number }[]
  attention: { text: string; action: string; href: string }[]
  target_on_time_pct: number
}
export interface KFunctionDashboard {
  category_id: UUID
  name: string
  tile: KHealthTile
  by_category: { category_id: UUID; name: string; items: number; overdue: number; ok_pct: number }[]
  by_owner: { owner_id: UUID; name: string; items: number; overdue: number }[]
  overdue_owner_count: number
  items_without_backup: number
}
