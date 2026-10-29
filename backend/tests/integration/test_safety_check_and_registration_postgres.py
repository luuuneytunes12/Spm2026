"""From planned Event to registered Attendee, on real PostgreSQL:

    SCRUM-65  Submit Event for Safety Check
    SCRUM-83  Review Event for Operational Safety Check as Safety Officer
    SCRUM-84  Revise Event After Safety Check Feedback as Event Coordinator
    SCRUM-88  Approve Event in Operational Safety Check
    SCRUM-89  Reject or Request Changes in Operational Safety Check
    SCRUM-66  Schedule Registration for a Confirmed Event
    SCRUM-68  View Event Catalogue
    SCRUM-47  Register for Event
    SCRUM-48  Withdraw from Event
    SCRUM-49  View Registration Status
    SCRUM-50  View Attendee List for Event
    SCRUM-51  View Attendee-Facing Event Details

The SQLite tests (tests/test_submit_for_safety_check.py, test_safety_checks.py,
test_safety_check_return.py, test_schedule_registration.py, test_open_registration.py,
test_registrations.py, test_view_attendee_list.py, test_attendee_event_view.py)
seed each status directly. These build the Event the way users do -- every
step through the API: submit, assign, approve, book and approve a venue,
record and reserve equipment, submit for the check -- so each story is proven
against the state the previous ones really leave behind on the production
engine. One registration row per Attendee per Event is a database UNIQUE
constraint; the double-clicked Register is raced against it here.
"""

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus, RegistrationStatus
from app.models.equipment import Equipment
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.registrations import Registration
from app.models.venues import Venue, VenueBooking
from tests.integration.conftest import assign_event, submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

# Relative to today so registration windows are always "now"-shaped.
NOW = datetime.now(timezone.utc).replace(microsecond=0)
START = NOW + timedelta(days=14)
END = START + timedelta(hours=8)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@pytest.fixture()
def w(client, make_user, db):
    organiser, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    coordinator, coord_h = make_user(Role.COORDINATOR, "cora@connectsphere.test", "Cora Coord")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    staff, staff_h = make_user(Role.VENUE_STAFF, "vic@connectsphere.test", "Vic Venue")
    tech, tech_h = make_user(Role.TECH_SUPPORT, "tia@connectsphere.test", "Tia Tech")
    officer, safety_h = make_user(Role.SAFETY_OFFICER, "sol@connectsphere.test", "Sol Safety")
    hall = Venue(name="Main Hall", location="Block A, Level 1", capacity=300, supported_layouts=["Theatre"],
                 accessibility_features=["Step-free access"], emergency_access="Two exits to the car park",
                 known_restrictions="No open flames")
    annex = Venue(name="Annex", location="Block A, Level 2", capacity=80)
    mic = Equipment(name="Shure BLX24", category="Audio", total_quantity=10)
    db.add_all([hall, annex, mic])
    db.commit()
    days = itertools.count()
    return SimpleNamespace(**locals())


def _approved(client, w, **fields):
    # Each further event in a test is a day later, so they never compete for the hall.
    shift = timedelta(days=next(w.days))
    event_id = submit_event(client, w.org_h, proposed_start=_iso(START + shift), proposed_end=_iso(END + shift),
                            **fields)
    assign_event(client, w.lead_h, event_id, w.coordinator.id)
    assert client.post(f"/events/{event_id}/approve", headers=w.coord_h).status_code == 200
    return event_id


def _book(client, w, event_id, venue_id, approve=True):
    res = client.post(f"/venue-bookings/events/{event_id}", json={"venues": [{"venue_id": venue_id}]},
                      headers=w.coord_h)
    assert res.status_code == 201, res.text
    booking_id = res.json()[0]["id"]
    if approve:
        assert client.post(f"/venue-bookings/{booking_id}/approve", headers=w.staff_h).status_code == 200
    return booking_id


def _equip(client, w, event_id, reserve=True):
    req = client.post(f"/equipment-requirements/events/{event_id}",
                      json={"category": "Audio", "quantity_needed": 2, "technical_notes": "Lapel mics"},
                      headers=w.coord_h)
    assert req.status_code == 201, req.text
    if reserve:
        res = client.post(f"/equipment-requirements/{req.json()['id']}/reservations",
                          json={"equipment_id": w.mic.id, "placement_notes": "Lectern, stage left"},
                          headers=w.tech_h)
        assert res.status_code == 200, res.text
    return req.json()["id"]


