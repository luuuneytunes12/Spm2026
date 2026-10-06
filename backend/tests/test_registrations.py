"""Tests for the Attendee registration stories.

    As an Attendee, I want to register for a confirmed event that has
    registration enabled, so that I can secure my place.

    As an Attendee, I want to withdraw my registration, so that I release my
    place if I can no longer attend.

Each test name states the acceptance criterion it covers (see
docs/test-cases-attendee-registration.md).
"""

from datetime import datetime, timedelta, timezone

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event
from app.models.registrations import Registration
from app.models.user import User


def _user(client, db_session, role, email):
    password = "password123"
    res = client.post(
        "/auth/register", json={"name": "Test User", "email": email, "password": password}
    )
    assert res.status_code == 201
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def _event(db_session, organiser, *, status=EventStatus.safety_check_passed, enabled=True, days=30):
    """Nothing in the app moves an event to `confirmed` yet, so it is set
    directly here."""
    start = datetime.now(timezone.utc) + timedelta(days=days)
    event = Event(
        organiser_id=organiser.id,
        name="Partner Summit",
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
        registration_enabled=enabled,
        status=status,
    )
    db_session.add(event)
    db_session.commit()
    return event


def _setup(client, db_session):
    organiser, _ = _user(client, db_session, Role.ORGANISER, "org@example.com")
    _, attendee = _user(client, db_session, Role.ATTENDEE, "att@example.com")
    return organiser, attendee


def _row(client, headers, event_id):
    rows = client.get("/registrations/events", headers=headers).json()
    return next((r for r in rows if r["id"] == event_id), None)


# --- Register ---------------------------------------------------------------


def test_register_for_open_event_records_registered(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)

    res = client.post(f"/registrations/events/{event.id}", headers=attendee)

    assert res.status_code == 200
    assert res.json()["my_status"] == "registered"
    assert _row(client, attendee, event.id)["my_status"] == "registered"
    assert db_session.query(Registration).count() == 1


def test_open_event_is_listed_as_open_and_unregistered(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)

    row = _row(client, attendee, event.id)

    assert row["registration_open"] is True
    assert row["my_status"] is None


def test_already_registered_cannot_register_again(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)

    res = client.post(f"/registrations/events/{event.id}", headers=attendee)

    assert res.status_code == 409
    assert db_session.query(Registration).count() == 1


def test_event_that_has_started_is_closed(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser, days=-1)

    assert _row(client, attendee, event.id)["registration_open"] is False
    res = client.post(f"/registrations/events/{event.id}", headers=attendee)
    assert res.status_code == 409


def test_closed_event_stays_visible_to_someone_registered(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)

    event.registration_enabled = False
    db_session.commit()

    row = _row(client, attendee, event.id)
    assert row["registration_open"] is False
    assert row["my_status"] == "registered"


def test_unconfirmed_or_disabled_events_are_not_offered(client, db_session):
    organiser, attendee = _setup(client, db_session)
    draft = _event(db_session, organiser, status=EventStatus.event_approved)
    disabled = _event(db_session, organiser, enabled=False)

    assert _row(client, attendee, draft.id) is None
    assert _row(client, attendee, disabled.id) is None
    for event in (draft, disabled):
        res = client.post(f"/registrations/events/{event.id}", headers=attendee)
        assert res.status_code == 404


def test_only_attendees_can_register(client, db_session):
    organiser, _ = _setup(client, db_session)
    _, coordinator = _user(client, db_session, Role.COORDINATOR, "coord@example.com")
    event = _event(db_session, organiser)

    res = client.post(f"/registrations/events/{event.id}", headers=coordinator)

    assert res.status_code == 403


# --- Withdraw ---------------------------------------------------------------


def test_withdraw_changes_status_to_withdrawn(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)

    res = client.post(f"/registrations/events/{event.id}/withdraw", headers=attendee)

    assert res.status_code == 200
    assert res.json()["my_status"] == "withdrawn"
    registration = db_session.query(Registration).one()
    assert registration.withdrawn_at is not None


def test_cannot_withdraw_without_a_registration(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)

    res = client.post(f"/registrations/events/{event.id}/withdraw", headers=attendee)

    assert res.status_code == 404


