# Test Cases — Check Venue Suitability for an Event

## User story

As an Event Coordinator, I want to check whether a venue meets my event's
specific requirements, so that I only submit booking requests for venues that
can actually accommodate the event.

## Acceptance criteria

| AC | Given / When / Then |
|---|---|
| AC1 | Given I select one of my assigned events and a venue, when I run a suitability check, then capacity, layout, accessibility features, and required facilities are compared against that event's recorded requirements. |
| AC2 | Given every recorded requirement is met, when the check completes, then the venue is marked suitable. |
| AC3 | Given any requirement is not met, when the check completes, then the venue is marked not suitable and each failed requirement is identified with the venue's available value. |

## Requirement matching and workflow management

- Expected attendance must be recorded; otherwise capacity cannot be confirmed
  and the result is not suitable.
- Layout and requirement-item matching ignores case and surrounding spaces.
- The existing `accessibility_needs` and `venue_requirements` fields are free
  text. For this check, multiple accessibility features and required facilities
  must be separated with commas, semicolons, or newlines. Each item is compared
  against the venue's recorded values.
- The UI shows each check's category, required value, available value, and
  diagnostic message. A failed check is a recoverable result, not a process
  failure; the Coordinator can choose a different event or retry after
  correcting the event or venue data.
- The endpoint only returns a result for an event assigned to the requesting
  Coordinator. Other roles cannot run the check.

## Test cases

| AC | Test case | Automated by |
|---|---|---|
| AC1–AC2 | Capacity, layout, accessibility, and facilities all match; the result is suitable | `backend/tests/test_venue_suitability.py::test_suitability_marks_a_venue_suitable_when_every_requirement_is_met` |
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
