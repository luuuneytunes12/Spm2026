# Test Cases — View Equipment Requirements as Technical Support Staff

Covers one product backlog item:

- **View Equipment Requirements as Technical Support Staff.** *As a Technical
  Support Staff member, I want a list of Equipment Requirements waiting for me,
  so that I can review and reserve them without searching every Event.*

It builds on [Update Equipment Requirement Status](test-cases-equipment-requirement-status.md)
(the statuses, the Manage panel, placement and the reservation) and reuses the
Equipment Reservations feature without changing it. Same format as the other
test-case documents.

*Naming: the story and the screen say **Equipment Requirements** throughout,
the Coordinator's term. The acceptance criteria were first worded "Equipment
Requests"; the empty-state message is therefore **"No equipment requirements"**.*

## Acceptance criteria

| # | Criterion |
|---|---|
| **AC1** | Given one or more Equipment Requirements are "Requested", when I open Equipment Requirements, each is listed with its **Event, equipment type, quantity, date and time, oldest Event date first** |
| **AC2** | Given none are "Requested", a **"No equipment requirements"** message is shown |
| **AC3** | Given a requirement is listed, when I open it, I see its **technical notes and placement** and can **check availability or reserve** it |
| **AC4** | Given requirements exist, when a user **other than Technical Support Staff** tries to open the list (screen or direct request), access is **denied** |

Source: Week 4 Project Instructions, *Equipment Request Management*: *"Technical
Support Staff can review the requested equipment and update the request as
arrangements are made."*

### What "Requested" means, and what is decided

| | |
|---|---|
| **Requested** | The Definition of Done's status (11b): **nothing reserved, or only part of it.** A part-reserved requirement stays listed — still waiting for the rest — with "Requested — 3 of 5 reserved". |
| **Not listed** | **Reserved** (full quantity), **Unavailable** (marked, with a reason) and **Available** (reservation freed). None is waiting for Technical Support. Raising the quantity above what is reserved, or setting an Unavailable one back to Requested, puts a requirement back in the list. |
| **Which events** | The window Technical Support can already reserve in (approved, planning, confirmed). Never a draft, rejected, completed or cancelled event. |
| **Order** | **Earliest event date first**, an event with **no date last**, and an event's requirements in the order they were recorded. A dated event that has already happened is **still listed**: Requested is a status, not a date. |
| **Opening one** | **In place**, with the existing Manage panel — no new page. It shows the technical notes, where each reserved item is placed, the availability check and the reservation. A requirement not yet reserved has **no placement yet**: placement is recorded when equipment is reserved (see the status document). |
| **After a change** | A requirement stays in its place after it is reserved or marked Unavailable, showing its new status, so the panel's confirmation is not lost; it leaves the list the next time it is loaded. |

*Placement* is Ercong's own `placement_notes` on the reservation, which the
Safety Officer already reads; this story only shows it.

## How to run

```bash
cd backend  && uv run pytest tests/test_requested_requirements_list.py
cd frontend && npx vitest run src/pages/equipment/EquipmentRequirementsList.test.tsx \
                              src/App.access.test.tsx \
                              src/lib/equipmentRequirements.test.ts \
                              src/components/EquipmentRequirementItem.test.tsx
```

**34 pytest · 20 + 8 Vitest in the two new files (plus 3 added to existing
ones) · 1 manual script.** No Playwright. The full suites pass except two Venue
Availability calendar tests that depend on today's date and are not part of this
story.

## Design

| Piece | What it does |
|---|---|
| `GET /equipment-requirements/support/requested` | The list. Technical Support only (`require_role`), so a direct request from anyone else is **403** and an anonymous one **401**. |
| `TechSupportRequirementReader.requested()` | The rule: events in the window, ordered, and only those whose **derived** status is Requested. The status is worked out (never stored), so the filter is made on the worked-out progress rather than in SQL. |
| `RequestedRequirementOut` | Everything the Manage panel reads **plus** `event` (id, name, start, end), so a row opens with no second request. No author and no link to the Organiser's pick — the Coordinator's own bookkeeping stays out. |
| `EquipmentRequirementsList` page | Replaces the earlier per-event list as the screen at `/equipment-requirements`. Each event name still links to that event's full record (`/equipment-requirements/:eventId`), which is unchanged. |
| `RequireRole([TECH_SUPPORT])` | The screen guard. `App.access.test.tsx` renders the **real** routes, so it fails if the list is ever moved outside it. |

