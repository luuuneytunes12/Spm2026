# Test Cases — Coordinator Availability

Covers one product backlog item:

- **Mark myself unavailable.** *As an Event Coordinator, I want to mark
  myself as unavailable, so that my assigned events are automatically
  reassigned to another coordinator.*

  Acceptance criteria:
  1. The Event Organiser can see who their assigned coordinator is on
     their event page.
  2. The assigned coordinator receives a notification of their assignment.
  3. The assignment is recorded in the event's activity log with a
     timestamp.

Unavailability comes in two forms, both in scope for this story:

- **Global** (`PATCH /coordinators/me/availability`) — the Coordinator
  goes away entirely. Every one of their active events is reassigned, and
  they stop receiving new work until they toggle back on.
- **Per-event** (`POST /events/assigned/{id}/release`) — "I can't do THIS
  one." Only the named event moves; everything else on the Coordinator's
  plate, and their general eligibility for new assignments, is untouched.

Both go through the same picker and the same reassignment logic, so all
three ACs hold identically regardless of which one triggered it.

Every acceptance criterion below maps to at least one test case, and every
automated test is named after the criterion it proves. This mirrors
[test-cases-coordinator-assigned-events.md](test-cases-coordinator-assigned-events.md),
which covers *viewing* an assigned event once one exists.

**Scope note:** an earlier draft of this doc also covered "an available
Coordinator is assigned automatically when a request is submitted." That
behaviour is real and shipped (`assign_coordinator` in
`app/services/assignment.py`, exercised on submit), but it is properly
**"Get Coordinator Assigned"** — a separate backlog item from this one.
This story is about what happens when an *already-assigned* Coordinator
goes unavailable: the reassignment, and the same three guarantees
(visibility / notification / activity log) holding for it. The initial-
assignment tests still live in `test_coordinator_availability.py`
(`test_submitting_with_an_available_coordinator_assigns_them`,
`test_submitting_with_no_coordinator_leaves_it_unassigned`,
`test_unavailable_coordinator_is_never_assigned`,
`test_assignment_picks_the_least_loaded_available_coordinator`) since the
two stories share the same picker and the same file today — they just
aren't this story's ACs, so they aren't numbered below. Whoever owns "Get
Coordinator Assigned" should get their own AC list and doc for them.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_coordinator_availability.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| All of the above | push to any branch | GitHub Actions runs them |

There is no Playwright layer for this story yet.

## The pieces

- `users.is_available` (`backend/sql/004_coordinator_availability.sql`) —
  the column a Coordinator toggles. Every role's row carries it; only a
  Coordinator's is ever read or written.
- `PATCH /coordinators/me/availability` — the global toggle. Turning it
  off triggers reassignment of every active event as a side effect of the
  same request; there is no separate "reassign" call.
- `POST /events/assigned/{event_id}/release` — the per-event action. 404s
  if the event is not assigned to the caller (same rule as
  `GET /events/assigned/{id}`); 409s if the event's status is not one that
  still needs a Coordinator (already approved/rejected/completed/
  cancelled has nothing to hand off).
- `app/services/assignment.py` — the shared picker. `assign_coordinator`
  (used by `POST /events/{id}/submit`) belongs to "Get Coordinator
  Assigned", not this story; `reassign_event` and
  `events_needing_reassignment` are this story's own — the global toggle
  calls `reassign_event` once per active event it holds, the per-event
  route calls it once for the one named. Both use the same rule --
  "Available" = `is_available` true, ties in load broken by lowest user id
  -- so a reassignment picks the same way an initial assignment would.
- `GET /notifications` — how an assignment or reassignment reaches the
  Coordinator it lands on.
- `event_status_history` — reused for the activity-log entry an assignment
  writes: `from_status` and `to_status` are both the event's current
  status (it did not change), and the note carries the real information.
  See `AssignedEventView`'s `ActivityLine`, which renders a same-status
  entry as "Assignment" rather than a status arrow into itself.

