import { toast } from 'sonner'
import { useUndo } from '@/api/admin'
import type { Audience, BulkResult } from '@/api/types'

export const audienceChosen = (a: Audience) => !!(a.everyone || a.job_role_id || a.department_id || a.user_ids?.length)

/** "Sent to 14 people · Undo" for the undo window (golden rule 4). */
export function useUndoToast() {
  const undo = useUndo()
  return (result: BulkResult, what: string) => {
    const minutes = Math.max(1, Math.round((new Date(result.undo_until).getTime() - Date.now()) / 60_000))
    toast.success(`${what} · ${result.count} ${result.count === 1 ? 'person' : 'people'}`, {
      description: `You can undo this for ${minutes} minutes.`,
      duration: 15_000,
      action: { label: 'Undo', onClick: () => undo.mutate(result.bulk_action_id) },
    })
  }
}
