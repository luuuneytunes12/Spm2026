# Test Cases — Coordinator Availability

Covers two related backlog items:

- **SCRUM-24 Declare Coordinator Global Unavailability.** *As an Event
  Coordinator, I want to mark myself as unavailable, so that I stop
  receiving new ones until I'm available again.*

  Acceptance criteria:
  1. Marking my global status "Unavailable" shows "Unavailable" on my
     profile until I mark myself "Available" again.
  2. While "Unavailable", I am excluded from the pool of assignable
     Coordinators when a new event is being assigned.
  3. Marking myself "Available" again puts me back in the pool.
  4. Each change is recorded with a timestamp, even with no active events.

- **SCRUM-64 Declare Coordinator Per-Event Unavailability** — declining one
  specific event so it is reassigned to another Coordinator.

The two forms behave differently on purpose:

- **Global** (`PATCH /coordinators/me/availability`) — the Coordinator
  stops receiving NEW work until they toggle back on. It does **not** move
  anything they already hold: those events stay with them, and they can
  keep working them. Nothing is reassigned, so no reassignment
  notification or activity-log entry is produced.
- **Per-event** (`POST /events/assigned/{id}/release`) — "I can't do THIS
  one." Only the named event moves (through the same picker as an initial
  assignment); everything else on the Coordinator's plate, and their
  general eligibility for new assignments, is untouched.

The ACs numbered **AC1-AC3 below** (Organiser sees the coordinator, the
coordinator is notified, the assignment is logged) are the older
"who is on my event" guarantees. They are now driven by the per-event
release, since the global toggle no longer reassigns; the Organiser-side
view of them is SCRUM-23, covered in
`backend/tests/test_organiser_coordinator_visibility.py`.

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
`test_scrum24_ac2_unavailable_coordinator_is_never_assigned`,
`test_assignment_picks_the_least_loaded_available_coordinator`) since the
two stories share the same picker and the same file today — they just
aren't this story's ACs, so they aren't numbered below. Whoever owns "Get
Coordinator Assigned" should get their own AC list and doc for them.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend unit (pytest, SQLite) | `cd backend && uv run pytest -q --ignore=tests/integration` | nothing — in-memory SQLite |
| Backend integration + concurrency (pytest, **PostgreSQL**) | `cd backend && uv run pytest -q tests/integration` | Docker — Testcontainers starts a throwaway `postgres:16` from `db/schema.sql`. Skips with a reason if Docker is off; **fails** when `REQUIRE_INTEGRATION=1` (set in CI) |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| End-to-end + accessibility (Playwright, real browser) | `cd frontend && npm run test:e2e` | a local Postgres on `localhost:5432` with `db/schema.sql` applied and the `e2e_organiser` seeded (CI does this; see `.github/workflows/ci.yml`). The specs seed and remove their own coordinator accounts |
| All of the above | push to any branch | GitHub Actions runs them |

## The pieces

- `users.is_available` (`backend/sql/004_coordinator_availability.sql`) —
  the column a Coordinator toggles. Every role's row carries it; only a
  Coordinator's is ever read or written.
- `PATCH /coordinators/me/availability` — the global toggle. It only flips
  the flag and records history; it moves no events.
- `GET /coordinators/available-count` — Organiser-only debugging aid: the
  Coordinators currently in the assignment pool (`id`, `name`, `email`) and
  how many there are (`test_available_coordinator_count.py`, and the
  collapsible `AvailableCoordinatorsCount` dropdown on the Organiser's
  request list and event page).
- `POST /events/assigned/{event_id}/release` — the per-event action. 404s
  if the event is not assigned to the caller (same rule as
  `GET /events/assigned/{id}`); 409s if the event's status is not one that
  still needs a Coordinator (already approved/rejected/completed/
  cancelled has nothing to hand off).
- `app/services/assignment.py` — the shared picker. `assign_coordinator`
  (used by `POST /events/{id}/submit`) belongs to "Get Coordinator
  Assigned", not this story; `reassign_event` is used by the per-event
  release only. Both it and `assign_coordinator` draw from
  `available_coordinators` -- "Available" = `is_available` true, ties in
  load broken by lowest user id -- the same query the Organiser's count
  reports, so a reassignment picks the same way an initial assignment
  would.
- `GET /notifications` — how an assignment or reassignment reaches the
  Coordinator it lands on.
