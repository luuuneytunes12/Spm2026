# Test Cases — Technical Support Equipment Catalogue

Covers one product backlog item:

- **Story 4 — View Equipment Catalogue.** *As a Technical Support Staff
  member, I want to view the equipment catalogue, so that I can see what
  equipment exists and in what quantity when assessing an event's
  requirements.*

Every acceptance criterion below maps to at least one test case, and every
automated test is named after the criterion it proves, so a criterion can be
traced to the code that verifies it. This mirrors
[test-cases-organiser-event-requests.md](test-cases-organiser-event-requests.md)
and [test-cases-coordinator-assigned-events.md](test-cases-coordinator-assigned-events.md).

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_equipment.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| All of the above | push to any branch | GitHub Actions runs them |

**16 pytest · 12 Vitest · 1 manual.**

There is no Playwright layer for this story. The end-to-end job applies
`backend/db/schema.sql` only and never runs `backend/sql/006_seed_equipment.sql`,
so the catalogue is empty on a CI database. All three criteria are fully
covered without it; adding a seed step to the workflow is a separate change.

## Two different facts, both named by AC2

AC2 asks for **availability** *and* **operational status**. They are not the
same thing, and the database keeps them apart on purpose:

| | What it is | Where it lives |
|---|---|---|
| `operational_status` | The **condition** of the item — `available`, `maintenance`, `damaged`, `retired` | Stored column on `equipment` |
| `available_quantity` | How many units are **free to reserve right now** | Computed per request; never stored |

```
available_quantity = total_quantity − Σ(quantity_requested where status = 'reserved')
```

With one override: **an item that is not operational reports 0**, whatever
the arithmetic says. Two damaged mixers are not two available mixers. The
Week 1 briefing is explicit that equipment recorded as unavailable must not
be treated as freely available.

Note that `equipment.operational_status` and `equipment_requests.status` are
deliberately **separate enums**. One describes a physical item, the other the
lifecycle of a request. Reusing one for both would conflate "this request is
reserved" with "this projector works".

> Until the equipment-reservation story lands, `equipment_requests` is empty,
> so every operational item shows its full stock as available. That is
> correct, not a defect — worth saying aloud during the demo.

---

## AC1 — every item held is visible

> *I can open the equipment catalogue and see every equipment item held by
> ConnectSphere.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S4-1a | Every row in the table comes back | pytest | `test_equipment.py` › *test_catalogue_returns_every_item_held* |
| TC-S4-1b | Damaged, under-maintenance and retired items are **still listed** | pytest | `test_equipment.py` › *test_catalogue_still_lists_items_that_cannot_be_used* |
| TC-S4-1c | One row renders per item returned, unusable ones included | Vitest | `EquipmentCatalogue.test.tsx` › *renders one row per item…* / *shows items that cannot be used…* |
| TC-S4-1d | An empty catalogue says so rather than rendering a blank page | Vitest | `EquipmentCatalogue.test.tsx` › *says the catalogue is empty…* |
| — | Nothing recorded yet is an empty list, not a 404 | pytest | `test_equipment.py` › *test_empty_catalogue_returns_an_empty_list_not_an_error* |

> **TC-S4-1b is the one to keep.** "See every item held" is not "see every
> usable item" — a retired projector is still held by ConnectSphere, and it
> is exactly the kind of thing Technical Support needs to know about when
> assessing an event. A future change that "helpfully" hid non-operational
> items would break AC1, and this test is what catches it.

## AC2 — each item shows six things

> *Each item shows its equipment type, description, total quantity, location,
> availability and operational status.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S4-2a | All six fields are present in the response | pytest | `test_equipment.py` › *test_each_item_shows_every_field_named_in_the_criterion* |
| TC-S4-2b | Availability is total minus reserved | pytest | `test_equipment.py` › *test_availability_subtracts_reserved_units* |
| TC-S4-2c | A non-operational item reports 0 available | pytest | `test_equipment.py` › *test_a_non_operational_item_reports_nothing_available* |
| TC-S4-2d | Only `reserved` counts — `requested`/`reviewing`/`rejected`/`cancelled` do not | pytest | `test_equipment.py` › *test_only_reserved_requests_reduce_availability* |
| TC-S4-2e | All six are on screen per row | Vitest | `EquipmentCatalogue.test.tsx` › *type, description, total quantity, location, availability and status* |
| TC-S4-2f | A null description, location or type reads as such, not as a blank | Vitest | `EquipmentCatalogue.test.tsx` › *a missing description or location reads as such…* |
| TC-S4-2g | Status renders as "Under maintenance", not `maintenance` | Vitest | `EquipmentCatalogue.test.tsx` › *renders the status as a label…* |
| — | Over-reservation reports 0, never a negative count | pytest | `test_equipment.py` › *test_over_reservation_reports_none_left_rather_than_a_negative* |