def _ready(client, w, **fields):
    """Approved, venue approved, equipment reserved: ready for the check."""
    event_id = _approved(client, w, **fields)
    booking_id = _book(client, w, event_id, w.hall.id)
    _equip(client, w, event_id)
    return event_id, booking_id


def _awaiting(client, w, **fields):
    event_id, booking_id = _ready(client, w, **fields)
    res = client.post(f"/events/{event_id}/confirm", headers=w.coord_h)
    assert res.status_code == 200, res.text
    return event_id, booking_id


def _confirmed(client, w, **fields):
    event_id, booking_id = _awaiting(client, w, **fields)
    assert client.post(f"/safety-checks/{event_id}/approve", headers=w.safety_h).status_code == 200
    return event_id, booking_id


def _status(db, event_id):
    db.expire_all()
    return db.get(Event, event_id).status


# --------------------------------------------------------------------------
# SCRUM-65 Submit Event for Safety Check
# --------------------------------------------------------------------------


def test_scrum65_ac1_ac6_a_ready_event_goes_to_the_check_and_is_logged(client, w, db):
    event_id, _b = _ready(client, w)
    assert _status(db, event_id) == EventStatus.planning_event  # the venue request moved it on

    res = client.post(f"/events/{event_id}/confirm", headers=w.coord_h)

    assert res.status_code == 200 and res.json()["status"] == "awaiting_safety_check"
    line = db.query(EventStatusHistory).filter_by(event_id=event_id,
                                                  to_status=EventStatus.awaiting_safety_check).one()
    assert line.changed_by == w.coordinator.id and line.created_at is not None
    told = db.query(Notification).filter_by(type="safety_check_requested").all()
    assert [n.user_id for n in told] == [w.officer.id]


def test_scrum65_ac2_no_venue_or_only_cancelled_venues_blocks_it(client, w, db):
    event_id = _approved(client, w)
    blocked = client.post(f"/events/{event_id}/confirm", headers=w.coord_h)
    assert blocked.status_code == 409 and "no venue" in blocked.json()["detail"]

    booking_id = _book(client, w, event_id, w.hall.id, approve=False)
    db.get(VenueBooking, booking_id).status = BookingStatus.cancelled
    db.commit()
    assert client.post(f"/events/{event_id}/confirm", headers=w.coord_h).status_code == 409
    assert _status(db, event_id) == EventStatus.planning_event


def test_scrum65_ac3_every_outstanding_item_is_listed_with_its_status(client, w, db):
    event_id = _approved(client, w)
    _book(client, w, event_id, w.hall.id)
    _book(client, w, event_id, w.annex.id, approve=False)
    _equip(client, w, event_id, reserve=False)

    res = client.post(f"/events/{event_id}/confirm", headers=w.coord_h)

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "Annex" in detail and "pending" in detail.lower()
    assert "Audio" in detail
    assert "Main Hall" not in detail
    assert _status(db, event_id) == EventStatus.planning_event


def test_scrum65_ac4_ac5_wrong_status_or_wrong_coordinator_is_refused(client, w, make_user, db):
    event_id, _b = _awaiting(client, w)
    assert client.post(f"/events/{event_id}/confirm", headers=w.coord_h).status_code == 409

    other_id, _b2 = _ready(client, w, name="Other")
    _x, priya_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    assert client.post(f"/events/{other_id}/confirm", headers=priya_h).status_code == 404
    assert _status(db, other_id) == EventStatus.planning_event


def test_scrum65_a_double_clicked_submit_queues_and_notifies_once(make_client, client, w, db):
    event_id, _b = _ready(client, w)

    results = race(make_client, THREADS, lambda c: c.post(f"/events/{event_id}/confirm", headers=w.coord_h).status_code)

    assert sorted(results) == [200] + [409] * (THREADS - 1)
    assert db.query(EventStatusHistory).filter_by(event_id=event_id,
                                                  to_status=EventStatus.awaiting_safety_check).count() == 1
    assert db.query(Notification).filter_by(type="safety_check_requested").count() == 1


