# Test Cases — Equipment on an Event Request

Covers the equipment half of the Event Request Creation core feature:

- **As an Event Organiser, I want to pick the equipment I need from
  ConnectSphere's catalogue and say how many of each, so that my request says
  exactly what I need instead of a sentence somebody has to interpret.**

Every criterion below maps to at least one test case, and every automated test
is named after what it proves. Same format as
[test-cases-organiser-event-requests.md](test-cases-organiser-event-requests.md).

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_event_equipment.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| All of the above | push to any branch | GitHub Actions runs them |

**24 pytest · 16 Vitest · 1 manual.**

## What replaced what

`events.equipment_requirements` was one mandatory free-text box. It is now an
**optional note** ("Other equipment notes"), and the real content lives in
**`equipment_requests`** — one row per catalogue item, with a quantity.

That table already existed and had never been written to. Nothing new was
created for this; the only schema change is a unique constraint.

| | Before | After |
|---|---|---|
| Storage | `events.equipment_requirements` text | `equipment_requests` rows + optional note |
| Countable | no | yes |
| Linked to the catalogue | no | FK, `ON DELETE RESTRICT` |
| Readable by availability logic | no | yes |
| Mandatory at submit | yes | no — plenty of events need no equipment |

### Why lines are created as `requested`, not `reserved`

`GET /equipment` computes `available_quantity` by subtracting only units on
**`reserved`** lines. New Organiser lines are `requested`, so **asking for
equipment never reduces the stock other events are offered**. Granting it is
Technical Support's job (W1 p7, W4 p4). `test_equipment_lines_do_not_reduce_catalogue_availability`
pins this end to end.

---

## AC1 — the Organiser can state exactly what they need

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-E-1a | An empty request says so rather than showing a blank row | Vitest | `EquipmentPicker.test.tsx` › *starts empty and says so…* |
| TC-E-1b | Adding a row offers the catalogue | Vitest | *adding a row offers the whole catalogue* |
| TC-E-1c | Typing narrows the list | Vitest | *typing narrows the list to matching items* |
| TC-E-1d | Choosing an item shows it in the row | Vitest | *choosing an item shows it in the row* |
| TC-E-1e | Quantity defaults to 1 and can be changed | Vitest | *quantity defaults to one and can be changed* |
| TC-E-1f | Items and quantities reach the API | pytest | `test_a_draft_can_be_created_with_equipment_lines` |
| TC-E-1g | A line carries the catalogue name and type back | pytest | `test_lines_carry_the_catalogue_name_and_type` |
| TC-E-1h | Search matches equipment type as well as name | Vitest | *can be searched by equipment type as well as by name* |
| TC-E-1i | The picker works from the keyboard alone | Vitest | *can be driven entirely from the keyboard* · *Escape closes the list…* |

## AC2 — one row per item

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-E-2a | An item already picked is not offered on another row | Vitest | *an item already picked is not offered on another row* |
| TC-E-2b | A row still offers its own current choice | Vitest | *a row still offers its own current choice…* |
| TC-E-2c | The same item twice is rejected by the API | pytest | `test_the_same_item_twice_is_rejected` |

> **Why block it at all?** Quantity is how you ask for more of one thing, so
> two rows naming the same item is always a mistake. It would also have to be
> summed everywhere availability is calculated — a silent trap for whoever
> writes the reservation story. Enforced three deep: the dropdown, a 422, and
> a `unique (event_id, equipment_id)` constraint.

## AC3 — a draft stays saveable

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-E-3a | No control is marked `required` | Vitest | `EquipmentPicker.test.tsx` › *no control is marked required* |
| TC-E-3b | A row with nothing picked yet is allowed to exist | Vitest | *a row with nothing picked yet is allowed to exist* |
| TC-E-3c | Lines survive saving and reopening | pytest | `test_equipment_lines_survive_a_reopen` |
| TC-E-3d | Submitting is not blocked by having no equipment | pytest | `test_submitting_is_not_blocked_by_having_no_equipment` |
| TC-E-3e | An emptied quantity can be retyped, not snapped back | Vitest | *an emptied quantity box can be retyped…* |
| TC-E-3f | A quantity left empty becomes 1 on blur | Vitest | *a quantity left empty becomes one when the field is left* |

> **TC-E-3a is the one to keep.** A `required` attribute on the quantity box
> would let the browser block submission before any handler ran, silently
> breaking the whole draft story. The same guard exists on the main form
> (`EventForm.test.tsx` TC-S1-2f).

## AC4 — editing a draft's equipment

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-E-4a | PATCH replaces the lines | pytest | `test_patching_equipment_lines_replaces_them` |
| TC-E-4b | PATCH omitting equipment leaves it alone | pytest | `test_patch_omitting_equipment_does_not_clear_it` |
| TC-E-4c | PATCH with `[]` clears the lines | pytest | `test_patching_an_empty_list_clears_the_lines` |
| TC-E-4d | Removing a row drops it | Vitest | `EquipmentPicker.test.tsx` › *removing a row drops it* |

