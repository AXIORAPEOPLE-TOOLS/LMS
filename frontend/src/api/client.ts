import { QueryClient, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ApiError, errorMessage } from '@/lib/api'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 24 * 60 * 60 * 1000, // keep for the persisted cache (offline/degraded view)
      refetchOnWindowFocus: true,
      retry: (count, error) => {
        if (error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) return false
        return count < 2
      },
    },
  },
})

interface MutationOptions<TVars, TData> {
  invalidate?: QueryKey[]
  success?: string | ((data: TData, vars: TVars) => string | undefined)
  onSuccess?: (data: TData, vars: TVars) => void
  silentError?: boolean
}

/** A mutation that shows a plain-language toast and refreshes the screens it affects. */
export function useApiMutation<TVars, TData = unknown>(fn: (vars: TVars) => Promise<TData>, options: MutationOptions<TVars, TData> = {}) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async (data, vars) => {
      await Promise.all((options.invalidate ?? []).map((key) => client.invalidateQueries({ queryKey: key })))
      const message = typeof options.success === 'function' ? options.success(data, vars) : options.success
      if (message) toast.success(message)
      options.onSuccess?.(data, vars)
    },
    onError: (error) => {
      if (!options.silentError) toast.error(errorMessage(error))
    },
  })
}