# --------------------------------------------------------------------------
# SCRUM-83 Review Event for Safety Check
# --------------------------------------------------------------------------


def test_scrum83_ac1_ac2_the_queue_lists_waiting_events_with_name_date_and_coordinator(client, w):
    assert client.get("/safety-checks", headers=w.safety_h).json() == []

    event_id, _b = _awaiting(client, w)
    _ready(client, w, name="Not yet submitted")

    [row] = client.get("/safety-checks", headers=w.safety_h).json()
    assert row["id"] == event_id and row["name"] == "Regional Partner Conference"
    assert row["coordinator"]["name"] == "Cora Coord" and row["proposed_start"] is not None


def test_scrum83_ac3_detail_carries_attendance_venue_safety_facts_and_equipment_placement(client, w):
    event_id, booking_id = _awaiting(client, w)

    detail = client.get(f"/safety-checks/{event_id}", headers=w.safety_h).json()

    assert detail["expected_attendance"] == 120
    assert detail["accessibility_needs"] == "Step-free access, hearing loop"
    [booking] = detail["venue_bookings"]
    venue = booking["venue"]
    assert booking["id"] == booking_id and venue["capacity"] == 300
    assert venue["supported_layouts"] == ["Theatre"]
    assert venue["emergency_access"] == "Two exits to the car park"
    assert venue["known_restrictions"] == "No open flames"
    assert [(e["equipment_name"], e["placement_notes"]) for e in detail["equipment"]] == [
        ("Shure BLX24", "Lectern, stage left")]


# --------------------------------------------------------------------------
# SCRUM-88 Approve in Safety Check
# --------------------------------------------------------------------------


def test_scrum88_ac1_to_ac3_approval_confirms_notifies_everyone_once_and_is_logged(client, w, db):
    event_id, _b = _awaiting(client, w)

    res = client.post(f"/safety-checks/{event_id}/approve", headers=w.safety_h)

    assert res.status_code == 200 and res.json()["status"] == "safety_check_passed"
    told = sorted(n.user_id for n in db.query(Notification).filter_by(type="safety_check_passed"))
    assert told == sorted([w.organiser.id, w.coordinator.id, w.staff.id, w.tech.id])
    line = db.query(EventStatusHistory).filter_by(event_id=event_id,
                                                  to_status=EventStatus.safety_check_passed).one()
    assert line.changed_by == w.officer.id and line.from_status == EventStatus.awaiting_safety_check


def test_scrum88_ac4_only_an_awaiting_event_can_be_approved(client, w, db):
    event_id, _b = _ready(client, w)

    assert client.post(f"/safety-checks/{event_id}/approve", headers=w.safety_h).status_code == 409
    assert _status(db, event_id) == EventStatus.planning_event


def test_scrum88_ac6_an_arrangement_that_lapsed_meanwhile_blocks_approval(client, w, db):
    event_id, booking_id = _awaiting(client, w)
    db.get(VenueBooking, booking_id).status = BookingStatus.pending
    db.commit()

    res = client.post(f"/safety-checks/{event_id}/approve", headers=w.safety_h)

    assert res.status_code == 409 and "Main Hall" in res.json()["detail"]
    assert _status(db, event_id) == EventStatus.awaiting_safety_check


def test_scrum88_two_officers_deciding_at_once_leave_one_decision(make_client, client, w, make_user, db):
    event_id, booking_id = _awaiting(client, w)
    _o2, officer2_h = make_user(Role.SAFETY_OFFICER, "sam-safety@connectsphere.test", "Sam Safety")
    calls = iter([True, False])

    def decide(c):
        if next(calls):
            return c.post(f"/safety-checks/{event_id}/approve", headers=w.safety_h).status_code
        return c.post(f"/safety-checks/{event_id}/reject", json={"reason": "Fire exits blocked"},
                      headers=officer2_h).status_code

    assert sorted(race(make_client, 2, decide)) == [200, 409]
    decisions = db.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == event_id,
        EventStatusHistory.from_status == EventStatus.awaiting_safety_check).all()
    assert len(decisions) == 1 and _status(db, event_id) == decisions[0].to_status


