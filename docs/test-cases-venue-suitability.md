# Test Cases — Check Venue Suitability for an Event

## User story

As an Event Coordinator, I want to check whether a venue meets my event's
specific requirements, so that I only submit booking requests for venues that
can actually accommodate the event.

## Acceptance criteria

| AC | Given / When / Then |
|---|---|
| AC1 | Given I select one of my assigned events, when I run a suitability check, then every attached venue is independently checked for capacity, layout, accessibility features, and required facilities. |
| AC2 | Each venue is marked suitable only when all of its recorded requirements are met. |
| AC3 | Each failing venue identifies all unmet requirements. Combined venue capacity is separately compared with expected attendance and must exceed it. |

## Requirement matching and workflow management

- Expected attendance must be recorded; otherwise capacity cannot be confirmed
  and the result is not suitable.
- Layout and requirement-item matching ignores case and surrounding spaces.
- The existing `accessibility_needs` and `venue_requirements` fields are free
  text. For this check, multiple accessibility features and required facilities
  must be separated with commas, semicolons, or newlines. Each item is compared
  against the venue's recorded values.
- The UI shows each check's category, required value, available value, and
  diagnostic message and a suggested resolution. On a venue detail page the
  check compares the selected venue with the selected event; a booking does
  not need to exist first. A failed check is a recoverable result, not a process
  failure; the Coordinator can choose a different event or retry after
  correcting the event or venue data.
- On an assigned event's planning view, every active venue booking is checked
  independently, and the combined-capacity result is shown separately. This
  does not replace the direct selected-venue check on a venue detail page.
- The endpoint only returns a result for an event assigned to the requesting
  Coordinator. Other roles cannot run the check.
- One venue's failed checks do not alter other bookings. Combined capacity
  counts each distinct attached venue once.

## Test cases

| AC | Test case | Automated by |
|---|---|---|
| AC1–AC2 | Capacity, layout, accessibility, and facilities all match; the result is suitable | `backend/tests/test_venue_suitability.py::test_suitability_marks_a_venue_suitable_when_every_requirement_is_met` |
| AC1 | A venue with 250-person capacity is checked directly for an event without an existing venue booking | individual venue suitability endpoint; `VenueSuitability.test.tsx` |
| AC1–AC3 | Two attached venues are checked independently; one can fail while combined capacity passes | `backend/tests/test_venue_suitability.py::test_event_suitability_checks_each_venue_and_combines_capacity`; `VenueSuitability.test.tsx` |
| AC1–AC3 | The assigned-event view shows each attached venue's result and the separate combined-capacity result | `frontend/src/components/EventVenueSuitability.test.tsx` |
| AC1, AC3 | Several mismatches are all reported, including insufficient capacity, unsupported layout, missing accessibility, and missing facility | `backend/tests/test_venue_suitability.py::test_suitability_reports_each_unmet_requirement` |
| AC3 | Missing expected attendance does not produce a false suitable result | `backend/tests/test_venue_suitability.py::test_suitability_does_not_claim_success_when_attendance_is_missing` |
| Workflow | A Coordinator can select an assigned event; mismatch details remain visible for follow-up | `frontend/src/pages/venues/VenueSuitability.test.tsx` |
| Workflow | Failed event-list and suitability requests retain the page workflow and can be retried | `frontend/src/pages/venues/VenueSuitability.test.tsx` |
| Access | An event assigned to another Coordinator is indistinguishable from an unknown event; Venue Staff are denied | `test_suitability_only_exposes_events_assigned_to_the_coordinator`; `test_suitability_rejects_non_coordinator_roles` |

## How to run

| Layer | Command |
|---|---|
| Backend unit cases | `cd backend && uv run pytest -q tests/test_venue_suitability.py` |
| Frontend component cases | `cd frontend && npx vitest run src/pages/venues/VenueSuitability.test.tsx` |
