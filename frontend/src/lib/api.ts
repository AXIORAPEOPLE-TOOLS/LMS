/** Typed fetch client for /api. Turns the backend error contract into ApiError. */
import { getToken, clearToken } from './auth'

export interface ApiErrorBody {
  code: string
  message: string
  request_id?: string
  details?: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId?: string
  readonly details?: unknown

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.status = status
    this.code = body.code
    this.requestId = body.request_id
    this.details = body.details
  }

  /** The service itself is unreachable or degraded: show last data, not an error page. */
  get isUnavailable() {
    return this.status === 503 || this.status === 0
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

function buildUrl(path: string, query?: Query) {
  const url = new URL(`/api${path}`, window.location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value))
  }
  return url.toString()
}

async function request<T>(method: string, path: string, options: { body?: unknown; query?: Query; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (options.form) body = options.form
  else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), { method, headers, body })
  } catch {
    throw new ApiError(0, { code: 'network', message: 'You seem to be offline. We will keep showing what we last loaded.' })
  }
  if (response.status === 401 && token) {
    clearToken()
    window.dispatchEvent(new Event('lms:signed-out'))
  }
  if (!response.ok) {
    let errorBody: ApiErrorBody = { code: 'unexpected', message: 'Something went wrong. Please try again.' }
    try {
      const json = await response.json()
      if (json?.error) errorBody = json.error
    } catch {
      /* not JSON (proxy error page) */
      if (response.status >= 502) errorBody = { code: 'service_unavailable', message: 'The service is restarting. Please try again in a minute.' }
    }
    throw new ApiError(response.status, errorBody)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body: body ?? {} }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body: body ?? {} }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body: body ?? {} }),
  del: <T>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, form: FormData) => request<T>('POST', path, { form }),
  /** Download a file (exports, PDFs) with the auth header and save it. */
  async download(path: string, query?: Query, fallbackName = 'download') {
    const token = getToken()
    const response = await fetch(buildUrl(path, query), { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    if (!response.ok) {
      const json = await response.json().catch(() => null)
      throw new ApiError(response.status, json?.error ?? { code: 'unexpected', message: 'The download failed.' })
    }
    const disposition = response.headers.get('content-disposition') ?? ''
    const name = /filename="?([^"]+)"?/.exec(disposition)?.[1] ?? fallbackName
    const blob = await response.blob()
    const href = URL.createObjectURL(blob)
    const link = Object.assign(document.createElement('a'), { href, download: name })
    link.click()
    URL.revokeObjectURL(href)
  },
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}
