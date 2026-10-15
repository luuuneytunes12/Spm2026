# Test Cases — Change or Cancel One Venue Booking

Covers one product backlog item (SCRUM-96):

- **Change or Cancel One Venue Booking.** *As an Event Coordinator, I want to
  change or cancel one Venue Booking of an Event without touching the others,
  so that one room change does not undo the whole Event.*

Every acceptance criterion maps to at least one test, and every automated test
is named after what it proves. Same format as
[test-cases-venue-booking-decision.md](test-cases-venue-booking-decision.md).

## Acceptance criteria

| # | Criterion |
|---|---|
| **AC1** | Given an Event has one or more Venue Bookings, when I **cancel one**, then only that booking becomes "Cancelled" and the others stay unchanged |
| **AC2** | Given an Event has one or more Venue Bookings, when I **change the Venue (or the layout, accessibility or facilities I need from it)** of one, then only that booking returns to "Pending" for Venue Staff review and does not count as approved until it is "Approved" again |
| **AC3** | Given I choose to **cancel all** Venue Bookings of an Event, when I confirm, then the bookings to be cancelled are listed first and I must confirm again |
| **AC4** | Given a Venue Booking is changed or cancelled, when it is saved, then the **Venue Staff are notified** and the change is recorded in the **Activity Log** |

AC2 was reworded from "change the time or Venue". A booking has no time of its
own: the server copies the Event's, so the booking can never disagree with what
the Organiser asked for (W4 p5: venue and equipment reservations *"reflect the
date and time of the corresponding event"*). A booking's time following the
Event's later changes is a separate piece of work (see *Related, not in this
story*).

### What the documents require, and what is inferred

| | Source |
|---|---|
| **Explicit** | W7 #3: *"Changes or cancellation of one venue arrangement should not automatically remove the other venue bookings unless this is explicitly required."* — AC1 and AC2; "cancel all" is the explicit case. |
| **Explicit** | W7 #5: *"Event Coordinators should only be able to manage events assigned to them"* — only the assigned Coordinator may do any of this. |
| **Explicit** | W1 p11 lists, as something to notify, *"A venue booking is requested, approved, rejected, **or changed**"* — AC4. |
| **Explicit** | DoD 11a: *"A change to one Venue Booking … does not change the Event status by itself."* DoD 11c: *"Cancelled – this one booking was cancelled; other bookings on the same Event are not affected."* DoD §4/§11: every change is in the Activity Log with actor and time. |
| **Inferred** | The two-step confirmation of "cancel all". No document describes it; it is the story's own AC. |
| **Inferred** | That a venue change tells Venue Staff of both venues; that all Venue Staff are told (no document assigns staff to venues, and their queue is already global); that changing and cancelling are limited to the planning statuses. |

## How to run

```bash
cd backend  && uv run pytest tests/test_venue_booking_change_cancel.py \
                             tests/test_venue_booking_change_service.py
cd backend  && uv run pytest tests/integration/test_venue_booking_change_cancel_postgres.py   # needs Docker
cd frontend && npx vitest run src/lib/venueBookingChanges.test.ts \
                              src/components/VenueBookingChange.test.tsx
```

**92 + 38 pytest · 3 Postgres · 53 Vitest · 1 manual script.** No Playwright.
Every one of the 21 deliberate breakages tried (no log line, no window, anyone
may, everyone told, a stale list accepted, …) was caught by a failing test.
The 3 Postgres tests were written but **not run** here (they need Docker).

## Design decisions the tests pin

