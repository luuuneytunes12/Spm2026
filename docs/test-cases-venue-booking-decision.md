# Test Cases — Approve or Reject Venue Booking Request

> *As a Venue Staff member, I want to approve or reject a submitted booking
> request, so that the Event Coordinator receives a clear decision on the
> venue.*

Builds on Submit Venue Booking Request (SCRUM-39,
[test-cases-venue-booking-request.md](test-cases-venue-booking-request.md)),
which creates the pending request and the queue this story decides from.

Every acceptance criterion below maps to at least one test case, and every
automated test is named after the criterion it proves. Test case IDs are
`TC-VBD-<AC><letter>`; `N` is a negative or edge case, `M` the manual script.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend unit (pytest, SQLite) | `cd backend && uv run pytest -q tests/test_venue_booking_decision.py` | nothing — in-memory SQLite |
| Backend integration + concurrency (pytest, **PostgreSQL**) | `cd backend && uv run pytest -q tests/integration/test_venue_booking_decision_postgres.py` | Docker — Testcontainers starts a throwaway `postgres:16` from `db/schema.sql`. Skips with a reason if Docker is off; **fails** when `REQUIRE_INTEGRATION=1` (set in CI) |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| End-to-end + accessibility (Playwright) | `cd frontend && npx playwright test e2e/venue-booking-decision.spec.ts` | a local Postgres with `db/schema.sql` applied (see `.github/workflows/ci.yml`). The spec seeds and removes its own users and venue |
| All of the above | push to any branch | GitHub Actions runs them |

Where the tests live:

- **pytest** — `backend/tests/test_venue_booking_decision.py`
- **Postgres** — `backend/tests/integration/test_venue_booking_decision_postgres.py`
- **Vitest (queue)** — `frontend/src/pages/venues/VenueBookingQueue.test.tsx`
- **Vitest (coordinator card)** — `frontend/src/components/VenueBookingSection.test.tsx`
- **Playwright** — `frontend/e2e/venue-booking-decision.spec.ts`

## The pieces

| Endpoint | Who | Result |
|---|---|---|
| `GET /venue-bookings/queue` | Venue Staff | Pending requests, oldest first (from SCRUM-39). |
| `POST /venue-bookings/{id}/approve` | Venue Staff | Request becomes `approved`. 409 if it is already decided, or if the venue is already confirmed for another event, or blocked out, at an overlapping time. |
| `POST /venue-bookings/{id}/reject` | Venue Staff | Body `{reason?, suggested_alternative?}`, at least one non-blank (422 otherwise). Request becomes `rejected`. 409 if it is already decided. |
| `GET /venue-bookings/events/{event_id}` | the event's Coordinator | Every request for the event, newest first, each with its outcome. |

Both decisions record `reviewed_by` and `reviewed_at`. A booking response
also carries `decision_notes` (the reason) and `suggested_alternative`.

Schema: `venue_bookings.suggested_alternative` —
`backend/sql/014_venue_bookings_suggested_alternative.sql` (rollback in its
header), mirrored in `db/schema.sql`. The reason uses the existing
`decision_notes` column.

Screens: Venue Staff decide at `/venue-staff/bookings`; the Coordinator sees
the outcome in the **Venue booking** card on `/coordinator/events/{id}`.

---

## AC1 — pending requests appear in a queue for review

> *Given a new booking request is submitted, when Venue Staff open the
> system, then pending requests appear in a queue for review.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-VBD-1a | A newly submitted request is in the queue, and leaves it once approved | pytest | `test_ac1_a_new_request_is_in_the_queue_until_it_is_decided` |
| TC-VBD-1b | A rejected request leaves the queue | pytest | `test_ac1_a_rejected_request_leaves_the_queue` |
| TC-VBD-1c | On PostgreSQL: the queue holds the pending request, then is empty after the decision | Postgres | `test_ac1_to_ac5_reject_resubmit_and_approve_persist_and_reach_the_coordinator` |
| TC-VBD-1d | The queue lists each pending request under its event; says so when empty; shows an error when it cannot load | Vitest (queue) | *SCRUM-39 AC2 - the request appears in the queue* |
| TC-VBD-1e | In a browser: the request's card is visible in the queue, and still gone after a reload once decided | Playwright | *AC1 + AC2 + AC4* |