TC-E-4b matters: it keeps equipment consistent with every other field under
`exclude_unset` — omitted means "leave alone", never "clear".

## Boundary, failure and permission cases

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-E-5a | An unknown `equipment_id` is a 422, not a 500 | pytest | `test_an_unknown_equipment_id_is_rejected_cleanly` |
| TC-E-5b | A retired item cannot be requested | pytest | `test_a_retired_item_cannot_be_requested` |
| TC-E-5c | A **damaged** item still can be | pytest | `test_a_damaged_item_can_still_be_requested` |
| TC-E-5d | Quantity 0 is rejected | pytest | `test_a_quantity_of_zero_is_rejected_cleanly` |
| TC-E-5e | Asking for more than exists is **accepted** | pytest | `test_asking_for_more_than_exists_is_accepted` |
| TC-E-5f | Another Organiser's draft returns 404 | pytest | `test_another_organiser_cannot_add_equipment_to_someone_elses_draft` |
| TC-E-5g | Equipment cannot change after submitting | pytest | `test_equipment_cannot_be_changed_after_submitting` |
| TC-E-5h | The catalogue failing to load does not block the request | Vitest | *says so without blocking the rest of the request* |

**TC-E-5b vs TC-E-5c is a deliberate pair.** Retired means permanently
withdrawn, so a request for one could never be fulfilled — refused up front.
Damaged and under-maintenance items stay requestable: repairs finish, the
event may be months away, and judging whether the kit can actually be
provided on the day is Technical Support's call, not the form's.

**TC-E-5e is deliberate too.** W1 p7 and W4 p4 both make sufficiency Technical
Support's decision, and stock can change between request and event. Blocking
would also mean telling an external client exactly how much kit ConnectSphere
owns.

## The picker's data source — `GET /equipment/options`

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-E-6a | Lists pickable items | pytest | `test_options_lists_items_for_the_picker` |
| TC-E-6b | Omits retired items | pytest | `test_options_omits_retired_items` |
| TC-E-6c | **Returns exactly `{id, name, category}`** | pytest | `test_options_exposes_only_what_the_picker_needs` |
| TC-E-6d | Can be searched | pytest | `test_options_can_be_searched` |
| TC-E-6e | An attendee gets 403 | pytest | `test_an_attendee_cannot_read_the_picker_options` |

**TC-E-6c is the reason this endpoint exists separately from `GET /equipment`.**
An Event Organiser is an *external* client. The catalogue response carries
storage locations, operational condition and live stock levels; a picker that
merely declines to *render* those would still have *received* them. The narrow
response is the actual boundary, and this test is what stops someone
"simplifying" the picker onto the catalogue endpoint later.

Gated on **`EVENT_WRITE`**, not `EQUIPMENT_READ` — the justification is "you
are filling in an event request", not "you may browse our inventory".

---

## Note for the Week 13 Q&A

The briefing assigns structured equipment entry to the **Coordinator**:

> W4 p4 (core): "**Event Coordinators** can record equipment required for an
> event, including the equipment type, quantity, and relevant technical
> requirements."
>
> W1 p2: "the Event Organiser … may request a hybrid event **without
> explaining what video-conferencing facilities are required**."

Giving the picker to the Organiser is a deliberate product decision, not an
oversight: structured data at the point of entry beats parsing prose later,
and the Coordinator still sees and works from the same rows. The mitigation
for the Organiser being external is `/equipment/options` — see TC-E-6c.

---

## Manual test — TC-E-7a

**Preconditions:** backend and frontend running, signed in as an Organiser,
`backend/sql/006_seed_equipment.sql` applied.

| # | Step | Expected result |
|---|---|---|
| 1 | New request → Requirements section | "Equipment requirements" is a group with an **Add equipment** button; "Other equipment notes" sits below it |
| 2 | Add equipment → type `mic` | The list narrows to the microphones as you type |
| 3 | Pick one, set quantity 6 | The row shows the full item name and 6 |
| 4 | Add equipment → open the dropdown | The item from step 3 is **not** offered again |
| 5 | Pick a projector, quantity 2 | Two rows |
| 6 | Check any option | No location, condition or stock count is shown; the retired Panasonic PT-VW360 never appears |
| 7 | Save as draft → reopen | Both rows repopulate with their quantities |
| 8 | Remove a row → save → reopen | One row |
| 9 | Ask for 99 of something → Submit | Accepted without complaint |
| 10 | Open the submitted request | Equipment shows as a list with quantities, not a sentence |
| 11 | Sign in as the Coordinator, open the assigned event | The same list appears |
| 12 | Narrow the window to ~400px | Rows stack; the Remove action wraps below rather than crushing the picker |
| 13 | Tab to the picker, use ↑ ↓ and Enter | An item can be chosen without a mouse |
| 14 | Toggle dark mode | The dropdown panel and highlighted option stay readable |

**Tester:** ______________ **Date:** ____________ **Result:** Pass / Fail

Steps 12–14 are what automation cannot judge: the dropdown is absolutely
positioned over the form, so it is the one piece of this feature most likely
to look wrong at a size or in a theme no test renders.
