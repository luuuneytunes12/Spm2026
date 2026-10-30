import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { E2E_DATABASE_URL, E2E_JWT_SECRET } from '../../playwright.config'

/**
 * Seeding and cleanup for the coordinator specs.
 *
 * Registration always creates an Attendee, so the Coordinators and the
 * Organiser these specs need have to be written straight into the database.
 * That goes through the backend's own models and password hasher (the same
 * approach as the CI "Seed an organiser" step), run with `uv` so nothing
 * here needs a database driver of its own in Node.
 *
 * Every script runs against E2E_DATABASE_URL -- which playwright.config.ts
 * restricts to localhost and the test database name. A local tunnel could still
 * forward to a remote database; the operator must ensure it is disposable.
 */
const BACKEND = fileURLToPath(new URL('../../../backend', import.meta.url))

/** Run a fixture operation with the backend models against the guarded test database. */
function python(script: string, payload: unknown): string {
  return execFileSync('uv', ['run', 'python', '-c', script, JSON.stringify(payload)], {
    cwd: BACKEND,
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL, JWT_SECRET: E2E_JWT_SECRET },
    encoding: 'utf8',
  })
}

export interface SeedUser {
  email: string
  name: string
  role: 'organiser' | 'coordinator' | 'venue_staff' | 'tech_support' | 'safety_officer' | 'event_coordinator_lead' | 'attendee'
  password: string
}

const SEED = `
import json, sys
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.user import User

users = json.loads(sys.argv[1])
db = SessionLocal()
for u in users:  # in the order given, so ids -- and load ties -- are predictable
    row = db.query(User).filter(User.email == u["email"]).one_or_none()
    if row is None:
        row = User(email=u["email"], name=u["name"], role=u["role"],
                   password_hash=hash_password(u["password"]))
        db.add(row)
    else:
        row.name, row.role = u["name"], u["role"]
    row.is_available = True
    db.commit()
db.close()
`

/** Create (or reset) the given users, all marked available. */
export function seedUsers(users: SeedUser[]): void {
  python(SEED, users)
}

const RESET = `
import json, sys
from sqlalchemy import or_
from app.core.db import SessionLocal
from app.models.events import Event
from app.models.notifications import Notification
from app.models.user import User

emails = json.loads(sys.argv[1])
db = SessionLocal()
ids = [u.id for u in db.query(User).filter(User.email.in_(emails)).all()]
# Their events go first (history, notifications on them and change requests
# cascade); then whatever is left that belongs to them.
db.query(Event).filter(or_(Event.organiser_id.in_(ids), Event.coordinator_id.in_(ids))).delete(synchronize_session=False)
db.query(Notification).filter(Notification.user_id.in_(ids)).delete(synchronize_session=False)
db.query(User).filter(User.id.in_(ids)).update({User.is_available: True}, synchronize_session=False)
db.commit()
db.close()
`

/** Back to a clean slate for these users: no events or notifications,
 *  and everyone available. */
export function resetUsers(emails: string[]): void {
  python(RESET, emails)
}

const MARK_UNAVAILABLE = `
import json, sys
from app.core.db import SessionLocal
from app.models.user import User

emails = json.loads(sys.argv[1])
db = SessionLocal()
db.query(User).filter(User.email.in_(emails)).update({User.is_available: False}, synchronize_session=False)
db.commit()
db.close()
`

/** Take these users out of the assignment pool, straight on their row.
 *  Nothing in the app does this any more; the specs that need an empty pool
 *  set it up here. resetUsers puts everyone back. */
export function markUnavailable(emails: string[]): void {
  python(MARK_UNAVAILABLE, emails)
}

const REMOVE = `
import json, sys
from sqlalchemy import or_
from app.core.db import SessionLocal
from app.models.events import Event
from app.models.user import User

emails = json.loads(sys.argv[1])
db = SessionLocal()
ids = [u.id for u in db.query(User).filter(User.email.in_(emails)).all()]
db.query(Event).filter(or_(Event.organiser_id.in_(ids), Event.coordinator_id.in_(ids))).delete(synchronize_session=False)
db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
db.commit()
db.close()
`

/** Delete the users and everything of theirs. Run after a spec so that the
 *  Coordinators do not linger in the assignment pool and quietly change
 *  what the specs that run after this one see. */
export function removeUsers(emails: string[]): void {
  python(REMOVE, emails)
}

const SEED_VENUE = `
import json, sys
from app.core.db import SessionLocal
from app.models.venues import Venue

v = json.loads(sys.argv[1])
db = SessionLocal()
if not db.query(Venue).filter(Venue.name == v["name"]).first():
    db.add(Venue(name=v["name"], location=v["location"], capacity=v["capacity"], is_active=True))
    db.commit()
db.close()
`

/** Make sure a bookable venue with this name exists. */
export function seedVenue(venue: { name: string; location: string; capacity: number }): void {
  python(SEED_VENUE, venue)
}

