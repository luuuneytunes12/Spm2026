"""As an Attendee, I want to be told when an Event is full, so that I do not
think I have a place when none is left.

AC4 (two Attendees racing for the last place) needs real concurrency, so it
lives in tests/integration/test_safety_check_and_registration_postgres.py.
"""

from app.core.roles import Role
from app.models.enums import RegistrationStatus
from app.models.registrations import Registration
from app.routers.registrations import event_is_full
from tests.test_registrations import _event, _user


def _full_event(client, db_session, capacity=1):
    organiser, _ = _user(client, db_session, Role.ORGANISER, "org@example.com")
    event = _event(db_session, organiser)
    event.expected_attendance = capacity
    db_session.commit()
    attendees = [
        _user(client, db_session, Role.ATTENDEE, f"att{i}@example.com")[1] for i in range(capacity + 1)
    ]
    for headers in attendees[:capacity]:
        assert client.post(f"/registrations/events/{event.id}", headers=headers).status_code == 200
    return event, attendees


def test_ac1_event_is_full_when_n_attendees_are_registered(client, db_session):
    event, _ = _full_event(client, db_session, capacity=2)

    assert event_is_full(event, db_session)


def test_ac1_withdrawn_registrations_do_not_count_and_no_capacity_means_no_limit(client, db_session):
    event, attendees = _full_event(client, db_session, capacity=2)
    client.post(f"/registrations/events/{event.id}/withdraw", headers=attendees[0])
    assert not event_is_full(event, db_session)

    event.expected_attendance = None
    db_session.commit()
    assert not event_is_full(event, db_session)


def test_ac2_registering_for_a_full_event_is_refused_and_says_full(client, db_session):
    event, attendees = _full_event(client, db_session)

    res = client.post(f"/registrations/events/{event.id}", headers=attendees[-1])

    assert res.status_code == 409 and res.json()["detail"] == "This event is full."
    assert db_session.query(Registration).filter_by(event_id=event.id).count() == 1


def test_ac2_a_withdrawn_attendee_cannot_re_register_into_a_full_event(client, db_session):
    event, attendees = _full_event(client, db_session)
    first, second = attendees
    client.post(f"/registrations/events/{event.id}/withdraw", headers=first)
    assert client.post(f"/registrations/events/{event.id}", headers=second).status_code == 200

    res = client.post(f"/registrations/events/{event.id}", headers=first)

    assert res.status_code == 409 and res.json()["detail"] == "This event is full."


def test_ac3_withdrawal_frees_the_place_for_another_attendee(client, db_session):
    event, attendees = _full_event(client, db_session)
    first, second = attendees

    assert client.post(f"/registrations/events/{event.id}/withdraw", headers=first).status_code == 200
    res = client.post(f"/registrations/events/{event.id}", headers=second)

    assert res.status_code == 200 and res.json()["my_status"] == "registered"
    statuses = sorted(r.status for r in db_session.query(Registration).filter_by(event_id=event.id))
    assert statuses == [RegistrationStatus.registered, RegistrationStatus.withdrawn]
