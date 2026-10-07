---
name: implement-user-story
description: Implement a Jira user story end to end in Spm2026 - read the story and acceptance criteria (from the prompt or Jira), write the code and unit tests, check dod.md, and report two tick tables (tasks, DoD items). Use when the user pastes a user story / ACs, gives a SCRUM-nn key or story title, or says "implement", "develop", "build", "do this story", "check DoD". Paths are relative to the repo root.
---

# Implement a user story

Input: a user story and acceptance criteria (ACs) in the prompt, or a Jira key / title to look up. If there is no story and nothing to look up, or it still contains an unfilled placeholder such as `{input}`, ask. Do not guess one.

## Speed rules (read first)

The whole story should take minutes of waiting, not tens of minutes.

- **The full backend suite takes about 15 s** (tests use cheap bcrypt, see Gotchas). Run it freely, but never *discover* breakage file by file.
- **Do the broad checks early, once, together** (step 5), not scattered.
- **Copy the nearest existing file** for every new test or spec (templates below); do not write them from scratch.
- **Batch independent tool calls** in one turn (reads, greps, lint + tsc, the two audits).
- **Run lint and `tsc` right after writing frontend code** and read the whole output (never `| tail -1`).
- **Leave Docker Desktop running** and reuse one Postgres container for the whole story.
- **Only run the story's own e2e specs.** The full e2e suite only if the user asks.

## Steps

1. **Read** the story and ACs. If given a Jira key or title, fetch it (see Jira). List the tasks the prompt asks for (code, tests per AC, DoD check, anything else it names). Each becomes one row in table 1.
2. **Read [dod.md](../../../dod.md)** and decide which sections apply. Items that don't apply are marked ➖ with a reason, not skipped.
3. **Look before writing.** Use the code map below instead of re-exploring; open only the files you will change or copy.
4. **Write the code**, then **tests named after the AC they prove** (`test_ac1_...`), copied from the templates below. Add a negative test for each AC where the DoD asks for one. After writing frontend code, run `cd frontend && npm run lint && npx tsc -b` straight away.
5. **Find breakage once, early.** If the story changes behaviour other code depends on (submit, statuses, assignment, roles, a response shape, a shared helper), then:
   1. `grep -rn` the whole of `backend/tests`, `backend/tests/integration`, `frontend/src` and `frontend/e2e` for that behaviour (e.g. `/submit`, `coordinator_id`, `under_review`), not just the obvious files;
   2. run `cd backend && uv run pytest -q -m "not integration"` and `uv run pytest tests/integration -q -m integration` **once**, read every failure, and fix them all together;
   3. if a shared e2e support file (`frontend/e2e/support/*.ts`) changed, run only the existing specs that import it, once.
   Otherwise run just the story's own tests while iterating.
6. **Complete the DoD.** Go through [dod.md](../../../dod.md) section by section and *do* every applicable item that is in your power, not just report on it:
   - missing test layers (backend unit, Vitest, Playwright, negative and edge cases)
   - accessibility: axe check and keyboard/focus check for any new UI; copy `TC-CA-A1` / `TC-CA-A2` from `frontend/e2e/coordinator-assignments.spec.ts` and change the page and selectors
   - migration, plus the `backend/db/schema.sql` update when the DB changes
   - `pip-audit` and `npm audit` (run both in one turn)
   - update C4/architecture views and `.env.example` only when the DoD says they are due
   - **optional:** `docs/test-cases-<story>.md`. The DoD does not require it, so only write it if the user asks
7. **Final pass, in one turn:** `cd frontend && npm run lint && npx tsc -b && npm run build && npm test`, the full backend suite and the integration tests, `pip-audit` and `npm audit`. Report real results; if something fails or was not run, say so.
8. **Remove the e2e Postgres container** if you started it, then report with the two tables below. Be concise.

Only items needing other people (PR review, CI, PO acceptance, staging) are left as ⏳. Anything you could not complete is ❌ with the reason.

## Jira

Site `scis-team-lunn.atlassian.net`, project `SCRUM` ("ConnectSphere SPM"), cloud id `98862a34-b623-4e27-8916-881a6fb58368`. Load the tool once with `ToolSearch` query `select:mcp__claude_ai_Atlassian_Rovo__searchJiraIssuesUsingJql`, then:

```
searchJiraIssuesUsingJql  cloudId=98862a34-b623-4e27-8916-881a6fb58368
  jql='project = SCRUM AND summary ~ "<words from the title>"'   (or key = SCRUM-82)
  fields=["summary","description","status","parent"]  responseContentFormat=markdown
```

