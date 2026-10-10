import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'
import { SkeletonPage } from '@/components/ui'
import { useSession } from '@/lib/session'

export function RequireAuth() {
  const { signedIn, isLoading, me } = useSession()
  const location = useLocation()
  if (!signedIn) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (isLoading || !me) return <div className="mx-auto max-w-6xl p-6"><SkeletonPage /></div>
  return <Outlet />
}

export function RequireRole({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { has } = useSession()
  return has(...roles) ? <>{children}</> : <Navigate to="/home" replace />
}

/** Knowledge Hub: records staff only (roles, or owning/heading part of the Hub). The server decides. */
export function RequireKnowledge({ children }: { children: ReactNode }) {
  const { me } = useSession()
  return me?.can_open_knowledge ? <>{children}</> : <Navigate to="/home" replace />
}