- `event_status_history` — reused for the activity-log entry an assignment
  writes: `from_status` and `to_status` are both the event's current
  status (it did not change), and the note carries the real information.
  See `AssignedEventView`'s `ActivityLine`, which renders a same-status
  entry as "Assignment" rather than a status arrow into itself.

---

## Marking unavailable stops NEW work (SCRUM-24)

The trigger this story is named for. It changes who is picked next; it
never moves what a Coordinator already holds.

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-0a | Turning availability off leaves the events already assigned to that Coordinator with them | pytest | `test_coordinator_availability.py` › *test_marking_unavailable_leaves_current_events_with_the_coordinator* |
| TC-CA-0b | That holds even when nobody else is available — the event is NOT left unassigned | pytest | *test_marking_unavailable_keeps_the_event_even_when_nobody_else_is_available* |
| TC-CA-0c | It leaves no trace: no event activity-log entry, and no notification to the Coordinator, the Organiser or anyone else | pytest | *test_marking_unavailable_leaves_no_trace_on_the_event_or_in_notifications* |
| TC-CA-0k | An unavailable Coordinator can still open and approve the events they hold | pytest | *test_an_unavailable_coordinator_can_still_work_the_events_they_hold* |
| TC-CA-0l | New events skip the unavailable Coordinator while their old ones stay put | pytest | *test_new_events_skip_the_unavailable_coordinator_but_old_ones_stay* |
| TC-CA-0m | An unavailable Coordinator is never assigned a new event (SCRUM-24 AC2) | pytest | *test_scrum24_ac2_unavailable_coordinator_is_never_assigned* |
| TC-CA-0o | A Coordinator's **profile** (`/profile`) shows their availability — "Available" or "Unavailable" — as read-only status, updates when it flips, links to the Coordinator page to change it, and is not shown to any other role (SCRUM-24 AC1) | Vitest | `Profile.test.tsx` › *SCRUM-24 AC1 - a Coordinator's profile shows their availability* |
| TC-CA-0n | The page tells the truth: new events won't be assigned, existing ones stay — and it never promises a hand-over | Vitest | `Coordinator.test.tsx` › *what "Unavailable" means, as the page words it* |
| TC-CA-0d | Toggling to the same value is a no-op — no spurious history entry | pytest | *test_toggling_to_the_same_value_is_a_no_op* |
| TC-CA-0e | Availability can be turned back on, and the Coordinator is eligible for new work again (SCRUM-24 AC3) | pytest | *test_scrum24_ac3_availability_can_be_turned_back_on* |
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
| TC-CA-6a | Releasing one event reassigns only that one — the rest of the Coordinator's list, and their `is_available`, are untouched | pytest | `test_coordinator_availability.py` › *test_64_ac1_releasing_one_event_reassigns_only_that_one* |
| TC-CA-6b | Release picks an available Coordinator the same way an initial assignment would | pytest | *test_releasing_reassigns_the_least_loaded_available_coordinator* |
| TC-CA-6c | With nobody else available, the event is left unassigned rather than the request failing | pytest | *test_releasing_with_no_replacement_leaves_it_unassigned* |
| TC-CA-6k | ...and the decline is STILL recorded in the activity log with the decliner's name and a timestamp (SCRUM-64 AC4 is unconditional) | pytest | *test_64_ac4_a_decline_is_logged_even_when_nobody_else_can_take_the_event* |
| TC-CA-6d | An event assigned to someone else → 404, same rule as viewing it | pytest | *test_cannot_release_an_event_not_assigned_to_you* |
| TC-CA-6e | An event with no Coordinator at all → 404 | pytest | *test_cannot_release_an_unassigned_event* |
| TC-CA-6f | A finished event (completed/rejected/cancelled) → 409, nothing changes | pytest | *test_cannot_release_a_finished_event* |
| TC-CA-6g | Not signed in → 401 | pytest | *test_anonymous_cannot_release_an_event* |
| TC-CA-6h | "Mark unavailable for this event" appears while the event is active, and disappears once it's finished — on both the list and the detail page | Vitest | `AssignedEvents.test.tsx` › *offers the action on an active event*, *does not offer it once the event has finished*; `AssignedEventView.test.tsx` › same two, under "marking unavailable for this one event" |
| TC-CA-6i | Clicking it releases the event: the list drops the row; the detail page leaves for **My Assigned Events** | Vitest | `AssignedEvents.test.tsx` › *releases the event and drops it from the list*; `AssignedEventView.test.tsx` › *releases the event and leaves the assigned-events list* |
| TC-CA-6j | A failed release shows an error rather than silently doing nothing, on both screens | Vitest | `AssignedEvents.test.tsx` / `AssignedEventView.test.tsx` › *shows an error … when releasing fails* |