def test_withdrawn_attendee_can_register_again_while_open(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)
    client.post(f"/registrations/events/{event.id}/withdraw", headers=attendee)

    res = client.post(f"/registrations/events/{event.id}", headers=attendee)

    assert res.status_code == 200
    assert res.json()["my_status"] == "registered"
    registration = db_session.query(Registration).one()  # same row, not a second one
    assert registration.withdrawn_at is None


def test_withdrawn_attendee_cannot_register_again_once_closed(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)
    client.post(f"/registrations/events/{event.id}/withdraw", headers=attendee)
    event.registration_enabled = False
    db_session.commit()

    res = client.post(f"/registrations/events/{event.id}", headers=attendee)

    assert res.status_code == 409


# --- View registration status (My Registrations) ------------------------------
#
# SCRUM-49. Each test is named for the acceptance criterion it covers.


def _mine(client, headers):
    res = client.get("/registrations/mine", headers=headers)
    assert res.status_code == 200
    return res.json()


def test_ac1_my_registrations_shows_name_date_time_and_status(client, db_session):
    organiser, attendee = _setup(client, db_session)
    first = _event(db_session, organiser, days=10)
    second = _event(db_session, organiser, days=20)
    client.post(f"/registrations/events/{first.id}", headers=attendee)
    client.post(f"/registrations/events/{second.id}", headers=attendee)

    rows = _mine(client, attendee)

    assert [r["id"] for r in rows] == [first.id, second.id]
    row = rows[0]
    assert row["name"] == "Partner Summit"
    # Date and time are both carried: a full timestamp, plus the end of the event.
    assert row["proposed_start"] is not None and "T" in row["proposed_start"]
    assert row["proposed_end"] is not None
    assert row["my_status"] == "registered"


def test_ac2_a_withdrawn_event_still_appears_as_withdrawn(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)
    client.post(f"/registrations/events/{event.id}/withdraw", headers=attendee)

    rows = _mine(client, attendee)

    assert len(rows) == 1
    assert rows[0]["id"] == event.id
    assert rows[0]["my_status"] == "withdrawn"


def test_ac3_registering_shows_registered_on_next_open(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    assert _mine(client, attendee) == []

    client.post(f"/registrations/events/{event.id}", headers=attendee)

    rows = _mine(client, attendee)
    assert [(r["id"], r["my_status"]) for r in rows] == [(event.id, "registered")]


def test_ac4_withdrawing_shows_withdrawn_on_next_open(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)
    assert _mine(client, attendee)[0]["my_status"] == "registered"

    client.post(f"/registrations/events/{event.id}/withdraw", headers=attendee)

    assert _mine(client, attendee)[0]["my_status"] == "withdrawn"


def test_ac5_withdraw_then_register_again_appears_once_as_registered(client, db_session):
    organiser, attendee = _setup(client, db_session)
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=attendee)
    client.post(f"/registrations/events/{event.id}/withdraw", headers=attendee)
    client.post(f"/registrations/events/{event.id}", headers=attendee)

    rows = _mine(client, attendee)

    assert len(rows) == 1
    assert rows[0]["id"] == event.id
    assert rows[0]["my_status"] == "registered"
    assert db_session.query(Registration).count() == 1


def test_ac6_never_registered_gives_an_empty_list(client, db_session):
    organiser, attendee = _setup(client, db_session)
    # An open event exists, but being offered it is not being registered for it.
    _event(db_session, organiser)

    assert _mine(client, attendee) == []


def test_my_registrations_only_lists_the_callers_own(client, db_session):
    organiser, attendee = _setup(client, db_session)
    _, other = _user(client, db_session, Role.ATTENDEE, "other@example.com")
    event = _event(db_session, organiser)
    client.post(f"/registrations/events/{event.id}", headers=other)

    assert _mine(client, attendee) == []
    assert len(_mine(client, other)) == 1


def test_my_registrations_is_attendee_only(client, db_session):
    _setup(client, db_session)
    _, coordinator = _user(client, db_session, Role.COORDINATOR, "coord@example.com")

    assert client.get("/registrations/mine", headers=coordinator).status_code == 403
    assert client.get("/registrations/mine").status_code == 401
