# Test Cases — Search and Filter Venues

Covers one product backlog item:

- **Search and Filter Venues.** *As an Event Coordinator, I want to search for
  venues by keyword and filter them by my event's requirements, so that I can
  quickly narrow down venues worth reviewing.*

Every acceptance criterion maps to at least one test, and every automated test
is named after the criterion it proves. Edge cases — boundaries, invalid input,
the overlap rule — are covered as **test cases**, not as extra criteria.

## Acceptance criteria

| # | Given / When / Then |
|---|---|
| **AC1** | Given I enter a keyword on the venue search page, when results are returned, then only venues whose **name or location** match that keyword are shown |
| **AC2** | Given I apply one or more filters (**date and time**, expected attendance, layout, accessibility, facilities), when results are returned, then only venues satisfying **all** selected filters appear |
| **AC3** | Given I apply an expected attendance or a date and time, when results are returned, then venues **below that capacity**, or **already booked or blocked during that time**, are excluded |
| **AC4** | Given results are displayed, when I view the list, then each result shows the venue name, location, capacity, and key facilities |
| **AC5** | Given I click on a search result, when the page loads, then the venue's full details are displayed |

### How this covers the core feature (W4 p3, *Venue Search and Filtering*)

The core feature lists eight criteria: *date, time, expected attendance,
location, capacity, accessibility, supported layout, required facilities*.

| From the PDF | Covered by |
|---|---|
| Date, time | AC2 + AC3 — a start and end; booked or blocked venues are excluded |
| Expected attendance, capacity | AC3 — one filter: *capacity at least N* **is** *fits N attendees* |
| Location | AC1 — locations are free-text addresses with no regions to pick from, so the keyword is the location search |
| Accessibility, layout, facilities | AC2 |

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_venue_search.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| All of the above | push to any branch | GitHub Actions runs them |

**47 pytest cases · 25 Vitest cases · 1 manual script.** No Playwright — the
end-to-end CI job is disabled for now.

---

## Business rules

| Rule | Basis | Tested by |
|---|---|---|
| A keyword matches name **or** location, partially, in any case | AC1 | `test_ac1_*` |
| Every selected filter must hold (AND) | AC2 | `test_ac2_keyword_and_every_kind_of_filter_combine` |
| Two facilities ticked → a venue needs **both** — likewise accessibility | AC2 "all selected filters" | `test_ac2_a_venue_must_have_every_selected_*` |
| One layout at a time — an event uses one | Team decision | `test_ac2_layout_filter_matches_in_any_case` |
| Filter values match in any case | Values are free text typed by Venue Staff | `test_ac2_facility_matching_ignores_case` |
| Capacity **equal** to the attendance is included | AC3 "below … excluded" | `test_ac3_a_venue_exactly_at_the_expected_attendance_is_included` |
| An **approved** booking overlapping the window excludes a venue | W4 p4: *"A confirmed booking should affect whether that venue is considered available"* | `test_ac3_an_approved_booking_*` |
| `pending`, `rejected`, `cancelled` bookings do **not** — ⚠ *provisional, see below* | Only a confirmed booking blocks | `test_ac3_a_booking_that_is_not_approved_does_not_block` |
| A recorded unavailability period overlapping the window excludes a venue | W4 p3: *"other recorded periods of unavailability should be reflected"* | `test_ac3_a_recorded_unavailability_*` |
| Overlap means `existing.start < end AND existing.end > start` — **back-to-back is free** | A session ending 09:00 leaves the room free at 09:00 | `test_ac3_back_to_back_is_not_an_overlap` |
| Half a window, or an end not after its start, is rejected (422) | A mistake, not a search | `test_ac3_an_invalid_time_window_is_rejected` |
| Inactive venues stay in results, flagged | Consistent with *View Venue Details* | `test_ac4_an_inactive_venue_*` |
| Filter choices are the distinct values recorded, deduplicated ignoring case | Columns are free text, not a fixed vocabulary | `test_filter_options_*` |

**Out of scope:** setup and turnaround time between events (a separate
briefing feature, not in the core 20) and operating hours (recorded as free
text such as *"Mon-Fri 08:00-23:00"*, which cannot be compared reliably).

### ⚠ Open dependency — booking statuses

Venue Booking Request and Venue Booking Approval are **not built on any
branch yet**, and nothing writes `venue_bookings` or `venue_unavailability`.
The date filter reads the existing `booking_status` enum
(`pending / approved / rejected / cancelled`) and treats only `approved` as
blocking, per the W4 p4 wording.

If the booking stories decide a *pending* request should also hold a venue,
that is a one-line change in the search plus one flipped test case.

Until those stories land, the only rows in either table are the demo data in
`backend/sql/012_seed_venue_availability_demo.sql`: one approved booking of
*Harbourfront Seminar Room 2* and one maintenance block on *Raffles Place
Training Studio*, both over the time of the confirmed *Registration Test
Event* (8 Oct 2026, 16:46–19:46 Singapore time).

---

## Traceability

### AC1 — keyword

| Test | Type |
|---|---|
| `test_ac1_keyword_matches_the_name_partially_and_in_any_case` | pytest |
| `test_ac1_keyword_matches_the_location` | pytest |
| `test_ac1_keyword_with_no_match_returns_an_empty_list` | pytest |
| `test_ac1_a_blank_keyword_is_no_keyword` | pytest |
| `test_no_criteria_returns_every_venue_alphabetically` | pytest |
| *searches by what is typed* · *waits for a pause in typing…* | Vitest |
| *VS AC1: sends the keyword trimmed…* | Vitest (lib) |