| Rule | Why | Tested by |
|---|---|---|
| **A booking has no time of its own.** A time sent with a change is ignored, not applied | It is the Event's (W4 p5) | `…a_bookings_time_is_the_events_and_cannot_be_changed_here` · `sends no time` |
| **Live bookings** (pending, held, approved) can be changed or cancelled; **rejected and cancelled are history** | Another venue is asked for with a new request | `…a_pending_held_or_approved_booking_can_be_cancelled` · `…a_rejected_or_cancelled_booking_cannot_be_cancelled` · `…cannot_be_changed` |
| **Only while the event is being planned** (Event Approved, Planning Event). After the Safety Check starts, the arrangement is judged as it stands; a send-back returns it here | DoD 11a: Awaiting Safety Check needs every booking Approved | `…outside_planning` (×3 endpoints, every other status) |
| **That window equals the window for requesting a venue**, and a test says so | W7 #2: a replacement can be requested after the Safety Check. If requesting is widened, this fails, and changing and cancelling widen with it | `test_the_window_for_changing_is_the_window_for_requesting` |
| A change **returns the booking to Pending** and clears the old decision, hold, safety re-review and conflict flag | Nothing of the old decision may read as if it still applied | `…approval_is_no_longer_there_once_it_goes_back` · `…a_held_booking_goes_to_pending_and_the_hold_is_dropped` |
| **Pending holds nothing**, so the booking does not count as approved until approved again, and the venue it left is free | The event waits on it; another event can take the slot | `…it_does_not_count_as_approved_until_it_is_approved_again` · `…it_counts_again_once_venue_staff_approve_it` · `…a_cancelled_booking_is_withdrawn_from_the_events_arrangements` |
| **Cancelling frees the venue**, and a conflict flag on the cancelled booking clears | Reuses the existing venue re-check | `…a_cancelled_booking_no_longer_holds_the_venue` · `…a_conflict_flag_on_the_cancelled_booking_is_cleared` |
| A change that **changes nothing is refused** (422) | Nothing for Venue Staff to review, and a repeat is not a second change | `…a_change_that_changes_nothing_is_refused` · `…the_same_change_twice_is_one_change` |
| A blank need is **what the event says** | Same rule as requesting | `…a_blank_need_goes_back_to_what_the_event_says` |
| A venue the event **already has a live booking at** is refused; an unknown or inactive one too | One live booking per venue per event | `…a_venue_the_event_already_has_is_refused` · `…an_unknown_or_inactive_venue_is_refused` |
| **Cancel all takes the ids that were listed**, and cancels nothing if the live bookings are no longer exactly those | The second confirmation is enforced by the server, not only the page; a stale list is never silently widened or narrowed | `…a_request_without_the_list_it_was_shown_cancels_nothing` · `…a_list_that_has_gone_stale…` · `…no_longer_live…` · `…another_events_booking_in_the_list…` |
| The **list is from the server**, and the page never retries a refused cancel-all on its own | It asks again, with the fresh list | *lists what the server says is live* · *when the list had gone stale…* |
| The **reason is optional**, and goes in the Activity Log and the notice — **not** `decision_notes` | That field is Venue Staff's; it would read as if they had given it | `…the_reason_is_optional_and_is_kept_in_the_log_and_the_notice` · `…a_reason_is_optional_and_goes_on_each_bookings_record` |
| **Venue Staff, and nobody else, are told** — not the Coordinator who did it, another Coordinator, the Organiser, Technical Support or an Attendee | DoD §3: no notification outside the intended recipients | `…nobody_outside_venue_staff_is_told` |
| A **venue change tells Venue Staff about both venues**, each person once | The old venue's staff learn it was withdrawn; the new venue's staff learn of the request | `…changing_the_venue_tells_venue_staff_both_venues` · `…a_venue_change_tells_the_staff_of_both_venues_once_each` |
| The **Activity Log** line has the actor, the time, the venue and the change, and the **same status before and after** | DoD 11a/§4: it is a log line, not a status change | `…the_activity_log_records_who_what_and_when` · `…the_log_line_leaves_the_events_status_as_it_was` |
| A **refused action writes nothing**: no log line, no notice | Every rule is checked before anything is changed | the `_nothing_happened` check in every refusal test |
| **Repeats are harmless**: a second cancel or change is refused and adds nothing | DoD §3 idempotency | `…cancelling_twice_is_refused_and_does_nothing_more` · `…confirming_twice_is_refused_the_second_time` |
| **Only the event's own Coordinator.** Not yours and does not exist look the same (404) | W7 #5; ids cannot be probed | `…another_coordinators_event_is_not_found` · `…only_a_coordinator_may_change_or_cancel` (6 other roles, 403) · `…an_anonymous_caller_is_unauthenticated` |

### Object-oriented structure, and how it is tested

