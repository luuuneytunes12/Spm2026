# Test Cases — Record Equipment Requirements for Event

Covers one product backlog item:

- **Record Equipment Requirements for Event.** *As an Event Coordinator, I want
  to record the equipment an event requires, so that Technical Support Staff
  know what to review and reserve.*

Every acceptance criterion maps to at least one test, and every automated test
is named after what it proves. Edge cases — boundaries, invalid input, who may
and may not — are test cases, not extra criteria. Same format as
[test-cases-venue-search.md](test-cases-venue-search.md).

## Acceptance criteria

| # | Criterion |
|---|---|
| **ER AC1** | I can add equipment requirements to an event: **equipment type**, **quantity needed**, and any **technical notes** |
| **ER AC2** | Requirements are **visible to Technical Support Staff** from the event record |

Suggested wording for Jira, so the criteria say what is built:

- **AC1:** *"…equipment type (a catalogue category), quantity needed, and any
  technical notes."* The Coordinator picks a **type**, not a specific item —
  choosing the actual item to reserve is Technical Support's job, in the next
  story.

### How this covers the core feature (W4 p4, *Equipment Request Management*)

> *"Event Coordinators can record equipment required for an event, including
> the equipment type, quantity, and relevant technical requirements. Technical
> Support Staff can review the requested equipment and update the request as
> arrangements are made."*

| From the PDF | Covered by |
|---|---|
| Coordinators record equipment, **type** | AC1 — a catalogue category |
| **quantity** | AC1 — quantity needed |
| **relevant technical requirements** | AC1 — technical notes |
| Technical Support **review** | AC2 — they can read it. *Updating* the request is the next story |

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q tests/test_equipment_requirements.py tests/test_equipment_requirement_service.py` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| All of the above | push to any branch | GitHub Actions runs them |

**107 pytest · 106 Vitest · 1 manual script.** No Playwright — the end-to-end CI
job is disabled for now.

---

## Design decisions the tests pin

### A requirement is not one of the Organiser's picks

The Organiser's equipment picks live in `equipment_requests`. Since commit
`0311abf`, an Organiser's **approved change request** calls
`replace_equipment_lines`, which **deletes every row of that table for the
event and rebuilds it** from the Organiser's list. A requirement stored there
would be deleted along with them.

So requirements have their own table, `coordinator_equipment_requirements`
(migration `015`):

| | |
|---|---|
| Link | `organiser_equipment_request_id` goes **from** the requirement **to** the Organiser's pick it was based on. The Organiser's table knows nothing about requirements |
| Nullable | A Coordinator may record a need the Organiser never mentioned |
| `ON DELETE SET NULL` | Replacing the pick clears the link; the requirement survives |
| One pick → many requirements | Allowed |
| One requirement → one pick | At most |

The test that guards this is
`test_replacing_the_organisers_lines_never_deletes_a_requirement`. It turns
SQLite's foreign keys on (they are off by default, and `SET NULL` is exactly
what is being proved) and asserts they are on, rather than passing vacuously.
It was **mutation-checked**: changing the rule to `ON DELETE CASCADE` makes it
fail.

### The Organiser's request: context, and an optional starting point

W1 Step 8 has Technical Support reviewing equipment *"required and requested by
the Event Organiser"*, so the Coordinator plans against what the Organiser asked
for. W4 p4 only requires the Coordinator to record **type, quantity and
technical requirements** — nothing says a requirement must be linked to an
Organiser request. So the link is **optional**, and the card is built around
that.

| Rule | Tested by (Vitest) |
|---|---|
| The Organiser's equipment requests and their **Other equipment notes** are shown **read-only** above the requirements, as planning context — no field, dropdown or button | *the Organiser's request, shown as planning context* |
| The Organiser's general note is **never copied** into a requirement's technical notes | `…never copies the Organiser's notes into a requirement's technical notes` |
| The link field is **"Based on organiser equipment request (optional)"**; its empty choice is **"Not based on an organiser request"** | *basing a requirement on an Organiser equipment request (optional)* |
| The Coordinator chooses an equipment **type** (a catalogue category), never an exact item or model; picking the exact resource is Technical Support's job, later | `…offers the catalogue's own equipment types, and no others` |
| Choosing a request fills in **type and quantity** (where derivable); both stay editable. Technical notes are the Coordinator's own and are **not** filled in | `…fills in the equipment type and quantity…` · `…does not fill in technical notes…` · `…leaves notes already typed alone…` |
| An **independent** requirement can always be added, even when the Organiser requested equipment | `…can add an independent requirement even though the Organiser requested equipment` |
| **Add requirement** saves at once, as *Requested*, visible to Technical Support. There is **no draft/submit step**, and the card says so | *adding is immediate* |
| A saved requirement shows the request it was based on, or **"Coordinator-added requirement"** | *where a requirement came from* |
| **Edit** shows that origin read-only and offers no way to relink it; it changes type, quantity and notes only, and **Save changes** saves them | `…shows the Organiser request it was based on, read-only` · `…changes only type, quantity and notes, and keeps the link…` |

