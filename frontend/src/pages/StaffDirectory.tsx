import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { departmentLabel } from '../lib/departments'
import { ROLE_LABELS } from '../lib/roles'
import type { Role } from '../lib/roles'
import { listStaff } from '../lib/staff'
import type { StaffMember } from '../lib/staff'

/** Who works in which department and what they handle, so internal staff
 *  can find the right point of contact (SCRUM-19). Read-only; each person
 *  edits their own entry on My Profile. */
export function StaffDirectory() {
  const [staff, setStaff] = useState<StaffMember[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listStaff()
      .then((rows) => !cancelled && setStaff(rows))
      .catch(
        (err) =>
          !cancelled &&
          setError(err instanceof ApiError ? err.message : 'Could not load the staff directory.'),
      )
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Staff directory</h1>
        <p className="page-subtitle">
          Find the right colleague by department and responsibilities.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {staff && staff.length === 0 && (
        <div className="card notice-empty">
          <p>No staff to show.</p>
        </div>
      )}

      {staff && staff.length > 0 && (
        <div className="card">
          <table className="table">
            <caption className="visually-hidden">Internal staff</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Role</th>
                <th scope="col">Department</th>
                <th scope="col">Responsibilities</th>
                <th scope="col">Email</th>
              </tr>
            </thead>
            <tbody>
              {staff.map((s) => (
                <tr key={s.id}>
                  <th scope="row">{s.name}</th>
                  <td>{ROLE_LABELS[s.role as Role] ?? s.role}</td>
                  <td>{departmentLabel(s.department)}</td>
                  <td>{s.responsibilities ?? '—'}</td>
                  <td>{s.email}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
