# Test Cases — Filter Venues by Date and Time

> *As an Event Coordinator, I want to filter Venues by the date and time my
> Event needs, so that I only see Venues that are free then.*

Builds on *Search and Filter Venues*
([test-cases-venue-search.md](test-cases-venue-search.md)), *Tentative Venue
Holds* (SCRUM-97) and *Configure Venue Setup & Turnaround Time* (SCRUM-78).
Those stories already exclude approved bookings and unexpired tentative
holds, padded by each venue's setup and turnaround time. This story adds:

- **closures padded too**: the searched event's setup and turnaround cannot
  fall inside a recorded closure;
- **a date, a start time and an end time** on the search page, in place of
  two date-time boxes;
- **a blocked search** with both time fields flagged when the end time is not
  after the start time.

Every acceptance criterion maps to at least one test, and every automated
test is named after the criterion it proves (`DT AC1`–`DT AC4`).

## Acceptance criteria

| # | Given / When / Then |
|---|---|
| **AC1** | Given I enter a date and a start and end time, when results are returned, then Venues with an **Approved** booking, a **Tentative Hold** or an **unavailability period** overlapping that window (**including setup and turnaround time**) are excluded |
| **AC2** | Given a Venue's only overlapping booking is **Rejected**, **Cancelled** or **Hold Expired**, when results are returned, then the Venue is still shown |
| **AC3** | Given the end time is earlier than the start time, when I search, then the search is **blocked** and the fields are **flagged** |
| **AC4** | Given I combine the date and time filter with other filters, when results are returned, then only Venues meeting **all** of them are shown |

## The rule

An event of `[start, end)` keeps a venue busy from **start − setup** to
**end + turnaround** (`app/domain/venue_occupancy.py`; an unset value is read
as 0). The venue is left out of a search when that padded period overlaps:

| What | Padded? | Source |
|---|---|---|
| An **approved** booking | Yes, by the same venue's setup and turnaround | SCRUM-78 |
| A **tentative hold** whose `expires_at` has not passed | Yes, the same way | SCRUM-97 |
| A recorded **closure** | No: it is a raw period, but the searched event's padding must not fall inside it | **This story** |

Touching is not overlapping. With exactly `setup + turnaround` minutes between
two events, the venue is free.

**Hold Expired** is a tentative hold past its `expires_at`. The search releases
it first (`expire_tentative_holds`: status `hold_expired`, notes *"Tentative hold
expired."*), so it never blocks. **Pending** requests (awaiting a decision, not
a hold) and rejected or cancelled bookings never block.

## Decisions taken

| Decision | Why |
|---|---|
| **Closures are padded by the searched event's setup and turnaround.** | AC1 lists unavailability among the things excluded "including setup and turnaround time". A room that is closed cannot be prepared before the event or reset after it. Before this story, the search treated closures as raw periods. |
| **Booking approval is unchanged.** It still compares closures as raw periods. | Approval belongs to another story. ⚠ The search and approval can therefore disagree about a booking whose setup or turnaround touches a closure. Flagged for the owner of the approval story. |
| **One date, a start time and an end time.** An end time not after the start time (earlier **or equal**) blocks the search: nothing is sent, results are replaced by *"Search paused."*, and both time fields are flagged. | AC3. Showing results for a back-to-front window would present venues as free for a time nobody asked about. As a result, an event that runs past midnight cannot be searched in one go. |
| **An unfinished window** (e.g. date and start only) is left out of the search, and only the missing field is flagged. | It is usually a half-typed value, not a mistake, so the rest of the search keeps working. |

## The pieces

| Piece | Change |
|---|---|
| `GET /venues?start=&end=` | Closures are compared against the searched window padded by the venue's setup and turnaround (`_free_of_closures` in `app/routers/venues.py`). Bookings and holds are unchanged. |
| `/venues` page | The **Date & time** filter: Date, Start time, End time; blocking and flagging. |
| Demo data | `backend/sql/026_seed_venue_setup_turnaround_demo.sql`: setup and turnaround on three seeded venues. No schema change. |

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend unit (pytest, SQLite) | `cd backend && uv run pytest -q tests/test_venue_date_filter.py` | nothing |
| Backend integration (pytest, **PostgreSQL**) | `cd backend && uv run pytest -q tests/integration/test_venue_date_filter_postgres.py` | Docker (Testcontainers) |
| Components (Vitest) | `cd frontend && npx vitest run src/pages/venues/Venues.test.tsx` | nothing |
| End-to-end + accessibility (Playwright) | `cd frontend && npx playwright test e2e/venue-date-filter.spec.ts` | a local Postgres with `db/schema.sql` applied (see `.github/workflows/ci.yml`) |
| All of the above | push to any branch | GitHub Actions |

**30 pytest · 3 Postgres · 14 Vitest · 6 Playwright · 1 manual script.**

---

## Traceability

