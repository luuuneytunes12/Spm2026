# Test Cases — View Venue Availability Calendar

## User story

As an Event Coordinator, I want to view a calendar of a venue's existing
bookings, so that I can identify available windows before submitting a booking
request.

## Acceptance criteria

| AC | Given / When / Then |
|---|---|
| AC1 | Given I open a selected venue's availability calendar, when the calendar loads, then confirmed bookings and recorded unavailability are laid out by date and time. |
| AC2 | Given a booking is confirmed, when its time overlaps the selected range, then it appears on the calendar. Pending, rejected, and cancelled requests do not appear as confirmed bookings. |
| AC3 | Given a recorded unavailability overlaps the selected range, when the calendar loads, then the period and its recorded reason appear. |
| AC4 | Given I change the start or end date/time, when I check availability, then only bookings and unavailability overlapping that range are shown. |

## Workflow and diagnostic behavior

- The date-range form remains available while data loads.
- Missing dates and a range whose end is not after its start are reported inline;
  invalid input is not sent to the API.
- A request error is shown in the page with a Retry action. It does not end the
  application or discard the selected range.
- An empty result is shown as an explicit "No confirmed bookings or closures"
  state, not as a loading failure.

## Test cases

| AC | Test case | Automated by |
|---|---|---|
| AC1–AC3 | A confirmed booking and a recorded closure both appear with date/time; the closure reason is visible | `backend/tests/test_venue_availability_calendar.py::test_calendar_shows_confirmed_bookings_and_recorded_unavailability`; `VenueAvailability.test.tsx` |
| AC2 | Pending booking and an out-of-range closure are omitted | `backend/tests/test_venue_availability_calendar.py::test_calendar_excludes_unconfirmed_bookings_and_records_outside_the_range` |
| AC3 | Closures for another venue do not leak into this venue's calendar | covered by the venue-scoped query in calendar endpoint tests |
| AC4 | The selected range is passed to the API; an invalid range is rejected before the request | `VenueAvailability.test.tsx`; `test_calendar_rejects_a_date_range_that_ends_before_it_starts` |
| Workflow | A failed calendar request retains the page and selected range; Retry can load an empty result | `VenueAvailability.test.tsx` |
| Access | Coordinator and Venue Staff can view the calendar; external roles cannot | `test_calendar_is_limited_to_internal_roles` |

## How to run

| Layer | Command |
|---|---|
| Backend unit cases | `cd backend && uv run pytest -q tests/test_venue_availability_calendar.py` |
| Frontend component cases | `cd frontend && npx vitest run src/pages/venues/VenueAvailability.test.tsx` |

Calendar entries use the venue's confirmed (`approved`) bookings and recorded
unavailability periods. Each entry is included when it overlaps the selected
half-open interval `[start, end)`, so periods ending exactly at the range start
are excluded.