Availability and total quantity are always shown **together** ("14 of 16
available"). A bare "0 available" reads as though the item does not exist.

## AC3 — search or filter by type

> *I can search or filter the catalogue by equipment type.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S4-3a | `?type=` returns only that type | pytest | `test_equipment.py` › *test_filtering_by_type_returns_only_that_type* |
| TC-S4-3b | `?q=` matches name and description, case-insensitively | pytest | `test_equipment.py` › *test_search_matches_name_and_description_case_insensitively* |
| TC-S4-3c | Type and search combine with AND, not OR | pytest | `test_equipment.py` › *test_type_and_search_combine* |
| TC-S4-3d | An unknown type returns an empty list, not a 404 | pytest | `test_equipment.py` › *test_an_unknown_type_returns_an_empty_list* |
| TC-S4-3e | The dropdown lists **every** type while a filter is active | pytest + Vitest | *test_the_type_list_covers_the_whole_catalogue_even_while_filtered* / *the type dropdown still lists every type…* |
| TC-S4-3f | Choosing a type asks the API for it | Vitest | `EquipmentCatalogue.test.tsx` › *choosing a type asks the API for that type* |
| TC-S4-3g | Typing in search asks the API for that text | Vitest | `EquipmentCatalogue.test.tsx` › *typing in the search box asks the API…* |
| TC-S4-3h | No matches reads differently from an empty catalogue, and can be undone | Vitest | `EquipmentCatalogue.test.tsx` › *no matches reads differently…* |
| — | Typing is debounced into one request, not one per keystroke | Vitest | `EquipmentCatalogue.test.tsx` › *debounces typing into a single request…* |

> **TC-S4-3e is the subtle one.** `GET /equipment` returns `types` alongside
> `items`, and that list is deliberately *not* narrowed by the active filter.
> A dropdown built from the filtered `items` would collapse to the one type
> already selected, leaving no way to choose another or clear the filter.

## Beyond the acceptance criteria — who may read the catalogue

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-S4-4a | An attendee gets 403 | pytest | `test_equipment.py` › *test_an_attendee_cannot_read_the_catalogue* |
| TC-S4-4b | An anonymous caller gets 401, not 403 | pytest | `test_equipment.py` › *test_an_anonymous_caller_cannot_read_the_catalogue* |
| TC-S4-4c | **A Coordinator can read it** | pytest | `test_equipment.py` › *test_a_coordinator_can_read_the_catalogue* |

TC-S4-4c is not redundant. `GET /equipment` is gated on the
`EQUIPMENT_READ` **permission**, not on the `tech_support` **role** —
Coordinators hold that permission too, because they have to know what exists
before requesting it. This test is what stops someone "tightening" the
endpoint to a single role and silently breaking the Coordinator's
equipment-request story later.

---

## Manual test — TC-S4-5a

The one case automation should not claim to cover. Assertions check that a
field is *present and labelled*; whether the page is *readable* is a
judgement a person has to make.

**Preconditions:** backend and frontend running, signed in as a user with
the `tech_support` role, `backend/sql/006_seed_equipment.sql` applied.

| # | Step | Expected result |
|---|---|---|
| 1 | Open the sidebar | **Equipment Catalogue** appears as a link; **Manage equipment** is still listed under *Planned* |
| 2 | Click it | The catalogue opens at `/equipment` with 19 items |
| 3 | Scan one row | Name, type, location, description, status badge and "x of y available" are all legible without squinting |
| 4 | Find the Behringer X32 | Its badge reads **Damaged** and its stock reads **None of 2 available** |
| 5 | Choose **Audio** from the type dropdown | Only audio items remain; the dropdown still offers the other six types |
| 6 | Type `mic` in the search box | The list narrows as you pause typing, not on every keystroke |
| 7 | Choose a type with no matches | "No equipment matches this filter." with a working **Clear filters** action |
| 8 | Toggle dark mode | Text, badges and the muted description stay readable; available and non-available badges remain distinguishable |
| 9 | Narrow the window to ~400px | Rows stack rather than overflowing; nothing scrolls sideways |

**Tester:** ______________ **Date:** ____________ **Result:** Pass / Fail

Step 8 matters more than it looks: the available/non-available distinction is
carried by badge colour, and a palette that reads fine in light mode can
flatten the two into the same grey in dark mode.