The backend already ignores any attempt to change the link on an edit
(`test_er_ac1_the_link_to_an_organisers_pick_cannot_be_edited`).

**Known limit.** When an approved change request replaces the Organiser's list,
the database clears the link (`ON DELETE SET NULL`) so the requirement
survives. After that, the requirement reads *Coordinator-added requirement*
even though it was originally based on a request. The card does not keep a
history of what it was based on.

**Technical notes stay optional.** A requirement needs a type and a quantity;
notes may be empty (W4 p4 says *relevant* technical requirements, and a
projector may have none). Blank notes are stored as no notes.

### Where equipment can be recorded — PROVISIONAL

| Status | Coordinator may record | Technical Support sees the event |
|---|---|---|
| approved · planning · confirmed | ✅ | ✅ |
| draft · submitted · under review · changes requested · rejected · completed · cancelled | ❌ (409) | ❌ (404) |

**Neither PDF defines this window.** It is inferred:

- **W4 p3:** the Coordinator can *"view and update relevant event information
  **during the planning process**"*
- **W1 p10:** Step 8 (Technical Requirements) comes **after** Step 5 (Initial
  Approval)
- **W1 p3:** equipment changes keep arriving *"even after it has been
  confirmed"*
- **W1 p8:** *"reservations should no longer remain committed to a cancelled
  event"* — so not after cancellation, completion or rejection

It is **one constant**, `EQUIPMENT_ACTIVE_STATUSES`, used by both the
Coordinator's side and Technical Support's side, so a requirement can never sit
somewhere Technical Support is not looking. It is tested **status by status, in
both directions**, so if the customer answers differently the change is one
line and the matching test cases flip.

> **Question for the customer (Q&A):** *"Should an Event Coordinator be able to
> record equipment while a request is still under review, or only once it has
> been approved? And after an event is confirmed, should equipment changes
> still be allowed?"*

### Other rules

| Rule | Basis | Tested by |
|---|---|---|
| Type must be one of the **catalogue's** categories, matched ignoring case, stored in the catalogue's spelling | One list of types; "audio" and "Audio" cannot become two | `test_er_ac1_the_type_is_matched_to_the_catalogue_ignoring_case` |
| Quantity at least 1 | Mirrors the database `CHECK` → a 422 naming the field, not a 500 | `test_er_ac1_a_quantity_below_one_is_rejected` |
| Blank notes are stored as no notes | Spaces are not a note | `test_er_ac1_blank_notes_are_stored_as_no_notes` |
| **Two requirements of the same type are allowed** | Six microphones and a PA system are both *Audio* | `test_er_ac1_two_requirements_may_share_a_type` |
| A link may only point at a pick of the **same event** | It means "this need came from that request" | `test_er_ac1_a_pick_from_another_event_cannot_be_linked` |
| "Not yours" and "does not exist" are both **404** | Event ids cannot be probed | `test_er_ac1_another_coordinators_event_is_not_found` |
| Only the **Coordinator assigned to the event** may record | Same scoping as the assigned-event page | `…only_a_coordinator_can_record_equipment` |
| Requirements stay **readable** outside the window | Recording stops; the record doesn't vanish | `…stay_listed_once_the_event_is_outside_the_window` |
| Technical Support sees events across **all** Coordinators | They review equipment everywhere, not "mine" | `test_er_ac2_technical_support_sees_requirements_of_every_coordinators_events` |
| Technical Support receives only `id, category, quantity_needed, technical_notes, status` | No author, no link to the Organiser's pick — the Coordinator's bookkeeping | `test_er_ac2_technical_support_receives_only_what_it_needs_of_a_requirement` |
| The **Organiser never receives** the Coordinator's requirements | Internal planning stays internal | `test_the_organiser_never_receives_the_coordinators_requirements` |

