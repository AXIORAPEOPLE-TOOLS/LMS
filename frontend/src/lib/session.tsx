import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useMe } from '@/api/learner'
import type { Me } from '@/api/types'
import { setLanguage } from '@/i18n'
import { api } from './api'
import { clearToken, getToken, setToken } from './auth'

interface SessionValue {
  me: Me | undefined
  isLoading: boolean
  signedIn: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
  has: (...roles: string[]) => boolean
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const [signedIn, setSignedIn] = useState(() => !!getToken())
  const meQuery = useMe(signedIn)

  const signOut = useCallback(() => {
    clearToken()
    client.clear()
    setSignedIn(false)
  }, [client])

  useEffect(() => {
    const onSignedOut = () => signOut()
    window.addEventListener('lms:signed-out', onSignedOut)
    return () => window.removeEventListener('lms:signed-out', onSignedOut)
  }, [signOut])

  useEffect(() => {
    if (meQuery.data?.locale) setLanguage(meQuery.data.locale)
  }, [meQuery.data?.locale])

  const signIn = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.post<{ access_token: string }>('/auth/login', { email, password })
    setToken(access_token)
    client.clear()
    setSignedIn(true)
  }, [client])

  const value = useMemo<SessionValue>(() => ({
    me: meQuery.data,
    isLoading: signedIn && meQuery.isLoading,
    signedIn,
    signIn,
    signOut,
    has: (...roles) => roles.some((role) => meQuery.data?.system_roles.includes(role)),
  }), [meQuery.data, meQuery.isLoading, signedIn, signIn, signOut])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession() {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside SessionProvider')
  return value
}
