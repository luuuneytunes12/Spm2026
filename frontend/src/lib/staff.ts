// Mirror of the staff directory entry returned by GET /users/staff.

import { apiFetch } from './api'

export interface StaffMember {
  id: number
  name: string
  email: string
  role: string
  department: string | null
  responsibilities: string | null
}

export function listStaff(): Promise<StaffMember[]> {
  return apiFetch('/users/staff') as Promise<StaffMember[]>
}