## Organiser-facing debugging aid — coordinators available

The Organiser sees how many Coordinators a new submission could go to, and
can expand a dropdown to see exactly who they are, so a request sitting
"Not yet assigned" is explainable (nobody available).

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-4a | The count equals the number of available Coordinators; 0 when there are none; `available` always equals the list length | pytest | `test_available_coordinator_count.py` › *test_the_count_is_zero_…*, *test_the_count_is_the_number_of_available_coordinators*, *test_the_count_always_equals_the_length_of_the_list* |
| TC-CA-4g | The pool lists each available Coordinator by name and email; an unavailable one leaves the list and returns when available; the list is empty when nobody is | pytest | *test_the_pool_lists_each_available_coordinator_by_name_and_email*, *test_an_unavailable_coordinator_leaves_the_list_and_returns_when_available*, *test_the_list_is_empty_when_nobody_is_available* |
| TC-CA-4h | The listed Coordinator is who a new event actually goes to, and only `id`, `name`, `email` are exposed (no hash, role, flag or workload) | pytest | *test_the_listed_coordinator_is_who_a_new_event_actually_goes_to*, *test_the_list_exposes_only_id_name_and_email* |
| TC-CA-4b | Non-Coordinators are not counted | pytest | *test_the_count_ignores_users_who_are_not_coordinators* |
| TC-CA-4c | Going unavailable lowers it; coming back raises it; declining one event leaves it alone | pytest | *test_going_unavailable_lowers_the_count_…*, *test_declining_one_event_does_not_change_the_count* |
| TC-CA-4d | It matches reality: 0 → a submission stays unassigned; >0 → it gets a Coordinator | pytest | *test_zero_available_means_…*, *test_a_positive_count_means_…* |
| TC-CA-4e | Coordinators, Attendees and anonymous callers are refused (403/401) | pytest | *test_a_coordinator_cannot_read_the_count*, *test_an_attendee_…*, *test_an_anonymous_…* |
| TC-CA-4f | The summary shows the count and starts collapsed (names hidden); opening it lists every Coordinator with a `mailto:` link, and a second click collapses it; an empty pool is a plain explanation with nothing to expand; loading or a failed fetch shows nothing | Vitest | `AvailableCoordinatorsCount.test.tsx` (the summary / the dropdown / an empty pool / when the pool is not shown) |
| TC-CA-4i | The dropdown appears on the request list and beside the Coordinator card (not on a draft) and opens to the names | Vitest | `MyRequests.test.tsx` and `EventView.test.tsx` › *coordinators available (debugging aid)* |

## AC1 — the Organiser can see their (newly reassigned) Coordinator

> *The Event Organiser can see who their assigned coordinator is on their
> event page.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-1a | `GET /events/{id}` names the assigned Coordinator and their email | pytest | `test_coordinator_availability.py` › *test_organiser_sees_the_assigned_coordinators_name_and_email* |
| TC-CA-1b | Before one is assigned, the field reads null, not missing or an error | pytest | *test_organiser_sees_no_coordinator_before_one_is_assigned* |
| TC-CA-1c | After a reassignment (a declined event), the event page names the NEW Coordinator, not the one who declined | pytest | `test_organiser_coordinator_visibility.py` › *test_ac3_organiser_sees_new_coordinators_name_and_contact_after_reassignment* |
| TC-CA-1d | The event page shows the Coordinator's name and a `mailto:` link | Vitest | `EventView.test.tsx` › *names the Coordinator and links their email once one is assigned* |
| TC-CA-1e | Unassigned reads as "Not yet assigned", not a blank section | Vitest | `EventView.test.tsx` › *says plainly that nobody is assigned yet…* |
| TC-CA-1f | A draft (nothing to assign yet) shows no Coordinator section at all | Vitest | `EventView.test.tsx` › *does not show a Coordinator section for a draft…* |

## AC2 — the assigned Coordinator is notified

