"""Tests for "Mark Venue Temporarily Unavailable" (SCRUM-93).

    AC1  start, end and a reason category are saved
    AC2  an end not after the start is refused (422 naming end_time), nothing saved
    AC3  the availability calendar shows the period as busy, with its reason
    AC4  a booking request overlapping it is flagged to Venue Staff in review
    AC5  bookings already inside it are identified and flagged, never
         cancelled; their Events keep their status
    AC6  edit / end early / delete: the venue is available again outside
    AC7  only Venue Staff may create or edit
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.venues import VenueBooking, VenueUnavailability
from tests.test_booking_conflict_flags import _approved, _flagged, _log, _notes, _world

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def _at(hour, minute=0, day=2, year=2030):
    return datetime(year, 11, day, hour, minute, tzinfo=timezone.utc)


def _body(start=None, end=None, category="Maintenance", reason="Aircon repair"):
    return {
        "start_time": (start or _at(8)).isoformat(),
        "end_time": (end or _at(18)).isoformat(),
        "reason_category": category,
        "reason": reason,
    }


def _post(client, w, body=None, venue=None, headers=None):
    return client.post(
        f"/venues/{(venue or w['venue']).id}/unavailability", json=body or _body(), headers=headers or w["staff_h"]
    )


def _put(client, w, period_id, body, headers=None):
    return client.put(
        f"/venues/{w['venue'].id}/unavailability/{period_id}", json=body, headers=headers or w["staff_h"]
    )


def _busy(client, w, start, end, headers=None):
    res = client.get(
        f"/venues/{w['venue'].id}/availability",
        params={"start": start.isoformat(), "end": end.isoformat()},
        headers=headers or w["staff_h"],
    )
    assert res.status_code == 200
    return res.json()["busy"]


def _closures(client, w, start, end):
    return [b for b in _busy(client, w, start, end) if b["kind"] == "closure"]


# --- AC1 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "category", ["Maintenance", "Equipment failure", "Renovation", "Safety concern", "Other"]
)
def test_ac1_a_period_with_each_reason_category_is_saved(client, db_session, category):
    w = _world(client, db_session)
    res = _post(client, w, _body(category=category))
    assert res.status_code == 201
    body = res.json()
    assert body["reason_category"] == category and body["reason"] == "Aircon repair"
    assert body["start_time"].startswith("2030-11-02T08:00") and body["end_time"].startswith("2030-11-02T18:00")
    row = db_session.get(VenueUnavailability, body["id"])
    assert row.reason_category == category and row.created_by == w["staff"].id


def test_ac1_details_are_optional_and_blank_is_not_stored(client, db_session):
    w = _world(client, db_session)
    res = _post(client, w, _body(reason="   "))
    assert res.status_code == 201 and res.json()["reason"] is None


def test_ac1_an_unknown_reason_category_is_refused_and_nothing_is_saved(client, db_session):
    w = _world(client, db_session)
    assert _post(client, w, _body(category="Party")).status_code == 422
    assert _post(client, w, {**_body(), "reason_category": None}).status_code == 422
    assert db_session.query(VenueUnavailability).count() == 0


def test_ac1_an_unknown_venue_is_404(client, db_session):
    w = _world(client, db_session)
    res = client.post("/venues/99999/unavailability", json=_body(), headers=w["staff_h"])
    assert res.status_code == 404


def test_ac1_the_list_shows_saved_periods_with_reasons(client, db_session):
    w = _world(client, db_session)
    _post(client, w, _body(_at(8), _at(9), "Renovation", "New floor"))
    rows = client.get(f"/venues/{w['venue'].id}/unavailability", headers=w["sam_h"]).json()
    assert [(r["reason_category"], r["reason"]) for r in rows] == [("Renovation", "New floor")]


# --- AC2 -----------------------------------------------------------------------


@pytest.mark.parametrize("end_hour", [7, 8])  # before the start, and equal to it
def test_ac2_end_not_after_start_is_blocked_and_names_the_end_field(client, db_session, end_hour):
    w = _world(client, db_session)
    res = _post(client, w, _body(_at(8), _at(end_hour)))
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "end_time"]
    assert db_session.query(VenueUnavailability).count() == 0


def test_ac2_editing_to_an_end_before_the_start_changes_nothing(client, db_session):
    w = _world(client, db_session)
    pid = _post(client, w).json()["id"]
    assert _put(client, w, pid, _body(_at(10), _at(9))).status_code == 422
    db_session.expire_all()
    assert db_session.get(VenueUnavailability, pid).start_time.hour == 8


# --- AC3 -----------------------------------------------------------------------


def test_ac3_the_calendar_shows_the_period_with_its_reason(client, db_session):
    w = _world(client, db_session)
    _post(client, w, _body(_at(8), _at(18), "Safety concern", "Cracked beam"))
    for headers in (w["staff_h"], w["sam_h"]):  # Coordinators see it too
        [busy] = _busy(client, w, _at(0), _at(23), headers)
        assert busy["kind"] == "closure"
        assert busy["reason_category"] == "Safety concern" and busy["reason"] == "Cracked beam"
    assert _busy(client, w, _at(19), _at(22)) == []


def test_ac3_venue_search_excludes_the_venue_during_the_period(client, db_session):
    w = _world(client, db_session)
    _post(client, w)
    found = client.get(
        "/venues", params={"start": _at(9).isoformat(), "end": _at(10).isoformat()}, headers=w["sam_h"]
    ).json()
    assert w["venue"].id not in [v["id"] for v in found]


# --- AC4 -----------------------------------------------------------------------


def test_ac4_a_pending_request_overlapping_the_period_is_flagged_in_review(client, db_session):
    w = _world(client, db_session)
    _post(client, w, _body(_at(8), _at(18), "Renovation", "New floor"))
    pending = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)
    res = client.get(f"/venue-bookings/{pending.id}", headers=w["staff_h"]).json()
    [c] = res["conflicts"]
    assert c["kind"] == "unavailability" and c["reason"] == "Renovation: New floor"
    assert c["overlap_start"].startswith("2030-11-02T10:00") and c["booking_id"] is None
    # the queue shows it too, and approving is refused
    queue = client.get("/venue-bookings/queue", headers=w["staff_h"]).json()
    assert queue[0]["conflicts"][0]["kind"] == "unavailability"
    assert client.post(f"/venue-bookings/{pending.id}/approve", headers=w["staff_h"]).status_code == 409


def test_ac4_a_request_outside_the_period_has_no_conflict(client, db_session):
    w = _world(client, db_session)
    _post(client, w, _body(_at(8), _at(9)))
    outside = _approved(db_session, w, _at(9), _at(12), status=BookingStatus.pending)  # touches only
    assert client.get(f"/venue-bookings/{outside.id}", headers=w["staff_h"]).json()["conflicts"] == []


def test_ac4_the_coordinator_never_sees_the_conflict(client, db_session):
    w = _world(client, db_session)
    _post(client, w)
    pending = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)
    mine = client.get(f"/venue-bookings/events/{pending.event_id}", headers=w["sam_h"]).json()
    assert all(b["conflicts"] == [] for b in mine)


# --- AC5 -----------------------------------------------------------------------


def test_ac5_the_period_is_saved_and_affected_bookings_are_identified_not_cancelled(client, db_session):
    w = _world(client, db_session)
    inside = _approved(db_session, w, _at(10), _at(12), name="Gala")
    pending = _approved(db_session, w, _at(13), _at(14), status=BookingStatus.pending, name="Talk")
    outside = _approved(db_session, w, _at(20), _at(21), name="Late")
    cancelled = _approved(db_session, w, _at(11), _at(12), status=BookingStatus.cancelled, name="Gone")

    res = _post(client, w)
    assert res.status_code == 201
    body = res.json()
    assert {a["booking_id"]: a["status"] for a in body["affected_bookings"]} == {
        inside.id: "approved",
        pending.id: "pending",
    }
    assert body["recheck"] == {"flagged": 1, "cleared": 0}
    assert db_session.get(VenueUnavailability, body["id"]) is not None

    db_session.expire_all()
    assert db_session.get(VenueBooking, inside.id).status == BookingStatus.approved
    assert _flagged(db_session, inside, pending, outside, cancelled) == [True, False, False, False]
    for booking in (inside, pending, outside):
        assert db_session.get(Event, booking.event_id).status == EventStatus.planning_event
    assert any("temporarily unavailable" in n for n in _log(db_session, inside.event_id))
    [note] = _notes(db_session, w["sam"].id)
    assert "unavailable" in note.message


def test_ac5_flagged_approved_booking_lists_the_period_as_its_conflict(client, db_session):
    w = _world(client, db_session)
    inside = _approved(db_session, w, _at(10), _at(12))
    _post(client, w, _body(category="Equipment failure", reason="Lights"))
    [row] = client.get("/venue-bookings/flagged", headers=w["staff_h"]).json()
    assert row["id"] == inside.id and row["status"] == "approved"
    assert row["conflicts"][0]["kind"] == "unavailability"
    assert row["conflicts"][0]["reason"] == "Equipment failure: Lights"


def test_ac5_past_bookings_are_not_affected(client, db_session):
    w = _world(client, db_session)
    past = _approved(db_session, w, _at(10, day=1, year=2020), _at(12, day=1, year=2020))
    body = _post(client, w, _body(_at(8, day=1, year=2020), _at(18, day=1, year=2020))).json()
    assert body["affected_bookings"] == [] and _flagged(db_session, past) == [False]


def test_ac5_coordinators_get_no_affected_bookings(client, db_session):
    w = _world(client, db_session)
    _approved(db_session, w, _at(10), _at(12))
    _post(client, w)
    rows = client.get(f"/venues/{w['venue'].id}/unavailability", headers=w["sam_h"]).json()
    assert rows[0]["affected_bookings"] == []


# --- AC6 -----------------------------------------------------------------------


def test_ac6_editing_the_period_frees_the_venue_outside_it_and_clears_the_flag(client, db_session):
    w = _world(client, db_session)
    inside = _approved(db_session, w, _at(10), _at(12))
    pid = _post(client, w).json()["id"]
    res = _put(client, w, pid, _body(_at(14), _at(18), "Other", None))
    assert res.status_code == 200
    assert res.json()["recheck"] == {"flagged": 0, "cleared": 1}
    assert res.json()["reason_category"] == "Other" and res.json()["affected_bookings"] == []
    assert _flagged(db_session, inside) == [False]
    assert _closures(client, w, _at(8), _at(13)) == []
    assert len(_closures(client, w, _at(14), _at(15))) == 1
    db_session.expire_all()
    assert db_session.get(VenueUnavailability, pid).updated_by == w["staff"].id


def test_ac6_editing_to_overlap_a_booking_flags_it(client, db_session):
    w = _world(client, db_session)
    inside = _approved(db_session, w, _at(10), _at(12))
    pid = _post(client, w, _body(_at(14), _at(18))).json()["id"]
    assert _flagged(db_session, inside) == [False]
    assert _put(client, w, pid, _body(_at(9), _at(11))).json()["recheck"]["flagged"] == 1


def test_ac6_ending_a_period_early_makes_the_venue_available_again(client, db_session):
    w = _world(client, db_session)
    now = datetime.now(timezone.utc)
    pid = _post(client, w, _body(now - timedelta(hours=1), now + timedelta(days=2))).json()["id"]
    later = now + timedelta(days=1)
    assert len(_busy(client, w, later, later + timedelta(hours=1))) == 1
    res = client.post(f"/venues/{w['venue'].id}/unavailability/{pid}/end", headers=w["staff_h"])
    assert res.status_code == 200
    assert _busy(client, w, later, later + timedelta(hours=1)) == []


def test_ac6_a_period_not_under_way_cannot_be_ended_early(client, db_session):
    w = _world(client, db_session)
    pid = _post(client, w).json()["id"]  # 2030: not started
    res = client.post(f"/venues/{w['venue'].id}/unavailability/{pid}/end", headers=w["staff_h"])
    assert res.status_code == 409
    db_session.expire_all()
    assert db_session.get(VenueUnavailability, pid).end_time.hour == 18


def test_ac6_deleting_a_period_clears_flags_and_frees_the_venue(client, db_session):
    w = _world(client, db_session)
    inside = _approved(db_session, w, _at(10), _at(12))
    pid = _post(client, w).json()["id"]
    assert _flagged(db_session, inside) == [True]
    res = client.delete(f"/venues/{w['venue'].id}/unavailability/{pid}", headers=w["staff_h"])
    assert res.status_code == 204
    assert _flagged(db_session, inside) == [False]
    assert _closures(client, w, _at(0), _at(23)) == []
    assert client.delete(f"/venues/{w['venue'].id}/unavailability/{pid}", headers=w["staff_h"]).status_code == 404


def test_ac6_a_period_of_another_venue_cannot_be_edited_through_this_one(client, db_session):
    from tests.test_venue_booking_request import _venue

    w = _world(client, db_session)
    other = _venue(db_session, name="Other Hall")
    pid = _post(client, w, venue=other).json()["id"]
    assert _put(client, w, pid, _body()).status_code == 404


# --- AC7 -----------------------------------------------------------------------


@pytest.mark.parametrize("who", ["sam_h", "kim_h"])
def test_ac7_a_coordinator_cannot_create_edit_end_or_delete(client, db_session, who):
    w = _world(client, db_session)
    pid = _post(client, w).json()["id"]
    base = f"/venues/{w['venue'].id}/unavailability"
    assert _post(client, w, headers=w[who]).status_code == 403
    assert _put(client, w, pid, _body(), headers=w[who]).status_code == 403
    assert client.post(f"{base}/{pid}/end", headers=w[who]).status_code == 403
    assert client.delete(f"{base}/{pid}", headers=w[who]).status_code == 403
    assert db_session.query(VenueUnavailability).count() == 1


def test_ac7_no_token_is_401(client, db_session):
    w = _world(client, db_session)
    assert client.post(f"/venues/{w['venue'].id}/unavailability", json=_body()).status_code == 401
    assert client.get(f"/venues/{w['venue'].id}/unavailability").status_code == 401


def test_ac7_an_attendee_cannot_read_or_write(client, db_session):
    from tests.event_review_test_helpers import user
    from app.core.roles import Role

    w = _world(client, db_session)
    _, att_h = user(client, db_session, Role.ATTENDEE, "att@example.com", "Ann Attendee")
    assert _post(client, w, headers=att_h).status_code == 403
    assert client.get(f"/venues/{w['venue'].id}/unavailability", headers=att_h).status_code == 403


# --- SCRUM-94: Coordinators are told, nothing is cancelled -----------------------


def test_scrum94_a_pending_requests_coordinator_is_notified_and_the_event_is_untouched(client, db_session):
    w = _world(client, db_session)
    pending = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending, name="Talk")
    assert _post(client, w, _body(category="Renovation", reason="New floor")).status_code == 201
    db_session.expire_all()
    [note] = db_session.query(Notification).filter_by(
        user_id=w["sam"].id, type="venue_unavailability_recorded"
    ).all()
    assert "unavailable" in note.message and "Renovation: New floor" in note.message
    assert "Alternative arrangements" in note.message
    db_session.expire_all()
    assert db_session.get(VenueBooking, pending.id).status == BookingStatus.pending
    assert db_session.get(Event, pending.event_id).status == EventStatus.planning_event


def test_scrum94_an_active_hold_inside_the_period_is_flagged_and_an_expired_one_is_not(client, db_session):
    w = _world(client, db_session)
    active = _approved(db_session, w, _at(10), _at(11), status=BookingStatus.tentative_hold)
    expired = _approved(
        db_session, w, _at(12), _at(13), status=BookingStatus.tentative_hold,
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    body = _post(client, w).json()
    assert [a["booking_id"] for a in body["affected_bookings"]] == [active.id]
    assert _flagged(db_session, active) == [True]
    db_session.expire_all()
    assert db_session.get(VenueBooking, expired.id).status == BookingStatus.cancelled


def test_scrum94_ending_or_editing_the_period_tells_the_coordinator_the_mark_is_gone(client, db_session):
    w = _world(client, db_session)
    inside = _approved(db_session, w, _at(10), _at(12))
    pid = _post(client, w).json()["id"]
    assert "Action Required" in _notes(db_session, w["sam"].id)[0].message
    assert "alternative arrangements" in _notes(db_session, w["sam"].id)[0].message
    assert _put(client, w, pid, _body(_at(14), _at(18))).json()["recheck"]["cleared"] == 1
    assert _flagged(db_session, inside) == [False]
    assert "cleared" in _notes(db_session, w["sam"].id)[-1].message
