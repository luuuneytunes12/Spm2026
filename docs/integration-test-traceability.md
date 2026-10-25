# Integration Test Traceability — Sprints 1 to 4

Every user story from Jira Sprints 1–4, mapped to the integration tests that
prove it. Test names carry the story key and the criteria they cover
(`test_scrum65_ac1_ac6_...`), so this table points at files.

## What "integration" means here

Integration tests live in `backend/tests/integration/`. Each one goes through
the real application path — HTTP request → FastAPI route → domain logic →
SQLAlchemy → **real PostgreSQL** — with only the database replaced by a
throwaway `postgres:16` container (Testcontainers), built from
`backend/db/schema.sql`. Every request gets its own database session, as in
production.

They exist alongside the fast unit tests in `backend/tests/` (in-memory
SQLite) because SQLite cannot show what these can:

- **Native types**: `timestamptz`, the `user_role` / `booking_status` enums,
  `text[]` venue lists, JSON change requests.
- **Database rules**: foreign keys, `UNIQUE`, and `CHECK` constraints.
- **Concurrency**: SQLite serialises writes, so a double-clicked button can
  never race there. The `race()` helper fires the same request from 6 threads
  at once and checks that it took effect exactly once.

Run them (Docker must be running):

```bash
cd backend
uv run pytest tests/integration -q          # skips if Docker is off
REQUIRE_INTEGRATION=1 uv run pytest -q       # as CI does: fails if Docker is off
```

## Traceability

