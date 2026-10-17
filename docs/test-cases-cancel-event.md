# Cancel Event test cases

As an Event Coordinator, I can cancel an active Event assigned to me by giving
a reason. The status history records the reason, actor and time.

| ID | Scenario | Expected result |
|---|---|---|
| CE-01 | Assigned Coordinator cancels an active Event with a non-blank reason | Event becomes `event_cancelled`; reason is in Activity Log with Coordinator name and timestamp |
| CE-02 | Cancellation reason is missing, empty or whitespace-only | Request is refused with a validation error; Event and its arrangements are unchanged |
| CE-03 | Event is completed, rejected or already cancelled | Request is refused with a status-specific conflict; Event is unchanged |
| CE-04 | Different Coordinator attempts cancellation | Request is refused with `403`; Event is unchanged |
| CE-05 | Event has no assigned Coordinator | Request is refused with a clear conflict; Event is unchanged |
| CE-06 | Event has reserved equipment and live venue bookings | Reserved equipment and live bookings are released; non-reserved equipment requests are unchanged |
| CE-07 | A different approved Event requests the equipment after cancellation | The released quantity is available and can be reserved normally |
| CE-08 | Event cancellation races a Technical Support reservation | Cancellation wins or the reservation completes first and is then released; no cancelled Event retains a reserved line |
| CE-09 | Event cancellation races Venue Staff approval | The booking ends cancelled regardless of which request acquires its lock first |
| ER-01 | Event becomes completed before its scheduled end | Reserved stock is available in the catalogue and can be reserved for another Event |

Backend coverage: `backend/tests/test_cancel_event.py`.
Equipment completion coverage: `backend/tests/test_equipment_auto_release.py`.
PostgreSQL integration coverage: `backend/tests/integration/test_event_cancellation_postgres.py`.
Coordinator screen coverage: `frontend/src/pages/events/AssignedEventView.test.tsx`.
