# E2E review and presentation guide

Use **Ctrl+Shift+F** in the repository to search for the uppercase keywords or
the E01–E31 case IDs below. The four new journey specs also have `E2E SEARCH`
keywords at the top and explanations above their helpers and test scenarios.
For the intended cases and known gaps, see `test-cases-e2e-coverage-map.md`
and `test-cases-e2e-access-intake-review.md`.

## ENVIRONMENT SIMULATION and DATABASE ISOLATION

- **Real components:** Chromium drives the project's actual frontend, backend,
  authentication and PostgreSQL database engine. The README identifies the team's
  database as Supabase Postgres; the test database is a separate PostgreSQL
  container, not the shared Supabase project. CI installs the project
  dependencies, creates the schema from `backend/db/schema.sql`, starts a
  `postgres:16` service and seeds fake test users. The browser and app servers
  run on GitHub's runner; the database runs in a service container.
- **Separate data:** The CI database is created for that job and discarded
  afterward. Local runs must use a separately prepared disposable database.
  The URL guard checks the actual hostname and database name, and the config
  starts its own servers rather than reusing a developer's running server.
  This guard cannot identify a remote database forwarded through localhost:
  the person running the tests must ensure the database is disposable.
- **Production parity:** This is production-like application integration, not
  an identical production environment. Hosting, operating system, build and
  deployment, configuration, infrastructure, PostgreSQL version/schema
  history and external services may differ. The frontend uses the Vite dev
  server; this does not validate a built deployment artifact. A separately
  controlled staging smoke test would be needed to check deployment-specific
  behaviour. Verify actual production configuration before claiming parity.
- **Credentials:** Fake passwords and a test-only signing key are checked in
  for this isolated environment. Never reuse actual credentials or production
  personal data. Reports, screenshots and traces can contain test inputs or
  session information; restrict access to CI artifacts. Future real external
  test credentials should come from appropriate secrets, not source code.

## REQUIREMENTS and DECISION COVERAGE

The Week 9 lecture, pages 26–29, recommends exercising critical user journeys
through a real browser and checking outcomes against requirements. The new
journeys use role and label locators and assert what the relevant users see.
Some later-stage scenarios prepare prerequisites using the API or direct
database fixtures; those setup actions do not prove their corresponding UI
paths. The access/intake journey does exercise its central hand-offs in the UI.

Decision coverage here means selected observable alternatives, for example
valid versus incomplete submission or approval versus rejection. It is not a
measurement of source-code branch coverage, every boundary or all role-action
combinations. A green test establishes only its asserted behaviour for its
test data; evaluate the assertions against the requirements, not just the
current implementation (lecture pages 6 and 18–20).

## Search index for presentation

| Search terms | Where to look and what to explain |
| --- | --- |
| E01 AUTHENTICATION, E02 OWNERSHIP | `access-intake-review-journeys.spec.ts`: unauthenticated redirect, wrong password, another organiser and wrong role. |
| E03 DRAFT, E04 VALIDATION, E05 ASSIGNMENT, E07 CLARIFICATION | Same file: incomplete draft, complete submission and cross-role hand-offs. |
| E06 REASSIGNMENT, E08 APPROVAL, E08 REJECTION | Same file: changed coordinator and the two review decisions. |
| E10 CAPACITY, E15 MULTIPLE VENUES | `venue-equipment-journeys.spec.ts`: sufficient/insufficient capacity and independent booking decisions. |
| E17 EQUIPMENT, E18 STOCK, E19 OVERLAP | Same file: reservation, competing event and unavailable outcome. |
| E20 SAFETY APPROVAL, E21 REGISTRATION, E22 WITHDRAWAL, E23 RE-REGISTRATION, E24 TIME WINDOW | `safety-attendee-journey.spec.ts`: safety gate and attendee journeys. Exact boundary instants and all safety outcomes are not claimed. |
| E25 REGISTRATION CAPACITY | Coverage map: not established; product requirements need confirmation. |
| E26 CHANGE REQUEST, E27 AFTER BOOKING | `change-cancellation-journeys.spec.ts` and coverage map: approve/reject covered; changes after bookings are a known UI gap. |
| E29 CANCELLATION, RESOURCE RELEASE | Same file: cancellation reason and venue/equipment release; some resource assertions use the real API. |
| E30 NOTIFICATIONS, E31 PERSISTENCE, ACCESSIBILITY | Coverage map and existing story specs: representative checks, not a complete audit. |
| TEST ISOLATION, BROWSER CONTEXT ISOLATION | Hooks in the four new journey files and `support/db.ts`; browser sessions and database state are separate concerns. |
| API SETUP, FIXTURE, AUTO ASSIGN | Helpers in the journey files and `support/api.ts`/`support/db.ts`; distinguish setup from the decision being tested. |
| CI, PLAYWRIGHT REPORT, TRACE | `.github/workflows/ci.yml` and `frontend/playwright.config.ts`. |

## TEST ISOLATION and FLAKINESS

Lecture pages 24 and 31–34 emphasise known data, independence and avoiding
fixed sleeps. In these journeys, `beforeEach` clears the relevant events and
notifications, and the safety journey removes its previously registered
attendee before registering again. Role sessions use separate browser
contexts, which are closed after each journey. Cleanup is scoped to test
fixture identities; it is not a fresh database per individual test. The
configured single worker reduces conflicts in the shared test database, but
does not prove every older spec is independent. Running one test, repeating it
and running it after other tests provide different evidence.

Playwright's web-first assertions wait for observable conditions. The suite
has one CI retry: a pass on retry is reported as flaky and must be investigated,
not treated as evidence of a reliable first pass. Failed traces and screenshots
help diagnosis. Future dates reduce calendar-dependent failures but do not
prove every midnight, timezone or exact opening/closing boundary.

## CI, SMOKE TESTS and RELEASE GATES

The workflow currently runs the complete Playwright suite on pushes and pull
requests, along with separate backend and frontend jobs. Week 9 page 34
suggests a small critical smoke suite as the fast pull-request gate and the
full E2E suite after merge or on a schedule. This repository has not yet split
those runs: measure the full suite and agree on a critical subset before
changing the gate. Chromium is the only configured browser, so Firefox and
WebKit compatibility are not established.

An Actions job does not by itself prevent merging: repository branch protection
or rulesets must require the relevant checks. This checkout cannot establish
whether those remote settings are enabled. The project's lecture says CI is
required; deployment/CD is not expected for the project (page 43). This
CI workflow does not deploy. The separate `.github/workflows/deploy.yml`
contains Supabase database migration steps for staging and production; this
review did not verify their remote environment rules, approvals or execution.
It does not establish frontend/backend deployment or staging smoke tests.

## Evidence and limitations

Use an actual Playwright/Actions report to say what passed and when; discovering
tests is not a successful run. On 29 October 2026, all 11 new journeys passed together locally against a
disposable PostgreSQL container. The full 223-test suite has not yet been
verified green.
See the coverage map for unresolved requirements and missing paths; in
particular E25, E27, some safety rejection/recovery paths, role combinations,
exact time boundaries and complete notification/accessibility coverage.

Additional references: [Playwright best practices](https://playwright.dev/docs/best-practices),
[Playwright locators](https://playwright.dev/docs/locators), and
[Playwright CI and artifact security](https://playwright.dev/docs/ci-intro).