### AC1 — approved bookings, tentative holds and unavailability are excluded, setup and turnaround included

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-1a | An approved booking overlapping the window excludes the venue | pytest | `test_ac1_an_approved_booking_overlapping_the_window_excludes_the_venue` |
| TC-DT-1b | An unexpired tentative hold overlapping the window excludes the venue | pytest | `test_ac1_a_tentative_hold_overlapping_the_window_excludes_the_venue` |
| TC-DT-1c | A closure overlapping the window excludes the venue | pytest | `test_ac1_an_unavailability_period_overlapping_the_window_excludes_the_venue` |
| TC-DT-1d | Setup: a booking ending 08:45 leaves too little of 30 min setup → excluded; ending 08:30 → listed (**boundary**) | pytest | `test_ac1_setup_time_before_the_event_is_counted` |
| TC-DT-1e | Turnaround: a booking ending 08:30 leaves too little of a 60-min reset → excluded; ending 08:00 → listed (**boundary**) | pytest | `test_ac1_turnaround_time_after_an_earlier_booking_is_counted` |
| TC-DT-1f | A later booking needs turnaround + setup after 17:00: starting 18:29 → excluded, 18:30 → listed (**boundary**) | pytest | `test_ac1_a_later_booking_needs_turnaround_and_setup_after_the_window` |
| TC-DT-1g | **Closures:** the searched event's setup and turnaround count against them, before and after (4 cases, 2 boundaries) | pytest | `test_ac1_setup_and_turnaround_count_against_unavailability_too` |
| TC-DT-1h | An approved booking or hold whose published times do not touch the window still excludes the venue once padding is counted | pytest | `test_ac1_a_booking_that_only_clashes_because_of_setup_and_turnaround_excludes_the_venue` |
| TC-DT-1i | Each venue is padded by its own setup and turnaround; unset is 0 | pytest | `test_ac1_each_venue_is_padded_by_its_own_setup_and_turnaround` |
| TC-DT-1j | A window given in Singapore time is the same moment in UTC | pytest | `test_ac1_a_window_given_in_singapore_time_is_compared_correctly` |
| TC-DT-1k | On PostgreSQL: hold, padded booking and padded closure all excluded; same result for an SGT window | Postgres | `test_ac1_ac2_holds_bookings_closures_and_padding_on_postgres` |
| TC-DT-1l | The page sends the date, start and end time as one UTC window | Vitest | *DT AC1 › searches for venues free on that date between the start and end time* |
| TC-DT-1m | The page says bookings, holds, closures and setup/turnaround count | Vitest | *DT AC1 › says that bookings, tentative holds, closures…* |
| TC-DT-1n | The applied window shows on its chip | Vitest | *DT AC1 › shows the window on its chip once the panel is closed* |
| TC-DT-1o | In a browser: of seven seeded venues, the booked, held, padded and closed ones are gone; the next day all are back | Playwright | *DT AC1 + AC2* |
| TC-DT-1p | In a browser: the padded venue is listed from 09:30 and not at 09:29 | Playwright | *DT AC1: a window that clears the padding…* |

### AC2 — rejected, cancelled and expired holds do not exclude a venue

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-2a | A venue whose only overlapping booking is rejected or cancelled is shown, even with setup and turnaround set | pytest | `test_ac2_a_venue_whose_only_overlapping_booking_is_rejected_or_cancelled_is_still_shown` |
| TC-DT-2b | A venue whose only overlapping hold has expired is shown, and the hold is released as Hold Expired | pytest | `test_ac2_a_venue_whose_only_overlapping_hold_has_expired_is_still_shown` |
| TC-DT-2c | "Only" matters: rejected and expired bookings do not cancel out an approved one | pytest | `test_ac2_one_live_booking_still_excludes_a_venue_that_also_has_dead_ones` |
| TC-DT-2d | On PostgreSQL: the expired hold is listed, and its release persists | Postgres | `test_ac1_ac2_holds_bookings_closures_and_padding_on_postgres` |
| TC-DT-2e | In a browser: the rejected venue and the expired-hold venue are listed | Playwright | *DT AC1 + AC2* |

### AC3 — an end time earlier than the start time blocks the search and flags the fields

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-3a | The API refuses an end before or equal to the start with 422, naming `end` | pytest | `test_ac3_an_end_earlier_than_the_start_is_refused_and_the_end_is_flagged` |
| TC-DT-3b | The same on PostgreSQL | Postgres | `test_ac3_an_end_before_the_start_is_refused_on_postgres` |
| TC-DT-3c | The page sends nothing, shows *"Search paused."*, and flags Start time and End time (not Date) | Vitest | *DT AC3 › blocks the search and flags both time fields* |
| TC-DT-3d | It stays blocked while other filters change; the chip reads *"Date & time: invalid"* | Vitest | *DT AC3 › stays blocked while other filters change* |
| TC-DT-3e | An end time equal to the start time is blocked the same way | Vitest | *DT AC3 › treats an end time equal to the start time the same way* |
| TC-DT-3f | Fixing the end time resumes the search and clears the flags | Vitest | *DT AC3 › resumes the search, and clears the flags…* |
| TC-DT-3g | In a browser: blocked, flagged, then resumed once fixed | Playwright | *DT AC3* |

