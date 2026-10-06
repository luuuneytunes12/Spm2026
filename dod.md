# Definition of Done

## 1. Acceptance Criteria & Story Completion

- All ACs satisfied and demonstrated to the Product Owner
- Product Owner has reviewed and accepted the story

## 2. Testing — Automated

- Backend unit tests: pytest passing (in-memory SQLite for speed)
- Backend integration tests: pytest passing against the production database engine (e.g. Postgres via Testcontainers), wherever the story touches persistence, transactions, or conflict handling
- Frontend: Vitest passing (jsdom, API mocked)
- End-to-end: Playwright passing, wherever the story touches DB + UI
- Every AC maps to ≥1 test, named after the AC it proves (traceability)

## 3. Testing — Negative & Edge Cases

- Access-denied path tested (wrong role / wrong org / not-yours data)
- No data or notifications reach users outside the intended role, org, or recipient set (explicit negative test)
- Invalid status transition blocked, state unchanged, error shown
- Field-level input validation tested (bad format blocks save, no partial write)
- Duplicate/repeat action handled correctly (idempotency)
- Resource conflicts tested with concurrent requests, not just sequential ones (double-booking, overcommitted equipment), run against the production database engine

## 4. Audit Trail (if the story changes state)

- Actor identity and timestamp recorded on the action
- Log entry is read-only / immutable

## 5. Data & Persistence

- Data persists correctly across logout/login and reload
- Reason/comment captured where the AC requires one (e.g. rejection reason)
- Schema changes include a migration that applies cleanly to a copy of the current schema and has a working downgrade

## 6. Code Quality & CI

- Code reviewed via PR (no direct pushes to main)
- CI green: lint, type-check, build, and all test layers
- `uv.lock` / `package-lock.json` in sync with dependencies
- Secret scanning passes in CI (e.g. gitleaks); no secrets or `.env` values committed

## 7. Security

- Authorization enforced server-side, not only hidden in the UI
- `pip-audit` and `npm audit` report no new high or critical vulnerabilities

## 8. Accessibility (if the story changes UI)

- Automated axe checks pass in Playwright with no serious or critical violations
- New UI is keyboard-navigable, with visible focus and labelled form fields

## 9. Documentation

- Docs / C4 architecture views updated when the story adds or changes an endpoint, adds a container or service, changes data flow between components, or adds/changes environment variables
- `.env.example` updated when environment variables change

## 10. Deployment

- Deployed to the staging/test environment
- Smoke-tested there
- Integrated into the Increment

## 11. Status Rules (if the story creates or changes a status)

- Only the status names below are used, spelled exactly the same in the UI, database and tests
- Every status change is recorded in the Activity Log with actor identity and timestamp (see Section 4)
- Every allowed status change has a test, and every blocked change has a negative test (see Section 3)

### 11a. Event Statuses (one per Event)

- **Draft** – Event Organiser saved the request but has not submitted it
- **Submitted – Awaiting Coordinator** – request is in the Event Coordinator Lead's unassigned queue
- **Under Review** – an Event Coordinator is assigned and reviewing it
- **Awaiting Organiser Reply** – Event Coordinator asked the Event Organiser for clarification
- **Event Approved** – Event Coordinator approved the request
- **Planning Event** – Venue Bookings and Equipment Requirements are being arranged
- **Awaiting Safety Check** – submitted to the Safety Officer; allowed only when every Venue Booking is Approved and every Equipment Requirement is Reserved
- **Safety Check Passed (Event Confirmed)** – Safety Officer approved the Event; registration can open
- **Event Completed** – the Event has taken place
- **Event Rejected** – Event Coordinator rejected the request
- **Event Cancelled** – the Event was cancelled, with a recorded reason

> **Rule:** the Event status changes only at these milestones. A change to one Venue Booking or Equipment Requirement does not change the Event status by itself.

### 11b. Equipment Requirement Statuses (one per item on an Event)

- **Requested** – Event Coordinator recorded the item; waiting for Technical Support Staff
- **Reserved** – full quantity reserved and linked to this requirement; set only by [Reserve Equipment for Event]
- **Unavailable** – Technical Support Staff cannot provide it; reason required (e.g. damaged, under maintenance, not enough stock)
- **Available** – reservation freed because the Event was cancelled or completed

> **Rule:** "Reserved" cannot be set by hand. If the required quantity rises above the reserved quantity, the status returns to "Requested".

### 11c. Venue Booking Statuses (one per Venue on an Event)

- **Pending** – request submitted, waiting for Venue Staff
- **Approved** – Venue Staff approved the booking
- **Rejected** – Venue Staff rejected it, with a reason and/or alternative
- **Tentative Hold** – Venue held until an expiry date and time; not an approved booking
- **Hold Expired** – hold passed its expiry; the Venue is free for other requests
- **Venue Unavailable** – Venue Staff marked the Venue unavailable after booking; the Event is not cancelled
- **Cancelled** – this one booking was cancelled; other bookings on the same Event are not affected

> **Rule:** each Venue Booking changes status on its own, even within a multi-Venue Event.
