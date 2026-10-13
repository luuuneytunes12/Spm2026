"""SCRUM-50: View Attendee List for Event.

    As an Event Coordinator / Event Organiser, I want to view the list of
    registered attendees for an event I manage, so I can plan for turnout.

AC1  registration enabled: the number of Registered Attendees and the
     attendees by name are shown
AC2  each attendee's registration status is shown
"""

from app.core.roles import Role
from tests.test_registrations import _event, _user


def _world(client, db_session, *, enabled=True):
    organiser, org_h = _user(client, db_session, Role.ORGANISER, "org@example.com")
    coord, coord_h = _user(client, db_session, Role.COORDINATOR, "coord@example.com")
    event = _event(db_session, organiser, enabled=enabled)
    event.coordinator_id = coord.id
    db_session.commit()
    return organiser, org_h, coord, coord_h, event


def _register(client, db_session, event, email, name):
    user, headers = _user(client, db_session, Role.ATTENDEE, email)
    user.name = name
    db_session.commit()
    assert client.post(f"/registrations/events/{event.id}", headers=headers).status_code == 200
    return user, headers


def _get(client, headers, event):
    return client.get(f"/registrations/events/{event.id}/attendees", headers=headers)


def test_ac1_coordinator_sees_count_and_names(client, db_session):
    _, _, _, coord_h, event = _world(client, db_session)
    _register(client, db_session, event, "b@example.com", "Bea")
    _register(client, db_session, event, "a@example.com", "Amir")

    res = _get(client, coord_h, event)

    assert res.status_code == 200
    body = res.json()
    assert body["registered_count"] == 2
    assert [a["name"] for a in body["attendees"]] == ["Amir", "Bea"]


def test_ac1_organiser_sees_the_list_for_their_event(client, db_session):
    _, org_h, _, _, event = _world(client, db_session)
    _register(client, db_session, event, "a@example.com", "Amir")

    body = _get(client, org_h, event).json()

    assert body["registered_count"] == 1
    assert body["attendees"][0]["name"] == "Amir"


def test_ac1_enabled_event_with_no_registrations_is_empty(client, db_session):
    _, org_h, _, _, event = _world(client, db_session)

    body = _get(client, org_h, event).json()

    assert body == {"event_id": event.id, "registered_count": 0, "attendees": []}


def test_ac2_each_attendee_shows_registration_status(client, db_session):
    _, _, _, coord_h, event = _world(client, db_session)
    _register(client, db_session, event, "a@example.com", "Amir")
    _, bea_h = _register(client, db_session, event, "b@example.com", "Bea")
    client.post(f"/registrations/events/{event.id}/withdraw", headers=bea_h)

    body = _get(client, coord_h, event).json()

    assert {a["name"]: a["status"] for a in body["attendees"]} == {
        "Amir": "registered",
        "Bea": "withdrawn",
    }
    # Withdrawn people are listed but do not count towards turnout.
    assert body["registered_count"] == 1


# --- Negative ---------------------------------------------------------------


def test_registration_not_enabled_has_no_attendee_list(client, db_session):
    _, org_h, _, coord_h, event = _world(client, db_session, enabled=False)

    assert _get(client, coord_h, event).status_code == 409
    assert _get(client, org_h, event).status_code == 409


def test_attendee_is_denied_and_sees_no_names(client, db_session):
    _, _, _, _, event = _world(client, db_session)
    _, att_h = _register(client, db_session, event, "a@example.com", "Amir")

    res = _get(client, att_h, event)

    assert res.status_code == 403
    assert "Amir" not in res.text


def test_coordinator_not_assigned_gets_not_found(client, db_session):
    _, _, _, _, event = _world(client, db_session)
    _register(client, db_session, event, "a@example.com", "Amir")
    _, other_h = _user(client, db_session, Role.COORDINATOR, "other@example.com")

    res = _get(client, other_h, event)

    assert res.status_code == 404
    assert "Amir" not in res.text


def test_organiser_of_another_event_gets_not_found(client, db_session):
    _, _, _, _, event = _world(client, db_session)
    _, other_h = _user(client, db_session, Role.ORGANISER, "other@example.com")

    assert _get(client, other_h, event).status_code == 404


def test_unknown_event_is_not_found_and_anonymous_is_401(client, db_session):
    _, org_h, _, _, event = _world(client, db_session)

    assert client.get("/registrations/events/9999/attendees", headers=org_h).status_code == 404
    assert client.get(f"/registrations/events/{event.id}/attendees").status_code == 401


def test_other_internal_roles_are_denied_and_see_no_names(client, db_session):
    _, _, _, _, event = _world(client, db_session)
    _register(client, db_session, event, "a@example.com", "Amir")
    for role, email in (
        (Role.VENUE_STAFF, "vs@example.com"),
        (Role.TECH_SUPPORT, "ts@example.com"),
        (Role.SAFETY_OFFICER, "so@example.com"),
    ):
        _, headers = _user(client, db_session, role, email)
        res = _get(client, headers, event)
        assert res.status_code == 403, role
        assert "Amir" not in res.text


def test_the_list_carries_no_email_or_phone(client, db_session):
    _, org_h, _, _, event = _world(client, db_session)
    _register(client, db_session, event, "amir.private@example.com", "Amir")

    res = _get(client, org_h, event)

    assert res.status_code == 200
    assert "amir.private@example.com" not in res.text
    assert not {"email", "phone"} & set(res.json()["attendees"][0])
