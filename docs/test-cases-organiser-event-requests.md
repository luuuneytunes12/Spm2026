# Test Cases — Organiser Event Requests

Covers two product backlog items:

- **Story 1 — Draft an Event Request.** *As an Event Organiser, I want to save
  an incomplete event request as a draft, so that I can capture my
  requirements over time and edit them before submitting.*
- **Story 2 — Submit an Event Request.** *As an Event Organiser, I want to
  submit a completed event request, so that ConnectSphere can begin reviewing
  and planning my event.*

Every acceptance criterion below maps to at least one test case, and every
automated test is named after the criterion it proves, so a criterion can be
traced to the code that verifies it.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| End-to-end (Playwright) | `cd frontend && npm run test:e2e` | a local throwaway postgres |
| All of the above | push to any branch | GitHub Actions runs them |

Playwright needs a disposable database on `localhost:5432`. It will **refuse
to start** against anything else — see the guard rail in
`frontend/playwright.config.ts`, which exists so test data can never be
written into the shared Supabase project.

```bash
docker run --rm -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=connectsphere_test -p 5432:5432 postgres:16
# then, in another terminal:
psql postgresql://postgres:postgres@localhost:5432/connectsphere_test \
  -f backend/db/schema.sql
cd backend && DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/connectsphere_test \
  ADMIN_PASSWORD=e2e-password-123 \
  uv run python scripts/create_admin.py "E2E Organiser" e2e_organiser@cs.local
```

A teammate without Docker can run pytest and Vitest locally and let CI cover
the end-to-end layer.

## Why three layers

| Layer | Tool | What it proves | Browser | Server | Database |
|---|---|---|---|---|---|
| Backend | pytest | API rules, permissions, status transitions | No | No | No |
| Components | Vitest | the screens render and wire up correctly | No | No | No |
| End-to-end | Playwright | the whole journey genuinely works together | Yes | Yes | Yes |

Tests assert what a **user experiences** — visible text, labels,
`aria-invalid` — never CSS class names, so restyling the app cannot turn a
passing test red.

---

## Story 1 — Draft an Event Request

### AC1 — the form captures the required information

> *Given an Event Organiser is creating an event request, when they open the
> form, then it captures purpose and type, preferred date and time, expected
> attendees, general programme, room layout preferences, accessibility
> requirements, equipment requirements, registration requirements, and any
> other special arrangements.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S1-1a | An input exists for every field named in the criterion | Vitest | `EventForm.test.tsx` › *renders an input for every field named in the acceptance criterion* |
| TC-S1-1b | What the organiser types is what reaches the API | Vitest | `EventForm.test.tsx` › *sends what the organiser typed to the API* |
| TC-S1-1c | Fields are readable, sensibly grouped, and legible in dark mode | **Manual** | script below |

### AC2 — an incomplete request persists and can be resumed

> *Given an incomplete event request, when the Event Organiser saves it as a
> draft, then the draft is persisted and can be reopened later with all
> previous input intact.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S1-2a | A request with almost every field empty still saves | pytest | `test_draft_saves_with_almost_everything_empty` |
| TC-S1-2b | Reopening returns every value previously entered | pytest | `test_draft_reopens_with_all_previous_input_intact` |
| TC-S1-2c | Requirements can be added across several separate saves | pytest | `test_draft_can_be_edited_and_completed_over_time` |
| TC-S1-2d | An edit that omits a field does not erase it | pytest | `test_patch_omitting_a_field_does_not_clear_it` |
| TC-S1-2e | Reopening a draft repopulates every input on screen | Vitest | `EventForm.test.tsx` › *reopening a draft repopulates every value previously entered* |
| TC-S1-2f | No field is marked `required`, so an empty form still saves | Vitest | `EventForm.test.tsx` › *no field is marked required…* |
| TC-S1-2g | In a browser: save a partial draft, reopen it, values intact | Playwright | `draft-and-submit.spec.ts` › TC-S1-2g |

> TC-S1-2f is the load-bearing one. A `required` attribute added to the form
> would let the browser block submission before any handler runs, silently
> breaking the entire draft story.

### AC3 — a draft is not visible to coordinators

> *Given a draft event request, when an Event Coordinator views the submitted
> requests queue, then the draft does not appear until it is submitted.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S1-3a | The queue excludes drafts | pytest | `test_draft_does_not_appear_in_the_review_queue` |
| TC-S1-3b | The request appears in the queue only once submitted | pytest | `test_draft_appears_in_the_queue_only_once_submitted` |

> **No browser test here, by necessity.** `GET /events/queue` is an API
> endpoint with no UI page yet — the Coordinator's review screen belongs to a
> later story. There is nothing for a browser to click, so this criterion is
> verified at the API layer. Not a coverage gap.

---

## Story 2 — Submit an Event Request

### AC1 — incomplete submissions are blocked and the gaps flagged

