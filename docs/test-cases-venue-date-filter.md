# Test Cases — Filter Venues by Date and Time

> *As an Event Coordinator, I want to filter Venues by the date and time my
> Event needs, so that I only see Venues that are free then.*

Builds on *Search and Filter Venues*
([test-cases-venue-search.md](test-cases-venue-search.md)), which added the
search page and a start/end window that excluded approved bookings and
recorded unavailability. This story adds **tentative holds**, **setup and
turnaround time**, and a **date + start time + end time** entry that blocks
the search when the end is not after the start.

Source: Week 4 Project Instructions, *Venue Search and Filtering*; Week 1
Customer Briefing, *Tentative Venue Holding* and *Setup and Turnaround Time*;
Week 7 #1 (setup and turnaround in availability) and #2 (replacement venue
search).

Every acceptance criterion maps to at least one test, and every automated
test is named after the criterion it proves (`DT AC1`–`DT AC4`).

## Acceptance criteria

| # | Given / When / Then |
|---|---|
| **AC1** | Given I enter a date and a start and end time, when results are returned, then Venues with an **Approved** booking, a **Tentative Hold** or an **unavailability period** overlapping that window (**including setup and turnaround time**) are excluded |
| **AC2** | Given a Venue's only overlapping booking is **Rejected**, **Cancelled** or **Hold Expired**, when results are returned, then the Venue is still shown |
| **AC3** | Given the end time is earlier than the start time, when I search, then the search is **blocked** and the fields are **flagged** |
| **AC4** | Given I combine the date and time filter with other filters, when results are returned, then only Venues meeting **all** of them are shown |

## Decisions taken

| Decision | Why |
|---|---|
| **A Tentative Hold is a `pending` booking request.** A request awaiting a Venue Staff decision holds the venue until it is decided. | The briefing: a venue "may be temporarily held while an event is still being finalised". No new status or rename was needed; the team chose this over a separate hold status. |
| **New status `hold_expired`.** It never holds a venue. | AC2 names it. *When* a hold expires (and who sets it) belongs to the Tentative Venue Holding story; this story only guarantees an expired hold does not block. |
| **Setup and turnaround are per venue**: `venues.setup_minutes` (preparation before every event) and `venues.turnaround_minutes` (reset after it). Both default to 0. | The AC requires them to be counted but does not say where they come from. Per venue needs no extra input from the Coordinator. Existing venues behave exactly as before until Venue Staff set values. |
| **The padding rule.** A booking of `[start, end)` keeps its venue busy for `[start − setup, end + turnaround)`, and so does the event being searched for. Two events at a venue therefore need `setup + turnaround` minutes between them. An unavailability period clashes with the searched event's padded period. | The briefing: "preparation before an event and reset time after an event, rather than only the published event start and end times". |
| **Touching is not overlapping.** With exactly `setup + turnaround` minutes between two events, the venue is free. | Same boundary rule as before; with 0 / 0 it is the old "back-to-back is free". |
| **Booking approval uses the same rule.** Approving a request is refused when a *confirmed* booking or a closure clashes, padding included. Another *tentative hold* does not stop an approval. | The search and the approval must never disagree about one venue (briefing: "Users should not be presented with contradictory information"). Letting holds block approval would leave two holds on one slot both stuck. |
| **One date, a start time and an end time.** An end time not after the start time (earlier **or equal**) blocks the search: nothing is sent, results are replaced by *"Search paused."*, and both time fields are flagged. | AC3. Showing results for a back-to-front window would present venues as free for a time nobody asked about. As a consequence, an event that runs past midnight cannot be searched in one go. |
| **An unfinished window** (e.g. date and start only) is left out of the search, and only the missing field is flagged. | It is usually a half-typed value, not a mistake, so the rest of the search keeps working. |
| **Venue details show the setup and turnaround time.** | A Coordinator can see *why* a venue is missing from a window that looks free by its published times. |

## The pieces

