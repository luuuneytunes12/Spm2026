"""Filter Venues by Date and Time, on real PostgreSQL.

The SQLite unit tests (tests/test_venue_date_filter.py) prove the rules;
these prove they hold on the production engine -- the new `hold_expired`
enum value and the setup/turnaround columns in db/schema.sql, padding real
`timestamptz` values -- and under concurrency: two requests whose times only
clash once turnaround is counted, approved at the same moment, never both
get confirmed.
"""

from datetime import datetime, timedelta, timezone

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from tests.integration.conftest import submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

UTC = timezone.utc
WINDOW = {"start": "2026-11-02T09:00:00Z", "end": "2026-11-02T17:00:00Z"}


def _at(hour, minute=0):
    return datetime(2026, 11, 2, hour, minute, tzinfo=UTC)


def _venue(db, name, **fields):
    venue = Venue(name=name, location="10 Bayfront Ave", capacity=250, **fields)
    db.add(venue)
    db.commit()
    return venue


def _approved_event_with_request(client, db, org_h, sam_h, venue_id, start, end):
    """An approved event for [start, end) with a pending request for the
    venue -- a tentative hold. Returns the booking id."""
    event_id = submit_event(client, org_h)
    event = db.get(Event, event_id)
    event.status = EventStatus.approved
    event.proposed_start, event.proposed_end = start, end
    db.commit()
    res = client.post(f"/venue-bookings/events/{event_id}", json={"venue_id": venue_id}, headers=sam_h)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _names(client, headers, **params):
    res = client.get("/venues", params={**WINDOW, **params}, headers=headers)
    assert res.status_code == 200, res.text
    return [v["name"] for v in res.json()]


def test_ac1_ac2_holds_bookings_closures_and_padding_on_postgres(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    _sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    vera, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera Staff")

    held = _venue(db, "A Held Hall")
    padded = _venue(db, "B Padded Hall", setup_minutes=30, turnaround_minutes=60)
    closed = _venue(db, "C Closed Hall", setup_minutes=30)
    expired = _venue(db, "D Expired Hall")
    _venue(db, "E Free Hall")

    # A tentative hold, made the real way: a submitted request.
    _approved_event_with_request(client, db, org_h, sam_h, held.id, _at(10), _at(12))
    # An approved booking that only clashes because of turnaround + setup.
    booking_id = _approved_event_with_request(client, db, org_h, sam_h, padded.id, _at(6), _at(8))
    assert client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h).status_code == 200
    # A closure ending inside the venue's 30 minutes of setup.
    db.add(VenueUnavailability(
        venue_id=closed.id, start_time=_at(6), end_time=_at(8, 45), reason="Repairs", created_by=vera.id,
    ))
    # A hold that lapsed: the new enum value round-trips through Postgres.
    lapsed = _approved_event_with_request(client, db, org_h, sam_h, expired.id, _at(10), _at(12))
    db.get(VenueBooking, lapsed).status = BookingStatus.hold_expired
    db.commit()
    db.expire_all()
    assert db.get(VenueBooking, lapsed).status == BookingStatus.hold_expired

    assert _names(client, sam_h) == ["D Expired Hall", "E Free Hall"]
    # The same window in Singapore time is the same moment.
    sgt = {"start": "2026-11-02T17:00:00+08:00", "end": "2026-11-03T01:00:00+08:00"}
    assert _names(client, sam_h, **sgt) == ["D Expired Hall", "E Free Hall"]
    # A window clear of everything, padding included, shows them all again.
    later = {"start": "2026-11-02T13:00:00Z", "end": "2026-11-02T14:00:00Z"}
    assert _names(client, sam_h, **later) == [
        "B Padded Hall", "C Closed Hall", "D Expired Hall", "E Free Hall",
    ]


def test_ac3_an_end_before_the_start_is_refused_on_postgres(client, make_user):
    _sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    res = client.get(
        "/venues",
        params={"start": "2026-11-02T17:00:00Z", "end": "2026-11-02T09:00:00Z"},
        headers=sam_h,
    )
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["query", "end"]


def test_setup_and_turnaround_columns_default_to_zero_and_refuse_negatives(db):
    """The schema, not just the model: an existing venue is unaffected, and a
    negative buffer is impossible."""
    venue = _venue(db, "Plain Hall")
    db.expire_all()
    assert (db.get(Venue, venue.id).setup_minutes, db.get(Venue, venue.id).turnaround_minutes) == (0, 0)

    db.add(Venue(name="Broken Hall", location="x", capacity=10, setup_minutes=-5))
    try:
        db.commit()
    except Exception as exc:  # IntegrityError from the check constraint
        db.rollback()
        assert "setup_minutes" in str(exc)
    else:
        raise AssertionError("a negative setup time was accepted")


def test_requests_that_only_clash_through_turnaround_are_never_both_confirmed(
    make_client, client, make_user, db
):
    """Half the requests are for 09:00-17:00, half for 17:30-20:00. The two
    slots do not overlap, but the venue needs an hour to reset, so any two of
    them clash. Approved all at once, exactly one may be confirmed."""
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    _sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _vera, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera Staff")
    venue = _venue(db, "Marina Hall", turnaround_minutes=60)
    slots = [(_at(9), _at(17)), (_at(17, 30), _at(20))]
    booking_ids = [
        _approved_event_with_request(client, db, org_h, sam_h, venue.id, *slots[i % 2])
        for i in range(THREADS)
    ]
    todo = iter(booking_ids)

    results = race(
        make_client, THREADS,
        lambda c: c.post(f"/venue-bookings/{next(todo)}/approve", headers=staff_h),
    )

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    confirmed = db.query(VenueBooking).filter(
        VenueBooking.venue_id == venue.id, VenueBooking.status == BookingStatus.approved
    ).all()
    assert len(confirmed) == 1
    # And the venue search agrees: neither slot is offered any more.
    for start, end in slots:
        params = {"start": start.isoformat(), "end": end.isoformat()}
        assert _names(client, sam_h, **params) == []
    # One hour after the confirmed booking ends (plus nothing for setup), it is.
    after = confirmed[0].end_time.astimezone(UTC) + timedelta(hours=1)
    params = {"start": after.isoformat(), "end": (after + timedelta(hours=1)).isoformat()}
    assert _names(client, sam_h, **params) == ["Marina Hall"]
