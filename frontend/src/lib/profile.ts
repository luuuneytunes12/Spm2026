// Mirror of backend/app/schemas/user.py UserOut / UserProfileUpdate -- keep
// field names byte-identical. The backend is the authority on what a
// request may contain; nothing here is a security boundary.

import { apiFetch } from './api'

export interface UserProfile {
  id: number
  name: string
  email: string
  role: string
  organisation: string | null
  phone_country_code: string | null
  phone_number: string | null
  communication_preference: string | null
  created_at: string
}

export interface ProfileInput {
  name?: string
  organisation?: string | null
  email?: string
  phone_country_code?: string | null
  phone_number?: string | null
  communication_preference?: string | null
}

export function updateMyProfile(input: ProfileInput): Promise<UserProfile> {
  return apiFetch('/users/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }) as Promise<UserProfile>
}