> *The assigned coordinator receives a notification of their assignment.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-2a | Reassignment notifies the new Coordinator | pytest | `test_coordinator_availability.py` › *test_releasing_is_recorded_in_the_activity_log_and_notifies_both_sides* |
| TC-CA-2b | Notifications are scoped — nobody sees another Coordinator's | pytest | *test_notification_is_scoped_to_the_assigned_coordinator* |
| TC-CA-2c | The Coordinator who declined is ALSO notified of who took over — not just left to notice the event is gone | pytest | *test_releasing_is_recorded_in_the_activity_log_and_notifies_both_sides*; role-specific delivery in `test_organiser_coordinator_visibility.py` › *test_reassignment_sends_the_outgoing_coordinator_only_their_own_notice* |
| TC-CA-2d | No replacement exists → the Organiser gets no second "now coordinating" notification, since nobody took over | pytest | `test_organiser_coordinator_visibility.py` › *test_ac4_no_second_notification_when_reassignment_finds_nobody* |
| TC-CA-2e | The Coordinator's own page renders each notification message | Vitest | `Coordinator.test.tsx` › *renders each notification message* |
| TC-CA-2f | No notifications yet reads as an empty state, not a missing list | Vitest | `Coordinator.test.tsx` › *shows an empty state rather than an empty box…* |

## AC3 — the (re)assignment is in the activity log, with a timestamp

> *The assignment is recorded in the event's activity log with a
> timestamp.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-3a | A reassignment writes its own entry, naming who declined and who it moved to, timestamped and attributed | pytest | `test_coordinator_availability.py` › *test_releasing_is_recorded_in_the_activity_log_and_notifies_both_sides* |
| TC-CA-3b | The screen renders a same-status entry as "Assignment", not a status change into itself | Vitest | `AssignedEventView.test.tsx` › *renders an assignment as "Assignment"…* |

---

## Integration and concurrency — real PostgreSQL

SQLite serialises every write, so it can never show a race. These run on the
production engine, with every request in its own session, and repeat each
story's criteria plus the cases where two requests overlap.
Files: `backend/tests/integration/test_coordinator_stories_postgres.py`
(criteria) and `test_coordinator_concurrency_postgres.py` (races).

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-7a | SCRUM-23 AC1-AC4 hold on Postgres: coordinator shown, Organiser notified, new coordinator shown and notified after a decline; notifications role-specific, log shared | pytest (Postgres) | `test_scrum23_*` |
| TC-CA-7b | SCRUM-24 AC1-AC4 on Postgres: status persists across separate sessions; excluded from and restored to the pool; held events don't move; each change logged with a timezone-aware timestamp | pytest (Postgres) | `test_scrum24_*` |
| TC-CA-7c | SCRUM-28 on Postgres: every requirement, organiser contact, status, log; someone else's event is invisible | pytest (Postgres) | `test_scrum28_*` |
| TC-CA-7d | SCRUM-64 on Postgres: reassigns one event, stays available and in the pool, decline logged with actor and time — also with nobody to take over; a second decline is refused | pytest (Postgres) | `test_scrum64_*` |
| TC-CA-8a | A **double-clicked Submit** (6 at once) assigns and notifies exactly once — one 200, the rest 409 | pytest (Postgres) | `test_a_submit_fired_many_times_at_once_assigns_the_event_exactly_once` |
| TC-CA-8b | A **double-clicked Decline** (6 at once) hands the event over exactly once and logs one decline (SCRUM-64 AC4) — one 200, the rest 404 | pytest (Postgres) | `test_a_decline_fired_many_times_at_once_hands_the_event_over_exactly_once` |
| TC-CA-8c | The **same availability change** sent 6 times at once is recorded once (SCRUM-24 AC4) | pytest (Postgres) | `test_the_same_availability_change_sent_many_times_at_once_is_recorded_once` |
| TC-CA-8d | **Opposing** availability changes at once leave the history consistent with the final flag, every entry a real change | pytest (Postgres) | `test_opposing_availability_changes_at_once_…` |
| TC-CA-8e | Events submitted at the same moment never go to an unavailable coordinator (SCRUM-24 AC2) | pytest (Postgres) | `test_events_submitted_at_the_same_moment_never_go_to_a_coordinator_who_is_unavailable` |

The races behind 8a-8d were real: before the row locks on Submit, Decline and
the availability toggle (`SELECT ... FOR UPDATE`), all six overlapping
requests succeeded. Approve and Reject (`_get_reviewable_event`) have the same
shape and are not yet locked.

