# Test Cases — Update Equipment Requirement Status

Covers one product backlog item:

- **Update Equipment Requirement Status.** *As a Technical Support Staff member,
  I want to update the status of an event's equipment requirements, so that the
  Event Coordinator can track progress.*

It builds on [Record Equipment Requirements for
Event](test-cases-equipment-requirements.md) (the Coordinator's requirements)
and **reuses** the Equipment Reservations feature ([Scrum 45/46](../backend/tests/test_equipment_reservations.py))
without changing it. Same format as the other test-case documents.

## Acceptance criteria

| # | Criterion |
|---|---|
| **UR AC1** | I can update the **status** of each requirement (e.g. "reserved", "unavailable") so the Event Coordinator can track progress |
| **UR AC2** | I can update the **quantity** of the equipment as changes appear |
| **UR AC3** | The updated status and quantity are **visible to the Event Coordinator** on the event record |

Suggested wording for Jira, so the criteria say what is built:

- **AC1:** *"…update the status of each requirement. **Reserved** is set by
  reserving real equipment for it (through Equipment Reservations); I can also
  mark it **Reviewing** or **Unavailable**."* A requirement is never *marked*
  reserved by hand.
- **AC2:** *"…update the **quantity needed**, not below what is already
  reserved."*

### What the documents require, and what is inferred

| | Source |
|---|---|
| **Explicit** | W4 p4, *Equipment Request Management*: the Coordinator records type, quantity and technical requirements; *"Technical Support Staff can review the requested equipment and **update the request as arrangements are made**."* |
| **Explicit** | W4 p4, *Availability Checking* and *Reservation*: Technical Support determines whether equipment is available for the event's date and time; a reservation **reduces what overlapping events can have** and **stays associated with its event**. |
| **Explicit** | W1 p11: a notification when *"requested equipment is confirmed or found to be **unavailable**"* — the customer's word for the outcome. |
| **Explicit** | W1 steps 8–9: Technical Support *"determine whether suitable resources can be provided and reserved"* and *"update the relevant preparation information as work progresses"*. |
| **Inferred** | That a requirement's **reserved** status is *derived* from reservations, and that "unavailable" is stored as the existing `rejected`. No document names these statuses; the words "reserved" and "unavailable" are the story's own. |
| **Inferred** | That a reservation made for a requirement is **linked** to it, that reserving more than is needed is refused, and what the Coordinator may still change once equipment is reserved. No document speaks to any of this. |
| **Not in any document** | Releasing or cancelling a reservation, partial reservation, notifications for this story. See *Existing limitations*. |

## How to run

```bash
cd backend  && uv run pytest tests/test_requirement_reservation_atomicity.py \
                             tests/test_equipment_fulfillment_service.py \
                             tests/test_equipment_requirement_fulfillment.py
cd frontend && npx vitest run src/lib/equipmentRequirements.test.ts \
                              src/components/EquipmentRequirementItem.test.tsx \
                              src/components/RequirementStatusEditor.test.tsx \
                              src/components/RequirementReservePanel.test.tsx \
                              src/pages/equipment/EquipmentRequirementsRecord.test.tsx \
                              src/components/EquipmentRequirementsSection.test.tsx
```

**147 pytest · 77 Vitest added (and the Story A card/record tests extended) · 1 manual script.**
No Playwright. Ercong's reservation tests
(`test_equipment_reservations.py`) run **unchanged** as the regression guard.

## Design decisions the tests pin

### Reuse, not rebuild — Ercong's reservation is untouched

Technical Support reserves **through** his `reserve_equipment`, called as it is.
That function does the stock check, the overlap check, the event-status check
and the write. Nothing in this story reimplements any of them.

| His (unchanged) | Ours (added) |
|---|---|
| availability = total − reserved for overlapping events; 0 if not operational | which **requirement** a reservation is for (a link) |
| refusing an item reserved elsewhere or short of stock, in his own words | refusing a reservation that would **over-fill the requirement** |
| the reservation itself — an `equipment_requests` row moved to `reserved` | the requirement's **progress** and **status**, read from those rows |
| his page, API, schema, availability service, tests | a contextual way in from the requirement |

`test_ur_ac1_his_own_endpoints_see_the_reservation` and
`…the_reservation_reduces_what_an_overlapping_event_can_have` show one
reservation, visible and counted by his own endpoints. `…his_stock_check_is_what_refuses_an_unavailable_quantity`
and `…stock_held_by_an_overlapping_event_is_not_reserved_again` show his rules
refusing, with **his** messages passed through. `test_his_function_is_called_unchanged`
pins the signature this depends on, so a change on his side fails loudly here.

### The link, and why it commits with the reservation

`coordinator_requirement_reservations` (migration `016`) holds
`(requirement, event, item)`. It is keyed by **(event, item)**, not by the
reservation row's id:

- the row's id does not exist until his function creates it, so a link to it
  could only be written **after** his commit — leaving a window with a
  reservation and no link;
- an approved Organiser change deletes and rebuilds those rows, which would
  take a row-keyed link with them.

Keyed by (event, item), the link is added to the session **before** his
function runs, and his own `db.commit()` writes both in one transaction.

| Claim | Tested by |
|---|---|
| One commit writes the link and the reservation | `test_the_link_and_the_reservation_are_committed_together` |
| A reservation he refuses leaves no link behind | `test_a_reservation_he_refuses_leaves_no_link_behind` · `…a_refusal_from_the_gateway_leaves_nothing_linked` |
| A link that cannot be written stops the reservation too | `test_a_link_that_cannot_be_written_stops_the_reservation_too` |

These three were written and passed **before** anything was built on the
design; the alternative (two commits) would have allowed a reservation with no
link.

### Needed and reserved are two numbers

| Rule | Tested by |
|---|---|
| `quantity_needed` is the Coordinator's and is **never written by a reservation**: 5 needed / 3 reserved is a normal state | `…reserving_never_changes_the_quantity_needed` · `…part_of_a_requirement_can_be_reserved_and_shows_its_progress` |
| Reserved is **read from the reserved rows** the links point at — never stored | `…a_link_with_no_reserved_row_behind_it_counts_for_nothing` · `…reserving_after_the_organiser_replaced_their_lines_works_again` |
| The quantity needed **cannot go below what is reserved** (Technical Support or Coordinator); equal is allowed | `…the_quantity_needed_cannot_go_below_what_is_reserved` · `…can_drop_to_exactly_what_is_reserved` · `…the_coordinator_cannot_drop_the_quantity_below_what_is_reserved` |
| Raising it above what is reserved reopens the requirement | `…raising_the_quantity_reopens_a_fully_reserved_requirement` |
| A quantity left out reserves **what is still needed** | `…a_quantity_left_out_reserves_what_is_still_needed` |
| A reservation that would **over-fill** the requirement is refused, before anything is written — including when his rule forces the Organiser's whole quantity | `…a_reservation_that_would_over_fill_the_requirement_is_refused` · `…more_than_is_still_needed_is_refused` · `…a_quantity_the_organisers_line_would_force_over_the_remainder_is_refused` |
| An item the Organiser asked for is reserved at **their** quantity (his rule, kept) | `…an_item_the_organiser_asked_for_is_reserved_at_their_quantity` |

There is no way to give a reservation back, so over-filling cannot be undone.
That is the reason for refusing it, and for the protections below.

### Status: reserved is worked out, Unavailable is `rejected`

| Reserved vs needed | Status everyone sees |
|---|---|
| all of it | **Reserved** (worked out — never stored, never selectable) |
| some of it | **Reviewing**, with "3 of 5 reserved" |
| none | what Technical Support set: **Requested**, **Reviewing** or **Unavailable** |

- **Unavailable** is the stored `rejected`. The status enum is shared with the
  Organiser's equipment requests, so no value is added for one feature; it is
  *shown* as Unavailable (W1 p11's word).
- Technical Support can set only **Requested / Reviewing / Unavailable**.
  `reserved` is refused with a reason; `cancelled` belongs to the event.
- **Unavailable** cannot be set while anything is reserved, and reserving
  against an Unavailable requirement moves it to Reviewing.

Tested by `…reserved_and_cancelled_cannot_be_set_by_hand` ·
`…unavailable_is_the_stored_rejected_value` · `…unavailable_cannot_be_set_once_something_is_reserved` ·
`…reserving_clears_an_unavailable_outcome` · `…a_status_set_by_hand_does_not_hide_what_is_reserved` ·
`test_the_effective_status_follows_the_reservations` (nine cases) ·
`test_reserved_is_never_taken_from_what_was_stored`; on screen, *shows rejected as Unavailable*.

### What the Coordinator may still do once equipment is reserved

| Rule | Why | Tested by |
|---|---|---|
| **Cannot be removed** | nothing releases a reservation; removal would leave stock held for no need | `…a_requirement_with_a_reservation_cannot_be_deleted` |
| **Type cannot change** (the same type sent again is not a change) | it was reserved *as* that type | `…the_type_of_a_requirement_with_a_reservation_cannot_change` · `…the_same_type_sent_again_is_not_a_change` |
| **Notes can change** | no effect on what is held | `…notes_can_change_once_something_is_reserved` |
| Removal and retyping work again once **no reservation is held** (e.g. wiped by an Organiser change) | "reserved" means reserved *now* | `…a_requirement_whose_reservation_was_lost_can_be_deleted` |

This replaces Story A's *"no post-reservation rules"*. The card does not offer
Remove, and locks the type, where the server would refuse.

### Other rules

| Rule | Tested by |
|---|---|
| The Coordinator picks a **type**; Technical Support picks the **item**, which must be of that type | `…an_item_of_another_type_is_refused` · on screen, *offers only equipment of the requirement’s type* |
| One item **cannot fulfil two requirements** of one event (his rows are unique per event and item) | `…the_same_item_cannot_fulfil_two_requirements_of_one_event` · `…an_item_reserved_for_another_requirement_cannot_be_claimed` |
| A **stale link** (its reservation wiped) is taken over, not a dead end | `…a_stale_link_to_another_requirement_is_taken_over` |
| Only **Technical Support** reserves or updates; the Organiser never receives requirements or progress | `…only_technical_support_can_reserve` · `…can_update_a_requirement` · `…the_organiser_still_never_receives_requirements_or_their_progress` |
| Technical Support still gets **no author and no link** to the Organiser's pick; progress is added, nothing of the Coordinator's | `…technical_support_sees_what_is_reserved_without_the_coordinators_bookkeeping` |
| Outside the window, a requirement is **404** to Technical Support | `…outside_the_window_cannot_be_reserved` · `…cannot_be_updated` |
| The window for **recording** equals the window for **reserving** (his `PLANNED_EVENT_STATUSES`) | `test_the_window_for_recording_is_the_window_for_reserving` |
| An event with **no date and time** cannot have equipment reserved; the panel says why | `…an_event_with_no_date_cannot_have_equipment_reserved` · *says so for an event with no date and time* |

### Existing limitations — documented, not fixed here

Found while building this; all are properties of the existing reservation
feature or of cross-feature design, outside this story's acceptance criteria.
Each needs a team decision, and some may need the customer.

| # | Limitation | Effect on this story |
|---|---|---|
| 1 | **Reserving an item the Organiser did not ask for** adds an `equipment_requests` row, which appears in the Organiser's own equipment list. | Reserving for a requirement can add a line the Organiser never requested. Kept as his page does it; a separate integration fix if the team wants internal reservations hidden from the Organiser. |
| 2 | **No release / unreserve / cancel.** A reservation cannot be undone. | Hence the protections above, and refusing over-fill. The panel offers no undo (tested). |
| 3 | **An approved Organiser change replaces every `equipment_requests` row**, reserved ones included, with no guard. | The requirement's progress falls (it is derived), and the same item can be reserved again. The reservation itself is lost — W1 p3 expects such changes to *"require existing arrangements to be reconsidered"*. |
| 4 | **A cancelled event keeps its stock** until its end time; the availability query ignores event status. | W1 p3/p8: cancelled events must not stay committed. Nothing in the app cancels an event yet. |
| 5 | **Rescheduling moves a reservation with the event** without re-checking for overbooking. | Progress would still read Reserved. |
| 6 | **Equipment damaged after it is reserved** stays `reserved`. | W1 p3: *"reserved equipment may become unavailable"*. Not reflected in progress. |
| 7 | **One item cannot be topped up** (his rows are unique per event and item). | A requirement is completed from *different* items, never by adding to one. |
| 8 | **A reservation takes the Organiser's quantity whole** for an item they asked for. | If that exceeds what a requirement still needs, it is refused (see over-fill). |
| 9 | **No notification** when equipment is confirmed or found unavailable (W1 p11). | Not in this story's ACs; a candidate follow-up. |

Questions for the customer (Q&A): *When may equipment be recorded and reserved
(the provisional status window)? Should an Unavailable outcome carry a reason?
Should reserved equipment be releasable, and what should a cancelled event do
to it?*

### Object-oriented structure, and how it is tested

| Class | Responsibility | Unit-tested in |
|---|---|---|
| `EquipmentRequirementFulfillmentService` | The rules and orchestration: reserve for a requirement; update status and quantity. Given its collaborators; builds none. | `test_equipment_fulfillment_service.py` — no web layer |
| `ReservationGateway` (abstract) | What the service needs from a reservation capability. | `…a_gateway_cannot_be_used_without_implementing_the_contract` |
| `ErcongReservationGateway` | Production implementation: delegates to his unchanged function, and turns his `HTTPException` into a domain `ReservationRefused`, keeping his status and words. | `…turns_his_refusals_into_domain_errors` · `…reports_the_quantity_his_rule_would_force` |
| `FakeReservationGateway` (tests) | A second implementation with no rules — **polymorphism**: the service runs the same with either. | `…the_service_runs_the_same_with_either_gateway` |
| `RequirementProgress` (value object, immutable) | needed, reserved, remaining, the effective status, and the quantity floor | the parametrised status tests |
| `RequirementReservationLinks` (repository) | which reserved items fulfil which requirement; claims an item; reads progress in one query | `…progress_is_read_from_the_reserved_rows…` and the *claiming* tests |
| `ReservationRefused` (a `DomainError`) | His refusal, as a domain error carrying its own status code | the gateway tests; the existing one error handler maps it |

The domain owns the `ReservationGateway` contract and imports no
implementation of it: the adapter, which has to import his router, lives in
`app/services/reservation_gateway.py`. Routes stay thin — parse, call, commit,
shape the reply.

**Mutation check.** Fifteen deliberate breakages of these rules (no link, no
rollback, no over-fill check, no type check, reserved selectable, Unavailable
while reserved, no quantity floor, stale links counted, delete/retype not
blocked, …) were each caught by a failing test.

## Traceability

### UR AC1 — update the status

| Test | Level |
|---|---|
| Reserving fulfils a requirement through his reservation · his endpoints see it · it reduces overlapping availability · part reserved reads Reviewing with progress · the rest from another item · quantity left out · the Organiser's item at their quantity | pytest (API) |
| Over-fill refused · more than needed refused · other type refused · unknown item refused · his stock check refuses, in his words · overlap protection · one item, one requirement · no date · lost reservation can be reserved again · clears Unavailable | pytest (API) |
| Technical Support sets Requested / Reviewing / Unavailable (`rejected`) · `reserved` and `cancelled` refused · unknown status refused · Unavailable refused while reserved · a hand-set status does not hide what is reserved | pytest (API) |
| Only Technical Support (4 other roles) · anonymous · outside the window (7 statuses) · unknown requirement — for **both** endpoints | pytest (API) |
| Effective status (9 cases) · reserved never believed from storage · statuses Technical Support may set · reserve rules (delegation, default quantity, type, over-fill ×3, refusal leaves nothing, clears Unavailable, window, unknown) | pytest (unit) |
| The link commits with the reservation · a refusal leaves no link · a failed link stops the reservation · his function's signature | pytest (unit) |
| Editor: offers the three statuses, never Reserved · Unavailable shown · replaced by an explanation once reserved · sends only what changed · hands the server's answer back · nothing to save until changed · server reason and stays open · cancel | Vitest |
| Panel: type-filtered items · needs, window, still-to-reserve · no event/type/date fields · quantity defaults to what is needed · Organiser's quantity shown and not asked · check availability (his endpoint, the event's window; enough / only N) · reserve (quantity, none for the Organiser's item) · confirmation and reset · his refusal in his words · no date · fully reserved · no undo · close | Vitest |
| Record page: Reserve equipment and Update on each requirement, none without one · panel given this requirement and event, under its row · the row shows the new progress at once · one panel at a time · no release control · Unavailable shown | Vitest |

### UR AC2 — update the quantity

| Test | Level |
|---|---|
| Technical Support changes the quantity needed · reopens a fully reserved requirement · cannot go below reserved · can drop to exactly reserved · below one refused · reserving never changes it · type and notes sent anyway are ignored · empty update changes nothing | pytest (API) |
| Quantity floor (3 + any) · validation (0, −1, `true`, `"3"`) · only status and quantity updatable | pytest (unit) |
| The Coordinator cannot drop it below reserved; can set it to reserved or more | pytest (API) |
| Editor: starts at the quantity needed · minimum is what is reserved, and says why · never sends below one or below reserved | Vitest |
| Card: minimum is what is reserved · never sends below it · shows the progress the server answers with | Vitest |

### UR AC3 — visible to the Coordinator on the event record

| Test | Level |
|---|---|
| A status set by Technical Support is visible · a changed quantity is visible · the Coordinator sees what is reserved and how far · fully reserved reads Reserved · Technical Support and the Coordinator read **the same** progress · a new requirement reads Requested with nothing reserved · add and edit answer with the progress | pytest (API) |
| Card: progress and what is reserved ("3 of 6 reserved", "3 × Shure BLX24") · Reserved when all of it is · Unavailable shown · Remove withdrawn once reserved, kept otherwise · still editable · type locked and says why · server's reason when it refuses a removal | Vitest |
| Shared row: needed and status · rejected as Unavailable · progress and items · fully reserved · an older response still renders | Vitest |
| Labels and helpers: *Reviewing*, *Unavailable*, `progressText`, the options Technical Support may set (never Reserved), the two client calls | Vitest |

## Manual test — TC-UR-M1

Needs an approved event **with a date and time**, its Coordinator (e.g.
`coordinator@cs.local`), Technical Support (`tech_supp@cs.local`) and a catalogue
with at least two items of one type.

| # | Step | Expected |
|---|---|---|
| 1 | As the Coordinator, open the approved event → **Equipment Requirements** → add **Audio**, quantity `5` | The row reads **Requested**, with no progress line |
| 2 | As Technical Support → **Equipment Requirements** → open the event | The Audio row shows **× 5**, **Requested**, and **Reserve equipment** and **Update** |
| 3 | **Update** → Status **Reviewing** → **Save changes** | The row reads **Reviewing** |
| 4 | **Update** → Status **Unavailable** → **Save changes** | The row reads **Unavailable** |
| 5 | As the Coordinator, reload the event | The Audio row reads **Unavailable** (UR AC3) |
| 6 | As Technical Support, **Reserve equipment** | The panel names the event's date and time, offers only **Audio** items, and asks only for the item and a quantity |
| 7 | Choose an item the Organiser did not ask for | **Quantity to reserve** starts at `5` |
| 8 | **Check availability** | "*x* of *y* … available for …" and "Enough for the 5 to reserve" (or "Only *n* available") |
| 9 | Set the quantity to `3` → **Reserve** | "Reserved 3 × …". The row reads **Reviewing**, **3 of 5 reserved**, with the item named; Unavailable is gone |
| 10 | Open **Equipment Reservations** (the global page) → choose the event | The **same** 3 × item is listed under *Reserved for …* — one reservation, not two |
| 11 | **Reserve equipment** → another Audio item, quantity left at `2` → **Reserve** | The row reads **Reserved**, **5 of 5 reserved**, both items named |
| 12 | **Update** → quantity `4` → **Save changes** | Refused: "5 already reserved; the quantity needed cannot be less than that." |
| 13 | **Update** → quantity `6` | The row reads **Reviewing**, **5 of 6 reserved** |
| 14 | As the Coordinator, reload | The same row. No **Remove**. **Edit**: the type is locked and says why, the minimum quantity is 5, the notes can be changed |
| 15 | Add a second **Audio** requirement of `2`, with the Organiser having asked for a microphone × 4 → **Reserve equipment** → that microphone | Refused: "This event asked for 4 …, and a reservation takes that whole quantity; this requirement needs only 2 more." Nothing is reserved |
| 16 | Open an event with **no date** | Reserve equipment says it has no date and time, and offers nothing to press |
| 17 | As the Organiser, open the event | No requirements, no progress, no reservation detail anywhere |
| 18 | Toggle dark mode | Panel, editor and progress stay legible |

## Note for the Week 13 Q&A

- **Why does Technical Support reserve from the requirement and not only from
  the Equipment Reservations page?** Because the three responsibilities —
  *recording* what an event needs, *checking* availability, and *reserving* —
  stay separate, but Technical Support works from one queue. The requirement
  page is a contextual way into the existing reservation, with the event, type
  and date already known. His page is unchanged and is still the global view.
- **Why is "reserved" not a status Technical Support can pick?** A status that
  can be set by hand can disagree with the stock. Reserved is worked out from
  the real reservations, so the two cannot drift.
- **Why is the link keyed by (event, item)?** So it can be written in the same
  commit as his reservation. A link to his row's id would have needed a second
  commit — and a window where one succeeded and the other did not. The three
  atomicity tests were written first.
- **What did you leave alone, and why?** Everything of Ercong's. The limits we
  found in it (nothing can be released; an Organiser change wipes reservations)
  are listed above as decisions for the team, not silently patched in this
  story.