The earlier endpoint `GET /equipment-requirements/support/events` (events with a
requirement count) and its tests are left in place; the page no longer uses it.

## Traceability

### AC1 — listed with event, type, quantity, date and time, oldest first

| Test | Level |
|---|---|
| A requirement is listed with its event, type, quantity and time · every event's requirements in one list · **oldest event date first** · one event's requirements in recorded order · **no date last** · a past event still listed | pytest (API) |
| Part reserved is still Requested and says how far · a stored `reviewing` counts as Requested · **fully reserved**, **Unavailable** and **freed (Available)** are not listed · set back to Requested, or quantity raised over what is reserved, lists it again · events outside the window (7 statuses) not listed | pytest (API) |
| Each row: event, type, × quantity, date and time · the server's order kept · Requested (and how far) · technical notes on the row · event links to its record · no date yet · untitled event · load failure shown | Vitest |

### AC2 — none Requested

| Test | Level |
|---|---|
| No requirements at all → an empty list | pytest (API) |
| "No equipment requirements" and no rows · not shown while failed · not shown when there are rows | Vitest |

### AC3 — opening one

| Test | Level |
|---|---|
| The listed shape is what the Manage panel is given plus its event, and nothing of the Coordinator's bookkeeping · technical notes carried · each reserved item's placement carried · nothing placed before it is reserved · reservable through the existing route | pytest (API) |
| One **Manage requirement** action per requirement · opens the panel under that row, given the requirement and its event · gives it the technical notes · a change shows at once, panel stays open · stays in place once fully reserved · closes · pressed again closes (`aria-expanded`) · one panel at a time · no release control | Vitest |
| The panel's notes, placement, availability check and reservation | see the status document (`RequirementManagePanel.test.tsx`) |

### AC4 — only Technical Support

| Test | Level |
|---|---|
| Coordinator, Organiser, Venue Staff, Attendee, Safety Officer → **403** · the denial leaks nothing · anonymous → **401** | pytest (API) |
| Technical Support reaches the list · Coordinator, Coordinator Lead, Organiser, Venue Staff, Attendee, Safety Officer see **No Access** · signed out is sent to log in — against the real routes in `App.tsx` | Vitest |

## Manual test — TC-VR-M1

Needs two approved events with different dates, each with at least one
requirement recorded by its Coordinator, Technical Support
(`tech_supp@cs.local`) and a catalogue with items of those types.

| # | Step | Expected |
|---|---|---|
| 1 | As Technical Support → **Equipment Requirements** | Every Requested requirement from every event is listed, each with its **event name** (a link), type, **× quantity**, date and time, status **Requested**, and the technical notes. The **earliest event is first**; an event with no date is last |
| 2 | Open **Manage requirement** on one | The panel opens under that row with the notes, a *Placement* line ("Recorded when equipment is reserved"), and the equipment list. Pick an item → its availability appears by itself |
| 3 | Reserve part of it, with a **Placement** | The row now reads **Requested — *n* of *m* reserved**, names the item with *(placed: …)*, and stays in the list. The panel's Placement line shows it |
| 4 | Reserve the rest | The row reads **Reserved** and stays in place. **Reload** the page: it is gone from the list |
| 5 | Mark another requirement **Unavailable** with a reason, then reload | It is gone from the list. Set it back to **Requested** (from the event's record) and reload: it is back |
| 6 | Click an event's name | That event's full record, with all of its requirements, as before |
| 7 | When nothing is Requested | The page shows **"No equipment requirements"** and no rows |
| 8 | Sign in as the Coordinator (or any other role) and open `/equipment-requirements` | **No Access**. The Equipment Requirements link is not in their menu |
| 9 | As that user, request `/equipment-requirements/support/requested` directly | **403** |
| 10 | Toggle dark mode | The list, status badges and panel stay legible |

## Note for the Week 13 Q&A

- **Why is part-reserved still listed?** It is still Requested in the
  Definition of Done: some of what was asked for is not yet reserved, so it is
  still waiting for Technical Support.
- **Why filter after the query, not in SQL?** Reserved and Available are worked
  out from the reservations and the event's end time, never stored. Filtering
  on the stored column would disagree with what every screen shows.
- **Why open in place?** The Manage panel already holds the notes, placement,
  availability and reservation. A new page would be a second copy of it.