**Deferred to the next story** (*Update Equipment Requirement Status*): moving a
requirement past `requested`, reserving, the stock check, notifications, the
reserved quantity, and what editing or removing a *reviewed* line does. Until
then every requirement is `requested`, so add, edit and delete are plain.

### Object-oriented structure, and how it is tested

| Class | Responsibility | Unit-tested in |
|---|---|---|
| `DomainError` → `NotFound` · `Conflict` · `InvalidInput` · `Forbidden` | What went wrong, independent of HTTP. Each carries its **own** status code; one handler maps the hierarchy, so a new kind of failure is one subclass | `test_equipment_requirement_service.py` |
| `CategoryResolver` (Protocol) / `CatalogueCategories` | How a typed category becomes a catalogue category. The service **depends on the interface**, so a test hands it a fake | `…takes_its_category_rule_as_a_dependency` |
| `EquipmentRequirementService` | The Coordinator's side: add, edit, remove, list | same file — called directly, **no web layer** |
| `TechSupportRequirementReader` | Technical Support's side: read-only | same file |

---

## Traceability

### ER AC1 — add type, quantity needed and technical notes

| Test | Type |
|---|---|
| `test_er_ac1_a_requirement_records_type_quantity_and_notes` | pytest |
| `test_er_ac1_a_new_requirement_starts_as_requested` | pytest |
| `test_er_ac1_technical_notes_are_optional` · `…blank_notes_are_stored_as_no_notes` | pytest |
| `test_er_ac1_the_type_is_matched_to_the_catalogue_ignoring_case` | pytest |
| `test_er_ac1_an_unknown_type_is_rejected` · `…a_blank_type_is_rejected` (2 cases) | pytest |
| `test_er_ac1_a_quantity_below_one_is_rejected` (0, −1) | pytest — **boundary** |
| `test_er_ac1_two_requirements_may_share_a_type` | pytest |
| `test_er_ac1_a_requirement_may_be_based_on_an_organisers_pick` · `…need_not_come_from…` · `…one_pick_may_have_several_requirements` | pytest |
| `test_er_ac1_a_pick_from_another_event_cannot_be_linked` · `…that_does_not_exist_cannot_be_linked` | pytest |
| `test_er_ac1_equipment_can_be_recorded_in_these_statuses` (approved, planning, confirmed) | pytest |
| `test_er_ac1_equipment_cannot_be_recorded_in_any_other_status` (7 statuses) | pytest |
| `test_er_ac1_another_coordinators_event_is_not_found` · `…an_event_that_does_not_exist_is_not_found` | pytest |
| `test_er_ac1_only_a_coordinator_can_record_equipment` (Organiser, Attendee, Tech Support, Venue Staff → 403) · `…anonymous…` (401) | pytest |
| `test_er_ac1_the_coordinator_lists_an_events_requirements_oldest_first` · `…an_event_with_no_requirements_lists_an_empty_array` · `…of_another_coordinators_event_are_not_found` · `…stay_listed_once_the_event_is_outside_the_window` | pytest |
| **Edit:** `…can_be_edited` · `…an_edit_that_omits_a_field_leaves_it_alone` · `…notes_can_be_cleared_with_an_explicit_null` · `…an_invalid_edit_is_rejected_and_changes_nothing` (3) · `…the_link_to_an_organisers_pick_cannot_be_edited` · `…another_coordinators_requirement_cannot_be_edited` · `…cannot_be_edited_once_the_event_leaves_the_window` · `…a_requirement_that_does_not_exist_is_not_found` | pytest |
| **Delete:** `…can_be_deleted` · `…another_coordinators_requirement_cannot_be_deleted` · `…cannot_be_deleted_once_the_event_leaves_the_window` · `…only_a_coordinator_can_edit_or_delete` | pytest |
| `test_replacing_the_organisers_lines_never_deletes_a_requirement` ⭐ · `test_a_requirement_is_not_one_of_the_organisers_picks` · `test_the_organiser_never_receives_the_coordinators_requirements` | pytest |
| Service, called directly: records without a web layer · takes its category rule as a dependency · raises domain errors, never `HTTPException` · refuses outside the window (7) · edits and removes · an empty edit changes nothing | pytest (unit) |
| Error hierarchy: each error knows its own status (404, 409, 422, 403) · a field-naming `InvalidInput` · the status window is exactly approved/planning/confirmed | pytest (unit) |
| Card: lists type, quantity, notes, status · empty state ("No Coordinator equipment requirements recorded yet.") · load failure | Vitest |
| Card, add: records type/quantity/notes · shows the new row and clears the form · quantity defaults to 1 · offers only the catalogue's types · empty notes sent as `null` · asks for a type rather than sending without one · shows the server's reason and keeps what was typed · still usable if the type list fails to load | Vitest |
| Card, Organiser context: shows the Organiser's requests read-only (no field, dropdown or button) · shows their other equipment notes · says so when they asked for none · leaves the notes row out when they wrote none (null, empty, blank — 3) · still shown while nothing can be recorded · says it is for reference · never copies the notes into a requirement | Vitest |
| Card, based on an Organiser equipment request (optional): absent when they requested nothing · labelled "Based on organiser equipment request (optional)" with "Not based on an organiser request" as the empty choice · fills in type and quantity · does **not** fill in technical notes · leaves typed notes alone · filled values stay editable · remembers the request · **an independent requirement can be added even when the Organiser requested equipment** · can go back to "not based" | Vitest |
| Card, adding is immediate: says Technical Support will see it · no draft or submit step, one click saves it as Requested · the promise is not made where nothing can be added | Vitest |
| Card, where a requirement came from: names the Organiser request · "Coordinator-added requirement" otherwise · shown straight after adding (both ways) · a link to a request the page does not have is not called Coordinator-added | Vitest |
| Card, edit and remove: opens filled in · saves changes · "Save changes", not "Save" · shows its Organiser request read-only with no way to relink · "Coordinator-added" in the editor of an independent one · changes only type, quantity and notes and keeps the link · cancel changes nothing · shows the server's reason and stays open · removes · keeps the row and says why when refused · **the add form stays distinguishable from an open editor** | Vitest |
| Card, status window: editable in approved/planning/confirmed (3) · explains the wait while under review · no controls in any other status (7) · still shows what was recorded after the event finishes | Vitest |
| Event page: the card is on it, for that event · is handed the Organiser's picks · is handed the Organiser's other equipment notes · is present under review · doesn't replace the Organiser's own equipment under *Event Details* | Vitest |
| `lib`: window is exactly approved/planning/confirmed · recordable in each (3) · not in any other (7) · status labels · an unknown status is shown as it arrives | Vitest (lib) |

