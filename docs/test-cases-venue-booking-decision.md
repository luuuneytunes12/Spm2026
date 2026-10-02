# Test cases — Approve or Reject Venue Booking Request

> As a Venue Staff member, I want to approve or reject a submitted booking request, so that the Event Coordinator receives a clear decision on the venue.

Builds on Submit Venue Booking Request (SCRUM-39, [test-cases-venue-booking-request.md](test-cases-venue-booking-request.md)), which creates the pending request and the queue this story decides from.

## Endpoints added

| Endpoint | Who | Result |
|---|---|---|
| `POST /venue-bookings/{id}/approve` | Venue Staff | Request becomes `approved`. 409 if it is already decided, or if the venue is already confirmed for another event, or blocked out, at an overlapping time. |
| `POST /venue-bookings/{id}/reject` | Venue Staff | Body `{reason?, suggested_alternative?}`, at least one non-blank (422 otherwise). Request becomes `rejected`. 409 if it is already decided. |

Both record `reviewed_by` and `reviewed_at`. `VenueBookingOut` (the queue, and the Coordinator's `GET /venue-bookings/events/{event_id}`) now also carries `decision_notes`, `suggested_alternative`, `reviewed_by` and `reviewed_at`.

Schema: `venue_bookings.suggested_alternative` — `backend/sql/014_venue_bookings_suggested_alternative.sql` (rollback in its header), mirrored in `db/schema.sql`. The reason uses the existing `decision_notes` column.

## Acceptance criteria

| AC | Criterion | Backend unit (`tests/test_venue_booking_decision.py`) | Postgres (`tests/integration/test_venue_booking_decision_postgres.py`) | Vitest | Playwright (`e2e/venue-booking-decision.spec.ts`) |
|---|---|---|---|---|---|
| AC1 | Pending requests appear in a queue for review | `ac1_a_new_request_is_in_the_queue_until_it_is_decided`, `ac1_a_rejected_request_leaves_the_queue` | `ac1_to_ac5_…` | `VenueBookingQueue.test.tsx` "SCRUM-39 AC2" (queue listing) | "AC1 + AC2 + AC4" |
| AC2 | Venue Staff can either approve or reject | `ac2_venue_staff_can_approve_…`, `ac2_venue_staff_can_reject_…` | `ac1_to_ac5_…` | `VenueBookingQueue.test.tsx` "AC2" | "AC1 + AC2 + AC4", "AC2 + AC3 + AC4 + AC5" |
| AC3 | A rejection records a reason, an alternative, or both, visible to the Coordinator | `ac3_a_rejection_records_…` (reason / alternative / both), `ac3_a_rejection_with_neither_is_refused_…`, `ac3_an_overlong_reason_is_refused_…` | `ac1_to_ac5_…` | `VenueBookingQueue.test.tsx` "AC3"; `VenueBookingSection.test.tsx` "AC3" | "AC2 + AC3 + AC4 + AC5" |
| AC4 | The outcome is visible to the Event Coordinator | `ac4_the_coordinator_sees_an_approval_…`, `ac4_the_coordinator_sees_a_rejection_…` | `ac1_to_ac5_…` | `VenueBookingSection.test.tsx` "AC4" | "AC1 + AC2 + AC4", "AC2 + AC3 + AC4 + AC5" |
| AC5 | A rejected request can be resubmitted and reviewed again, with no limit | `ac5_a_rejected_request_can_be_resubmitted_and_reviewed_again_without_limit` (five rounds) | `ac1_to_ac5_…` | `VenueBookingSection.test.tsx` "AC5" | "AC2 + AC3 + AC4 + AC5" (two rejections, then approved) |

## Negative and edge cases (DoD 3)

| Case | Test |
|---|---|
| Wrong role (coordinator / organiser / anonymous) cannot decide; state unchanged | `test_only_venue_staff_can_decide`; e2e "negative: a Coordinator cannot decide" |
| Outcome not visible to a Coordinator the event is not assigned to | `ac4_the_outcome_is_not_visible_to_another_coordinator` |
| Unknown request | `test_deciding_on_an_unknown_request_is_not_found` |
| Invalid transition: a decided request cannot be decided again, first decision stands | `test_an_approved_request_cannot_be_decided_again`, `test_a_rejected_request_cannot_be_decided_again` |
| Validation: neither reason nor alternative (empty, blank, null); reason over 2000 characters | `ac3_a_rejection_with_neither_…`, `ac3_an_overlong_reason_…`; Vitest "cannot be confirmed with neither, or with only spaces" |
| Double-booking: venue already confirmed for an overlapping event, or blocked out; back-to-back is allowed | `test_a_venue_already_confirmed_for_an_overlapping_event_…`, `test_a_venue_blocked_out_for_that_time_…`, `test_a_back_to_back_booking_…`; Vitest "shows why a decision was refused…" |
| Concurrent decisions on Postgres: a repeated approve; approve racing reject; several requests for one venue and time approved at once | `…approve_fired_many_times_at_once_decides_the_request_exactly_once`, `…approve_and_a_reject_at_the_same_moment_…`, `…two_requests_for_the_same_venue_and_time_approved_at_once_confirm_only_one` |

## Audit, persistence, accessibility

- Actor and time: `reviewed_by` and `reviewed_at` are asserted in the AC2 and AC4 tests. A decided request is refused any further decision, so the record cannot be overwritten.
- Persistence across reload / sessions: the Postgres tests use a session per request; e2e reloads both the queue and the Coordinator's page.
- Accessibility: e2e axe check with the rejection form open (no serious/critical), both text areas labelled, and the whole reject flow driven from the keyboard, with focus moving into the form and then onto the confirmation.

## Decisions taken

- **A rejection needs at least one of reason or alternative.** AC3 lists "a reason, an alternative, or both"; a rejection with neither is refused.
- **The alternative is free text**, so it can be another venue, another date or anything else.
- **"Returned" has no status of its own.** The booking statuses are pending / approved / rejected / cancelled; a rejection that suggests an alternative is the "returned" case in AC5.
- **Resubmitting creates a new request**; rejected ones stay as history, each with its own decision.
- **Approval refuses a double-booking** using the venue search's overlap rule. It does not change the event's status.

## Not covered (separate stories)

Notifying the Coordinator when a decision is made; notifying Venue Staff of a new request (SCRUM-54); cancelling an approved booking.
