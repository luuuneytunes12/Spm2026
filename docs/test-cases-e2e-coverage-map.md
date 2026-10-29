# End-to-end coverage map

The E01–E31 identifiers are planning categories, not a claim of complete
source-code branch coverage. They combine requirements from the Week 4 core
features, Week 7 changes, Jira, and `dod.md`. An E2E browser journey checks
user-visible decisions across components; database concurrency and exhaustive
validation also need the existing integration and unit tests.

| Area | Cases | Evidence or remaining gap |
| --- | --- | --- |
| Access, intake and review | E01–E08 | `access-intake-review-journeys.spec.ts`; detailed mapping in `test-cases-e2e-access-intake-review.md`. Other story specs cover empty clarification, assignment permissions and reassignment. |
| Venue search, suitability and booking | E09–E12 | Existing `venue-catalogue`, `venue-date-filter`, `venue-booking`, `venue-booking-decision`, and `venue-booking-conflicts` specs. The multi-venue journey checks both sufficient and insufficient capacity; not every suitability rule or filter combination is asserted end to end. |
| Week 7 venue changes | E13–E16 | Existing `venue-booking-flags`, `venue-unavailability`, `venue-replacement`, `venue-tentative-hold`, and `venue-hold-expiry` specs; `venue-equipment-journeys.spec.ts` adds a two-venue cancellation journey. |
| Equipment | E17–E19 | `venue-equipment-journeys.spec.ts`: full reservation, zero stock in an overlapping event, unavailable with reason, and increasing the requirement above reserved stock. Other stock boundaries and races remain in backend integration tests. |
| Safety and registration | E20–E24 | `safety-attendee-journey.spec.ts`: submission, safety approval, registration, withdrawal, re-registration and before/after the registration window; `safety-check-and-registration.spec.ts` covers blocked arrangements and registration settings. Not every safety rejection/recovery path is covered in the browser. |
| Registration capacity | E25 | Not established in this E2E suite. The backlog marks waiting-list behaviour as uncertain; confirm the applicable release criteria and current implementation. |
| Event change and cancellation | E26–E29 | `change-cancellation-journeys.spec.ts` tests approve/reject of a proposed change, pending-request guard, and cancellation/resource release. The UI offers organiser changes only before review is decided, so changing an event after bookings are made (E27) remains a gap; the backend's allowed statuses are broader. Event cancellation returns its venue booking as **Released** even though `dod.md` lists **Cancelled** for venue bookings; the team should reconcile the terminology. Concurrent cancellation/resource races belong in PostgreSQL integration tests. |
| Notifications, persistence and accessibility | E30–E31 | New journeys check representative notification and reload outcomes; existing axe and keyboard Playwright specs cover selected pages. This is not a complete notification-recipient or accessibility audit. |

## Running in CI and handling credentials

`.github/workflows/ci.yml` runs on branch pushes and pull requests. Its E2E
job uses GitHub's ephemeral `postgres:16` service, creates the schema, seeds
test-only users and installs Chromium. The job starts the backend and frontend
through the Playwright config and uploads the report even on failure. A local
Docker installation is not required on a developer's computer for GitHub's
hosted runner, but local E2E runs need disposable PostgreSQL.

The passwords and JWT key in these fixtures are intentionally fake, only used
with a disposable local/CI test database. They are not access credentials for
the team's real accounts or shared database, so GitHub Secrets are not needed.
Never reuse a real password in test fixtures. If future tests must access a real
external service, use a separate test account and GitHub Secrets, avoid logging
the values, and consider whether traces or screenshots can contain sensitive
data. GitHub's CI report can contain test input and should be treated as a
project artifact, even when these current values are fake.

`E2E_DATABASE_URL`, `E2E_API_PORT` and `E2E_WEB_PORT` can be set for an isolated
local run; the defaults are a localhost test database and dedicated ports.
The Playwright config must not be pointed at shared development or production
data. The CI job will run only after these changes are committed and pushed;
only the actual GitHub Actions run can establish whether that run is green.

The registration and lifecycle fixtures that require an open registration
window use relative dates. Shared event and venue fixtures use a common future
year from `frontend/e2e/support/dates.ts`; date-sensitive queue, venue search,
replacement, calendar and hold scenarios were checked locally. A complete
223-test run was started but not completed, so a green full suite is not yet
verified. Review CI failures rather than assuming all existing tests pass.