---

## Marking unavailable reassigns active work

The trigger this story is named for. Every AC below describes something
that becomes true once this fires.

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-0a | Turning availability off reassigns every active event to another available Coordinator | pytest | `test_coordinator_availability.py` › *test_marking_unavailable_reassigns_active_events_to_another_coordinator* |
| TC-CA-0b | With nobody else available, the event is left unassigned rather than the toggle failing | pytest | *test_marking_unavailable_with_no_replacement_leaves_event_unassigned* |
| TC-CA-0c | An event already finished (completed/cancelled/rejected) is left alone — only active work moves | pytest | *test_marking_unavailable_does_not_touch_completed_events* |
| TC-CA-0d | Toggling to the same value is a no-op — no spurious reassignment or log entry | pytest | *test_toggling_to_the_same_value_is_a_no_op* |
| TC-CA-0e | Availability can be turned back on, and the Coordinator is eligible for new work again | pytest | *test_availability_can_be_turned_back_on* |
| TC-CA-0f | Only a Coordinator can toggle their own availability | pytest | *test_only_a_coordinator_can_set_their_own_availability* |
| TC-CA-0g | Not signed in → 401 | pytest | *test_anonymous_cannot_set_availability*, *test_anonymous_cannot_list_notifications* |
| TC-CA-0h | The screen shows "Available"/"Unavailable" and the matching action | Vitest | `Coordinator.test.tsx` › *shows "Available" and offers to mark unavailable…*, *shows "Unavailable" and offers to mark available again…* |
| TC-CA-0i | Toggling calls the API and refreshes the signed-in user so the rest of the app sees the new state | Vitest | `Coordinator.test.tsx` › *calls the API and refreshes the signed-in user when toggled off* |
| TC-CA-0j | A failed toggle shows an error rather than silently flipping the displayed state | Vitest | `Coordinator.test.tsx` › *shows an error rather than silently failing…* |

## Releasing a single event

The narrower trigger: hands off one event without touching the rest, or
the Coordinator's own eligibility.

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-6a | Releasing one event reassigns only that one — the rest of the Coordinator's list, and their `is_available`, are untouched | pytest | `test_coordinator_availability.py` › *test_releasing_one_event_reassigns_only_that_one* |
| TC-CA-6b | Release picks an available Coordinator the same way an initial assignment would | pytest | *test_releasing_reassigns_the_least_loaded_available_coordinator* |
| TC-CA-6c | With nobody else available, the event is left unassigned rather than the request failing | pytest | *test_releasing_with_no_replacement_leaves_it_unassigned* |
| TC-CA-6d | An event assigned to someone else → 404, same rule as viewing it | pytest | *test_cannot_release_an_event_not_assigned_to_you* |
| TC-CA-6e | An event with no Coordinator at all → 404 | pytest | *test_cannot_release_an_unassigned_event* |
| TC-CA-6f | A finished event (completed/rejected/cancelled) → 409, nothing changes | pytest | *test_cannot_release_a_finished_event* |
| TC-CA-6g | Not signed in → 401 | pytest | *test_anonymous_cannot_release_an_event* |
| TC-CA-6h | "Mark unavailable for this event" appears while the event is active, and disappears once it's finished — on both the list and the detail page | Vitest | `AssignedEvents.test.tsx` › *offers the action on an active event*, *does not offer it once the event has finished*; `AssignedEventView.test.tsx` › same two, under "marking unavailable for this one event" |
| TC-CA-6i | Clicking it releases the event: the list drops the row; the detail page leaves for **My Assigned Events** | Vitest | `AssignedEvents.test.tsx` › *releases the event and drops it from the list*; `AssignedEventView.test.tsx` › *releases the event and leaves the assigned-events list* |
| TC-CA-6j | A failed release shows an error rather than silently doing nothing, on both screens | Vitest | `AssignedEvents.test.tsx` / `AssignedEventView.test.tsx` › *shows an error … when releasing fails* |

