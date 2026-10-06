import { Navigate, Route, Routes } from 'react-router'
import { RequireAuth } from './auth/RequireAuth'
import { AppLayout } from './components/AppLayout'
import { RequireRole } from './auth/RequireRole'
import { Role } from './lib/roles'
import { Forbidden } from './pages/Forbidden'
import { Login } from './pages/Login'
import { My } from './pages/My'
import { Notifications } from './pages/Notifications'
import { Profile } from './pages/Profile'
import { Register } from './pages/Register'
import { EquipmentCatalogue } from './pages/equipment/EquipmentCatalogue'
import { EquipmentRequirementsList } from './pages/equipment/EquipmentRequirementsList'
import { EquipmentRequirementsRecord } from './pages/equipment/EquipmentRequirementsRecord'
import { EquipmentReservations } from './pages/equipment/EquipmentReservations'
import { AssignedEvents } from './pages/events/AssignedEvents'
import { AssignedEventView } from './pages/events/AssignedEventView'
import { EventForm } from './pages/events/EventForm'
import { EventView } from './pages/events/EventView'
import { MyRequests } from './pages/events/MyRequests'
import { AttendeeEvents } from './pages/registrations/AttendeeEvents'
import { MyRegistrations } from './pages/registrations/MyRegistrations'
import { Attendee } from './pages/roles/Attendee'
import { Coordinator } from './pages/roles/Coordinator'
import { CoordinatorLead } from './pages/roles/CoordinatorLead'
import { CoordinatorAssignments, UnassignedQueue, UnassignedRequests } from './pages/lead/LeadPages'
import { AssignedEventReview } from './pages/lead/AssignedEventReview'
import { QueuedRequestView } from './pages/lead/QueuedRequestView'
import { Organiser } from './pages/roles/Organiser'
import { TechSupport } from './pages/roles/TechSupport'
import { VenueStaff } from './pages/roles/VenueStaff'
import { VenueBookingQueue } from './pages/venues/VenueBookingQueue'
import { VenueView } from './pages/venues/VenueView'
import { Venues } from './pages/venues/Venues'
import { SafetyChecks } from './pages/safety/SafetyChecks'

import './App.css'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forbidden" element={<Forbidden />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<My />} />
          <Route path="/my" element={<My />} />
          {/* Notifications and Profile are per-user, not per-role, so
              these routes sit outside every RequireRole group below. */}
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/profile" element={<Profile />} />

          <Route element={<RequireRole roles={[Role.ORGANISER]} />}>
            <Route path="/organiser" element={<Organiser />} />
            {/* Static "new" is declared before the ":id" params so it is
                never captured as an event id. */}
            <Route path="/organiser/events" element={<MyRequests />} />
            <Route path="/organiser/events/new" element={<EventForm />} />
            <Route path="/organiser/events/:id" element={<EventView />} />
            <Route path="/organiser/events/:id/edit" element={<EventForm />} />
          </Route>
          <Route element={<RequireRole roles={[Role.COORDINATOR]} />}>
            <Route path="/coordinator" element={<Coordinator />} />
            <Route path="/coordinator/events" element={<AssignedEvents />} />
            <Route path="/coordinator/events/:id" element={<AssignedEventView />} />
          </Route>
          <Route element={<RequireRole roles={[Role.COORDINATOR_LEAD]} />}>
            <Route path="/coordinator-lead" element={<CoordinatorLead />} />
            <Route path="/coordinator-lead/queue" element={<UnassignedQueue />} />
            <Route path="/coordinator-lead/queue/:id" element={<QueuedRequestView />} />
            <Route path="/coordinator-lead/unassigned" element={<UnassignedRequests />} />
            <Route path="/coordinator-lead/assignments" element={<CoordinatorAssignments />} />
            <Route path="/coordinator-lead/assignments/:id" element={<AssignedEventReview />} />
          </Route>
          <Route element={<RequireRole roles={[Role.VENUE_STAFF]} />}>
            <Route path="/venue-staff" element={<VenueStaff />} />
            <Route path="/venue-staff/bookings" element={<VenueBookingQueue />} />
          </Route>
          {/* Shared by both internal roles that assess venues, so not
              nested under either role's home path. */}
          <Route element={<RequireRole roles={[Role.COORDINATOR, Role.VENUE_STAFF]} />}>
            <Route path="/venues" element={<Venues />} />
            <Route path="/venues/:id" element={<VenueView />} />
          </Route>
          <Route element={<RequireRole roles={[Role.TECH_SUPPORT]} />}>
            <Route path="/tech-support" element={<TechSupport />} />
            {/* Not nested under /tech-support/ on purpose: the catalogue is
                one shared reference list, not a per-user view, and the
                Coordinator's equipment-request story will read the same
                page. When it does, this guard takes a second role and the
                URL stays correct. */}
            <Route path="/equipment" element={<EquipmentCatalogue />} />
            {/* Technical Support only: the Coordinator records requirements
                on the event page, so there is nothing here for them. */}
            <Route path="/equipment-requirements" element={<EquipmentRequirementsList />} />
            <Route
              path="/equipment-requirements/:eventId"
              element={<EquipmentRequirementsRecord />}
            />
            <Route path="/equipment/reservations" element={<EquipmentReservations />} />
          </Route>
          <Route element={<RequireRole roles={[Role.ATTENDEE]} />}>
            <Route path="/attendee" element={<Attendee />} />
            <Route path="/attendee/events" element={<AttendeeEvents />} />
            <Route path="/attendee/registrations" element={<MyRegistrations />} />
          </Route>
          <Route element={<RequireRole roles={[Role.SAFETY_OFFICER]} />}>
            <Route path="/safety-checks" element={<SafetyChecks />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