---

## AC2 — Venue Staff can either approve or reject

> *Given a submitted request, when Venue Staff review it, then they can
> either approve or reject it.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-VBD-2a | Approving sets the status to approved and records who decided and when | pytest | `test_ac2_venue_staff_can_approve_and_the_decision_records_who_and_when` |
| TC-VBD-2b | Rejecting sets the status to rejected and records who decided and when | pytest | `test_ac2_venue_staff_can_reject_and_the_decision_records_who_and_when` |
| TC-VBD-2c | Every pending card offers both **Approve** and **Reject** | Vitest (queue) | *offers both decisions on every pending request* |
| TC-VBD-2d | Approve: the request leaves the queue, a confirmation appears and takes focus, other requests stay | Vitest (queue) | *approves the request, takes it out of the queue and confirms the decision* |
| TC-VBD-2e | Reject: the request leaves the queue and a confirmation appears | Vitest (queue) | *rejects the request, takes it out of the queue and confirms the decision* |
| TC-VBD-2f | In a browser: Venue Staff approve a queued request | Playwright | *AC1 + AC2 + AC4* |
| TC-VBD-2g | In a browser: Venue Staff reject a queued request | Playwright | *AC2 + AC3 + AC4 + AC5* |

---

## AC3 — a rejection records a reason, an alternative, or both

> *Given Venue Staff reject a request, when they submit the rejection, then
> a reason, an alternative, or both can be recorded against the decision and
> is visible to the Event Coordinator.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-VBD-3a | A rejection with a reason only is saved and returned to the Coordinator | pytest | `test_ac3_a_rejection_records_a_reason_an_alternative_or_both_for_the_coordinator[reason]` |
| TC-VBD-3b | A rejection with an alternative only is saved and returned to the Coordinator | pytest | `…[alternative]` |
| TC-VBD-3c | A rejection with both is saved and returned to the Coordinator | pytest | `…[both]` |
| TC-VBD-3d | A rejection with neither (empty, blank or null) is refused with 422 and the request stays pending | pytest | `test_ac3_a_rejection_with_neither_is_refused_and_the_request_stays_pending` |
| TC-VBD-3e | A reason over 2000 characters is refused and nothing is saved | pytest | `test_ac3_an_overlong_reason_is_refused_and_nothing_is_saved` |
| TC-VBD-3f | The form sends a reason only, an alternative only, or both | Vitest (queue) | *AC3* › *sends a reason only / an alternative only / both* |
| TC-VBD-3g | **Confirm rejection** stays disabled with neither, or with only spaces | Vitest (queue) | *cannot be confirmed with neither, or with only spaces* |
| TC-VBD-3h | **Cancel** closes the form and leaves the request undecided | Vitest (queue) | *can be cancelled, leaving the request undecided* |
| TC-VBD-3i | The Coordinator's card shows the reason, the alternative and who decided | Vitest (coordinator card) | *shows a rejection with its reason, its alternative and who decided* |
| TC-VBD-3j | The card leaves out whichever of the two was not given | Vitest (coordinator card) | *leaves out whichever of the two was not given* |
| TC-VBD-3k | In a browser: a rejection with both, then one with an alternative only, each shown on the Coordinator's page | Playwright | *AC2 + AC3 + AC4 + AC5* |

---

## AC4 — the outcome is visible to the Event Coordinator

> *Given Venue Staff have made a decision, when the Event Coordinator views
> the request, then the outcome is visible to them.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-VBD-4a | The Coordinator sees an approval with who decided and when; nothing is shown before the decision | pytest | `test_ac4_the_coordinator_sees_an_approval_with_who_decided_and_when` |
| TC-VBD-4b | The Coordinator sees a rejection with who decided and when | pytest | `test_ac4_the_coordinator_sees_a_rejection_with_who_decided_and_when` |
| TC-VBD-4c | The card shows "Approved" with the decider's name, and no submit form | Vitest (coordinator card) | *shows an approval with who decided, and no form* |
| TC-VBD-4d | The card shows no decision while the request is still pending | Vitest (coordinator card) | *shows no decision while the request is still pending* |
| TC-VBD-4e | In a browser: after Venue Staff decide, the Coordinator's event page shows the outcome | Playwright | *AC1 + AC2 + AC4*, *AC2 + AC3 + AC4 + AC5* |