# --------------------------------------------------------------------------
# SCRUM-89 Reject or Request Changes / SCRUM-84 Revise and resubmit
# --------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["reject", "request-changes"])
def test_scrum89_ac1_a_decision_without_a_reason_is_not_saved(client, w, db, action):
    event_id, booking_id = _awaiting(client, w)

    res = client.post(f"/safety-checks/{event_id}/{action}",
                      json={"reason": "  ", "venue_booking_ids": [booking_id]}, headers=w.safety_h)

    assert res.status_code == 422
    assert _status(db, event_id) == EventStatus.awaiting_safety_check


def test_scrum89_ac2_ac4_ac5_request_changes_flags_only_the_marked_item(client, w, db):
    event_id, booking_id = _awaiting(client, w)
    reason = "Stage too close to the fire exit"

    res = client.post(f"/safety-checks/{event_id}/request-changes",
                      json={"reason": reason, "venue_booking_ids": [booking_id]}, headers=w.safety_h)

    assert res.status_code == 200 and res.json()["status"] == "planning_event"
    db.expire_all()
    booking = db.get(VenueBooking, booking_id)
    assert booking.safety_recheck_reason == reason and booking.status == BookingStatus.approved  # flagged, not cancelled
    told = sorted(n.user_id for n in db.query(Notification).filter_by(type="safety_changes_requested"))
    assert told == sorted([w.organiser.id, w.coordinator.id, w.staff.id])  # tech's item was not marked
    line = db.query(EventStatusHistory).filter_by(event_id=event_id, from_status=EventStatus.awaiting_safety_check).one()
    assert reason in line.note and line.changed_by == w.officer.id


def test_scrum89_ac3_rejection_flags_every_arrangement_and_cancels_nothing(client, w, db):
    event_id, booking_id = _awaiting(client, w)

    res = client.post(f"/safety-checks/{event_id}/reject", json={"reason": "Overcrowding risk"}, headers=w.safety_h)

    assert res.status_code == 200 and res.json()["status"] == "planning_event"
    detail = client.get(f"/safety-checks/{event_id}", headers=w.safety_h).json()
    assert all(b["safety_recheck_reason"] == "Overcrowding risk" for b in detail["venue_bookings"])
    assert all(e["safety_recheck_reason"] == "Overcrowding risk" for e in detail["equipment"])
    assert all(e["status"] == "reserved" for e in detail["equipment"])
    told = {n.user_id for n in db.query(Notification).filter_by(type="safety_check_rejected")}
    assert told == {w.organiser.id, w.coordinator.id, w.staff.id, w.tech.id}


def test_scrum89_ac6_only_an_awaiting_event_can_be_sent_back(client, w, db):
    event_id, _b = _confirmed(client, w)

    assert client.post(f"/safety-checks/{event_id}/reject", json={"reason": "x"}, headers=w.safety_h).status_code == 409
    assert _status(db, event_id) == EventStatus.safety_check_passed


def test_scrum84_ac1_to_ac3_the_coordinator_sees_why_fixes_it_and_resubmits(client, w, db):
    event_id, booking_id = _awaiting(client, w)
    client.post(f"/safety-checks/{event_id}/request-changes",
                json={"reason": "Move the stage", "venue_booking_ids": [booking_id]}, headers=w.safety_h)

    detail = client.get(f"/events/assigned/{event_id}", headers=w.coord_h).json()
    sent_back = detail["safety_check_return"]
    assert sent_back["result"] == "Changes Requested" and sent_back["reason"] == "Move the stage"
    assert any("Main Hall" in item for item in sent_back["items_to_review"])
    assert client.post(f"/events/{event_id}/confirm", headers=w.coord_h).status_code == 409  # flag still open

    # Venue Staff look again and re-approve: the flag clears.
    assert client.post(f"/venue-bookings/{booking_id}/approve", headers=w.staff_h).status_code == 200
    again = client.post(f"/events/{event_id}/confirm", headers=w.coord_h)

    assert again.status_code == 200 and again.json()["status"] == "awaiting_safety_check"
    history = [(h.from_status, h.to_status) for h in db.query(EventStatusHistory).filter_by(event_id=event_id)]
    assert (EventStatus.awaiting_safety_check, EventStatus.planning_event) in history  # earlier decision kept
    assert history.count((EventStatus.planning_event, EventStatus.awaiting_safety_check)) == 2
    resubmitted = db.query(Notification).filter_by(type="safety_check_requested").order_by(Notification.id).all()
    assert "resubmitted" in resubmitted[-1].message