### AC2 — every selected filter holds

| Test | Type |
|---|---|
| `test_ac2_layout_filter_matches_in_any_case` | pytest |
| `test_ac2_a_venue_must_have_every_selected_facility` | pytest |
| `test_ac2_facility_matching_ignores_case` | pytest |
| `test_ac2_a_venue_must_have_every_selected_accessibility_feature` | pytest |
| `test_ac2_keyword_and_every_kind_of_filter_combine` | pytest |
| `test_filter_options_*` (4 tests) | pytest |
| *offers the layouts recorded…* · *asks for every facility ticked…* · *asks for every accessibility feature ticked* · *unticking a facility…* · *combines the keyword with every filter…* · *still lets you search… if the filter choices fail to load* | Vitest |
| *VS AC2: repeats the parameter…* · *sends a single layout* | Vitest (lib) |

### AC3 — attendance and date/time exclude venues

| Test | Type |
|---|---|
| `test_ac3_venues_below_the_expected_attendance_are_excluded` | pytest |
| `test_ac3_a_venue_exactly_at_the_expected_attendance_is_included` — **boundary** | pytest |
| `test_ac3_an_attendance_that_is_not_a_positive_number_is_rejected` (0, −5, text) | pytest |
| `test_ac3_an_approved_booking_overlapping_the_window_excludes_the_venue` | pytest |
| `test_ac3_a_booking_that_is_not_approved_does_not_block` (pending, rejected, cancelled) | pytest |
| `test_ac3_a_recorded_unavailability_overlapping_the_window_excludes_the_venue` | pytest |
| `test_ac3_every_kind_of_overlap_excludes_the_venue` (4 shapes) | pytest |
| `test_ac3_a_booking_outside_the_window_does_not_block` (3 cases) | pytest |
| `test_ac3_back_to_back_is_not_an_overlap` — **boundary** (both edges) | pytest |
| `test_ac3_a_booking_of_another_venue_changes_nothing` | pytest |
| `test_ac3_an_invalid_time_window_is_rejected` (5 cases) | pytest |
| *searches for venues that hold at least that many people* · *ignores an attendance that is not a positive number* | Vitest |
| *searches for venues free across the window entered* · *refuses a window that ends before it starts…* · *asks for the other half of the window…* | Vitest |

### AC4 — what each result shows

| Test | Type |
|---|---|
| `test_ac4_each_result_carries_name_location_capacity_and_facilities` | pytest |
| `test_ac4_an_inactive_venue_matching_the_filters_is_still_listed_and_flagged` | pytest |
| *shows the name, location, capacity and facilities of every result* | Vitest |
| *marks an inactive venue as inactive rather than hiding it* | Vitest |
| *says so when nothing matches, and can clear back to every venue* | Vitest |

### AC5 — opening a result

| Test | Type |
|---|---|
| *links each result to that venue's full details* | Vitest |

The details page itself is the *View Venue Details* story, already covered
by `VenueView.test.tsx` and `test_venues.py`. This story only proves the link.

### Who may search

| Test | Type |
|---|---|
| `test_roles_outside_venue_planning_cannot_read_filter_options` (Organiser, Attendee, Tech Support → 403) | pytest |
| `test_venue_staff_can_read_filter_options` | pytest |
| `test_an_anonymous_caller_is_unauthenticated` (both endpoints → 401) | pytest |

Gated on **role** (Coordinator, Venue Staff), not on the `VENUE_READ`
permission — Attendees hold that permission, and internal venue details are
not meant for them. Unchanged from *View Venue Details*.

---

## Manual test — TC-VS-M1

**Preconditions:** backend and frontend running, signed in as an Event
Coordinator, `backend/sql/010_seed_venues.sql` and
`backend/sql/011_seed_venues_for_search.sql` and
`backend/sql/012_seed_venue_availability_demo.sql` applied (12 venues, one
approved booking, one maintenance block).

| # | Step | Expected result |
|---|---|---|
| 1 | Open **Venues** | All 12 venues, alphabetical; *Changi Business Suite* marked **Inactive** |
| 2 | Type `marina` | 3 venues — including *Bayfront Conference Hall A*, matched through its **location** |
| 3 | Clear, then set expected attendance `100` | 7 venues, none holding fewer than 100 |
| 4 | Clear, tick **Projector** | 5 venues |
| 5 | Also tick **Video conferencing** | 3 venues — only those with **both** |
| 6 | Pick layout **Theatre** with step 5's facilities | The results narrow further |
| 7 | Clear, then set *Available from* 8 Oct 2026 16:00 and *Available until* 8 Oct 2026 20:00 | 10 venues — *Harbourfront Seminar Room 2* (booked) and *Raffles Place Training Studio* (closed for maintenance) are gone |
| 8 | Change both dates to 9 Oct 2026, same times | All 12 venues are back |
| 9 | Set *Available until* earlier than *Available from* | *"The end must be after the start."*; results unchanged |
| 10 | Search for something that matches nothing | *"No venues match your search."* and a working **Clear filters** |
| 11 | Click any result | That venue's full details open |
| 12 | Narrow to ~400px wide | Filters stack; nothing scrolls sideways |
| 13 | Toggle dark mode | Checkboxes, chips and the Inactive badge stay readable |

**Tester:** ______________ **Date:** ____________ **Result:** Pass / Fail
