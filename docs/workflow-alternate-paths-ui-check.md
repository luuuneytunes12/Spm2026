# Workflow alternate paths: UI check

Each step of the event workflow (Week 1 briefing, Section 5, with the Week 7 changes) was driven through the screens with Playwright, signed in as the role that does that step. The main path comes first in each table, then its alternatives.

**Environment.** Local stack only: web `localhost:5175`, API `localhost:8011`, a throwaway Postgres (`cs-happypath-pg`, port 5434) seeded from `backend/db/schema.sql` and `backend/sql/*seed*`. Accounts: the team demo accounts (`event_org`, `event_coord`, `event_coord_lead`, `ven_staff`, `tech_supp`, `safety_officer`, `attend`), plus `other_org`, `event_coord2` and a self-registered Attendee for the access, reassignment and capacity cases. The shared Supabase project was not touched.

**How results were judged.** Every action under test was done through the UI. The API was only read, to look up ids and confirm statuses. Two cases needed time travel that the UI cannot do; the database was changed directly for them and they are marked *[DB]*: a tentative hold past its expiry, and an event whose end time has passed.

| Result | Meaning | Count |
|---|---|---|
| ✅ PASS | Works as the documents describe | 65 |
| 🟡 PARTIAL | Some of it works; the gap is in the Evidence column | 7 |
| ❌ FAIL | The behaviour exists but did not do what the documents describe | 4 |
| ⛔ NOT SUPPORTED | No screen or action for it | 6 |
| ℹ️ ASK CUSTOMER | The documents leave the rule open; observed behaviour recorded | 1 |

## 1. Organiser drafts an Event Request

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Organiser fills in requirements and saves a draft | Saved; listed under Drafts as "Draft" | ✅ PASS | Drafts tab row: "A1 Draft Summit B Feb 1, 2027, 10:00 AM – 12:00 PM · 60 attendees · conference Draft Continue editing →" |
| Incomplete draft saved, reopened later and finished | Saved with only some fields; reopens with them; completed fields persist | ✅ PASS | reopened: purpose="Captured over time", attendees blank=true; after completing and reopening: attendees=45 |
| Draft edited several times before submission | Each save kept; last edit wins; then submits | ✅ PASS | after 3 saves attendees=70; submitted row: "A1 Incomplete Draft Feb 2, 2027, 10:00 AM – 12:00 PM · 70 attendees · conference Submitted – Awaiting Coordinator View → Request changes →" |