Do not use `mcp__jira__search_jira_issues` (it errors) and skip `getAccessibleAtlassianResources` and `list_jira_projects`: the ids above are already known.

## OOP / inheritance rule

New code should use classes and inheritance where it fits (e.g. a new role as a subclass that extends a parent's permissions; the Lead's views are `EventListing` -> `UnassignedRequests` / `CoordinatorAssignments` -> `UnassignedQueue` / `ActiveAssignments`). Do **not** refactor code outside the story. Existing tables and classes are only read from, never rewritten. Prove nothing broke with a "frozen literal" test for each existing behaviour the story could affect.

## Code map

| Area | Where |
|---|---|
| Roles, permissions, role profiles (classes) | `backend/app/core/roles.py` (mirror: `frontend/src/lib/roles.ts`) |
| Role guards | `backend/app/core/deps.py` (`require_role`, `require_permission`) |
| Event model, statuses | `backend/app/models/events.py`, `backend/app/models/enums.py` |
| Coordinator assignment service | `backend/app/services/assignment.py` (`assign_coordinator`, `ACTIVE_ASSIGNMENT_STATUSES`) |
| Lead's views (query classes) | `backend/app/services/assignment_overview.py` |
| Lead's endpoints (`/lead/...`) | `backend/app/routers/coordinator_lead.py` |
| Event schemas (`LeadEventOut`, `LeadEventDetail`, ...) | `backend/app/schemas/event.py` |
| Submit endpoint and its `_after_submit` hook | `backend/app/routers/events.py` |
| API client, Lead helpers | `frontend/src/lib/api.ts`, `frontend/src/lib/coordinatorLead.ts` |
| Landing pages (shared) and tiles per role | `frontend/src/components/RoleLanding.tsx`, `frontend/src/lib/roleLanding.ts` |
| Lead pages and shared list / review components | `frontend/src/pages/lead/` (`LeadEventList.tsx`, `LeadRequestReview.tsx`, `LeadPages.tsx`) |
| Routes and role guards | `frontend/src/App.tsx` |
| e2e support (seed users, `autoAssign`, `openAs`) | `frontend/e2e/support/` |

## Templates to copy for new tests

| New test | Copy this |
|---|---|
| Backend API tests for a Lead endpoint | `backend/tests/test_coordinator_assignments_overview.py` or `test_unassigned_queue.py` |
| Postgres integration test | `backend/tests/integration/test_coordinator_assignments_postgres.py` |
| Vitest page tests | `frontend/src/pages/lead/LeadPages.test.tsx`, `AssignedEventReview.test.tsx` |
| Vitest landing / tiles | `frontend/src/components/CoordinatorLeadLanding.test.tsx` |
| e2e spec with axe and keyboard | `frontend/e2e/coordinator-assignments.spec.ts` |

## Commands (verified in this repo)