> *Given an event request with one or more mandatory fields empty, when the
> Event Organiser attempts to submit it, then submission is blocked and the
> missing fields are flagged.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S2-1a | Submission is refused and every missing field is named | pytest | `test_submit_blocked_when_mandatory_fields_missing` |
| TC-S2-1b | **Boundary:** a whitespace-only field counts as missing | pytest | `test_submit_treats_whitespace_only_as_missing` |
| TC-S2-1c | Exactly the rejected inputs are marked, and no others | Vitest | `EventForm.test.tsx` › *marks exactly the fields the server rejected* |
| TC-S2-1d | The error summary states how many fields are incomplete | Vitest | `EventForm.test.tsx` › *summarises how many fields are still incomplete* |
| TC-S2-1e | In a browser: submit incomplete → blocked, fields flagged | Playwright | `draft-and-submit.spec.ts` › TC-S2-1e |

The mandatory list lives in exactly one place — `MANDATORY_FIELDS` in
`backend/app/schemas/event.py`. The form holds no copy of it; it renders
whatever the server reports, so the two cannot drift apart.

### AC2 — a complete request becomes Submitted

> *Given all mandatory fields are complete, when the Event Organiser submits
> the request, then its status becomes "Submitted".*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S2-2a | Status becomes `submitted` and `submitted_at` is stamped | pytest | `test_submit_sets_status_to_submitted` |
| TC-S2-2b | **Conflict:** submitting twice is refused | pytest | `test_submitting_twice_is_rejected` |

### AC3 — it moves to Submitted Requests and leaves Drafts

> *Given a request has been submitted, when the Event Organiser views their
> requests, then it appears on the "Submitted Requests" page. Request no
> longer appears under drafts.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S2-3a | Absent from drafts, present in submitted | pytest | `test_submitted_request_moves_from_drafts_to_submitted_list` |
| TC-S2-3b | Each tab requests the right status and renders it | Vitest | `MyRequests.test.tsx` |
| TC-S2-3c | In a browser: the row visibly moves between tabs | Playwright | `draft-and-submit.spec.ts` › TC-S2-3c |

---

## Additional cases beyond the acceptance criteria

The criteria describe the happy path. These cover the failure, conflict and
boundary behaviour a reviewer would reasonably expect.

| Test | Covers |
|---|---|
| `test_organiser_cannot_see_another_organisers_draft` | Ownership. `EVENT_WRITE` is granted to Coordinators too, so permission alone is not enough. Returns 404, not 403, so the endpoint cannot be used to discover which event ids exist. |
| `test_attendee_cannot_create_an_event_request` | Attendees hold `EVENT_READ` but not `EVENT_WRITE`. |
| `test_anonymous_cannot_list_events` | Signed-out access reveals nothing. |
| `test_submitted_request_cannot_be_edited` | A request under review cannot be altered underneath the reviewer. |
| `test_submit_records_status_history` | The `draft → submitted` transition is recorded with who and when. |
| `test_end_before_start_is_rejected_cleanly` | Boundary: mirrors the database CHECK, returning 422 rather than a 500 from an IntegrityError. |
| `test_zero_attendance_is_rejected_cleanly` | Boundary: mirrors the `expected_attendance > 0` CHECK. |

---

## Manual test script — TC-S1-1c

The only case left to a human: visual judgement, which no assertion captures
well. Run before each sprint review; it doubles as the demo walkthrough.

**Setup:** `cd backend && uv run uvicorn app.main:app --reload` and
`cd frontend && npm run dev`, then sign in as an Event Organiser.

| # | Step | Expected result | Pass/Fail |
|---|---|---|---|
| 1 | Open **My event requests** from the sidebar | Two tabs, Drafts selected, "New request" button visible | |
| 2 | Click **New request** | Form opens in three labelled groups: About the event / Schedule & size / Requirements | |
| 3 | Read every field label | Each is clear and unambiguous; no field looks like it belongs in another group | |
| 4 | Click **Save as draft** with the form empty | Saves without complaint; lands on Drafts showing "Untitled draft" | |
| 5 | Reopen the draft and fill in a few fields | Values persist; layout does not shift or overflow | |
| 6 | Click **Submit request** with fields still missing | Missing fields are visibly marked; the message is understandable without guessing | |
| 7 | Narrow the window to roughly phone width | No horizontal scrolling; the start/end date fields stack rather than squash | |
| 8 | Switch the OS or browser theme to dark | All text remains legible; the flagged-field colour is still clearly an error | |

**Tester:** ______________  **Date:** ____________  **Build/commit:** ____________

---

## Evidence for submission

Every CI run attaches downloadable artefacts:

- `pytest-results.xml` — JUnit results for the backend suite.
- `playwright-report/` — HTML report with traces and screenshots of any
  failure.

Screenshot the workflow summary and attach both to deliverable 3.
