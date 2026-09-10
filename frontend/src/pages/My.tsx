import { Navigate } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { ROLE_HOME_PATH } from '../lib/roles'

// Redirects a signed-in user to their own role's landing page. Sits behind
// RequireAuth, so `user` is guaranteed set once loading finishes.
export function My() {
  const { user, loading } = useAuth()

  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={ROLE_HOME_PATH[user.role]} replace />
}
