"""Safety Officer notifications on real PostgreSQL, with overlapping requests.

SQLite serialises every write, so this race only shows on Postgres: a
double-clicked "Submit for Safety Check" must tell each officer once.
"""

from datetime import datetime, timezone

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event, EventChangeRequest
from app.models.notifications import Notification
from app.models.venues import Venue, VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def test_ac1_a_double_clicked_submit_tells_each_safety_officer_once(make_client, db, make_user):
    org, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coord, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    staff, _ = make_user(Role.VENUE_STAFF, "vera@connectsphere.test", "Vera Staff")
    for i in (1, 2):
        make_user(Role.SAFETY_OFFICER, f"safety{i}@connectsphere.test", f"Officer {i}")
    event = Event(
        organiser_id=org.id,
        coordinator_id=coord.id,
        name="Regional Partner Conference",
        proposed_start=START,
        proposed_end=END,
        status=EventStatus.planning_event,
    )
    venue = Venue(
        name="Marina Hall",
        location="10 Bayfront Ave",
        capacity=250,
        facilities=[],
        accessibility_features=[],
        supported_layouts=["Theatre"],
    )
    db.add_all([event, venue])
    db.commit()
    db.add(
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=coord.id,
            reviewed_by=staff.id,
            start_time=START,
            end_time=END,
            status=BookingStatus.approved,
        )
    )
    db.commit()
    event_id = event.id

    results = race(make_client, THREADS, lambda c: c.post(f"/events/{event_id}/confirm", headers=coord_h))

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert db.query(Notification).filter(Notification.type == "safety_check_requested").count() == 2


def test_ac2_an_approval_clicked_twice_tells_each_safety_officer_once_it_left(make_client, db, make_user):
    """Two approvals of the same attendance change at once: the event leaves
    the queue once, and each Safety Officer is told once."""
    org, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coord, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    for i in (1, 2):
        make_user(Role.SAFETY_OFFICER, f"safety{i}@connectsphere.test", f"Officer {i}")
    event = Event(
        organiser_id=org.id,
        coordinator_id=coord.id,
        name="Regional Partner Conference",
        proposed_start=START,
        proposed_end=END,
        expected_attendance=120,
        status=EventStatus.awaiting_safety_check,
    )
    db.add(event)
    db.commit()
    change = EventChangeRequest(
        event_id=event.id,
        requested_by=org.id,
        description="More guests",
        proposed_changes={"expected_attendance": 400},
    )
    db.add(change)
    db.commit()
    change_id = change.id

    results = race(
        make_client, THREADS, lambda c: c.post(f"/events/change-requests/{change_id}/approve", json={}, headers=coord_h)
    )

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert db.get(Event, event.id).status == EventStatus.planning_event
    told = db.query(Notification).filter(Notification.type == "safety_check_withdrawn").all()
    assert len(told) == 2
    assert "changed from 120 to 400" in told[0].message
