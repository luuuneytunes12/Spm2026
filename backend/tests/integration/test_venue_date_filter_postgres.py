"""Filter Venues by Date and Time, on real PostgreSQL.

The SQLite unit tests (tests/test_venue_date_filter.py) prove the rules;
these prove they hold on the production engine: padding real `timestamptz`
values by each venue's setup and turnaround, the `tentative_hold` status and
its expiry, closures, and a window given in another time zone.
"""

from datetime import datetime, timezone

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking, VenueUnavailability

UTC = timezone.utc
WINDOW = {"start": "2026-11-02T09:00:00Z", "end": "2026-11-02T17:00:00Z"}


def _at(hour, minute=0):
    return datetime(2026, 11, 2, hour, minute, tzinfo=UTC)


def _venue(db, name, **fields):
    venue = Venue(name=name, location="10 Bayfront Ave", **{"capacity": 250, **fields})
    db.add(venue)
    db.commit()
    return venue


def _booking(db, owner, venue, start, end, status, expires_at=None):
    event = Event(name=f"{venue.name} event", organiser_id=owner.id)
    db.add(event)
    db.flush()
    booking = VenueBooking(
        event_id=event.id, venue_id=venue.id, requested_by=owner.id,
        start_time=start, end_time=end, status=status, expires_at=expires_at,
    )
    db.add(booking)
    db.commit()
    return booking


def _names(client, headers, **params):
    res = client.get("/venues", params={**WINDOW, **params}, headers=headers)
    assert res.status_code == 200, res.text
    return [v["name"] for v in res.json()]


def test_ac1_ac2_holds_bookings_closures_and_padding_on_postgres(client, make_user, db):
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")

    held = _venue(db, "A Held Hall")
    padded = _venue(db, "B Padded Hall", setup_minutes=30, turnaround_minutes=60)
    closed = _venue(db, "C Closed Hall", setup_minutes=30)
    expired = _venue(db, "D Expired Hall")
    rejected = _venue(db, "E Rejected Hall")
    _venue(db, "F Free Hall")

    _booking(db, sam, held, _at(10), _at(12), BookingStatus.tentative_hold,
             expires_at=datetime(2099, 1, 1, tzinfo=UTC))
    # Approved 06:00-08:00: clashes only once 60 min reset + 30 min setup count.
    _booking(db, sam, padded, _at(6), _at(8), BookingStatus.approved)
    # A closure ending inside the venue's 30 minutes of setup.
    db.add(VenueUnavailability(
        venue_id=closed.id, start_time=_at(6), end_time=_at(8, 45),
        reason_category="Maintenance", created_by=sam.id,
    ))
    db.commit()
    lapsed = _booking(db, sam, expired, _at(10), _at(12), BookingStatus.tentative_hold,
                      expires_at=datetime(2020, 1, 1, tzinfo=UTC))
    _booking(db, sam, rejected, _at(10), _at(12), BookingStatus.rejected)

    assert _names(client, sam_h) == ["D Expired Hall", "E Rejected Hall", "F Free Hall"]
    # The expired hold was released, and that persisted (its own session).
    db.expire_all()
    assert db.get(VenueBooking, lapsed.id).status == BookingStatus.hold_expired

    # The same window in Singapore time is the same moment.
    sgt = {"start": "2026-11-02T17:00:00+08:00", "end": "2026-11-03T01:00:00+08:00"}
    assert _names(client, sam_h, **sgt) == ["D Expired Hall", "E Rejected Hall", "F Free Hall"]
    # Clear of everything, padding included, they are all back but the hold.
    later = {"start": "2026-11-02T13:00:00Z", "end": "2026-11-02T14:00:00Z"}
    assert _names(client, sam_h, **later) == [
        "A Held Hall", "B Padded Hall", "C Closed Hall", "D Expired Hall", "E Rejected Hall", "F Free Hall",
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


def test_ac4_date_and_capacity_combine_on_postgres(client, make_user, db):
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    big_busy = _venue(db, "Big Busy Hall", capacity=500, turnaround_minutes=30)
    _venue(db, "Big Free Hall", capacity=500)
    _venue(db, "Small Free Hall", capacity=50)
    _booking(db, sam, big_busy, _at(8), _at(8, 45), BookingStatus.approved)

    assert _names(client, sam_h, min_capacity=300) == ["Big Free Hall"]