### ER AC2 — visible to Technical Support from the event record

| Test | Type |
|---|---|
| `test_er_ac2_technical_support_sees_what_the_coordinator_recorded` | pytest |
| `test_er_ac2_the_event_record_carries_what_is_needed_to_review_it` | pytest |
| `test_er_ac2_the_event_record_is_visible_before_anything_is_recorded` | pytest |
| `test_er_ac2_technical_support_lists_events_that_have_requirements` · `…an_event_with_no_requirements_is_not_listed` | pytest |
| `test_er_ac2_events_in_the_window_are_listed` (approved, planning, confirmed) | pytest |
| `test_er_ac2_events_outside_the_window_are_neither_listed_nor_openable` (7 statuses → 404) — **never drafts** | pytest |
| `test_er_ac2_an_event_that_does_not_exist_is_not_found` | pytest |
| `test_er_ac2_technical_support_sees_requirements_of_every_coordinators_events` | pytest |
| `test_er_ac2_technical_support_receives_only_what_it_needs_of_a_requirement` · `…does_not_leak_the_coordinators_password_hash` | pytest |
| `test_er_ac2_only_technical_support_can_use_the_support_view` (4 roles × 2 endpoints → 403) · `…anonymous…` (401) | pytest |
| Reader, called directly: lists only active events that have requirements · refuses events outside the window | pytest (unit) |
| List page: name, date, attendance, type · requirement count (singular and plural) · where each event is in its life · links to its record · an unnamed event is labelled · empty state · error · offers no buttons | Vitest |
| Record page: asks for the event in the address · event details · Coordinator named · "Not assigned" · "Not provided" · requirements with type/quantity/notes/status · empty state · back link · offers no buttons | Vitest |
| Record page, refusal: "Event not found" with a way back · a useful message when the server is unreachable | Vitest |
| Sidebar: Technical Support gets **Equipment Requirements** · keeps the catalogue · **still** sees *Equipment requests* as planned (reviewing isn't built) · the Coordinator's planned *Request equipment* is gone · nobody else is offered the page | Vitest |

> ⭐ **The test to keep.** Without a separate table this story would work in
> every demo and silently delete Coordinator work the first time an Organiser's
> change request was approved.

---

## Manual test — TC-ER-M1

The one thing automation cannot judge is whether it is **readable and obvious**
to a person — especially the two forms that can be open at once.

**Preconditions:** backend and frontend running. `tech_supp@cs.local` exists.
An **approved** event with an assigned Coordinator exists (e.g. *Testing_yk_2*,
Coordinator 2). `planning` and `confirmed` cannot be reached through the UI
yet; they are covered by the automated tests.

| # | Step | Expected result |
|---|---|---|
| 1 | Sign in as the event's Coordinator → **My Assigned Events** → open the approved event | An **Equipment Requirements** card sits above *Event Details*. At its top, **Requested by the Organiser** shows their equipment and, if they wrote any, their **Other equipment notes** — plain text, nothing to click |
| 2 | Read the card's empty state | *"No Coordinator equipment requirements recorded yet."* |
| 3 | Choose **Audio**, quantity `6`, notes `Handheld wireless` → **Add requirement** (no Organiser request chosen) | The row appears with type, **× 6**, the notes, a **Requested** badge and **Coordinator-added requirement**; the form clears. Above the button: *"Once added, this requirement will be visible to Technical Support."* |
| 4 | If the Organiser requested equipment: under **Based on organiser equipment request (optional)** choose one | Type and quantity fill in; **notes stay empty** (the Organiser's note is not copied). All three stay editable |
| 5 | Add it | The row shows **Based on organiser equipment request: *item* × *n*** |
| 6 | Add a second **Audio** requirement | Allowed — two rows of the same type |
| 7 | Click **Add requirement** with no type chosen | *"Choose an equipment type."*; nothing is saved |
| 8 | Click **Edit** on a row | The row is tinted and filled in, and states where it came from. There is **no** control to change that. **Add a requirement** is still titled, so the two forms can't be confused |
| 9 | Change the quantity → **Save changes** · then try **Cancel** on another | Save changes updates the row; Cancel changes nothing |
| 10 | Click **Remove** on a row | It disappears |
| 11 | Sign in as an Organiser who owns the event | Their own request does **not** show the Coordinator's requirements |
| 12 | Sign in as `tech_supp@cs.local` → **Equipment Requirements** | The event is listed with its requirement count |
| 13 | Open it | Event details (date, attendance, venue requirements, Coordinator) and every requirement; **no buttons** |
| 14 | Open an event that is still under review as its Coordinator | The card still shows what the Organiser requested, says *"Equipment can be recorded once the event is approved."* and offers no form |
| 15 | Narrow the window to ~400px | Rows wrap; nothing scrolls sideways |
| 16 | Toggle dark mode | Chips, badges and the tinted editor stay readable |

**Tester:** ______________ **Date:** ____________ **Result:** Pass / Fail

---

## Note for the Week 13 Q&A

The briefing says the **Organiser** *"provides preliminary information such as
… equipment requirements"* (W1 p2), and that the **Coordinator** records the
structured request (W4 p4). Both exist here, and deliberately in separate
tables: the Organiser's picks are theirs and can be replaced by an approved
change request; the Coordinator's requirements are the working record Technical
Support reviews. The optional link between them lets a Coordinator say *"this
need came from that request"* without either table depending on the other's
lifecycle.
