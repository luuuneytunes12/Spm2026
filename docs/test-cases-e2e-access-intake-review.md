# E2E journeys: access, intake and event review

These cases exercise real browsers, the application server and a disposable
PostgreSQL database. They test hand-offs and visible decisions, while the
existing story-specific Playwright and integration tests cover additional
boundaries. Test discovery does not establish that a case has passed: retain
the Playwright report from an actual run as evidence.

## How to explain the tests

- **Fixture:** `seedUsers` creates fake, known accounts in the isolated test
  database. `beforeEach` resets the events belonging to those accounts, and
  `afterAll` removes the accounts. This gives each scenario a repeatable start.
- **Roles and hand-offs:** `openAs` gives each person a separate browser
  context. For example, an organiser cannot accidentally share the lead's
  login, so the test can observe the real hand-off between them.
- **Actions and assertions:** `getByRole` and `getByLabel` locate controls as a
  user would; `click`, `fill` and `selectOption` perform actions; `expect`
  checks visible outcomes. Reloads and a fresh login check persistence.
- **Decision coverage:** the cases compare important outcomes such as complete
  versus incomplete submission and approval versus rejection. They do not
  measure every internal source-code branch or prove every input combination.
- **Scope:** some other specs use an API or database fixture to prepare an
  event before testing a later screen. The access/intake/review journey makes
  its event, assignment and decisions through the browser. Test accounts are
  fixtures; their passwords are deliberately fake and used only in test data.

| Planned area | Journey and expected outcome | Playwright coverage |
| --- | --- | --- |
| E01 Authentication | An unauthenticated user is redirected to login; incorrect credentials are rejected. | `access-intake-review-journeys.spec.ts`, E01–E02 |
| E02 Access | Another organiser cannot find or open the event and cannot open the lead's queue. | New E01–E02 journey; `lead-assign-event.spec.ts` also checks coordinator and direct-request boundaries. |
| E03 Draft | An incomplete draft persists across logout/login and is absent from the lead's queue. | New E03–E08 journey; `draft-and-submit.spec.ts` and `unassigned-queue.spec.ts`. |
| E04 Submit | Incomplete submission is blocked; complete submission moves the event from drafts to the queue. | New E03–E08 journey; `draft-and-submit.spec.ts`. |
| E05 Assignment | Lead assigns the queued request; the assigned coordinator sees it. | New E03–E08 journey; `lead-assign-event.spec.ts` covers invalid and unauthorised assignment. |
| E06 Reassignment | Lead moves ownership; the old coordinator no longer lists it, while the new coordinator and organiser see the change. | New E06 journey; `lead-reassign-event.spec.ts` covers history and access decisions. |
| E07 Clarification | Coordinator asks; organiser sees and replies; the request returns to review. | New E03–E08 journey; `clarification.spec.ts` covers empty messages and amendments. |
| E08 Review decision | Coordinator approves after clarification, or rejects with a reason; organiser sees the result. An empty rejection is blocked. | New E03–E08 and E08 journeys; backend review tests cover invalid direct status transitions. |

The Week 7 update makes the lead's queue and manual assignment part of the
workflow. The Definition of Done names the review state **Under Review**;
older wording in SCRUM-25 says **Submitted**, so this suite follows the later
assignment workflow. Jira SCRUM-27 and SCRUM-103 were in progress when these
cases were written; failures may indicate unfinished behaviour.
SCRUM-21 also lists equipment requirements among mandatory submission fields,
while `test-cases-organiser-event-equipment.md` describes equipment as
optional. Confirm the intended rule with the product owner before claiming
complete coverage of that acceptance criterion.

This is not an exhaustive security or boundary audit. The new journey checks
incorrect credentials, a protected route, one wrong-role route, and another
organiser's event. It does not by itself verify inactivity expiry, every role
against every protected action, all field boundaries, or every invalid status
transition. Some additional paths are in the existing story and backend tests;
their presence and execution should be reported separately.

Run the new file after preparing the disposable local database described in
`frontend/playwright.config.ts` and the repository's CI workflow:

```powershell
cd frontend
node node_modules/@playwright/test/cli.js test e2e/access-intake-review-journeys.spec.ts
```

Users are test-only accounts seeded by the existing E2E support module. Event
creation, assignment, clarification and review are performed in the browser.
Each test resets its own users and events. Never point this suite at a shared
database. The E2E job is enabled in `.github/workflows/ci.yml`; the first
GitHub Actions run after the changes are pushed will show its actual result.
