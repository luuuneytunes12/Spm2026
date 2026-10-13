# Test cases — Submit Venue Booking Request (SCRUM-39)

| AC | Criterion | Backend unit (`tests/test_venue_booking_request.py`) | Postgres (`tests/integration/test_venue_booking_postgres.py`) | Vitest | Playwright (`e2e/venue-booking.spec.ts`) |
|---|---|---|---|---|---|
| AC1 | No venue selected: not submitted, error shown | `scrum39_ac1_no_venue_selected_is_refused_and_nothing_is_saved`, `scrum39_ac1_an_unknown_or_inactive_venue_is_refused` | `scrum39_ac1_to_ac3_…` | `VenueBookingSection.test.tsx` "SCRUM-39 AC1" | "SCRUM-39 AC1" |
| AC2 | Submitted request appears in the Venue Staff queue | `scrum39_ac2_a_submitted_request_appears_in_the_venue_staff_queue`, `…_a_decided_request_leaves_the_queue` | `scrum39_ac1_to_ac3_…`, `…_persists_across_separate_sessions` | "SCRUM-39 AC2" (both test files) | "SCRUM-39 AC2 + AC3" |
| AC3 | Request carries venue, date/time, attendance, layout, accessibility/facility needs | `scrum39_ac3_the_request_carries_…` | `scrum39_ac1_to_ac3_…` | `VenueBookingQueue.test.tsx` "SCRUM-39 AC3" | "SCRUM-39 AC2 + AC3" |

## Negative and edge cases (DoD 3)

| Case | Test |
|---|---|
| Wrong role (venue staff / organiser / anonymous) cannot submit; coordinator cannot read the queue | `test_only_a_coordinator_can_submit`, `test_the_queue_and_detail_are_for_venue_staff_only`; e2e "a Coordinator cannot open the Venue Staff queue" |
| Event assigned to another coordinator | `test_a_coordinator_cannot_book_for_an_event_assigned_to_someone_else`; Postgres `…another_coordinator_cannot_book_or_read_it` |
| Invalid state (event not yet approved) blocked, nothing saved | `test_a_venue_cannot_be_requested_before_the_event_is_approved`; Vitest "is not offered while the request is still awaiting review" |
| Multiple venues per event; duplicate live request to the same venue is refused | `test_an_event_can_request_multiple_venues_but_not_duplicate_a_live_venue`; Postgres `test_scrum39_an_event_can_have_multiple_live_venue_requests` |
| Concurrent duplicate submits (double-click) for the same venue on Postgres | `scrum39_a_submit_fired_many_times_at_once_creates_exactly_one_request`; the event row lock serialises requests |

## Audit, persistence, accessibility

- Actor and time: `requested_by` and `created_at` are asserted in AC3 tests.
- Persistence across reload / sessions: Postgres `…persists_across_separate_sessions`; e2e reloads the page.
- Accessibility: e2e axe check (no serious/critical), labelled select, keyboard reaches Submit.

## Not covered (separate stories)

Venue Staff approve/reject — see [test-cases-venue-booking-decision.md](test-cases-venue-booking-decision.md); notifying Venue Staff (SCRUM-54).
