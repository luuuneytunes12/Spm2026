# Test Cases — View Venue Details

Covers one product backlog item:

- **View venue details.** *As an internal user (Event Coordinator & Venue
  Staff), I want to view the details of a venue so that I can assess whether
  it suits an event's requirements.*

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_venues.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npx vitest run src/pages/venues` | nothing — jsdom, API mocked |

There is no endpoint that creates venues yet (VENUE_MANAGE is a separate
story), so backend tests insert venues through the model. For a real
database, run `backend/sql/010_seed_venues.sql` in the Supabase SQL editor.

## Who can see venues

`GET /venues` and `GET /venues/{id}` are gated on the **Coordinator** and
**Venue Staff** roles, not on `VENUE_READ`: Attendees hold `VENUE_READ`, and
the story is for internal users only. Inactive venues are listed with an
"Inactive" badge rather than hidden.

## Test cases

| AC | Test case | Automated by |
|---|---|---|
| AC1 — name, location, capacity | Coordinator and Venue Staff each see them in the list and on the detail page | `test_internal_user_sees_name_location_and_capacity` (both roles); component: *venue list …*, *AC1: shows name, location and capacity* |
| AC1 — (list) | Venues are alphabetical; inactive ones still listed | `test_venue_list_is_alphabetical_and_includes_inactive` |
| AC2 — layouts, facilities, accessibility | All three lists shown as recorded | `test_detail_shows_layouts_facilities_and_accessibility`; component: *AC2: shows supported layouts, facilities and accessibility features* |
| AC2 — (empty) | Nothing recorded → "None recorded", not a missing row | `test_detail_returns_empty_lists_when_nothing_recorded`; component: *says so when … not recorded* |
| AC3 — operating hours | Multi-line hours shown line by line | `test_detail_shows_operating_hours`; component: *AC3: shows operating hours, one entry per line* |
| AC3 — (empty) | No hours recorded → "Not recorded" | `test_detail_operating_hours_may_be_unrecorded`; component: *says so when … not recorded* |
| (guard) Unknown venue | 404 → "Venue not found." | `test_unknown_venue_is_not_found`; component: *shows "not found" …* |
| (guard) External / other roles | Attendee, Organiser, Tech Support get 403 | `test_non_internal_roles_cannot_view_venues` |
| (guard) Signed out | 401 | `test_unauthenticated_request_is_rejected` |
