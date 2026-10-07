# Test Cases — Event Coordinator Lead Landing Page

Covers one product backlog item:

- **Event Coordinator Lead landing page.** *As an Event Coordinator Lead, I
  want a landing page after I log in with shortcuts to unassigned Event
  Requests and all Coordinator Assignments, so that I can assign and balance
  work in one click.*

Scope: the landing page and the two read-only lists its shortcuts open. The
assign / reassign actions are separate stories.

Design: `UnassignedRequests` and `CoordinatorAssignments`
(`backend/app/services/assignment_overview.py`) inherit from `EventListing`,
which holds the shared "active events, newest first" query. `LeadEventOut`
extends `EventSummary`. "Active" reuses `ACTIVE_ASSIGNMENT_STATUSES`; nothing
existing was modified. Both endpoints (`GET /lead/unassigned-requests`,
`GET /lead/assignments`) are Lead-only.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest tests/test_coordinator_lead_landing.py -q` | nothing |
| Components (Vitest) | `cd frontend && npx vitest run src/components/CoordinatorLeadLanding.test.tsx src/pages/lead` | nothing |
| End-to-end + axe (Playwright) | `cd frontend && npx playwright test e2e/coordinator-lead-landing.spec.ts` | local throwaway postgres built from `backend/db/schema.sql` |

## AC1 — login lands on the Lead page, welcome by full name and role

| Test | Layer |
|---|---|
| `AC1: welcomes the Lead with their full name and role` ("Lena Marie Lead" → "Welcome back, Lena Marie Lead") | Vitest |
| `TC-CLL-1e` login lands on `/coordinator-lead` and shows the welcome | Playwright |
| role → home-page mapping (`roles.test.ts`, from the previous story) | Vitest |

## AC2 — shortcuts to the features, each opens its feature

| Test | Layer |
|---|---|
| `AC2: shows the four shortcuts and each links to its feature` | Vitest |
| `AC2: Unassigned Requests lists …` / `Coordinator Assignments shows who holds each event` | Vitest |
| `test_ac2_unassigned_requests_lists_only_active_unassigned_events` (drafts, rejected and assigned excluded) | pytest |
| `test_ac2_assignments_lists_active_assigned_events_with_their_coordinator` | pytest |
| `test_ac2_assignments_include_every_coordinators_events` | pytest |
| `TC-CLL-2e` (×3) each shortcut opens its page; Assignments shows the Coordinator | Playwright |

## AC3 — counts shown when there are items

| Test | Layer |
|---|---|
| `AC3: shows how many unassigned requests and unread notifications there are` | Vitest |
| `test_ac3_count_is_the_number_of_unassigned_requests` | pytest |
| `TC-CLL-3e` two unassigned requests → "2" on the shortcut | Playwright |

## AC4 — no number when there are none

| Test | Layer |
|---|---|
| `AC4: shows no number when there are none` | Vitest |
| `AC4: a failed count hides the number but keeps the shortcut` | Vitest |
| `test_ac4_no_unassigned_requests_gives_an_empty_list`, `…_no_events_at_all_…` | pytest |
| `TC-CLL-4e` no tile shows a number | Playwright |

## Negative and regression

| Test | Layer |
|---|---|
| `test_other_roles_are_forbidden` (Organiser, Coordinator, Venue Staff, Tech Support, Attendee × both endpoints → 403) | pytest |
| `test_unauthenticated_is_rejected` (401) | pytest |
| `test_reading_the_views_changes_nothing` | pytest |
| `test_views_inherit_from_the_shared_listing`, `…_never_overlap` | pytest |
| `TC-CL-3e` a Coordinator still lands on `/coordinator` and cannot open Lead pages (previous story) | Playwright |

## Definition of Done — accessibility (section 8)

| Test | Layer |
|---|---|
| `TC-CLL-A1` landing, unassigned and assignments pages: no serious/critical axe violations, light and dark | Playwright + axe |
| `TC-CLL-A2` all four shortcuts reachable by Tab, every focused element shows focus | Playwright |

Known limit: the unread-Notifications count (AC3) is asserted in Vitest with
the notifications context mocked; the e2e run creates no notifications for the
Lead.