## AC1 — the Organiser can see their (newly reassigned) Coordinator

> *The Event Organiser can see who their assigned coordinator is on their
> event page.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-1a | `GET /events/{id}` names the assigned Coordinator and their email | pytest | `test_coordinator_availability.py` › *test_organiser_sees_the_assigned_coordinators_name_and_email* |
| TC-CA-1b | Before one is assigned, the field reads null, not missing or an error | pytest | *test_organiser_sees_no_coordinator_before_one_is_assigned* |
| TC-CA-1c | After a reassignment, the event page names the NEW Coordinator, not the one who went unavailable | pytest | *test_marking_unavailable_reassigns_active_events_to_another_coordinator* (checks `coordinator_id` moved) |
| TC-CA-1d | The event page shows the Coordinator's name and a `mailto:` link | Vitest | `EventView.test.tsx` › *names the Coordinator and links their email once one is assigned* |
| TC-CA-1e | Unassigned reads as "Not yet assigned", not a blank section | Vitest | `EventView.test.tsx` › *says plainly that nobody is assigned yet…* |
| TC-CA-1f | A draft (nothing to assign yet) shows no Coordinator section at all | Vitest | `EventView.test.tsx` › *does not show a Coordinator section for a draft…* |

## AC2 — the assigned Coordinator is notified

> *The assigned coordinator receives a notification of their assignment.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-2a | Reassignment notifies the new Coordinator | pytest | `test_coordinator_availability.py` › *test_marking_unavailable_reassigns_active_events_to_another_coordinator* |
| TC-CA-2b | Notifications are scoped — nobody sees another Coordinator's | pytest | *test_notification_is_scoped_to_the_assigned_coordinator* |
| TC-CA-2c | The Coordinator who went unavailable is ALSO notified of who took over — not just left to notice the event is gone | pytest | *test_outgoing_coordinator_is_notified_who_took_over* |
| TC-CA-2d | No replacement exists → no "who took over" notification, since there is nothing to report | pytest | *test_no_reassigned_away_notification_when_nobody_replaces_them* |
| TC-CA-2e | The Coordinator's own page renders each notification message | Vitest | `Coordinator.test.tsx` › *renders each notification message* |
| TC-CA-2f | No notifications yet reads as an empty state, not a missing list | Vitest | `Coordinator.test.tsx` › *shows an empty state rather than an empty box…* |

## AC3 — the (re)assignment is in the activity log, with a timestamp

> *The assignment is recorded in the event's activity log with a
> timestamp.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-3a | A reassignment writes its own entry, naming who went unavailable and who it moved to, timestamped and attributed | pytest | `test_coordinator_availability.py` › *test_reassignment_is_recorded_in_the_activity_log* |
| TC-CA-3b | The screen renders a same-status entry as "Assignment", not a status change into itself | Vitest | `AssignedEventView.test.tsx` › *renders an assignment as "Assignment"…* |

---

## Manual check

Steps 1-2 are setup ("Get Coordinator Assigned" territory — an event needs
an initial Coordinator before one can go unavailable). Step 3 onward is
this story.

1. Sign up two Coordinators (or promote two users to `coordinator`).
2. Sign in as an Organiser and submit a complete request. Confirm it picks
   up one of the two Coordinators (whichever has the lighter load).
3. Sign in as that Coordinator, open the **Event Coordinator** role page,
   and click **Mark myself unavailable**. The badge flips to "Unavailable".
4. Still as that (now unavailable) Coordinator, check **Notifications** —
   there should be a message naming who took the event over (AC2).
5. Sign in as the *other* Coordinator: the event now appears in their **My
   Assigned Events** (AC2 — reassignment notification), and opening it
   shows a "Reassigned from … to …" entry in the activity log, timestamped
   (AC3).
6. Sign in as the Organiser again and reopen the request: the **Your
   Assigned Event Coordinator** section on the event page now names the
   new Coordinator, not the one who went unavailable (AC1).