---

## AC5 — a rejected request can be resubmitted and reviewed again, without limit

> *Given a request has been rejected or returned, when the coordinator
> resubmits it, then it can be reviewed again, with no limit on the number
> of times.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-VBD-5a | Reject then resubmit, five rounds in a row: each resubmission is back in the queue; the last is approved; all earlier decisions are kept | pytest | `test_ac5_a_rejected_request_can_be_resubmitted_and_reviewed_again_without_limit` |
| TC-VBD-5b | On PostgreSQL: reject, resubmit, approve — both requests persist with their own outcome | Postgres | `test_ac1_to_ac5_reject_resubmit_and_approve_persist_and_reach_the_coordinator` |
| TC-VBD-5c | After a rejection the form is offered again; submitting creates a new pending request and keeps the rejection under **Earlier requests** | Vitest (coordinator card) | *offers the form again after a rejection and submits a new request* |
| TC-VBD-5d | The form is offered again however many rejections there have been; the latest is shown first | Vitest (coordinator card) | *offers the form again however many times the request has been rejected* |
| TC-VBD-5e | In a browser: rejected twice, resubmitted twice, then approved | Playwright | *AC2 + AC3 + AC4 + AC5* |

---

## Additional cases beyond the acceptance criteria (DoD 3)

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-VBD-N1 | A Coordinator, an Organiser and a signed-out caller cannot approve or reject (403 / 403 / 401); the request stays pending | pytest | `test_only_venue_staff_can_decide` |
| TC-VBD-N2 | In a browser: a Coordinator's approve and reject calls are refused and the request is still in the queue | Playwright | *negative: a Coordinator cannot decide on a booking request* |
| TC-VBD-N3 | A Coordinator the event is not assigned to cannot see the outcome | pytest | `test_ac4_the_outcome_is_not_visible_to_another_coordinator` |
| TC-VBD-N4 | Deciding on a request that does not exist returns 404 | pytest | `test_deciding_on_an_unknown_request_is_not_found` |
| TC-VBD-N5 | An approved request cannot be approved or rejected again; the first decision stands | pytest | `test_an_approved_request_cannot_be_decided_again` |
| TC-VBD-N6 | A rejected request cannot be decided again; its reason is unchanged | pytest | `test_a_rejected_request_cannot_be_decided_again` |
| TC-VBD-N7 | A venue already confirmed for an overlapping event cannot be approved again; the second request stays pending | pytest | `test_a_venue_already_confirmed_for_an_overlapping_event_cannot_be_approved_again` |
| TC-VBD-N8 | A booking that starts exactly when another ends can be approved | pytest | `test_a_back_to_back_booking_of_the_same_venue_can_be_approved` |
| TC-VBD-N9 | A venue blocked out for that time cannot be approved | pytest | `test_a_venue_blocked_out_for_that_time_cannot_be_approved` |
| TC-VBD-N10 | A refused decision shows the server's reason on the card and keeps it in the queue | Vitest (queue) | *shows why a decision was refused and keeps the request in the queue* |
| TC-VBD-N11 | Concurrency: the same approve fired six times at once decides the request exactly once | Postgres | `test_an_approve_fired_many_times_at_once_decides_the_request_exactly_once` |
| TC-VBD-N12 | Concurrency: approve and reject at the same moment leave one consistent decision | Postgres | `test_an_approve_and_a_reject_at_the_same_moment_leave_one_consistent_decision` |
| TC-VBD-N13 | Concurrency: six requests for one venue and time approved at once confirm only one | Postgres | `test_two_requests_for_the_same_venue_and_time_approved_at_once_confirm_only_one` |
| TC-VBD-N14 | Accessibility: no serious or critical axe violations with the rejection form open; the whole reject flow works from the keyboard, with focus moving into the form and then onto the confirmation | Playwright | *accessibility: the decision controls have no serious axe violations and work from the keyboard* |

