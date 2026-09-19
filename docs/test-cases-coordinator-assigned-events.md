# Test Cases — Coordinator Assigned Events

Covers one product backlog item:

- **Story 3 — View Assigned Event Details.** *As an Event Coordinator, I want
  to view the full details of an event assigned to me, so that I can
  understand its requirements and plan accordingly.*

Every acceptance criterion below maps to at least one test case, and every
automated test is named after the criterion it proves, so a criterion can be
traced to the code that verifies it. This mirrors
[test-cases-organiser-event-requests.md](test-cases-organiser-event-requests.md),
which covers the two Organiser stories this one reads the output of.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_assigned_events.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| All of the above | push to any branch | GitHub Actions runs them |

There is no Playwright layer for this story yet.

Assignment itself now happens automatically on submission — see
[test-cases-coordinator-availability.md](test-cases-coordinator-availability.md),
which covers the "Mark myself unavailable" story that added it. The tests
below mostly still assign a Coordinator directly (`_assign()` in
`test_assigned_events.py`) rather than by submitting, so this story's tests
stay about *viewing* an assignment, not about how one came to exist.

## What "assigned to me" means

`events.coordinator_id == the signed-in user's id`. Nothing else: not the
`coordinator` role (every Coordinator holds it, and holding it must not open
every event), and not the `event:read` permission (**every** role in the
system holds that one — see `backend/app/core/roles.py`).

Because scoping is per row rather than per role, `GET /events/assigned`
returns an empty list to a caller who coordinates nothing, rather than a 403.
An empty list is the honest answer to "what is assigned to me?".

---

## AC1 — every requirement is visible

> *For an event assigned to me, I can view its name, purpose, description,
> date/time, expected attendance, venue requirements, accessibility needs,
> equipment requirements, and registration needs.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S3-1a | The API returns every field named in the criterion | pytest | `test_assigned_events.py` › *test_assigned_event_returns_every_requirement* |
| TC-S3-1b | Every field is on screen, under a readable label | Vitest | `AssignedEventView.test.tsx` › *shows every field named in the acceptance criterion* |
| TC-S3-1c | The optional planning fields (type, programme, room layout, special arrangements) come back too | pytest | `test_assigned_events.py` › *test_assigned_event_returns_the_supporting_planning_fields* |
| TC-S3-1d | A field the Organiser left empty reads "Not provided", not a blank row | Vitest | `AssignedEventView.test.tsx` › *marks a field the Organiser left empty…* |
| TC-S3-1e | "Registration needs" reads as an answer either way, not a raw boolean | Vitest | `AssignedEventView.test.tsx` › *says so plainly when registration is not required* |

## AC2 — the Event Organiser's name and contact details

> *I can see the Event Organiser's name and contact details.*

The `users` table carries a name and an email and nothing else, so **email is
the whole of "contact details" today**. `OrganiserContact` in
`backend/app/schemas/event.py` is a deliberate projection of that table — if
the customer later asks for a phone number, it goes on `users` and then on
that schema.

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S3-2a | The response names the Organiser and gives their email | pytest | `test_assigned_events.py` › *test_assigned_event_includes_the_organisers_name_and_contact* |
| TC-S3-2b | The screen names them and makes the email actionable (`mailto:`) | Vitest | `AssignedEventView.test.tsx` › *names the Organiser and links their email* |
| TC-S3-2c | Projecting the user row does not leak `password_hash` or `role` | pytest | `test_assigned_events.py` › *test_organiser_contact_does_not_leak_the_password_hash* |

## AC3 — the current status

> *I can see the event's current status.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S3-3a | The response carries the current status | pytest | `test_assigned_events.py` › *test_assigned_event_reports_its_current_status* |
| TC-S3-3b | The screen shows the label ("Under review"), never the stored slug (`under_review`) | Vitest | `AssignedEventView.test.tsx` › *shows the status under a readable label…* |

## AC4 — the activity log

> *I can see the event's activity log.*

The log is `event_status_history` — every recorded status change, with who
made it and when. Today the only writer is the submit endpoint, so a freshly
submitted event has exactly one entry; each later story that moves an event
adds its own.

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S3-4a | Each entry carries from/to status, actor and timestamp | pytest | `test_assigned_events.py` › *test_assigned_event_includes_its_activity_log* |
| TC-S3-4b | The screen renders each change, its actor and its note | Vitest | `AssignedEventView.test.tsx` › *shows each change, who made it, and any note* |
| TC-S3-4c | Newest first, on both sides | pytest + Vitest | *test_activity_log_is_newest_first* / *lists the most recent change first* |
| TC-S3-4d | An event that never changed status has an **empty** log, not a missing one | pytest + Vitest | *test_activity_log_is_empty_rather_than_absent…* / *shows an empty state rather than an empty box…* |
| TC-S3-4e | An entry whose actor cannot be named still renders | Vitest | `AssignedEventView.test.tsx` › *renders a log entry whose actor can no longer be named* |

## AC5 — I cannot view events that are not assigned to me

> *I cannot view events that are not assigned to me.*

Refusal is a **404, not a 403** — the same answer as an event id that does not
exist. "Not assigned to you" and "no such event" are deliberately
indistinguishable, so the endpoint cannot be walked to discover which ids
exist or who is coordinating them. This matches `_get_own_event`, which the
Organiser stories already rely on.

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S3-5a | An event assigned to a *different* Coordinator → 404 | pytest | `test_assigned_events.py` › *test_coordinator_cannot_view_an_event_assigned_to_someone_else* |
| TC-S3-5b | The screen turns that 404 into a refusal and renders none of the event | Vitest | `AssignedEventView.test.tsx` › *a 404 becomes a refusal, and none of the event is rendered* |
| TC-S3-5c | The list asks the scoped endpoint, so an unassigned event is never even offered | Vitest | `AssignedEvents.test.tsx` › *asks the scoped endpoint…* |
| TC-S3-5d | An event with **no** Coordinator at all → 404 | pytest | `test_assigned_events.py` › *test_coordinator_cannot_view_an_unassigned_event* |
| TC-S3-5e | The list contains only my events; a Coordinator assigned nothing sees nothing | pytest | `test_assigned_events.py` › *test_assigned_list_contains_only_my_events* |
| TC-S3-5f | Raising a request does not make you its Coordinator — and the Organiser's own route is unaffected | pytest | `test_assigned_events.py` › *test_the_organiser_of_an_event_is_not_its_coordinator* |
| TC-S3-5g | Not signed in → 401, no event information revealed | pytest | `test_assigned_events.py` › *test_anonymous_cannot_view_assigned_events* |
| TC-S3-5h | `/events/assigned` is a route, not `/events/{id}` with `id="assigned"` | pytest | `test_assigned_events.py` › *test_assigned_is_not_captured_as_an_event_id* |

---

## Manual check

Assignment is automatic now (see
[test-cases-coordinator-availability.md](test-cases-coordinator-availability.md)),
so exercising this story just needs one Coordinator to exist before an
Organiser submits a request — sign up (or promote, via
`scripts/create_admin.py`-style direct role update) one Coordinator, then
submit a complete request as an Organiser.

Sign in as that Coordinator and open **My assigned events** in the sidebar.

| ID | Check | Expected |
|---|---|---|
| TC-S3-M1 | The assigned event appears under My assigned events | one row, badged with its current status |
| TC-S3-M2 | Open it | every requirement, the Organiser's name and email, the status, and the activity log (including the "Assignment" entry) |
| TC-S3-M3 | Edit the URL to another event's id | "That event is not assigned to you." |
| TC-S3-M4 | Read the page in dark mode | the activity timeline and its dots stay legible |
