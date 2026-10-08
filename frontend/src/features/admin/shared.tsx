import { useDepartments, useJobRoles, useUsers } from '@/api/admin'
import type { Audience } from '@/api/types'
import { Field, Segmented, Select } from '@/components/ui'

type Kind = 'role' | 'department' | 'person' | 'everyone'

/** "Who is this for?" — the same picker for training, tests, sessions (golden rule 5: same pattern everywhere). */
export function AudiencePicker({ value, onChange }: { value: Audience; onChange: (a: Audience) => void }) {
  const roles = useJobRoles()
  const departments = useDepartments()
  const users = useUsers()
  const kind: Kind = value.everyone ? 'everyone' : value.department_id ? 'department' : value.user_ids?.length ? 'person' : 'role'
  return (
    <div className="space-y-3">
      <Segmented<Kind> value={kind} onChange={(k) => onChange(k === 'everyone' ? { everyone: true } : {})}
        options={[{ value: 'role', label: 'A role' }, { value: 'department', label: 'A department' }, { value: 'person', label: 'One person' }, { value: 'everyone', label: 'Everyone' }]} />
      {kind === 'role' && (
        <Field label="Role">
          <Select value={value.job_role_id ?? ''} onChange={(e) => onChange({ job_role_id: e.target.value || null })}>
            <option value="">Choose a role</option>
            {roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
        </Field>
      )}
      {kind === 'department' && (
        <Field label="Department">
          <Select value={value.department_id ?? ''} onChange={(e) => onChange({ department_id: e.target.value || null })}>
            <option value="">Choose a department</option>
            {departments.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
      )}
      {kind === 'person' && (
        <Field label="Person">
          <Select value={value.user_ids?.[0] ?? ''} onChange={(e) => onChange({ user_ids: e.target.value ? [e.target.value] : [] })}>
            <option value="">Choose a person</option>
            {users.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
        </Field>
      )}
    </div>
  )
}