const REMOVE_VENUE = `
import json, sys
from app.core.db import SessionLocal
from app.models.venues import Venue

db = SessionLocal()
db.query(Venue).filter(Venue.name == json.loads(sys.argv[1])).delete(synchronize_session=False)
db.commit()
db.close()
`

/** Delete a venue seeded by seedVenue. Remove the users' events first --
 *  a venue with bookings cannot be deleted. */
export function removeVenue(name: string): void {
  python(REMOVE_VENUE, name)
}

const AUTO_ASSIGN = `
import json, sys
from app.core.db import SessionLocal
from app.models.events import Event
from app.services.assignment import assign_coordinator

db = SessionLocal()
event = db.get(Event, json.loads(sys.argv[1]))
assign_coordinator(db, event, actor_id=event.organiser_id)
db.commit()
db.close()
`

/** Give a submitted event the Coordinator the old auto-assignment would have
 *  chosen (the available one with the lightest load), by running the real
 *  assign_coordinator. Submitting no longer assigns -- only the Coordinator
 *  Lead does -- so the specs that need an assigned event as their starting
 *  point call this after submitting. A no-op when nobody is available. */
export function autoAssign(eventId: number): void {
  python(AUTO_ASSIGN, eventId)
}

const ADD_NOTIFICATIONS = `
import json, sys
from app.core.db import SessionLocal
from app.models.notifications import Notification
from app.models.user import User

spec = json.loads(sys.argv[1])
db = SessionLocal()
user = db.query(User).filter(User.email == spec["email"]).one()
for i in range(spec["count"]):
    db.add(Notification(user_id=user.id, type="event_approved", message=f"Seeded notification {i + 1}"))
db.commit()
db.close()
`

/** Give a user `count` unread notifications. The app creates these as a side
 *  effect of other people's actions; a landing-page spec only needs them to
 *  exist. resetUsers clears them. */
export function addNotifications(email: string, count: number): void {
  python(ADD_NOTIFICATIONS, { email, count })
}

const ASSIGN_TO = `
import json, sys
from app.core.db import SessionLocal
from app.models.enums import EventStatus
from app.models.events import Event
from app.models.user import User

spec = json.loads(sys.argv[1])
db = SessionLocal()
event = db.get(Event, spec["event_id"])
event.coordinator_id = db.query(User).filter(User.email == spec["email"]).one().id
event.status = EventStatus.under_review
db.commit()
db.close()
`

/** Hand a submitted event to one named Coordinator, as the Lead would. Unlike
 *  autoAssign it does not pick: a spec that counts a Coordinator's events
 *  must know exactly whose they are. */
export function assignEventTo(eventId: number, email: string): void {
  python(ASSIGN_TO, { event_id: eventId, email })
}

const REGISTER = `
import json, sys
from app.core.db import SessionLocal
from app.models.enums import RegistrationStatus
from app.models.registrations import Registration
from app.models.user import User

spec = json.loads(sys.argv[1])
db = SessionLocal()
attendee = db.query(User).filter(User.email == spec["email"]).one()
db.add(Registration(event_id=spec["event_id"], attendee_id=attendee.id, status=RegistrationStatus(spec["status"])))
db.commit()
db.close()
`

/** Put an Attendee on an Event's registration list, as Registered or
 *  Withdrawn -- the starting position, without the confirm-and-open steps
 *  registering through the UI needs. */
export function registerAttendee(eventId: number, email: string, status: 'registered' | 'withdrawn' = 'registered'): void {
  python(REGISTER, { event_id: eventId, email, status })
}

const SEED_EQUIPMENT = `
import json, sys
from app.core.db import SessionLocal
from app.models.equipment import Equipment

e = json.loads(sys.argv[1])
db = SessionLocal()
row = db.query(Equipment).filter(Equipment.name == e["name"]).first()
if row is None:
    row = Equipment(name=e["name"], category=e["category"], total_quantity=e["total_quantity"])
    db.add(row)
    db.commit()
print(row.id)
db.close()
`

/** Make sure an equipment item with this name exists; returns its id. */
export function seedEquipment(item: { name: string; category: string; total_quantity: number }): number {
  return Number(python(SEED_EQUIPMENT, item).trim())
}

const REMOVE_EQUIPMENT = `
import json, sys
from app.core.db import SessionLocal
from app.models.equipment import Equipment

db = SessionLocal()
db.query(Equipment).filter(Equipment.name == json.loads(sys.argv[1])).delete(synchronize_session=False)
db.commit()
db.close()
`

/** Delete an item seeded by seedEquipment. Remove the users' events first --
 *  an item with reservations cannot be deleted. */
export function removeEquipment(name: string): void {
  python(REMOVE_EQUIPMENT, name)
}

const SET_BOOKING_STATUS = `
import json, sys
from app.core.db import SessionLocal
from app.models.venues import VenueBooking

spec = json.loads(sys.argv[1])
db = SessionLocal()
db.query(VenueBooking).filter(VenueBooking.event_id == spec["event_id"]).update(
    {VenueBooking.status: spec["status"]}, synchronize_session=False
)
db.commit()
db.close()
`