| Story | Title | Sprint | Integration tests |
|---|---|---|---|
| SCRUM-14 | Log In to System | 1–2 | `test_auth_roles_postgres.py` |
| SCRUM-18 | Edit User Profile | 1–2 | `test_auth_roles_postgres.py` |
| SCRUM-20 | Draft an Event Request | 1 | `test_event_request_lifecycle_postgres.py` |
| SCRUM-21 | Submit an Event Request | 1 | `test_event_request_lifecycle_postgres.py`, `test_coordinator_concurrency_postgres.py` |
| SCRUM-22 | Edit Submitted Event Request Before Review | 1–2 | `test_event_request_lifecycle_postgres.py` (2 known bugs, see below) |
| SCRUM-23 | View Coordinator Assignment | 1–2 | `test_coordinator_stories_postgres.py` |
| SCRUM-24 | Declare Coordinator Global Unavailability | 1–2 | **Not testable — no endpoint** (see below) |
| SCRUM-25 | Approve Event Request | 1 | `test_event_request_lifecycle_postgres.py` |
| SCRUM-26 | Reject Event Request | 1 | `test_event_request_lifecycle_postgres.py` |
| SCRUM-28 | View Full Event Details as Coordinator | 1 | `test_coordinator_stories_postgres.py` |
| SCRUM-35 | Search and Filter Venues | 2 | `test_venue_catalogue_postgres.py` |
| SCRUM-36 | View Venue Details | 2 | `test_venue_catalogue_postgres.py` |
| SCRUM-37 | View Venue Availability Calendar | 2 | `test_venue_catalogue_postgres.py` |
| SCRUM-39 | Submit Venue Booking Request | 2 | `test_venue_booking_postgres.py` |
| SCRUM-40 | Process Venue Booking Request | 2 | `test_venue_booking_decision_postgres.py` |
| SCRUM-41 | Identify Booking Conflicts | 3 | `test_booking_conflicts_postgres.py` |
| SCRUM-42 | View Equipment Catalogue | 1 | `test_equipment_postgres.py` |
| SCRUM-43 | Record Equipment Requirements | 2 | `test_equipment_postgres.py` |
| SCRUM-44 | Update Equipment Requirement Status | 2 | `test_equipment_postgres.py` |
| SCRUM-45 | Check Equipment Availability | 2 | `test_equipment_postgres.py` |
| SCRUM-46 | Reserve Equipment for Event | 2 | `test_equipment_postgres.py`, `test_event_cancellation_postgres.py` |
| SCRUM-47 | Register for Event | 1–2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-48 | Withdraw from Event | 1–2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-49 | View Registration Status | 2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-50 | View Attendee List | 3 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-51 | View Attendee-Facing Event Details | 3 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-58 | Check Venue Suitability | 2 | `test_venue_catalogue_postgres.py` |
| SCRUM-59 | Auto-Release Equipment on Cancel/Complete | 3 | `test_event_cancellation_postgres.py` |
| SCRUM-60 | Notification Infrastructure | 1–2 | `test_platform_postgres.py` |
| SCRUM-61 | Core Database Schema | 1 | `test_platform_postgres.py` |
| SCRUM-62 | RBAC Infrastructure | 1 | `test_auth_roles_postgres.py` |
| SCRUM-63 | Log Out | 1–2 | `test_auth_roles_postgres.py` |
| SCRUM-64 | Declare Per-Event Unavailability | 1–2 | **Not testable — no endpoint** (see below) |
| SCRUM-65 | Submit Event for Safety Check | 2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-66 | Schedule Registration | 2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-68 | View Event Catalogue | 2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-70 | Create Event Coordinator Lead Role | 2 | `test_auth_roles_postgres.py` |
| SCRUM-71–77 | Login as Organiser / Coordinator / Venue Staff / Tech Support / Attendee / Lead / Safety Officer | 2–4 | `test_auth_roles_postgres.py` |
| SCRUM-78 | Configure Venue Setup & Turnaround | 3 | `test_venue_setup_turnaround_postgres.py` |
| SCRUM-79 | Unassigned Request Queue | 2 | `test_unassigned_queue_postgres.py` |
| SCRUM-80 | Assign Event Request | 2 | `test_lead_assign_postgres.py` |
| SCRUM-81 | Reassign Event | 2 | `test_lead_reassign_postgres.py` |
| SCRUM-82 | View All Coordinator Assignments | 2 | `test_coordinator_assignments_postgres.py` |
| SCRUM-83 | Review Event for Safety Check | 2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-84 | Revise Event After Safety Feedback | 3 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-86 | Safety Officer Notifications | 2–3 | `test_safety_officer_notifications_postgres.py` |
| SCRUM-88 | Approve in Safety Check | 2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-89 | Reject / Request Changes in Safety Check | 2 | `test_safety_check_and_registration_postgres.py` |
| SCRUM-91 | Create Safety Officer Role | 2 | `test_auth_roles_postgres.py` |
| SCRUM-92 | Flag Bookings After Setup Change | 3 | `test_booking_conflict_flags_postgres.py` |
| SCRUM-93 | Mark Venue Temporarily Unavailable | 3 | `test_venue_unavailability_postgres.py` |
| SCRUM-94 | Notify Bookings Affected by Unavailability | 3 | `test_venue_unavailable_notice_postgres.py` |
| SCRUM-95 | Request Replacement Venue | 3 | **Not testable — not implemented** (see below) |
| SCRUM-96 | Change or Cancel One Venue Booking | 3 | `test_venue_booking_change_cancel_postgres.py` |
| SCRUM-97 | Tentative Venue Hold with Expiry | 3 | `test_venue_tentative_hold_postgres.py` |
| SCRUM-98 | Auto-Expire Tentative Holds | 3 | `test_venue_hold_expiry_postgres.py` |
| SCRUM-99 | Filter Venues by Date and Time | 3–4 | `test_venue_date_filter_postgres.py` |
| SCRUM-100 | Equipment Requirements for Tech Support | 3 | `test_equipment_postgres.py` |
| SCRUM-101 | Lead Notified of New Requests | 2 | `test_event_request_lifecycle_postgres.py` |
| SCRUM-102 | Past Safety Check Decisions | 3–4 | `test_past_safety_checks_postgres.py` |
| SCRUM-104 | Venue Suitability per Booking | 3 | `test_venue_catalogue_postgres.py` |
| SCRUM-105 | Cancel Event | 3 | `test_event_cancellation_postgres.py` |
| SCRUM-108 | Manage Venue Catalogue Details | 3 | **Not testable — not implemented** (see below) |

Sprint 4 stories still *To Do* or *In Progress* in Jira (SCRUM-19, 27, 29,
30, 32, 34, 52–56, 103, 106, 107, 109) get integration tests once they are
built.

## Gaps and findings

**Stories marked Done with no backend to test**

- **SCRUM-24, SCRUM-64**: the availability toggle and per-event decline
  were removed in commit `896957f` ("removed deprecated…"). The
  `users.is_available` column and the `coordinator_availability_history`
  table remain, but nothing writes to them through the API.
- **SCRUM-95**: there is no "find replacement" request, and no `replaced`
  booking status.
- **SCRUM-108**: there is no endpoint to add a venue or edit its catalogue
  details (only setup/turnaround and unavailability).

Either reopen these in Jira or record why they are out of scope.

**Bugs found by the new race tests** (marked `xfail(strict=True)`, so CI
stays green until they are fixed and goes red if the fix lands without
removing the marker):

1. *Double-clicked "request a change" (SCRUM-22)*: `POST
   /events/{id}/change-requests` reads the event without a row lock, so 6
   simultaneous requests stored 4 pending change requests. Fix: lock the
   event (`_get_own_event(..., lock=True)`).
2. *Double-clicked "approve change request" (SCRUM-22)*: the change request
   is loaded before the event row is locked, so every waiting request still
   sees it as pending. The change was applied, and the Organiser notified,
   6 times. Fix: load the change request `with_for_update=True`.