# --------------------------------------------------------------------------
# SCRUM-66 Schedule Registration
# --------------------------------------------------------------------------


def _open_registration(client, w, event_id, opens=None, closes=None, enabled=True):
    return client.put(f"/events/assigned/{event_id}/registration", headers=w.coord_h, json={
        "registration_enabled": enabled,
        "registration_opens_at": _iso(opens or NOW - timedelta(days=1)),
        "registration_closes_at": _iso(closes or NOW + timedelta(days=7)),
    })


def test_scrum66_ac1_dates_are_saved_as_instants_and_shown_on_the_event(client, w, db):
    event_id, _b = _confirmed(client, w)
    opens = (NOW - timedelta(days=1)).astimezone(timezone(timedelta(hours=8)))

    res = client.put(f"/events/assigned/{event_id}/registration", headers=w.coord_h, json={
        "registration_enabled": True, "registration_opens_at": opens.isoformat(),
        "registration_closes_at": _iso(NOW + timedelta(days=7))})

    assert res.status_code == 200 and res.json()["registration_enabled"] is True
    db.expire_all()
    stored = db.get(Event, event_id)
    assert stored.registration_opens_at == opens  # same instant, whatever the offset
    assert client.get(f"/events/{event_id}", headers=w.org_h).json()["registration_closes_at"] is not None


def test_scrum66_ac2_before_the_safety_check_passes_registration_stays_shut(client, w, db):
    event_id, _b = _awaiting(client, w)

    res = _open_registration(client, w, event_id)

    assert res.status_code == 409 and "Safety Officer" in res.json()["detail"]
    db.expire_all()
    assert db.get(Event, event_id).registration_enabled is False


def test_scrum66_ac3_a_lapsed_arrangement_blocks_opening(client, w, db):
    event_id, booking_id = _confirmed(client, w)
    db.get(VenueBooking, booking_id).status = BookingStatus.pending
    db.commit()

    res = _open_registration(client, w, event_id)

    assert res.status_code == 409 and "Main Hall" in res.json()["detail"]


def test_scrum66_ac4_bad_dates_are_flagged_and_nothing_is_saved(client, w, db):
    event_id, _b = _confirmed(client, w)

    backwards = _open_registration(client, w, event_id, opens=NOW + timedelta(days=3), closes=NOW + timedelta(days=1))
    after_start = _open_registration(client, w, event_id, closes=START + timedelta(hours=1))

    assert backwards.status_code == after_start.status_code == 422
    assert {d["loc"][-1] for d in backwards.json()["detail"]} == {"registration_opens_at", "registration_closes_at"}
    assert {d["loc"][-1] for d in after_start.json()["detail"]} == {"registration_closes_at"}
    db.expire_all()
    assert db.get(Event, event_id).registration_opens_at is None


def test_scrum66_ac6_another_coordinator_cannot_open_registration(client, w, make_user, db):
    event_id, _b = _confirmed(client, w)
    _x, priya_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")

    res = client.put(f"/events/assigned/{event_id}/registration", headers=priya_h,
                     json={"registration_enabled": True, "registration_opens_at": _iso(NOW),
                           "registration_closes_at": _iso(NOW + timedelta(days=1))})

    assert res.status_code == 404
    db.expire_all()
    assert db.get(Event, event_id).registration_enabled is False


# --------------------------------------------------------------------------
# SCRUM-68 Catalogue / SCRUM-51 Attendee-facing details
# --------------------------------------------------------------------------


@pytest.fixture()
def open_event(client, w):
    event_id, _b = _confirmed(client, w, description="A day with our partners", programme="09:00 Welcome")
    assert _open_registration(client, w, event_id).status_code == 200
    return event_id


@pytest.fixture()
def attendee(make_user):
    return make_user(Role.ATTENDEE, "ava@connectsphere.test", "Ava Attendee")