Audit trail: `reviewed_by` and `reviewed_at` are asserted in TC-VBD-2a, 2b,
4a and 4b. A decided request is refused any further decision (TC-VBD-N5,
N6), so the record cannot be overwritten.

Persistence: the Postgres tests use a separate session per request, and the
Playwright tests reload both the queue and the Coordinator's page.

---

## Manual test — TC-VBD-M1

**Preconditions:** `backend/sql/014_venue_bookings_suggested_alternative.sql`
applied; backend and frontend running; an Organiser, a Coordinator and a
Venue Staff account, each signed in in its own browser window; at least one
active venue. An event has been submitted by the Organiser, approved by the
Coordinator, and the Coordinator has submitted a venue booking request for
it (it shows **Pending review**).

| # | As | Step | Expected result |
|---|---|---|---|
| 1 | Venue Staff | Open **Booking Requests** | The request is listed with its venue, date and time, attendance and needs, and **Approve** and **Reject** buttons (AC1, AC2) |
| 2 | Venue Staff | Click **Reject** | A form opens with **Reason** and **Suggested alternative**; **Confirm rejection** is disabled |
| 3 | Venue Staff | Type only spaces in **Reason** | **Confirm rejection** is still disabled |
| 4 | Venue Staff | Type a reason and a suggested alternative, click **Confirm rejection** | The card disappears; "Rejected: …" confirmation appears (AC2, AC3) |
| 5 | Venue Staff | Refresh the page | The request is still gone |
| 6 | Coordinator | Refresh the event page | The Venue booking card shows **Rejected**, the reason, the alternative, and who decided and when (AC3, AC4) |
| 7 | Coordinator | Pick a venue and click **Submit booking request** | The card shows **Pending review**; the rejection is listed under **Earlier requests** with its reason (AC5) |
| 8 | Venue Staff | Refresh the queue | The request is back (AC5) |
| 9 | Venue Staff | Reject again with only a suggested alternative | The card disappears (AC3) |
| 10 | Coordinator | Refresh, then submit the request again | Only the alternative is shown for the latest rejection; the request is pending again (AC5, second time) |
| 11 | Venue Staff | Refresh and click **Approve** | "Approved: …" confirmation appears; the queue is empty (AC2) |
| 12 | Coordinator | Refresh the event page | The card shows **Approved** with who decided; the submit form is gone; both rejections are under **Earlier requests** (AC4) |
| 13 | Coordinator | Go to `/venue-staff/bookings` directly | The Forbidden page is shown |
| 14 | Venue Staff | With a second pending request for the same venue and time, click **Approve** | "The venue is already booked for another event at that time."; the request stays in the queue and can still be rejected |
| 15 | Venue Staff | Repeat steps 2–4 using only the keyboard (Tab, Enter) | Every control is reachable with a visible focus ring |
| 16 | Venue Staff | Narrow the window to ~400px, then toggle dark mode | The card and form stay readable; nothing scrolls sideways |

**Tester:** ______________ **Date:** ____________ **Result:** Pass / Fail

---

## Decisions taken

- **A rejection needs at least one of reason or alternative.** AC3 lists "a
  reason, an alternative, or both"; a rejection with neither is refused.
- **The alternative is free text**, so it can be another venue, another date
  or anything else.
- **"Returned" has no status of its own.** The booking statuses are pending /
  approved / rejected / cancelled; a rejection that suggests an alternative is
  the "returned" case in AC5.
- **Resubmitting creates a new request**; rejected ones stay as history, each
  with its own decision.
- **Approval refuses a double-booking** using the venue search's overlap rule.
  It does not change the event's status.

## Not covered (separate stories)

Notifying the Coordinator when a decision is made; notifying Venue Staff of a
new request (SCRUM-54); cancelling an approved booking.
