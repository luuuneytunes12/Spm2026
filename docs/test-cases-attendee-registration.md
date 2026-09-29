# Test Cases — Attendee Registration

Covers two product backlog items:

- **Register for an event.** *As an Attendee, I want to register for a
  confirmed event that has registration enabled, so that I can secure my
  place.*
- **Withdraw my registration.** *As an Attendee, I want to withdraw my
  registration, so that I release my place if I can no longer attend.*

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_registrations.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |

There is no Playwright layer for these stories yet. Nothing in the app moves
an event to `confirmed` yet, so the backend tests set that status directly.

## When is registration open?

Open means **all three**: the event's status is `confirmed`, its
`registration_enabled` flag is on, and its `proposed_start` has not passed.
`events` has no separate closing date, so the start time is what closes
registration. The rule lives in one place, `registration_open()` in
`backend/app/routers/registrations.py`.

## Register

| AC | Test case | Automated by |
|---|---|---|
| Confirmed + enabled → registering records it and shows "Registered" | Register for an open event | `test_register_for_open_event_records_registered`, `test_open_event_is_listed_as_open_and_unregistered`; component: *offers Register on an open event…* |
| Registration closed → no register option | Event has started; registration later disabled; unconfirmed/disabled events never offered | `test_event_that_has_started_is_closed`, `test_closed_event_stays_visible_to_someone_registered`, `test_unconfirmed_or_disabled_events_are_not_offered`; component: *offers no way to register once registration has closed* |
| Already registered → not offered a second registration | Register twice | `test_already_registered_cannot_register_again`; component: *does not offer Register to someone already registered* |
| (guard) Only Attendees register | Coordinator tries to register | `test_only_attendees_can_register` |

## Withdraw

| AC | Test case | Automated by |
|---|---|---|
| Registered → withdrawing sets status "Withdrawn" | Withdraw | `test_withdraw_changes_status_to_withdrawn`; component: *changes the status to Withdrawn* |
| Withdrawn + still open → can register again | Re-register after withdrawing | `test_withdrawn_attendee_can_register_again_while_open`; component: *offers Register again after withdrawing while still open* |
| (guard) Re-registering after close is refused | Withdraw, close, re-register | `test_withdrawn_attendee_cannot_register_again_once_closed` |
| (guard) Nothing to withdraw | Withdraw without registering | `test_cannot_withdraw_without_a_registration` |