def test_scrum68_ac1_ac4_open_events_are_listed_with_summary_only(client, w, open_event, attendee):
    _a, ava_h = attendee
    _ready(client, w, name="Still planning")

    rows = client.get("/registrations/events", headers=ava_h).json()

    assert [r["id"] for r in rows] == [open_event]
    row = rows[0]
    assert row["registration_open"] is True and row["my_status"] is None
    assert set(row) <= {"id", "name", "proposed_start", "proposed_end", "registration_open",
                        "registration_opens_at", "registration_closes_at", "my_status"}


def test_scrum68_ac2_closed_or_cancelled_events_are_not_offered(client, w, open_event, attendee, db):
    _a, ava_h = attendee
    closed_id, _b = _confirmed(client, w, name="Closed already")
    _open_registration(client, w, closed_id, opens=NOW - timedelta(days=5), closes=NOW - timedelta(days=1))
    db.get(Event, open_event).status = EventStatus.event_cancelled
    db.commit()

    rows = {r["id"]: r for r in client.get("/registrations/events", headers=ava_h).json()}

    assert open_event not in rows
    assert closed_id not in rows or rows[closed_id]["registration_open"] is False
    assert client.post(f"/registrations/events/{closed_id}", headers=ava_h).status_code == 409


def test_scrum68_ac5_with_nothing_open_the_catalogue_is_empty(client, w, attendee):
    _a, ava_h = attendee
    assert client.get("/registrations/events", headers=ava_h).json() == []


def test_scrum51_ac1_ac2_details_are_public_facing_only(client, w, open_event, attendee):
    _a, ava_h = attendee

    detail = client.get(f"/registrations/events/{open_event}", headers=ava_h).json()

    assert detail["description"] == "A day with our partners" and detail["programme"] == "09:00 Welcome"
    assert detail["venues"] == [{"name": "Main Hall", "location": "Block A, Level 1"}]
    assert detail["registration_opens_at"] and detail["registration_closes_at"]
    leaked = {"coordinator", "coordinator_id", "status", "safety_recheck_reason", "equipment_items",
              "decision_notes", "activity"} & set(detail)
    assert leaked == set()


def test_scrum51_ac3_internal_pages_are_refused_to_an_attendee(client, w, open_event, attendee):
    _a, ava_h = attendee

    assert client.get(f"/events/assigned/{open_event}", headers=ava_h).status_code == 404
    assert client.get(f"/safety-checks/{open_event}", headers=ava_h).status_code == 403
    assert client.get(f"/venue-bookings/events/{open_event}", headers=ava_h).status_code == 403
    assert client.get(f"/registrations/events/{open_event}/attendees", headers=ava_h).status_code == 403


def test_scrum51_ac4_a_replaced_venue_shows_the_current_one(client, w, open_event, attendee, db):
    _a, ava_h = attendee
    old = db.query(VenueBooking).filter_by(event_id=open_event).one()
    old.status = BookingStatus.cancelled
    db.add(VenueBooking(event_id=open_event, venue_id=w.annex.id, requested_by=w.coordinator.id,
                        status=BookingStatus.approved, start_time=START, end_time=END))
    db.commit()

    detail = client.get(f"/registrations/events/{open_event}", headers=ava_h).json()

    assert [v["name"] for v in detail["venues"]] == ["Annex"]


def test_scrum51_an_event_not_open_to_attendees_is_not_found(client, w, attendee):
    _a, ava_h = attendee
    event_id, _b = _awaiting(client, w)

    assert client.get(f"/registrations/events/{event_id}", headers=ava_h).status_code == 404


# --------------------------------------------------------------------------
# SCRUM-47 Register / SCRUM-48 Withdraw / SCRUM-49 My Registrations
# --------------------------------------------------------------------------


def test_scrum47_ac1_ac3_registering_records_one_row_and_cannot_repeat(client, w, open_event, attendee, db):
    ava, ava_h = attendee

    res = client.post(f"/registrations/events/{open_event}", headers=ava_h)

    assert res.status_code == 200 and res.json()["my_status"] == "registered"
    assert client.post(f"/registrations/events/{open_event}", headers=ava_h).status_code == 409
    [row] = db.query(Registration).filter_by(event_id=open_event).all()
    assert row.attendee_id == ava.id and row.status == RegistrationStatus.registered and row.registered_at


