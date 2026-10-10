import { lazy, Suspense, type ComponentType } from 'react'
import { createBrowserRouter, Navigate } from 'react-router'
import { SkeletonPage } from '@/components/ui'
import { AppShell } from '@/layouts/AppShell'
import { RequireAuth, RequireKnowledge, RequireRole } from '@/layouts/guards'

function page<M extends object>(loader: () => Promise<M>, name: keyof M & string) {
  const Component = lazy(async () => ({ default: (await loader())[name] as ComponentType }))
  return (
    <Suspense fallback={<SkeletonPage />}>
      <Component />
    </Suspense>
  )
}

const learner = () => import('@/features/learner')
const learning = () => import('@/features/learner/learning')
const tests = () => import('@/features/learner/tests')
const growth = () => import('@/features/learner/growth')
const manager = () => import('@/features/manager')
const admin = () => import('@/features/admin')
const adminOps = () => import('@/features/admin/operations')
const adminContent = () => import('@/features/admin/content')
const monitoring = () => import('@/features/admin/monitoring')
const adminAssign = () => import('@/features/admin/assign')
const adminMessages = () => import('@/features/admin/messages')
const adminTraining = () => import('@/features/admin/training')
const adminHelpers = () => import('@/features/admin/helpers')
const knowledge = () => import('@/features/knowledge')
const knowledgeItem = () => import('@/features/knowledge/item')
const knowledgeAdmin = () => import('@/features/knowledge/admin')