| Purpose | Command |
|---|---|
| Backend tests (story's files) | `cd backend && uv run pytest tests/test_<story>.py -q` |
| Backend tests (everything except integration, about 15 s) | `cd backend && uv run pytest -q -m "not integration"` |
| Backend integration tests (about 5 s, needs Docker) | `cd backend && uv run pytest tests/integration -q -m integration` |
| Frontend unit tests (about 8 s) | `cd frontend && npm test` |
| Lint / typecheck / build | `cd frontend && npm run lint && npx tsc -b && npm run build` |
| Dependency audits | `cd backend && uvx pip-audit` and `cd frontend && npm audit --audit-level=high` |
| Start backend | `cd backend && nohup uv run uvicorn app.main:app --reload --port 8010 --timeout-graceful-shutdown 2 &` (frontend `.env` points at **8010**, not 8000) |
| Start frontend | `cd frontend && npm run dev` (port 5173) |

Run servers detached (`nohup ... &`). Foreground background-tasks are killed at the tool time limit. macOS has no `timeout` command.

### End-to-end (Playwright + axe)

Needs a throwaway Postgres built from `backend/db/schema.sql` only, which is how CI does it. **Start the container once, keep it for the whole story, and remove it only when the story is finished.** Reuse an existing one (`docker ps | grep cs-e2e-pg`); after a schema change, reload the schema into the same container.

```bash
# once per story (Docker Desktop: leave it running; start with `open -a Docker` only if `docker info` fails)
docker ps --format '{{.Names}}' | grep -q cs-e2e-pg || {
  docker rm -f cs-e2e-pg >/dev/null 2>&1
  docker run -d --name cs-e2e-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=connectsphere_test -p 5432:5432 postgres:16
  for i in $(seq 1 30); do docker exec cs-e2e-pg pg_isready -U postgres -d connectsphere_test >/dev/null 2>&1 && break; sleep 2; done; sleep 3
  docker exec -i cs-e2e-pg psql -U postgres -d connectsphere_test -v ON_ERROR_STOP=1 < backend/db/schema.sql
}

# as often as needed: ONLY this story's specs, never the whole e2e suite
cd frontend && npx playwright test e2e/<story>.spec.ts

# when the story is finished
docker rm -f cs-e2e-pg
```

If an older spec fails, run just that spec once to check it is not yours (`git stash push -u`, run, `git stash pop`) rather than running everything. Two older specs, `venue-booking.spec.ts` and `venue-booking-decision.spec.ts`, already fail on the committed code.

Specs go in `frontend/e2e/`; reuse `e2e/support/db.ts` (`seedUsers`, `resetUsers`, `removeUsers`, `autoAssign`) and `e2e/support/coordinator-users.ts` (`openAs`). `submitEvent(request, headers, name, { assign: false })` leaves a request in the Lead's queue; the default hands it to a Coordinator. Scope link selectors to the page body (e.g. `.tile-grid`): the navbar has links with the same names and strict mode fails on two matches.

## Gotchas

- **Tests use cheap bcrypt.** `backend/tests/conftest.py` swaps the password-hashing context for 4 rounds (production hashing is untouched). That took the suite from about 7 min to about 15 s. Do not remove it. A new test that needs real bcrypt cost must say so.
- **Submit does not auto-assign.** A submitted request waits, unassigned, in the Lead's queue. Older coordinator-workflow tests opt back in with the `coordinator_auto_assign` fixture (`pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")`); tests of the queue must not use it. The e2e equivalent is `autoAssign`.
- **Roles live in three places.** `backend/app/core/roles.py`, `frontend/src/lib/roles.ts`, and the native Postgres enum `user_role`. A new role needs a migration in `backend/sql/` **and** a label added to `backend/db/schema.sql`, or CI's e2e database lacks it. The DB label can differ from the code slug; read it with `enum_range(null::user_role)` first.
- **`MeOut.permissions` is `list[Permission]`.** A permission not in the `Permission` enum makes `/auth/me` fail validation. `ORGANISER` gets every `Permission` member, so adding one widens Organiser. State this in the report.
- **JWT carries the role.** A DB role change does not affect an issued token until re-login.
- **`Record<Role, …>` in the frontend** forces an entry in `ROLE_LABELS`, `ROLE_PERMISSIONS`, `ROLE_HOME_PATH` and `roleLanding.ts`; `npx tsc -b` finds any you missed.
- **Registration always creates an Attendee.** Tests that need another role register, then update the row's `role`, then log in.
- **macOS `sed -i` needs an argument** and failed silently once; edit files with the Edit tool or Python instead, and re-check with grep.
- **Safety Officer** is in the DB enum but not yet a `Role` in code; "Awaiting Safety Check" is not yet an event status.
- **`dod.md` item "Backend integration tests (Postgres)"** is only required when the story touches persistence, transactions, conflicts, or database-specific queries (ordering, `GROUP BY`).
- **Dev backend can hang after a reload.** `uvicorn --reload` waits for open connections, and the browser's live `/notifications/stream` never closes, so after editing backend files the old process can get stuck ("Waiting for connections to close") while still holding the port: logins then hang. Start it with `--timeout-graceful-shutdown 2`. If it is already stuck, `pkill -9 -f "uvicorn app.main:app"` (plain `pkill` is ignored), then kill leftover `multiprocessing.spawn` Python processes on the port (`lsof -nP -iTCP:8010`) and start it again.
- Never run `npm audit fix` or change lockfiles without asking.

## Report format

Table 1: one row per task inferred from the prompt.

| Task | Done |
|---|---|
| ... | ✅ / ❌ |

Table 2: one row per DoD item (use ⏳ for steps only the team can do: PR review, CI, PO acceptance, staging; ➖ for not applicable, with a reason).

| DoD item | Status |
|---|---|
| ... | ✅ / ❌ / ⏳ / ➖ |

Then 3-5 short notes: anything not done, any widened permission, any pre-existing issue found. Finish with whether the story is ready for Done, and list what is still blocking it. Do not commit unless asked.