def test_scrum47_ac2_closed_registration_cannot_be_used(client, w, attendee, db):
    _a, ava_h = attendee
    event_id, _b = _confirmed(client, w)
    _open_registration(client, w, event_id, opens=NOW + timedelta(days=2), closes=NOW + timedelta(days=5))

    res = client.post(f"/registrations/events/{event_id}", headers=ava_h)

    assert res.status_code == 409 and "not opened" in res.json()["detail"]
    assert db.query(Registration).count() == 0


def test_scrum47_a_double_clicked_register_keeps_one_row(make_client, client, w, open_event, attendee, db):
    _a, ava_h = attendee

    results = race(make_client, THREADS, lambda c: c.post(f"/registrations/events/{open_event}", headers=ava_h).status_code)

    assert sorted(results) == [200] + [409] * (THREADS - 1)
    assert db.query(Registration).filter_by(event_id=open_event).count() == 1


def test_scrum48_ac1_ac2_withdraw_then_register_again_on_the_same_row(client, w, open_event, attendee, db):
    _a, ava_h = attendee
    client.post(f"/registrations/events/{open_event}", headers=ava_h)

    out = client.post(f"/registrations/events/{open_event}/withdraw", headers=ava_h)
    assert out.status_code == 200 and out.json()["my_status"] == "withdrawn"
    db.expire_all()
    assert db.query(Registration).one().withdrawn_at is not None

    back = client.post(f"/registrations/events/{open_event}", headers=ava_h)
    assert back.status_code == 200 and back.json()["my_status"] == "registered"
    db.expire_all()
    [row] = db.query(Registration).all()
    assert row.status == RegistrationStatus.registered and row.withdrawn_at is None
    assert client.post(f"/registrations/events/{open_event}/withdraw", headers=ava_h).status_code == 200
    assert client.post(f"/registrations/events/{open_event}/withdraw", headers=ava_h).status_code == 404


def test_scrum49_ac1_to_ac6_my_registrations_reflects_each_step(client, w, open_event, attendee):
    _a, ava_h = attendee
    assert client.get("/registrations/mine", headers=ava_h).json() == []  # "No registrations yet"
    second, _b = _confirmed(client, w, name="Second Event")
    _open_registration(client, w, second)

    client.post(f"/registrations/events/{open_event}", headers=ava_h)
    client.post(f"/registrations/events/{second}", headers=ava_h)
    client.post(f"/registrations/events/{second}/withdraw", headers=ava_h)
    mine = {r["id"]: r for r in client.get("/registrations/mine", headers=ava_h).json()}
    assert (mine[open_event]["my_status"], mine[second]["my_status"]) == ("registered", "withdrawn")
    assert mine[open_event]["name"] and mine[open_event]["proposed_start"] and mine[open_event]["proposed_end"]

    client.post(f"/registrations/events/{second}", headers=ava_h)
    mine = client.get("/registrations/mine", headers=ava_h).json()
    assert [r["id"] for r in mine].count(second) == 1
    assert {r["id"]: r["my_status"] for r in mine}[second] == "registered"


# --------------------------------------------------------------------------
# SCRUM-50 Attendee list
# --------------------------------------------------------------------------


def test_scrum50_ac1_ac2_count_names_and_status_for_the_managers(client, w, open_event, make_user):
    people = [make_user(Role.ATTENDEE, f"a{i}@connectsphere.test", name)
              for i, name in enumerate(["Zed Z", "Amy A", "Max M"])]
    for _u, headers in people:
        client.post(f"/registrations/events/{open_event}", headers=headers)
    client.post(f"/registrations/events/{open_event}/withdraw", headers=people[2][1])

    for headers in (w.coord_h, w.org_h):
        listing = client.get(f"/registrations/events/{open_event}/attendees", headers=headers).json()
        assert listing["registered_count"] == 2
        assert [(a["name"], a["status"]) for a in listing["attendees"]] == [
            ("Amy A", "registered"), ("Max M", "withdrawn"), ("Zed Z", "registered")]


def test_scrum50_nobody_else_sees_who_registered(client, w, open_event, make_user):
    _x, priya_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    _o, other_org_h = make_user(Role.ORGANISER, "oscar@connectsphere.test", "Oscar Other")

    assert client.get(f"/registrations/events/{open_event}/attendees", headers=priya_h).status_code == 404
    assert client.get(f"/registrations/events/{open_event}/attendees", headers=other_org_h).status_code == 404