| Piece | Change |
|---|---|
| `GET /venues?start=&end=` | Excludes approved bookings, tentative holds (`pending`) and unavailability, padded by each venue's setup and turnaround time. 422 naming `end` when the end is not after the start. |
| `GET /venues/{id}` | Adds `setup_minutes`, `turnaround_minutes`. |
| `POST /venue-bookings/{id}/approve` | Same padded rule against confirmed bookings and closures. |
| `app/services/venue_availability.py` | **New.** The one overlap rule, shared by the search and the approval. |
| `booking_status` enum | Adds `hold_expired`. |
| Schema | `backend/sql/015_venue_setup_turnaround_and_hold_expired.sql` (rollback in its header), mirrored in `db/schema.sql`. Demo values: `backend/sql/016_seed_venue_setup_turnaround_demo.sql`. |
| Screens | `/venues`: the **Date & time** filter (Date, Start time, End time). `/venues/{id}`: Setup time, Turnaround time. |

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend unit (pytest, SQLite) | `cd backend && uv run pytest -q tests/test_venue_date_filter.py` | nothing |
| Backend integration + concurrency (pytest, **PostgreSQL**) | `cd backend && uv run pytest -q tests/integration/test_venue_date_filter_postgres.py` | Docker (Testcontainers starts `postgres:16` from `db/schema.sql`) |
| Components (Vitest) | `cd frontend && npx vitest run src/pages/venues` | nothing |
| End-to-end + accessibility (Playwright) | `cd frontend && npx playwright test e2e/venue-date-filter.spec.ts` | a local Postgres with `db/schema.sql` applied (see `.github/workflows/ci.yml`); ports 8001 and 5174 free |
| All of the above | push to any branch | GitHub Actions |

**35 pytest · 4 Postgres · 16 Vitest · 6 Playwright · 1 manual script.**

---

## Traceability

### AC1 — approved bookings, tentative holds and unavailability are excluded, setup and turnaround included

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-1a | An approved booking overlapping the window excludes the venue | pytest | `test_ac1_an_approved_booking_overlapping_the_window_excludes_the_venue` |
| TC-DT-1b | A tentative hold (pending request) overlapping the window excludes the venue | pytest | `test_ac1_a_tentative_hold_overlapping_the_window_excludes_the_venue` |
| TC-DT-1c | An unavailability period overlapping the window excludes the venue | pytest | `test_ac1_an_unavailability_period_overlapping_the_window_excludes_the_venue` |
| TC-DT-1d | Setup time: a booking ending 08:45 leaves too little of a 30-minute setup → excluded; ending 08:30 → listed (**boundary**) | pytest | `test_ac1_setup_time_before_the_event_is_counted` |
| TC-DT-1e | Turnaround time: a booking ending 08:30 leaves too little of a 60-minute reset → excluded; ending 08:00 → listed (**boundary**) | pytest | `test_ac1_turnaround_time_after_an_earlier_booking_is_counted` |
| TC-DT-1f | A booking after the window needs turnaround + setup after 17:00: starting 18:29 → excluded, 18:30 → listed (**boundary**) | pytest | `test_ac1_a_later_booking_needs_turnaround_and_setup_after_the_window` |
| TC-DT-1g | Setup and turnaround count against unavailability, before and after the window (4 cases) | pytest | `test_ac1_setup_and_turnaround_count_against_unavailability_too` |
| TC-DT-1h | An approved booking or hold whose published times do not touch the window still excludes the venue once padding is counted | pytest | `test_ac1_a_booking_that_only_clashes_because_of_setup_and_turnaround_excludes_the_venue` |
| TC-DT-1i | Each venue is padded by its own setup and turnaround, not another venue's | pytest | `test_ac1_each_venue_is_padded_by_its_own_setup_and_turnaround` |
| TC-DT-1j | A window given in Singapore time is compared as the same moment in UTC | pytest | `test_ac1_a_window_given_in_singapore_time_is_compared_correctly` |
| TC-DT-1k | On PostgreSQL: a real submitted request holds the venue, an approved booking excluded only by padding, a closure inside setup; all persist and are excluded, and an SGT window gives the same result | Postgres | `test_ac1_ac2_holds_bookings_closures_and_padding_on_postgres` |
| TC-DT-1l | The page sends the date, start and end time as one UTC window | Vitest | *DT AC1 › searches for venues free on that date between the start and end time* |
| TC-DT-1m | The page says bookings, holds, closures and setup/turnaround count | Vitest | *DT AC1 › says that bookings, tentative holds, closures…* |
| TC-DT-1n | The applied window shows on its chip | Vitest | *DT AC1 › shows the window on its chip once the panel is closed* |
| TC-DT-1o | Venue details show setup and turnaround ("1 h 30 min before each event", "None") | Vitest | *VenueView › DT: shows the setup and turnaround time…* · *DT: says "None"…* |
| TC-DT-1p | In a browser: of seven seeded venues, the booked, held, padded and closed ones are gone for 09:00–17:00; the next day all are back | Playwright | *DT AC1 + AC2* |
| TC-DT-1q | In a browser: the padded venue is listed from 09:30 and not at 09:29 | Playwright | *DT AC1: a window that clears the padding…* |