| Class | Responsibility | Unit-tested in |
|---|---|---|
| `VenueBookingChangeService` | The rules and the orchestration: change one, cancel one, cancel the listed ones. Given its collaborators; commits nothing — the route does | `test_venue_booking_change_service.py` — no web layer |
| `BookingChange` (value object, immutable) | The venue and each need, before and after: whether anything changed, which fields, and the change in words | the `BookingChange` tests |
| `VenueStaffRecipients` (abstract) · `AllVenueStaff` | **Who is told.** Today everyone with the role; no document assigns staff to venues | `…recipients_cannot_be_used_without_saying_who` · `…all_venue_staff_is_every_venue_staff_member_and_nobody_else` |
| *`StaffOfOneVenue` (tests)* | A second rule — only the staff given for a venue. **Polymorphism**: the service tells exactly whoever it is handed | `…the_service_tells_exactly_the_people_it_is_handed` |
| `ActivityLog` (abstract) · `EventHistoryLog` | **Where the record goes.** The real one writes the Event's status history | `…the_event_history_log_writes_a_line_that_changes_no_status` · `…the_service_records_through_the_log_it_is_handed` |
| `DomainError` → `NotFound` · `Conflict` · `InvalidInput` | Existing; the one error handler maps them to HTTP | every refusal test |

Locks are taken in the order the rest of the venue code uses — the event, then
venues by id, then the booking — so none of them can deadlock on another. The
routes are thin: sweep expired holds, call the service, commit, shape the reply.

## Traceability

### AC1 — cancel one booking

| Test | Level |
|---|---|
| Cancels only that one; the others unchanged · a pending, held or approved booking can be cancelled · the event is not cancelled or moved on · it no longer holds the venue · a conflict flag clears · withdrawn from the event's arrangements · reason optional, kept in the log and notice, not `decision_notes` | pytest (API) |
| Rejected / cancelled cannot be cancelled · cancelling twice · outside planning (every other event status) | pytest (API) |
| Cancels that booking and leaves the rest · history cannot be cancelled · outside the window · another Coordinator's | pytest (unit) |
| Cancel offered on live bookings only · asks first, naming the venue, sends nothing · keep booking · cancels only that one · reason sent · actions leave a cancelled booking · server's reason · unreachable server | Vitest |

### AC2 — change one booking

| Test | Level |
|---|---|
| New venue, or a changed layout / accessibility / facilities, returns only that booking to Pending · the old decision is cleared · pending stays pending and is in the queue · a hold is dropped · does not count as approved until approved again, and does again once approved · time ignored · identity kept · blank need · the event is not moved on | pytest (API) |
| Refused: a venue the event has · unknown / inactive · nothing changed (4 forms) · the same change twice · rejected / cancelled · outside planning | pytest (API) |
| `BookingChange` (empty, venue, need, order, summary, "as the event says", unchanged left out, immutable) · returns to Pending, no time, nothing-changed, history, commit-free | pytest (unit) |
| Form opens filled in · venue choices (active, not another live booking's, a cancelled one's) · no time field · warning per status · nothing to save until changed · sends only what changed (venue / need / emptied → null) · shows that booking pending, others as they were · closes, says it went to Venue Staff, refreshes the page · server's reason · unreachable server · discard | Vitest |

### AC3 — cancel all, listed first, confirmed again

| Test | Level |
|---|---|
| The list is the live bookings, in order · listing changes nothing · confirming cancels those and only those · the event stays but has no venue · a request without the list cancels nothing · stale / no-longer-live / another event's id → 409, nothing cancelled · nothing to cancel · confirming twice · reason · outside planning | pytest (API) |
| Needs exactly the list shown · cancels each listed booking · the live list | pytest (unit) |
| A first question, nothing listed or sent · then the list, from the server, and ask again · exactly the listed ids sent · reason · keep / go back send nothing · empty list offers no confirm · stale → message, fresh list, asked again, **not retried** · unreachable server | Vitest |
| Cancelling all at once, many times · | Postgres (not run here) |

### AC4 — Venue Staff told, Activity Log

| Test | Level |
|---|---|
| Cancelling tells every Venue Staff member once · a venue change names both venues · a need change says what changed · **nobody else** is told · the log has who, what and when · same status before and after · cancel-all logs and tells per booking | pytest (API) |
| Tells exactly the people it is handed · both venues' staff, once each · the right kind of notice · records through the log it is handed · a refusal records and tells no one | pytest (unit) |
| Page refreshed after each change, so the Activity Log it shows is current | Vitest |

