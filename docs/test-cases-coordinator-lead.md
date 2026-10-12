# Test Cases — Create Event Coordinator Lead Role

Covers one product backlog item:

- **Create Event Coordinator Lead Role.** *As ConnectSphere, I want an Event
  Coordinator Lead role added to the system, so that the Lead can assign Event
  Requests.*

Scope includes the Lead's role, unassigned queue, assignment/reassignment
endpoints, and all-assignment overview. New submissions remain unassigned;
the Lead's assignment leaves an event in `submitted_awaiting_coordinator` so
the assigned Coordinator can approve it.

Design: `CoordinatorLeadProfile` inherits `CoordinatorProfile`
(`backend/app/core/roles.py`), so the Lead holds every Coordinator permission
plus the two above. Existing roles' tables are not modified.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest tests/test_coordinator_lead_role.py -q` | nothing — in-memory SQLite |
| Frontend (Vitest) | `cd frontend && npx vitest run src/lib/roles.test.ts` | nothing |
| End-to-end + axe (Playwright) | `cd frontend && npx playwright test e2e/coordinator-lead.spec.ts` | local throwaway postgres, built from `backend/db/schema.sql` |

## AC1 — the role exists with assign / reassign / view-all powers

| Test | Layer | Proves |
|---|---|---|
| `test_ac1_role_value_matches_the_database_enum_label` | pytest | role is `event_coordinator_lead`, labelled "Event Coordinator Lead" |
| `test_ac1_lead_can_assign_and_reassign_and_view_all_assignments` | pytest | Lead holds `assignment:manage` and `assignment:view_all` |
| `test_ac1_lead_account_reports_the_lead_role_and_assignment_permissions` | pytest | `/auth/me` shows the role and permissions |
| `test_ac1_a_plain_coordinator_cannot_assign_or_view_all_assignments` | pytest | negative: Coordinator lacks both |
| `test_ac1_lead_profile_inherits_from_coordinator_profile` | pytest | inheritance: Lead = Coordinator + assignment permissions |
| AC1 cases in `roles.test.ts` | Vitest | frontend mirror matches |

## AC2 — login, logout, profile edit work as for a Coordinator

Each pytest case is parametrised over Coordinator **and** Lead, so identical
behaviour is asserted directly.

| Test | Layer | Proves |
|---|---|---|
| `test_ac2_login_succeeds_and_sets_refresh_cookie` | pytest | login works |
| `test_ac2_wrong_password_is_rejected` | pytest | negative: bad password → 401 |
| `test_ac2_logout_clears_the_session` | pytest | logout ends the session |
| `test_ac2_profile_edit_saves_and_persists_across_login` | pytest | edit saves, role unchanged, survives re-login |
| `test_ac2_invalid_profile_edit_is_rejected_and_nothing_saved` | pytest | negative: bad email / blank name → 422, nothing written |
| `test_ac2_lead_holds_every_permission_a_coordinator_holds` | pytest | Lead ⊇ Coordinator |
| `TC-CL-2e` | Playwright | real browser: land on Lead page, edit profile, log out |

## AC3 — other roles unchanged

| Test | Layer | Proves |
|---|---|---|
| `test_ac3_existing_role_permissions_are_unchanged` | pytest | Coordinator, Venue Staff, Tech Support, Attendee grants equal a frozen literal |
| `test_ac3_organiser_keeps_every_permission_it_had` | pytest | Organiser loses nothing |
| `test_ac3_existing_role_logs_in_with_its_own_role_and_no_lead_powers` | pytest | each role logs in as itself, no Lead powers |
| `test_ac3_role_gated_endpoint_access_is_unchanged` | pytest | role-gated endpoint: Organiser 200, all others 403 |
| `test_ac3_lead_is_not_added_to_the_coordinator_assignment_pool` | pytest | the Lead remains outside the Coordinator role/pool; request submission itself does not assign |
| `test_ac3_existing_role_values_are_unchanged` | pytest | no existing role value changed |
| AC3 cases in `roles.test.ts` | Vitest | existing home pages and permissions unchanged |
| `TC-CL-3e` | Playwright | Coordinator still lands on `/coordinator`; Lead page is forbidden to them |

Known limit: Safety Officer exists in the live database enum but is not yet a
`Role` in code, so it has no behaviour to pin.

## Definition of Done — accessibility (section 8)

| Test | Layer | Proves |
|---|---|---|
| `TC-CL-A1` (light, dark) | Playwright + axe | no serious / critical WCAG 2.x A/AA violations on the Lead page |
| `TC-CL-A2` | Playwright | every focusable element on the Lead page shows visible focus |