### AC4 — combined with other filters, only venues meeting all are shown

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-4a | One venue meets every filter; eight others each fail exactly one (held, padded booking, padded closure, too small, wrong layout, missing facility, missing accessibility, wrong location) | pytest | `test_ac4_the_date_filter_combines_with_every_other_filter` |
| TC-DT-4b | Without a date, bookings, holds and closures do not affect the other filters | pytest | `test_ac4_without_a_date_the_same_filters_ignore_bookings_and_closures` |
| TC-DT-4c | On PostgreSQL: date and capacity together | Postgres | `test_ac4_date_and_capacity_combine_on_postgres` |
| TC-DT-4d | The page sends the date and time with every other filter in one search | Vitest | *DT AC4 › sends the date and time together with every other filter* |
| TC-DT-4e | The page lists exactly what the combined search returns | Vitest | *DT AC4 › shows only the venues the server returns…* |
| TC-DT-4f | In a browser: date and time plus attendance 250 leave only the venue that is free and large enough | Playwright | *DT AC4* |

### Additional cases beyond the acceptance criteria (DoD 3)

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-N1 | Organiser, Attendee and Tech Support cannot search by date (403); Venue Staff can; anonymous is 401 | pytest | `test_roles_outside_venue_planning_cannot_search_by_date` · `test_venue_staff_can_search_by_date` · `test_an_anonymous_caller_cannot_search_by_date` |
| TC-DT-N2 | In a browser: an Organiser opening `/venues` gets the Forbidden page | Playwright | *DT negative* |
| TC-DT-N3 | An unfinished window asks for what is missing, flags only that field, and is not searched with | Vitest | *DT - an unfinished date and time › asks for what is missing…* |
| TC-DT-N4 | An unfinished window is flagged on its chip | Vitest | *… › flags an unfinished window on its chip* |
| TC-DT-N5 | Removing the filter empties all three fields and lifts the block | Vitest | *… › removing the filter empties all three fields* |
| TC-DT-N6 | **Accessibility:** no serious or critical axe violations with the fields flagged; Date → Start time → End time reachable with Tab | Playwright | *DT accessibility* |

Not applicable: an audit trail and idempotency (a search changes no state),
and concurrency (no write).

---

## Manual test — TC-DT-M1

**Preconditions:** backend and frontend running; `backend/sql/010`–`026`
applied (Harbourfront Seminar Room 2 has an approved booking on 8 Oct 2026,
16:46–19:46 Singapore time, with 30 min setup and 60 min turnaround; Raffles
Place Training Studio is closed over the same time). An Event Coordinator, a
Venue Staff member and an Organiser can sign in. Browser in Singapore time.

| # | As | Step | Expected result |
|---|---|---|---|
| 1 | Coordinator | Open **Venues**, then **Date & time** | Three fields: **Date**, **Start time**, **End time**; the hint mentions bookings, holds, closures and setup and turnaround time |
| 2 | Coordinator | 8 Oct 2026, 16:00 – 20:00 | Harbourfront (booked) and Raffles Place (closed) are gone (AC1) |
| 3 | Coordinator | 21:00 – 23:00 | Raffles Place is back; Harbourfront is still gone, because it needs 60 min reset plus 30 min setup after 19:46 (AC1) |
| 4 | Coordinator | 21:30 – 23:00 | Harbourfront is back |
| 5 | Venue Staff | On *Orchard Gallery Loft*, set setup to 60 min; record a closure ending 8 Oct 15:30 | — |
| 6 | Coordinator | 8 Oct 2026, 16:00 – 18:00 | *Orchard Gallery Loft* is gone: its 60 min of setup would start at 15:00, inside the closure (AC1, closures padded) |
| 7 | Coordinator | Place a tentative hold on a venue for your event, then search that event's date and times | The held venue is gone (AC1) |
| 8 | Venue Staff | Reject the request, or let the hold expire | — |
| 9 | Coordinator | Search again | The venue is back (AC2) |
| 10 | Coordinator | Start time 17:00, End time 09:00 | *"The end time must be after the start time."*; both time fields outlined red; *"Search paused."*; chip *Date & time: invalid* (AC3) |
| 11 | Coordinator | Type a keyword while it is paused | Still paused, nothing reloads (AC3) |
| 12 | Coordinator | End time 18:00 | The flags clear and results return |
| 13 | Coordinator | 8 Oct 16:00 – 20:00 with **Expected attendance** 60 | Only venues that are free **and** hold 60 or more (AC4) |
| 14 | Organiser | Go to `/venues` | The Forbidden page |
| 15 | Coordinator | Steps 1–2 using only the keyboard | Every field is reachable, labelled and visibly focused |
| 16 | Coordinator | ~400px wide, then dark mode | The fields stay readable; nothing scrolls sideways |

**Tester:** ______________ **Date:** ____________ **Result:** Pass / Fail

## Not covered (separate stories)

Booking approval treating closures as raw periods (see Decisions); events
that run past midnight.