## End-to-end and accessibility — real browser

`frontend/e2e/coordinator-stories.spec.ts` drives the four stories on screen
(Organiser, Sam Tan and Priya Nair in separate browser contexts);
`coordinator-a11y.spec.ts` runs axe and keyboard-only checks. Getting an event
submitted is done through the API — it is the starting position, not the
behaviour under test.

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-CA-9a | SCRUM-23 AC1 / AC2 / log-vs-notifications on screen: coordinator card, bell count, notification with details and a working "View event" link | Playwright | `coordinator-stories.spec.ts` › *SCRUM-23 …* |
| TC-CA-9b | SCRUM-64 AC1-AC4 (+ SCRUM-23 AC3/AC4) on screen: decline drops the row, still Available on `/coordinator` and `/profile`, next event comes back to them, decline in the log with name and time — also with nobody to take over | Playwright | *SCRUM-64 …* |
| TC-CA-9c | SCRUM-24 AC1 / AC4 on screen: Unavailable on the Coordinator page and `/profile` until they return, survives reload, each change appears in History with a time **immediately** | Playwright | *SCRUM-24 AC1 + AC4 …* |
| TC-CA-9d | SCRUM-24 AC2 / AC3 on screen: the pool dropdown shows who is assignable; an unavailable coordinator leaves it, keeps their held event, and rejoins | Playwright | *SCRUM-24 AC2 + AC3 …*; *with nobody available …* |
| TC-CA-9e | SCRUM-28 AC1-AC5 on screen: every requirement, organiser contact, status, log; someone else's event is refused | Playwright | *SCRUM-28 …* |
| TC-CA-9f | The pool dropdown opens and closes from the keyboard (Enter/Space) with a visible focus indicator — the case jsdom cannot test | Playwright | *the coordinator dropdown opens and closes from the keyboard …* |
| TC-CA-10a | **axe**: no serious or critical violations on `/coordinator` (available, unavailable + history), `/profile`, `/coordinator/events`, `/coordinator/events/:id`, `/organiser/events` (pool collapsed and open), `/organiser/events/:id`, `/notifications` and the bell panel — in **both** light and dark themes | Playwright + axe | `coordinator-a11y.spec.ts` › *axe, light theme* / *axe, dark theme* |
| TC-CA-10b | Keyboard only: Tab reaches and Enter operates "Mark myself unavailable", "Decline this event" and the pool dropdown, each with a visible focus indicator; every profile field has a label | Playwright | *keyboard only* |

What these found (each fixed, with a regression test): the History list did
not refresh after toggling until a page reload
(`Coordinator.test.tsx` › *the history follows the status without a page
reload*); and the muted-text colour token failed WCAG AA contrast in both
themes (`--text-muted` in `index.css`).

---

## Manual check

Steps 1-2 are setup ("Get Coordinator Assigned" territory — an event needs
an initial Coordinator first).

1. Sign up two Coordinators (or promote two users to `coordinator`).
2. Sign in as an Organiser and open **My Event Requests**: the line
   "Coordinators currently available for assignment" should read 2; click
   it to expand the list of both Coordinators (name and email). Submit
   a complete request and confirm it picks up one of the two (whichever has
   the lighter load).
3. Sign in as that Coordinator, open the **Event Coordinator** role page,
   and click **Mark myself unavailable**. The badge flips to "Unavailable"
   and the History list gains a timestamped entry (SCRUM-24 AC1, AC4).
   Open **My profile** (`/profile`): its **Availability** card also reads
   "Unavailable" (AC1), and reads "Available" again after step 6.
4. Open **My Assigned Events**: the event is **still there**, and you can
   still open and approve it. Nothing was handed over, and no notification
   was sent to anyone.
5. Back as the Organiser: the count now reads 1, and the request's
   **Your Assigned Event Coordinator** card still names the same person.
   Submit a second request: it goes to the *other* Coordinator (AC2).
6. As the first Coordinator, click **Mark myself available**: the count
   reads 2 again (AC3), and a third request can be assigned to them.
7. To see a hand-over, click **Decline this event** on a held event
   (SCRUM-64): it moves to the other Coordinator, the Organiser's card
   shows the new name, and both Coordinators and the Organiser get their
   own notification.