## Related, not in this story

| Item | Why it matters here |
|---|---|
| **A booking's time following the event's.** Booking times are copied once, at request; an approved change to the event's date or time updates the event but not its bookings (equipment follows the event live). Agreed rule: an approved date or time change sends the event's live bookings back to Pending, tells Venue Staff and logs it. | AC2's "no time" depends on it. A separate preparatory piece of work. |
| **A replacement venue after the Safety Check** (W7 #2). Requesting is limited to planning, so a Coordinator cannot request a replacement once the event is past it. | Changing and cancelling share that window on purpose, and a test pins it. |
| **"Hold Expired" and "Venue Unavailable"** are DoD 11c statuses; an expired hold is stored as `cancelled`. | "Cancelled" here means the Coordinator cancelled it; the Activity Log note says which. |
| **Venue Staff assigned to venues.** No document defines it. | `VenueStaffRecipients` is where a per-venue rule would go. |

Fixed along the way: the request form treated only pending and approved venues
as taken, so a venue with a tentative hold could be ticked again and was then
refused by the server. It now treats held ones as taken too.

## Manual test — TC-VB-M1

Needs an event in **Planning Event** with three live bookings (one approved, one
pending, one held), its Coordinator, and Venue Staff (`staff@…`).

| # | Step | Expected |
|---|---|---|
| 1 | As the Coordinator, open the event → **Venue bookings** | Each live booking has **Change** and **Cancel booking**; a rejected or cancelled one has neither. **Cancel all venue bookings** is shown |
| 2 | **Change** the approved booking | A form opens under it: its venue and needs filled in, **no time field**, and "This booking will go back to Pending and will not count as approved until Venue Staff approve it again." **Save change** is disabled |
| 3 | Choose another venue (the event's other venues are not offered) → **Save change** | "Sent back to Venue Staff for review." That booking reads **Pending review** at the new venue; the other two are unchanged |
| 4 | As Venue Staff, open the booking queue | The changed booking is there; a notice names the old and the new venue |
| 5 | As the Coordinator, open the event's Activity Log | One line: who changed which booking, from what to what. The event's status is unchanged |
| 6 | **Cancel booking** on the pending one → **Keep booking** | Nothing happens |
| 7 | **Cancel booking** again → type a reason → **Yes, cancel booking** | That booking reads **Cancelled**, with no actions; the other two are unchanged. Venue Staff are notified (with the reason); a new Activity Log line |
| 8 | **Cancel all venue bookings** → **Keep bookings** | Nothing happens |
| 9 | **Cancel all venue bookings** → **Continue** | A second dialog lists the remaining live bookings and asks again |
| 10 | In another window, request one more venue for the event, then **Cancel all these bookings** | Refused: the bookings changed since the list was shown. The list is refreshed to include the new one, and it asks again. Nothing was cancelled |
| 11 | **Cancel all these bookings** | Every live booking reads **Cancelled**; one log line and one notice per booking. The event is still in Planning Event, and is no longer ready: it has no venue |
| 12 | As another Coordinator, try the same event's bookings | Not found |
| 13 | As the Organiser, Technical Support or an Attendee | Refused; none of them is ever notified |
| 14 | Send the event to the Safety Officer (every booking approved), then try to change or cancel a booking | Refused, naming the status; the page does not offer it |
| 15 | Toggle dark mode | The change form, both dialogs and the notice stay legible |

## Note for the Week 13 Q&A

- **Why can't a booking's time be changed?** It is the Event's, so it can never
  disagree with what the Organiser asked for (W4 p5). A single room moving is a
  *venue* change; the date and time belong to the event.
- **How is "confirm again" enforced?** The server is sent the ids that were
  listed and refuses unless the live bookings are still exactly those. A
  request without the list cannot cancel anything, so the second confirmation
  is not just a dialog.
- **Who is told?** All Venue Staff, because nothing in the documents assigns
  staff to venues and their queue already shows every venue. The rule is one
  small class, `VenueStaffRecipients`, so a per-venue rule is a new subclass
  and not a change to the service.
- **Why can't it be done after the Safety Check?** The DoD requires every
  booking to be Approved before the check, and the check judges the arrangement
  as it stands. A send-back returns the event to planning. The window is shared
  with requesting a venue, and a test fails if the two drift apart.