## 2. Organiser submits the request

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: complete request submitted -> unassigned queue (W7 #5) | "Submitted – Awaiting Coordinator"; in Lead queue with no Coordinator | ✅ PASS | organiser row: "A2 Partner Conference Feb 3, 2027, 10:00 AM – 12:00 PM · 60 attendees · conference Submitted – Awaiting Coordinator View → Request changes →"; Lead queue: "A2 Partner Conference Feb 3, 2027, 10:00 AM – 12:00 PM · conference · 60 attendees · Organiser: Olivia Organiser · Submitted Nov 1, 2026, 1:28 AM · Coordinator: not yet assigned Submitted – Awaiting Coordinator Review →" |
| Incomplete request submitted | Blocked; missing fields flagged; stays a Draft | ✅ PASS | alert: "Cannot submit yet — 7 required fields are incomplete. They are marked below."; 7 fields marked invalid; listed in Drafts=true |
| Duplicate: same request submitted twice | No way to submit it again | ✅ PASS | submitted request page has no Submit control (buttons: []) |
| Duplicate: a second identical request (same name, date, organiser) | Flagged or blocked as a possible duplicate | ❌ FAIL | no duplicate warning; organiser now has 2 submitted requests named "A2 Partner Conference" on the same date |

## 3. Lead assigns an Event Coordinator (W7 #5)

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Lead reviews basic details and assigns a Coordinator | Under Review; Coordinator (and Organiser) notified | ✅ PASS | basic details shown=true; status=under_review; Coordinator notified=true; Organiser notified of coordinator=true |
| Lead reassigns the Event to another Coordinator | New Coordinator gets it and is notified; old one loses it and is told | ✅ PASS | Lead sees "Reassigned to Priya Coordinator. The status and history are unchanged."; Priya's list has it=true, notified=true; Sam sees "'A2 Partner Conference' that was initially assigned to you by the Event Coordinator Lead has been reassigned to Priya Coordinator. ← Back to" |
| A Coordinator tries to manage an Event not assigned to them | No management controls; cannot reach the Lead queue | ✅ PASS | Sam on Priya's event: no controls ([]), sees "'A2 Partner Conference' that was initially assigned to you by the Event Coordinator Lead has been reassigned to Priya Co"; Lead queue redirected to /forbidden ("403 No Access This page belongs to a different role. If you think that's wrong, ask an Event Organiser to check your acc") |
| Lead views all assignments and active Events | Every active Event with its Coordinator; filter by Coordinator | ✅ PASS | 1 active Event; reassigned event shown with Priya; Priya filter keeps it=true |

## 4. Coordinator reviews and asks for clarification

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: details are clear and the Coordinator moves on | Approve available straight away, no clarification needed | ✅ PASS | Coordinator's decision buttons: ["Approve request","Reject request","Send clarification request"] |
| Coordinator asks for clarification; Organiser replies | Awaiting Organiser Reply; Organiser notified; reply returns it to Under Review | ✅ PASS | after asking: awaiting_organiser_reply; Organiser notified=true, sees question=true; after reply: under_review |
| Coordinator asks for an amendment; Organiser updates the request | Organiser edits fields in the reply; request updated | ✅ PASS | attendance after reply=90; coordinator page shows 90=true |
| Several rounds of clarification | Every question and reply kept, in order | ✅ PASS | positions of the 6 messages on the Coordinator page: 523, 599, 713, 783, 859, 942 (all present and ascending = in order) |

## 5. Coordinator approves the request for planning

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Coordinator approves the request for planning | "Event Approved"; Organiser notified | ✅ PASS | status=event_approved; Organiser page shows "Event Approved"=true; notified=true |
| Request rejected; decision kept on record | Reason required; Rejected; Organiser sees reason in the record | ✅ PASS | Reject disabled while reason blank=true; status=event_rejected; Organiser sees reason=true; who/when in Activity Log=true; notified=true |
| Request returned to the Organiser; decision kept on record | A "Return to Organiser" decision, recorded | 🟡 PARTIAL | No "Return" control. Decision buttons: ["Approve request","Reject request","Send clarification request"]. The nearest is "Send clarification request" (Awaiting Organiser Reply, kept in the thread) |

## 6. Coordinator looks for a Venue

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Coordinator finds a Venue that fits date, time, capacity, layout, accessibility, facilities | Search lists it; suitability check passes | ✅ PASS | search (60 people, 2 Mar 10:00-12:00) listed 8 venues incl. Bayfront; check: "Suitable for B6 Leadership Seminar capacity: Pass Capacity is sufficient. Required: 60 people; available: 300 people layout: Pass Layout 'Theatre' is supported. Required: Theatre; available: Theatre, Classroom accessibility: Pass Accessibility feature 'Wheelchair access' is available. Required: Wheelchair access; available: Whee" |
| Attendance is more than the Venue capacity, so the Venue is not suitable | Harbourfront (80) not suitable for 100; search with 100 hides it | ✅ PASS | search for 100 people hid Harbourfront; check: "Not suitable for B6 Big Town Hall capacity: Needs attention Insufficient capacity: Capacity 80 < attendance 100. Required: 100 people; available: 80 people How to resolve: Choose a venue with enough capacity, or correct the event attendance if it is inaccurate. layout: Pass Layout 'Classroom' is supported. Required: Classroom; a" |
| (extra) Attendance exactly equals capacity (80 at an 80-seat room) | Suitable: attendance does not exceed capacity | ✅ PASS | check: "Suitable for B6 Exact Fit Workshop capacity: Pass Capacity is sufficient. Required: 80 people; available: 80 people layout: Pass Layout 'Classroom' is supported. Required: Classroom; available: Classroom, U-shape, Boardroom accessibility: Pass Accessibility feature 'Wheelchair access' is available. Required: Wheelchair access; a" |
| Layout, accessibility or facilities do not match | Each mismatch reported; Not suitable | ✅ PASS | Banquet / Hearing loop / Catering kitchen vs Harbourfront: "Not suitable for B6 Gala Dinner capacity: Pass Capacity is sufficient. Required: 60 people; available: 80 people layout: Needs attention Unsupported layout: 'Banquet' is not offered by this venue. Required: Banquet; available: Classroom, U-shape, Boardroom How to resolve: Choose a layout this venue supports, or ask Venue Staff to update the venue layout list if it is incomplete. accessibility: Needs attention Missing accessibility featu |
| Time is outside the Venue operating hours | Harbourfront (Mon-Fri 08:00-18:00) flagged for Mon 19:00-21:00 | ❌ FAIL | check: "Suitable for B6 Evening Mixer capacity: Pass Capacity is sufficient. Required: 40 people; available: 80 people layout: Pass Layout 'Classroom' is supported. Required: Classroom; available: Classroom, U-shape, Boardroom accessibility: Pass Accessibility feature 'Wheelchair access' is available. Requi" (no operating-hours line); search for Mon 19:00-21:00 still lists Harbourfront=true |
| Venue is blocked for maintenance / renovation / safety / internal use | Venue Staff block it; it is excluded or flagged for that time | ✅ PASS | Venue Staff saved a Maintenance period ("Unavailable period saved. No existing bookings conflict."); search for that date/time hid Jurong Auditorium; venue-page check: "Suitable for B6 Blocked Venue Talk capacity: Pass Capacity is sufficient. Required: 100 people; available: 250 people layout: Pass Layout 'Theatre' is supported. Required: Theatre; available: Theatre accessibility: Pass " |
| Time overlaps an existing booking | Search hides it / check flags the conflict; double request blocked or flagged | ✅ PASS | search for 11:00-13:00 hid Bayfront (booked 10:00-12:00); venue-page check: "Suitable for B6 Overlapping Event capacity: Pass Capacity is sufficient. Required: 60 people; available: 300 people layout: Pass Layout 'Theatre' is supported. Required: Theatre; available: Theatre, Classroom accessibility: Pass Accessibility feature 'Wheelcha" |
| (W7 #1) Venue Staff configure setup and turnaround time | Saved; occupied window = start - setup to end + turnaround | ✅ PASS | "Setup and turnaround times saved. No existing bookings conflict."; page: "Venue occupied From the Event start minus 30 minutes to the Event end plus 45 minutes Setup time (minutes) Whole minutes, 0 or more" |
| (W7 #1) Event times do not overlap but setup/turnaround does (10:00-12:00 +30/+45 occupies 09:30-12:45) | The 12:30 event is flagged as conflicting | ✅ PASS | first booking shows "Event 10:00-12:00 \| Setup 09:30-10:00 \| Turnaround 12:00-12:45"; search 12:30-14:00 lists Raffles=false; check: "Suitable for B6 Afternoon Training capacity: Pass Capacity is sufficient. Required: 40 people; available: 50 people layout: Pass Layout 'Classroom' is supported"; request: "Still outstanding: Venue booking 'Raffles Place Training Studio' is not approved (status: pending) \| Combined capacity: 0 / 40 required · Combined capacity is 0; it must exceed 40 attendees. \|  |
| (W7 #3) The Event needs several Venues; each is checked on its own | Two bookings, each with its own suitability result | ✅ PASS | Venue suitability Each active venue booking is checked separately against its own attendance and needs. Combined capacity is checked separately and must exceed expected attendance. Marina Grand Ballroom: Suitable Attendance checked: 250 capacity: Capacity is sufficient. Required: 250 people; available: 600 people. layout: Layout 'Theatre' is supported. Required: Theatre; available: Theatre, Banquet, Classroom, Cocktail. accessibility: Accessibility feature 'Wheelchair access' is available. Requi |

## 7. Coordinator requests the Venue; Venue Staff decide

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Venue Staff approve the booking | Approved; Coordinator notified; event shows it | ✅ PASS | coordinator sees "Bayfront Conference Hall A · Mar 29, 2027, 10:00 AM – 12:00 PM · Approved"; notified=true |
| Rejected with a reason | Rejected; Coordinator sees the reason | ✅ PASS | coordinator sees "Bayfront Conference Hall A · Mar 31, 2027, 10:00 AM – 12:00 PM · Rejected Event 10:00-12:00 \| Setup 10:00-10:00 \| Turnaround 12:00-12:00 Reason Hall booked for internal audit Decided Nov 1," |
| Rejected with an alternative Venue or arrangement suggested | Coordinator sees the suggestion | ✅ PASS | coordinator sees: "Bayfront Conference Hall A · Apr 2, 2027, 10:00 AM – 12:00 PM · Rejected Event 10:00-12:00 \| Setup 10:00-10:00 \| Turnaround 12:00-12:00 Reason Stage under repair Suggested alternative Jurong Innovation Hub Auditorium, same time Decided Nov 1, 2026, " |
| Two requests for the same Venue and time: double-booking prevented | Only one can be approved | ✅ PASS | request for B: "Still outstanding: Venue booking 'Bayfront Conference Hall A' is not approved (status: pending) \| Combined capacity: 0 /"; Venue Staff on B: Approve disabled; card: "B7 Double Booking B Conflict · B7 Double Booking A · overlap 10:00–12:00 Venue Bayfront Conference Hall A — 10 Bayfront Ave, Marina Bay, Level 4 Date and time Apr 6, 2027, 10:00 AM – 12:00 PM Effectiv"; B's booking status=pending |
| (W7 #3) Several Venues: one approved, another rejected | Each decided on its own; the approved one stays | ✅ PASS | "Bayfront Conference Hall A · Apr 9, 2027, 10:00 AM – 12:00 PM · Approved" / "Suntec Exhibition Hall 3 · Apr 9, 2027, 10:00 AM – 12:00 PM · Rejected" |
| (W7 #4) Tentative hold; action finished before expiry: hold becomes a booking | Hold with expiry + required action, then approved | ✅ PASS | hold: "Tentative hold placed for Bayfront Conference Hall A until Nov 4, 2026, 1:34 AM. Required action: Confirm final headcount. The Coordinator has been notified. \| "; coordinator sees "Bayfront Conference Hall A · Apr 13, 2027, 10:00 AM – 12:00 PM · Tentative Hold Event 10:00-12:00 \| Setup 10:00-10:00 \| Turnaround 12:00-12:00 Held until Nov 4,", notified=true; approve: "Approved: Bayfront Conference Hall A for B7 Tentative Hold Kept. Sam Coordinator can now see the dec"; booking=approved |
| (W7 #4) Tentative hold not finished by expiry: hold expires, Venue freed | After expiry: Hold expired; Coordinator told; venue requestable by others [expiry simulated in DB] | ✅ PASS | lapsed booking=hold_expired; coordinator sees "Bayfront Conference Hall A · Apr 15, 2027, 10:00 AM – 12:00 PM · Hold Expired Event 10:00-12:00 \| Setup 10:00-10:00 \| Tu"; expiry notification=true; another event could request Bayfront for that slot -> pending ("Still outstanding: Venue booking 'Bayfront Conference Hall A' is not approved (status: pending) \| Co") |
| (W7 #4) An expired hold is never treated as a confirmed booking | Expired-hold event cannot go to the Safety Check | ✅ PASS | status stays planning_event; "Still outstanding: The event has no venue: no venue booking has been requested, or all were cancelled \| Cannot submit yet. Outstanding: The event has no venue: no venue booking has been requested, or all were cancelled. " |

## 8. Tech Support reviews equipment and support

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: enough equipment is available and it is reserved | Availability shown; Reserve succeeds; event shows Reserved | ✅ PASS | check: "8 of 8 Sennheiser XSW-D Lapel Microphone available for Apr 20, 2027, 10:00 AM – 12:00 PM. Enough stock for the 4 this event requires."; after reserve: ""; organiser sees reserved=true |
| The Event needs no equipment, so this step is skipped | Can go to the Safety Check with venue only | ✅ PASS | status=awaiting_safety_check |
| Equipment already reserved for another Event at the same time | Second event sees none free and cannot reserve | ✅ PASS | A: "3 of 3 Blackmagic ATEM Mini Pro available for Apr 26, 2027, 10:00 AM – 12:00 PM. Enough stock for the 3 this event requires." reserved=true; B: "0 of 3 Blackmagic ATEM Mini Pro available for Apr 26, 2027, 10:00 AM – 12:00 PM (3 reserved for overlapping events). Insufficient stock: this event requires 2, only 0 available." reserved=false "0 of 3 Blackmagic ATEM Mini Pro available for Apr 26, 2027, 10:00 AM – 12:00 PM (3 reserved for overlapping events). Ins" |
| The equipment is at another Venue/location | Location shown or flagged to Tech Support | 🟡 PARTIAL | reservation screen shows store location=false; check message: "6 of 6 Owl Labs Meeting Owl 3 available for Apr 29, 2027, 10:00 AM – 12:00 PM. Enough stock for the 2 this event requires.". No rule flags that it is stored away from the event venue (Bayfront) |
| The equipment is damaged or under maintenance | Not available; cannot be reserved | ✅ PASS | damaged mixer: "0 of 2 Behringer X32 Mixing Console available for May 3, 2027, 10:00 AM – 12:00 PM. Insufficient stock: this event requires 1, only 0 available." -> saved as reserved=false; maintenance projector: "0 of 4 BenQ MW612 Projector available for May 3, 2027, 10:00 AM – 12:00 PM. Insufficient stock: this event requires 1, only 0 available." -> reserved=false. Note: the Reserve button stays clickable even though nothing can be reserved |
| Not enough quantity is available | Shortfall shown; cannot reserve | ✅ PASS | "5 of 5 Logitech Rally Bar available for May 5, 2027, 10:00 AM – 12:00 PM. Insufficient stock: this event requires 8, only 5 available." -> saved as reserved=false; message after clicking Reserve: "5 of 5 Logitech Rally Bar available for May 5, 2027, 10:00 AM – 12:00 PM. Insufficient stock: this event requires 8, only 5 available. \| Onl" |
| The Event needs on-site technical support, so Tech Support Staff are assigned | A way to request and assign Tech Support Staff | ⛔ NOT SUPPORTED | no control to request on-site support or assign Tech Support Staff; Coordinator can only add equipment requirements; Tech Support menu: ["Equipment Catalogue","Equipment Reservations","Notifications","My Profile"] |

## 9. Safety Officer runs the Operational Safety Check (W7 #6)

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: venue and equipment confirmed; Safety Officer approves; Event moves on | Awaiting Safety Check, then Safety Check Passed (Event Confirmed); people notified | ✅ PASS | awaiting_safety_check -> listed for Safety Officer=true; review shows capacity/layout/emergency access/equipment=true; -> safety_check_passed; Coordinator notified=true, Organiser notified=true |
| Event sent for Safety Check before Venue/equipment confirmed: not allowed | Blocked with what is outstanding; never reaches Safety Officer | ✅ PASS | status stays planning_event; message: "Still outstanding: Venue booking 'Bayfront Conference Hall A' is not approved (status: pending) \| Cannot submit yet. Outstanding: Venue booking 'Bayfront Conference Hall A' is not approved (status: pe" |
| Safety Officer rejects the safety arrangement | Rejected with reason; Coordinator told; event does not proceed | ✅ PASS | status after reject=planning_event; Coordinator notified with reason=true; Coordinator page shows reason=true |
| Safety Officer requests changes: Event returns to planning; affected venue/equipment reviewed again | Planning Event; marked booking sent back for review; Coordinator told | ✅ PASS | status=planning_event; Coordinator notified=true; booking status=approved; Venue Staff queue shows it for safety re-review=false |
| Someone tries to move the Event to preparation without Safety Officer approval | No registration / completion while not passed | ✅ PASS | buttons: ["Submit for Safety Check"]; registration says "Registration can be opened once the Safety Officer has approved this event." |
| Event resubmitted after changes, and it passes | Venue re-approved, resubmitted, approved | ✅ PASS | resubmit -> awaiting_safety_check ; -> safety_check_passed; decision history lists both=true |

## 10. Event preparation

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Venue Staff and Tech Support update their preparation progress | A preparation status they can update | ⛔ NOT SUPPORTED | no preparation-progress control for Venue Staff (buttons: ["Calendar","List","B6 Overlapping Event\nMar 17 · 11:00–13:00\nConflict","B7 Double Booking B\nApr 6 · 10:00–12:00\nConflict","B7 Takes Freed Venue\nApr 15 · 10:00–12:00","C9 Premature Safety\nApr 6 · 10:00–12:00\nConflict","C9 Safety Rejected\nApr 7 · 10:00–12:00","B6 Afternoon Training\nMar 22 · 12:30–14:00\nConflict"]) or Tech Support reservations |
| Some arrangements still incomplete; Coordinator can see what is outstanding | Outstanding items listed | ✅ PASS | "Still outstanding: Venue booking 'Bayfront Conference Hall A' is not approved (status: pending) " |

## 11. Coordinator confirms the Event

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: essential arrangements done; Organiser sees the confirmed arrangements | Organiser sees confirmed status, venue, equipment, safety result | ✅ PASS | "Planning progress Venue bookings Bayfront Conference Hall A · Approved Apr 5, 2027, 10:00 AM – 12:00 PM Equipment Sennheiser XSW-D Lapel Microphone × 2 · Reserved Safety Check Safety Check: Passed ". Note: confirmation happens when the Safety Check passes; there is no separate Coordinator "Confirm" button |
| Coordinator tries to confirm while arrangements are incomplete | Blocked, outstanding items listed | ✅ PASS | "Still outstanding: Venue booking 'Bayfront Conference Hall A' is not approved (status: pending) \| Cannot submit yet. Outstanding: Venue booking 'Bayfront Conference Hall A' is not approved (status: pe" |

## 12. Attendee registration

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Attendee registers during the registration period | Registered; appears in My Registrations and the attendee list | ✅ PASS | save: "Registration settings saved."; row: "C12b Open Registration Talk Aug 2, 2027, 10:00 AM – 12:00 PM Registration: Oct 31, 2026, 1:39 AM – Nov 8, 2026, 1:39 AM Registered Withdraw"; in My Registrations=true; on Coordinator's attendee list=true; Attendee notified=true |
| The Event does not need registration | Not offered to Attendees for registration | ✅ PASS | listed on Attendee Events page=false |
| Someone tries to register before registration opens or after it closes | No Register button; told it is not open / closed | ✅ PASS | before open: "C12b Not Yet Open Aug 4, 2027, 10:00 AM – 12:00 PM Registration: Nov 3, 2026, 1:40 AM – Nov 10, 2026, 1:40 AM Registrati" (Register buttons=0); after close: "C12b Already Closed Aug 5, 2027, 10:00 AM – 12:00 PM Registration: Oct 23, 2026, 1:40 AM – Oct 30, 2026, 1:40 AM Registr" (Register buttons=0) |
| Registration reaches capacity; further registrations blocked | Second registration refused once full (event for 1 person) | ❌ FAIL | expected attendance 1; second attendee after Register: C12b Tiny Capacity Class Aug 6, 2027, 10:00 AM – 12:00 PM Registration: Oct 31, 2026, 1:40 AM – Nov  ; registered count now 2 |
| An Attendee joins the waiting list when the Event is full | Waiting-list option once full | ⛔ NOT SUPPORTED | no waiting-list option anywhere on the Attendee screens (registration status is only Registered / Withdrawn) |
| An Attendee withdraws; place released; next on waiting list takes it | Withdrawn; can register again; count drops | 🟡 PARTIAL | row: "C12b Open Registration Talk Aug 2, 2027, 10:00 AM – 12:00 PM Registration: Oct 31, 2026, 1:39 AM – Nov 8, 2026, 1:39 AM "; Coordinator list: "Registered attendees 0 registered Amy Attendee Withdrawn Edit event details Event name Description Event contact name Event contact email Ev". Place released, but no waiting list to promote anyone |

## 13. Changes before the Event

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Organiser requests a change (after confirmation); Coordinator reviews its impact | Organiser has a "Request changes" control on a confirmed event | ❌ FAIL | Organiser controls on a confirmed event: ["event_coord@cs.local","← Back to my requests"] (the backend accepts change requests in this status, but the screen offers none) |
| (variant) Organiser requests a change while Under Review; Coordinator reviews and approves it | Change request with reason; Coordinator sees it and approves | ✅ PASS | Coordinator sees: "Change requests Pending change requestImportant change More partners confirmed Expected attendance 75 Existing arrangements to reconsider No venue bookings need review. No equipment reservations need review. Review notes Approve changes Rej"; after Approve changes attendance=75. Only possible before approval (see MAIN row) |
| Date or time changes and causes a Venue or equipment conflict | Moved booking re-reviewed and the clash shown (or change blocked) | ✅ PASS | after the Coordinator moved the confirmed event onto event B's date: event status=planning_event, booking back to pending for Venue Staff; their card: "D13 Date Move A Conflict · D13 Date Holder B · overlap 10:00–12:00 Venue Bayfront Conference Hall A — 10 Bayfront Ave, Marina Bay, Level 4 Date and time Sep 9, "; Approve disabled=true |
| Attendance goes up (80 -> 150), so the Venue is no longer suitable | Coordinator sees Harbourfront (80) is now not suitable / flagged | ✅ PASS | save: "Still outstanding: Venue booking 'Harbourfront Seminar Room 2' is not approved (status: pending) \| Combined capacity: 80"; suitability: "Venue suitability Each active venue booking is checked separately against its own attendance and needs. Combined capacity is checked separately and must exceed expected attendance. Harbourfront Seminar Room 2: Not suitable Attendance checked: 150 capacity: Insufficient capacity: Capacity 80 < attend"; event status=planning_event |
| Major change approved after the Safety Check (customer to confirm the rule) | Observe: does the event need a new Safety Check? | ℹ️ ASK CUSTOMER | after raising attendance 60 -> 150 on a confirmed event, status is "planning_event" (event sent back). The briefing does not say which is right: ask the customer |
| Attendance goes down | Saved; venue still suitable; no flag | ✅ PASS | save: "Still outstanding: Venue booking 'Harbourfront Seminar Room 2' is not approved (status: pending) \| C"; suitability: "Venue suitability Each active venue booking is checked separately against its own attendance and needs. Combined capacity is checked separately and must exceed expected attendance. Harbourfront Seminar Room 2: Suitable A" |
| Extra equipment or technical support is requested | New requirement reaches Tech Support | ✅ PASS | Coordinator: ""; Tech Support requirements list shows the event=true; event status=safety_check_passed |
| Programme is extended and now cuts into the turnaround before the next booking | Extension flagged as conflicting with the next booking | ✅ PASS | save: "Still outstanding: Venue booking 'Raffles Place Training Studio' is not approved (status: pending) \| Combined capacity: 50 / 40 required · Combined capacity is 50; it must exceed 40 attendees. \| Overa"; Venue Staff flagged view lists A=true, B=false; bookings: pending, approved |
| Programme is split into several sessions | Sessions with their own times | ⛔ NOT SUPPORTED | no sessions on the event; only one start/end and a free-text programme |
| Reserved equipment becomes damaged or goes for maintenance | Tech Support can mark it; affected events flagged | ⛔ NOT SUPPORTED | Equipment catalogue has no control to change an item's condition (buttons: []) |
| (W7 #2) Booked Venue becomes unavailable: Event not cancelled, details kept, Coordinator finds a replacement | Booking flagged; Coordinator told; replacement can be requested; event intact | 🟡 PARTIAL | event still safety_check_passed (not cancelled, details kept); booking flagged=true; Coordinator notified ("Venue Unavailable - Action Required: alternative arrangements are required"). But on a confirmed event the Coordinator page hides the venue section, so there is no "Find replacement" (controls found=0). See the next row for the flow before confirmation |
| (W7 #3) One Venue booking changed or cancelled; the Event's other bookings stay | Cancelling one leaves the other approved | ✅ PASS | "Booking cancelled. Venue Staff have been told. \| Combined capacity: 900 / 200 required · Combined ca"; Bayfront Conference Hall A:approved, Marina Grand Ballroom:cancelled; event status=planning_event |
| (W7 #1) A Venue's setup or turnaround time changes; bookings that now clash are flagged, not removed | Both still booked; clash shown in Flagged | ✅ PASS | turnaround 60 -> 120: "2 bookings now conflict and were flagged. 2 existing bookings flagged for conflict; 0 flags cleared. View flagged bookin"; flagged-and-still-approved in DB=2; Flagged view lists them=true (with "Keep anyway" x0); setting it back to 60: "Setup and turnaround times saved. 0 existing bookings flagged for conflict; 2 flags cleare" |
| (W7 #2, before confirmation) Venue unavailable -> Coordinator finds and requests a replacement | Find replacement -> request another venue; original kept as history | ✅ PASS | Venue Staff: "Unavailable period saved. 1 future booking is inside this period. They are listed below and have not"; replacement: "Replacement requested at Marina Grand Ballroom. Venue Staff will see it replaces the booking at Jurong Innovation Hub Au"; bookings: Marina Grand Ballroom:pending, Jurong Innovation Hub Auditorium:approved; event planning_event |

## 14. Postponement or cancellation

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Event cancelled; Venue and equipment reservations released | Cancelled; booking released; kit back in stock; slot bookable; people told | ✅ PASS | status=event_cancelled; its booking(s)=released; another event can request the slot -> pending; ATEM check for that slot: "3 of 3 Blackmagic ATEM Mini Pro available for Sep 28, 2027, 10:00 AM – 12:00 PM."; Organiser notified=true |
| Event is postponed: rescheduled and the arrangements checked again | A postpone/reschedule action; venue and equipment re-checked for the new date | 🟡 PARTIAL | no Postpone action (buttons: ["Cancel event","Save registration settings","Save event details"]); editing the date instead: "Still outstanding: Venue booking 'Raffles Place Training Studio' is not approved (status: pending) \| Combined capacity: "; event now 2027-10-04T02:00:00Z status=planning_event; booking(s) pending |
| (W7 #3) One Venue booking is cancelled and the Event itself continues | Event status unchanged; other booking approved | ✅ PASS | "Booking cancelled. Venue Staff have been told. \| Combined capacity: 900 / 200 required · Combined ca"; status planning_event -> planning_event; Bayfront Conference Hall A:cancelled, Marina Grand Ballroom:approved |

## 15. Event delivery

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Venue Staff and Tech Support see the latest confirmed details | Both see the event with its date/time | ✅ PASS | Venue Staff (Approved): "D15 Delivery Day Oct 7 · 14:00–16:00 D13 Replace Before Confirm Nov 1 · 10:00–12:00 Harbourfront Seminar Room "; Tech Support: "D15 Delivery Day — Oct 7, 2027, 02:00 PM – 04:00 PM D13 Replace Before Confirm — Nov 1, 2027, 10:00 AM – 12:00" |
| Late change: everyone sees the updated details, not old ones | After moving the event to 14:00-16:00, Venue Staff / Tech Support / Attendee views show 14:00 | ✅ PASS | Venue Staff now: "D15 Delivery Day Oct 7 · 14:00–16:00 Harbourfront Seminar Room 2 B6 Multi Venue Conference Mar 25 · 10:00–12:00 D13 Attendance Rises Sep 14 "; Tech Support now: "10:00 AM – 12:00 PM D15 Delivery Day — Oct 7, 2027, 02:00 PM – 04:00 PM Equipment type All types Accessibility Audio Lighting Networking Pro"; booking record: 2027-10-07T06:00:00Z |

## 16. Completion

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| MAIN: Event marked completed; attendance and notes recorded; Event closed | Completed; attendance + notes captured [event end moved into the past in DB] | 🟡 PARTIAL | before the end time: "An event cannot be marked completed before its scheduled end time has passed."; after: status=event_completed; no field to record attendance, operational notes or issues (labels: ["Expected attendance","Attendees must register","Technical notes"]) |
| An Attendee registered but did not attend: registration and attendance recorded separately | Mark attended / no-show per registrant | ⛔ NOT SUPPORTED | attendee list only shows Registered / Withdrawn; there is no attendance (attended / no-show) record |

## Checks at every step

| Path | Expected | Result | Evidence (what the screens showed) |
|---|---|---|---|
| Access: an Organiser cannot see other clients' Events | Other organiser gets not-found and does not see it listed | ✅ PASS | other organiser opening the URL sees "Event not found ← Back to my requests"; their list shows it=false |
| Access: an Attendee cannot see internal planning details | Attendee event page has no internal planning info | ✅ PASS | attendee event page: "C9 Safety Main Description Full-day partner briefing Category conference Date and time Apr 5, 2027, 10:00 AM – 12:00 PM Venues Bayfront Conference Hall A, 10 Bayfront Ave, Marina Bay, Level 4 Accessib"; internal terms found: []; opening a coordinator URL -> /forbidden |
| Change history: every important change records what changed, who and when | Activity Log shows field changes (old -> new) with actor and time | 🟡 PARTIAL | who/when recorded; the entry says "Event Request update Sam Coordinator · Nov 1, 2026, 1:42 AM Event details updated: expected_attendance" -- the field name only, not the old and new values (60 -> 150 -> 30) |

## Gaps to raise

| Step | Path | Result |
|---|---|---|
| 2 | Duplicate: a second identical request (same name, date, organiser) | ❌ FAIL |
| 5 | Request returned to the Organiser; decision kept on record | 🟡 PARTIAL |
| 6 | Time is outside the Venue operating hours | ❌ FAIL |
| 8 | The equipment is at another Venue/location | 🟡 PARTIAL |
| 8 | The Event needs on-site technical support, so Tech Support Staff are assigned | ⛔ NOT SUPPORTED |
| 10 | MAIN: Venue Staff and Tech Support update their preparation progress | ⛔ NOT SUPPORTED |
| 12 | Registration reaches capacity; further registrations blocked | ❌ FAIL |
| 12 | An Attendee joins the waiting list when the Event is full | ⛔ NOT SUPPORTED |
| 12 | An Attendee withdraws; place released; next on waiting list takes it | 🟡 PARTIAL |
| 13 | MAIN: Organiser requests a change (after confirmation); Coordinator reviews its impact | ❌ FAIL |
| 13 | Major change approved after the Safety Check (customer to confirm the rule) | ℹ️ ASK CUSTOMER |
| 13 | Programme is split into several sessions | ⛔ NOT SUPPORTED |
| 13 | Reserved equipment becomes damaged or goes for maintenance | ⛔ NOT SUPPORTED |
| 13 | (W7 #2) Booked Venue becomes unavailable: Event not cancelled, details kept, Coordinator finds a replacement | 🟡 PARTIAL |
| 14 | Event is postponed: rescheduled and the arrangements checked again | 🟡 PARTIAL |
| 16 | MAIN: Event marked completed; attendance and notes recorded; Event closed | 🟡 PARTIAL |
| 16 | An Attendee registered but did not attend: registration and attendance recorded separately | ⛔ NOT SUPPORTED |
| Checks at every step | Change history: every important change records what changed, who and when | 🟡 PARTIAL |
