"""Attendee notifications on real PostgreSQL, with overlapping requests.

SQLite serialises every write, so these races only show on Postgres: a
double-clicked Register or Withdraw saves the registration once, and so
confirms it once (AC3).
"""

from datetime import datetime, timedelta, timezone

from app.core.roles import Role
from app.models.enums import EventStatus, RegistrationStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.registrations import Registration
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race


def _open_event(db, make_user):
    org, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    attendee, attendee_h = make_user(Role.ATTENDEE, "amy@connectsphere.test", "Amy Attendee")
    start = datetime.now(timezone.utc) + timedelta(days=30)
    event = Event(
        organiser_id=org.id,
        name="Partner Summit",
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
        registration_enabled=True,
        status=EventStatus.safety_check_passed,
    )
    db.add(event)
    db.commit()
    return event.id, attendee, attendee_h


def _saved(db):
    db.expire_all()
    return db.query(Notification).filter(Notification.type == "registration_status_changed").count()


def test_ac3_a_double_clicked_register_is_confirmed_once(make_client, db, make_user):
    event_id, _, attendee_h = _open_event(db, make_user)

    results = race(make_client, THREADS, lambda c: c.post(f"/registrations/events/{event_id}", headers=attendee_h))

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    assert _saved(db) == 1


def test_ac3_a_double_clicked_reregister_after_withdrawing_is_confirmed_once(make_client, db, make_user):
    event_id, attendee, attendee_h = _open_event(db, make_user)
    db.add(Registration(event_id=event_id, attendee_id=attendee.id, status=RegistrationStatus.withdrawn))
    db.commit()

    results = race(make_client, THREADS, lambda c: c.post(f"/registrations/events/{event_id}", headers=attendee_h))

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    assert _saved(db) == 1


def test_ac3_a_double_clicked_withdraw_is_confirmed_once(make_client, db, make_user):
    event_id, attendee, attendee_h = _open_event(db, make_user)
    db.add(Registration(event_id=event_id, attendee_id=attendee.id))
    db.commit()

    results = race(
        make_client, THREADS, lambda c: c.post(f"/registrations/events/{event_id}/withdraw", headers=attendee_h)
    )

    assert sorted(r.status_code for r in results) == [200] + [404] * (THREADS - 1)
    assert _saved(db) == 1