/** Put every venue booking of an event into `status`, straight on the row --
 *  how a spec stands in for "the venue became unavailable" without a
 *  screen for it. */
export function setBookingStatus(eventId: number, status: 'pending' | 'approved' | 'rejected' | 'cancelled'): void {
  python(SET_BOOKING_STATUS, { event_id: eventId, status })
}

export type ScheduledBookingStatus = 'pending' | 'tentative_hold' | 'approved' | 'rejected' | 'cancelled'

export interface ScheduledVenue {
  name: string
  capacity: number
  setupMinutes?: number
  turnaroundMinutes?: number
  /** ISO 8601 times. Each booking gets an event of its own, owned by the
   *  `owner` passed to seedVenueSchedule. A tentative hold needs `expiresAt`
   *  (the database refuses one without); a past one is an expired hold. */
  bookings?: { start: string; end: string; status: ScheduledBookingStatus; expiresAt?: string }[]
  /** Recorded unavailability periods, ISO 8601. */
  closures?: { start: string; end: string }[]
}

const SEED_SCHEDULE = `
import json, sys
from datetime import datetime
from app.core.db import SessionLocal
from app.models.events import Event
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability

p = json.loads(sys.argv[1])
db = SessionLocal()
owner = db.query(User).filter(User.email == p["owner"]).one()
for v in p["venues"]:
    venue = db.query(Venue).filter(Venue.name == v["name"]).one_or_none()
    if venue is None:
        venue = Venue(name=v["name"], location="1 Test Road")
        db.add(venue)
    venue.capacity = v["capacity"]
    venue.setup_minutes = v.get("setupMinutes")
    venue.turnaround_minutes = v.get("turnaroundMinutes")
    venue.is_active = True
    db.flush()
    # Start from an empty schedule, so a re-run sees exactly what is listed.
    db.query(VenueBooking).filter(VenueBooking.venue_id == venue.id).delete(synchronize_session=False)
    db.query(Event).filter(Event.name.like(v["name"] + " booking %")).delete(synchronize_session=False)
    db.query(VenueUnavailability).filter(VenueUnavailability.venue_id == venue.id).delete(synchronize_session=False)
    for i, b in enumerate(v.get("bookings", [])):
        event = Event(name=f"{v['name']} booking {i}", organiser_id=owner.id)
        db.add(event)
        db.flush()
        expires = b.get("expiresAt")
        db.add(VenueBooking(event_id=event.id, venue_id=venue.id, requested_by=owner.id,
                            start_time=datetime.fromisoformat(b["start"]),
                            end_time=datetime.fromisoformat(b["end"]), status=b["status"],
                            expires_at=datetime.fromisoformat(expires) if expires else None))
    for c in v.get("closures", []):
        db.add(VenueUnavailability(venue_id=venue.id, start_time=datetime.fromisoformat(c["start"]),
                                   end_time=datetime.fromisoformat(c["end"]),
                                   reason_category="Maintenance", created_by=owner.id))
    db.commit()
db.close()
`

/** Create (or reset) venues with exactly the setup and turnaround time,
 *  bookings and closures given. `owner` -- a seeded user -- owns the events
 *  the bookings hang off and records the closures. */
export function seedVenueSchedule(owner: string, venues: ScheduledVenue[]): void {
  python(SEED_SCHEDULE, { owner, venues })
}

const REMOVE_SCHEDULE = `
import json, sys
from app.core.db import SessionLocal
from app.models.events import Event
from app.models.venues import Venue, VenueBooking

names = json.loads(sys.argv[1])
db = SessionLocal()
ids = [v.id for v in db.query(Venue).filter(Venue.name.in_(names)).all()]
db.query(VenueBooking).filter(VenueBooking.venue_id.in_(ids)).delete(synchronize_session=False)
for name in names:
    db.query(Event).filter(Event.name.like(name + " booking %")).delete(synchronize_session=False)
# Closures go with their venue (ON DELETE CASCADE).
db.query(Venue).filter(Venue.id.in_(ids)).delete(synchronize_session=False)
db.commit()
db.close()
`

/** Delete venues seeded by seedVenueSchedule, with their bookings, the
 *  events behind them and their closures. Run before removing the owner. */
export function removeVenueSchedule(names: string[]): void {
  python(REMOVE_SCHEDULE, names)
}

const LAPSE_HOLD = `
import json, sys
from datetime import datetime, timedelta, timezone
from app.core.db import SessionLocal
from app.models.venues import VenueBooking

spec = json.loads(sys.argv[1])
db = SessionLocal()
db.query(VenueBooking).filter(VenueBooking.id == spec["booking_id"]).update(
    {VenueBooking.expires_at: datetime.now(timezone.utc) - timedelta(minutes=1)},
    synchronize_session=False,
)
db.commit()
db.close()
`

/** Move a tentative hold's expiry a minute into the past, straight on the
 *  row -- how a spec stands in for waiting for it to expire. The next sweep
 *  (any venue request, or the background sweeper) expires it. */
export function lapseHold(bookingId: number): void {
  python(LAPSE_HOLD, { booking_id: bookingId })
}
