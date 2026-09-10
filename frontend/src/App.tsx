import { Navigate, Route, Routes } from 'react-router'
import { RequireAuth } from './auth/RequireAuth'
import { AppLayout } from './components/AppLayout'
import { RequireRole } from './auth/RequireRole'
import { Role } from './lib/roles'
import { Dashboard } from './pages/Dashboard'
import { Forbidden } from './pages/Forbidden'
import { Login } from './pages/Login'
import { My } from './pages/My'
import { Register } from './pages/Register'
import { Attendee } from './pages/roles/Attendee'
import { Coordinator } from './pages/roles/Coordinator'
import { Organiser } from './pages/roles/Organiser'
import { TechSupport } from './pages/roles/TechSupport'
import { VenueStaff } from './pages/roles/VenueStaff'
import './App.css'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forbidden" element={<Forbidden />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/my" element={<My />} />

          <Route element={<RequireRole roles={[Role.ORGANISER]} />}>
            <Route path="/organiser" element={<Organiser />} />
          </Route>
          <Route element={<RequireRole roles={[Role.COORDINATOR]} />}>
            <Route path="/coordinator" element={<Coordinator />} />
          </Route>
          <Route element={<RequireRole roles={[Role.VENUE_STAFF]} />}>
            <Route path="/venue-staff" element={<VenueStaff />} />
          </Route>
          <Route element={<RequireRole roles={[Role.TECH_SUPPORT]} />}>
            <Route path="/tech-support" element={<TechSupport />} />
          </Route>
          <Route element={<RequireRole roles={[Role.ATTENDEE]} />}>
            <Route path="/attendee" element={<Attendee />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