### AC2 — rejected, cancelled and expired bookings do not exclude a venue

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-2a | A venue whose only overlapping booking is rejected / cancelled / hold expired is still shown, even with setup and turnaround set | pytest | `test_ac2_a_venue_whose_only_overlapping_booking_holds_nothing_is_still_shown` |
| TC-DT-2b | "Only" matters: a rejected and an expired booking do not cancel out an approved one | pytest | `test_ac2_one_live_booking_still_excludes_a_venue_that_also_has_dead_ones` |
| TC-DT-2c | An expired hold lets the event ask for a venue again | pytest | `test_ac2_an_expired_hold_frees_the_venue_for_a_new_request` |
| TC-DT-2d | The old search suite: rejected / cancelled / hold expired never block | pytest | `test_venue_search.py::test_ac3_a_booking_that_holds_nothing_does_not_block` |
| TC-DT-2e | On PostgreSQL: `hold_expired` round-trips through the enum and the venue is listed | Postgres | `test_ac1_ac2_holds_bookings_closures_and_padding_on_postgres` |
| TC-DT-2f | In a browser: the rejected and the expired venue are listed | Playwright | *DT AC1 + AC2* |

### AC3 — an end time earlier than the start time blocks the search and flags the fields

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-3a | The API refuses an end before or equal to the start with 422, naming `end` | pytest | `test_ac3_an_end_earlier_than_the_start_is_refused_and_the_end_is_flagged` |
| TC-DT-3b | The same on PostgreSQL | Postgres | `test_ac3_an_end_before_the_start_is_refused_on_postgres` |
| TC-DT-3c | The page sends nothing, shows *"Search paused."* instead of results, and flags Start time and End time (not Date) | Vitest | *DT AC3 › blocks the search and flags both time fields* |
| TC-DT-3d | It stays blocked while other filters change; the chip reads *"Date & time: invalid"* | Vitest | *DT AC3 › stays blocked while other filters change* |
| TC-DT-3e | An end time equal to the start time is blocked the same way | Vitest | *DT AC3 › treats an end time equal to the start time the same way* |
| TC-DT-3f | Fixing the end time resumes the search and clears the flags | Vitest | *DT AC3 › resumes the search, and clears the flags…* |
| TC-DT-3g | In a browser: blocked, flagged, then resumed once fixed | Playwright | *DT AC3* |

### AC4 — combined with other filters, only venues meeting all are shown

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-4a | One venue meets every filter; seven others each fail exactly one (held, padded, too small, wrong layout, missing facility, missing accessibility, wrong location) — only the first is listed | pytest | `test_ac4_the_date_filter_combines_with_every_other_filter` |
| TC-DT-4b | Without a date, bookings do not affect the other filters | pytest | `test_ac4_without_a_date_the_same_filters_ignore_bookings` |
| TC-DT-4c | The page sends the date and time with keyword, attendance, layout, facilities and accessibility in one search | Vitest | *DT AC4 › sends the date and time together with every other filter* |
| TC-DT-4d | The page lists exactly what the combined search returns | Vitest | *DT AC4 › shows only the venues the server returns…* |
| TC-DT-4e | In a browser: date and time plus attendance 250 leave only the venue that is both free and large enough | Playwright | *DT AC4* |