export const router = createBrowserRouter([
  { path: '/', element: page(() => import('@/features/landing'), 'LandingPage') },
  { path: '/login', element: page(() => import('@/features/auth'), 'LoginPage') },
  { path: '/signup', element: page(() => import('@/features/auth'), 'SignupPage') },
  { path: '/verify/:code', element: page(() => import('@/features/auth'), 'VerifyPage') },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: 'home', element: page(learner, 'HomePage') },
          { path: 'path', element: page(learner, 'PathwayPage') },
          { path: 'messages', element: page(learner, 'MessagesPage') },
          { path: 'learn', element: page(learning, 'LearnPage') },
          { path: 'learn/catalogue', element: <Navigate to="/learn?tab=catalogue" replace /> },
          { path: 'learn/courses/:id', element: page(learning, 'CoursePage') },
          { path: 'learn/sessions/:id', element: <Navigate to="/learn?tab=sessions" replace /> },
          { path: 'learn/tests', element: <Navigate to="/learn?tab=tests" replace /> },
          { path: 'learn/tests/:id', element: page(tests, 'TestIntroPage') },
          { path: 'learn/tests/attempts/:id', element: page(tests, 'AttemptPage') },
          { path: 'learn/tests/attempts/:id/result', element: page(tests, 'ResultPage') },
          { path: 'learn/certificates', element: page(tests, 'CertificatesPage') },
          { path: 'rank', element: page(growth, 'RankPage') },
          { path: 'career', element: page(growth, 'CareerPage') },
          { path: 'me/profile', element: page(growth, 'ProfilePage') },
          { path: 'me/reminders', element: page(growth, 'RemindersPage') },
          { path: 'team', element: <RequireRole roles={['manager', 'admin']}>{page(manager, 'TeamPage')}</RequireRole> },
          { path: 'team/skills', element: <RequireRole roles={['manager', 'admin']}>{page(manager, 'TeamSkillsPage')}</RequireRole> },
          { path: 'team/approvals', element: <RequireRole roles={['manager', 'admin']}>{page(manager, 'ApprovalsPage')}</RequireRole> },
          { path: 'team/reports', element: <RequireRole roles={['manager', 'admin']}>{page(adminOps, 'ReportsPage')}</RequireRole> },
          { path: 'team/people/:id', element: <RequireRole roles={['manager', 'admin']}>{page(manager, 'PersonPage')}</RequireRole> },
          { path: 'admin', element: <RequireRole roles={['admin']}>{page(admin, 'AdminHomePage')}</RequireRole> },
          { path: 'admin/messages', element: <RequireRole roles={['admin']}>{page(adminMessages, 'MessageLogPage')}</RequireRole> },
          { path: 'admin/assign', element: <RequireRole roles={['admin']}>{page(adminAssign, 'AssignTrainingPage')}</RequireRole> },
          { path: 'admin/helpers', element: <RequireRole roles={['admin']}>{page(adminHelpers, 'HelpersPage')}</RequireRole> },
          { path: 'admin/helpers/:id', element: <RequireRole roles={['admin']}>{page(adminHelpers, 'HelperRunPage')}</RequireRole> },
          { path: 'admin/answers', element: <RequireRole roles={['admin', 'expert']}>{page(adminHelpers, 'WrittenAnswersPage')}</RequireRole> },
          { path: 'admin/training', element: <RequireRole roles={['manager', 'admin']}>{page(adminTraining, 'TrainingOverviewPage')}</RequireRole> },
          { path: 'admin/training/:id', element: <RequireRole roles={['manager', 'admin']}>{page(adminTraining, 'TrainingCoursePage')}</RequireRole> },
          { path: 'admin/people', element: <RequireRole roles={['admin']}>{page(admin, 'PeoplePage')}</RequireRole> },
          { path: 'admin/skills', element: <RequireRole roles={['admin']}>{page(admin, 'SkillsTestsPage')}</RequireRole> },
          { path: 'admin/courses', element: <RequireRole roles={['admin', 'expert']}>{page(adminContent, 'CoursesPage')}</RequireRole> },
          { path: 'admin/courses/new', element: <RequireRole roles={['admin']}>{page(adminContent, 'CourseBuilderPage')}</RequireRole> },
          { path: 'admin/courses/:id', element: <RequireRole roles={['admin', 'expert']}>{page(adminContent, 'CourseReviewPage')}</RequireRole> },
          { path: 'admin/sessions', element: <RequireRole roles={['admin']}>{page(adminContent, 'SessionsPage')}</RequireRole> },
          { path: 'admin/workflows', element: <RequireRole roles={['admin']}>{page(adminOps, 'WorkflowsPage')}</RequireRole> },
          { path: 'admin/reports', element: <RequireRole roles={['admin']}>{page(adminOps, 'ReportsPage')}</RequireRole> },
          { path: 'admin/proctoring', element: <RequireRole roles={['admin', 'reviewer']}>{page(adminOps, 'ProctoringPage')}</RequireRole> },
          { path: 'admin/settings', element: <RequireRole roles={['admin']}>{page(adminOps, 'SettingsPage')}</RequireRole> },
          { path: 'admin/monitoring', element: <RequireRole roles={['admin']}>{page(monitoring, 'MonitoringPage')}</RequireRole> },
          { path: 'knowledge', element: <RequireKnowledge>{page(knowledge, 'KnowledgeHomePage')}</RequireKnowledge> },
          { path: 'knowledge/library', element: <RequireKnowledge>{page(knowledge, 'LibraryPage')}</RequireKnowledge> },
          { path: 'knowledge/my-items', element: <RequireKnowledge>{page(knowledge, 'MyItemsPage')}</RequireKnowledge> },
          { path: 'knowledge/add', element: <RequireKnowledge>{page(knowledgeItem, 'AddKnowledgePage')}</RequireKnowledge> },
          { path: 'knowledge/items/:id', element: <RequireKnowledge>{page(knowledgeItem, 'ItemPage')}</RequireKnowledge> },
          { path: 'knowledge/items/:id/history', element: <RequireKnowledge>{page(knowledgeItem, 'HistoryPage')}</RequireKnowledge> },
          { path: 'knowledge/items/:id/access', element: <RequireKnowledge>{page(knowledgeAdmin, 'AccessPage')}</RequireKnowledge> },
          { path: 'knowledge/dashboard', element: <RequireKnowledge>{page(knowledgeAdmin, 'LeaderDashboardPage')}</RequireKnowledge> },
          { path: 'knowledge/dashboard/:id', element: <RequireKnowledge>{page(knowledgeAdmin, 'FunctionDashboardPage')}</RequireKnowledge> },
          { path: 'knowledge/admin', element: <RequireRole roles={['admin', 'knowledge_admin']}>{page(knowledgeAdmin, 'KnowledgeAdminPage')}</RequireRole> },
          { path: 'knowledge/admin/access', element: <Navigate to="/knowledge/admin" replace /> },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/home" replace /> },
])
