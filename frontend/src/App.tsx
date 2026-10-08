import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { MotionConfig } from 'motion/react'
import { RouterProvider } from 'react-router'
import { Toaster } from 'sonner'
import { queryClient } from '@/api/client'
import { SplashScreen } from '@/components/SplashScreen'
import { SessionProvider } from '@/lib/session'
import { router } from '@/router'

// The last loaded data survives reloads, so a degraded backend still shows something useful.
const persister = createSyncStoragePersister({
  storage: typeof window !== 'undefined' ? window.localStorage : undefined,
  key: 'lms.cache',
  throttleTime: 2000,
})

export default function App() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: 24 * 60 * 60 * 1000,
        buster: 'v1',
        // Never persist anything admin-only or secret-looking; only the person's own screens.
        dehydrateOptions: { shouldDehydrateQuery: (q) => q.state.status === 'success' && ['me', 'courses', 'k', 'challenges', 'boards'].includes(String(q.queryKey[0])) },
      }}
    >
      <MotionConfig reducedMotion="user">
        <SessionProvider>
          <RouterProvider router={router} />
          <SplashScreen />
          <Toaster position="top-center" richColors closeButton toastOptions={{ className: 'font-sans' }} />
        </SessionProvider>
      </MotionConfig>
    </PersistQueryClientProvider>
  )
}