### Additional cases beyond the acceptance criteria (DoD 3)

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-DT-N1 | Organiser, Attendee and Tech Support cannot search by date (403); Venue Staff can; anonymous is 401 | pytest | `test_roles_outside_venue_planning_cannot_search_by_date` · `test_venue_staff_can_search_by_date` · `test_an_anonymous_caller_cannot_search_by_date` |
| TC-DT-N2 | In a browser: an Organiser opening `/venues` gets the Forbidden page | Playwright | *DT negative* |
| TC-DT-N3 | An unfinished window asks for what is missing, flags only that field and is not searched with | Vitest | *DT - an unfinished date and time › asks for what is missing…* |
| TC-DT-N4 | An unfinished window is flagged on its chip | Vitest | *… › flags an unfinished window on its chip* |
| TC-DT-N5 | Removing the filter empties all three fields and lifts the block | Vitest | *… › removing the filter empties all three fields* |
| TC-DT-N6 | Approval refuses a booking inside the venue's turnaround (409, stays pending) | pytest | `test_approval_refuses_a_booking_inside_the_venues_turnaround` |
| TC-DT-N7 | Approval allows a booking exactly one turnaround later (**boundary**) | pytest | `test_approval_allows_a_booking_exactly_one_turnaround_later` |
| TC-DT-N8 | Another tentative hold on the same slot does not block approval; once one is confirmed the other is refused | pytest | `test_approval_is_not_blocked_by_another_tentative_hold_on_the_same_slot` |
| TC-DT-N9 | Schema: setup and turnaround default to 0 and a negative value is refused by the database | Postgres | `test_setup_and_turnaround_columns_default_to_zero_and_refuse_negatives` |
| TC-DT-N10 | **Concurrency:** requests whose times only clash through turnaround, approved all at once, confirm exactly one; the search then offers neither slot, and offers the venue again one turnaround later | Postgres | `test_requests_that_only_clash_through_turnaround_are_never_both_confirmed` |
| TC-DT-N11 | **Accessibility:** no serious or critical axe violations with the fields flagged; Date → Start time → End time reachable with Tab | Playwright | *DT accessibility* |

Not applicable: an audit trail (the search changes no state) and idempotency
(a search is a read).

---

## Manual test — TC-DT-M1

**Preconditions:** backend and frontend running; `backend/sql/010`–`016`
applied (12 venues; Harbourfront Seminar Room 2 has an approved booking on
8 Oct 2026, 16:46–19:46 Singapore time, with 30 min setup and 60 min
turnaround; Raffles Place Training Studio is closed for maintenance over the
same time). An Event Coordinator with an approved event, a Venue Staff
member and an Organiser can sign in. Browser in Singapore time.

| # | As | Step | Expected result |
|---|---|---|---|
| 1 | Coordinator | Open **Venues**, then the **Date & time** filter | Three fields: **Date**, **Start time**, **End time**; the hint mentions bookings, tentative holds, closures and setup and turnaround time |
| 2 | Coordinator | Date 8 Oct 2026, 16:00 – 20:00 | 10 venues; Harbourfront (booked) and Raffles Place (closed) are gone (AC1) |
| 3 | Coordinator | Change to 21:00 – 23:00 | 11 venues: Raffles Place is back; Harbourfront is still gone, because it needs 60 min reset plus 30 min setup after 19:46 (AC1, setup and turnaround) |
| 4 | Coordinator | Change to 21:30 – 23:00 | All 12 venues |
| 5 | Coordinator | Open Harbourfront Seminar Room 2 | *Setup time: 30 min before each event*, *Turnaround time: 1 h after each event* |
| 6 | Coordinator | On your approved event's page, submit a booking request for *Orchard Gallery Loft*; then search your event's date and times | *Orchard Gallery Loft* is gone: the pending request is a tentative hold (AC1) |
| 7 | Venue Staff | **Reject** that request with a reason | — |
| 8 | Coordinator | Search the same date and times again | *Orchard Gallery Loft* is back (AC2) |
| 9 | Coordinator | Set Start time 17:00, End time 09:00 | *"The end time must be after the start time."*; Start time and End time outlined red; the list is replaced by *"Search paused."*; the chip reads *Date & time: invalid* (AC3) |
| 10 | Coordinator | Type a keyword while it is paused | Still paused, nothing reloads (AC3) |
| 11 | Coordinator | Set End time 18:00 | The flags clear and results return |
| 12 | Coordinator | 8 Oct 2026 16:00 – 20:00 with **Expected attendance** 60 | Only venues that are free **and** hold 60 or more (AC4) |
| 13 | Coordinator | Add the keyword `harbour` | *"No venues match your search."*: the only Harbourfront room is booked (AC4) |
| 14 | Organiser | Go to `/venues` | The Forbidden page |
| 15 | Coordinator | Steps 1–2 using only the keyboard | Every field is reachable, labelled and visibly focused |
| 16 | Coordinator | ~400px wide, then dark mode | The fields stay readable; nothing scrolls sideways |

*Hold Expired* has no screen yet: it is set by the Tentative Venue Holding
story. To see it here, set a booking's `status` to `hold_expired` in SQL and
repeat step 8.

**Tester:** ______________ **Date:** ____________ **Result:** Pass / Fail

## Not covered (separate stories)

When and how a tentative hold expires; Venue Staff editing a venue's setup
and turnaround time (VENUE_MANAGE); refusing a *new* request for a slot
another Coordinator already holds; events that run past midnight.
