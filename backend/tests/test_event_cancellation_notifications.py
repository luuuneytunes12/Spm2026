"""Tests for telling everyone involved that an Event was cancelled.

    AC1  A registered Attendee gets the Event name and the cancellation reason.
    AC2  Each active Venue Booking: Venue Staff get the Event, Venue and date/time
         (every Venue Staff member manages every venue -- confirmed with the customer).
    AC3  Reserved equipment: the Technical Support Staff who reserved it get the
         Event and the equipment.
    AC4  An Event awaiting its Safety Check: the Safety Officer is told it left
         the queue, and why.
    AC5  The Organiser and the assigned Coordinator get the reason.
    AC6  An Attendee who withdrew gets nothing.

Test names carry the acceptance criterion they prove.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType, RegistrationStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.registrations import Registration
from app.models.user import User
from app.services.attendee_notices import AttendeeNotice
from app.services.cancellation_notices import (
    AttendeeCancelledNotice,
    CoordinatorCancelledNotice,
    EquipmentCancelledNotice,
    OrganiserCancelledNotice,
    SafetyCheckCancelledNotice,
    VenueCancelledNotice,
)
from app.services.coordinator_notices import CoordinatorNotice
from app.services.organiser_notices import OrganiserNotice
from app.services.safety_notices import SafetyOfficerNotice
from app.services.tech_support_notices import TechSupportNotice
from app.services.venue_staff_notices import VenueStaffNotice
from tests.event_review_test_helpers import user
from tests.test_safety_officer_notifications import _confirm, _ready
from tests.test_venue_booking_request import _submit_many, _venue

CANCELLED = NotificationType.event_cancelled.value
RELEASED = NotificationType.venue_booking_released.value
LEFT_QUEUE = NotificationType.safety_check_withdrawn.value
EVENT = "Regional Partner Conference"


def _inbox(client, headers, type=None):
    """Messages, oldest first; only `type` when given."""
    return [
        n["message"] for n in client.get("/notifications", headers=headers).json() if type is None or n["type"] == type
    ][::-1]


def _world(client, db_session, awaiting_safety=True):
    """An Event with a booking approved by Vera and a projector reserved by
    Tess, awaiting its Safety Check (or still planning), with a registered
    and a withdrawn Attendee and a bystander in every role. Earlier notices
    are cleared so each test reads only what the cancel caused."""
    w = _ready(client, db_session)
    if awaiting_safety:
        assert _confirm(client, w).status_code == 200
    _, w["vic_h"] = user(client, db_session, Role.VENUE_STAFF, "vic@example.com", "Vic Staff")
    _, w["tom_h"] = user(client, db_session, Role.TECH_SUPPORT, "tom@example.com", "Tom Tech")
    amy, w["amy_h"] = user(client, db_session, Role.ATTENDEE, "amy@example.com", "Amy Attendee")
    ben, w["ben_h"] = user(client, db_session, Role.ATTENDEE, "ben@example.com", "Ben Attendee")
    _, w["other_org_h"] = user(client, db_session, Role.ORGANISER, "otto@example.com", "Otto Other")
    db_session.add_all([
        Registration(event_id=w["event_id"], attendee_id=amy.id),
        Registration(event_id=w["event_id"], attendee_id=ben.id, status=RegistrationStatus.withdrawn),
    ])
    db_session.query(Notification).delete()
    db_session.commit()
    return w


def _cancel(client, w, reason="Budget cut"):
    res = client.post(f"/events/{w['event_id']}/cancel", json={"reason": reason}, headers=w["coord_h"])
    assert res.status_code == 200, res.text
    return res


# --- AC1 / AC6: Attendees ----------------------------------------------------


def test_ac1_a_registered_attendee_gets_the_event_and_the_reason(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    assert _inbox(client, w["amy_h"], CANCELLED) == [
        f"'{EVENT}', which you are registered for, has been cancelled. Reason: Budget cut"
    ]


def test_ac6_a_withdrawn_attendee_gets_nothing(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    assert _inbox(client, w["ben_h"]) == []


# --- AC2: Venue Staff, per active booking -------------------------------------


def test_ac2_venue_staff_get_the_event_the_venue_and_the_date_and_time(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    assert _inbox(client, w["vic_h"], CANCELLED) == [
        f"'{EVENT}' has been cancelled. Its booking of Marina Hall (2 Nov 2026, 09:00-17:00 UTC) is no longer needed."
    ]


def test_ac2_the_staff_member_who_decided_it_is_told_once_with_the_same_facts(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    assert _inbox(client, w["staff_h"], CANCELLED) == []
    assert _inbox(client, w["staff_h"], RELEASED) == [
        f"The venue booking for Marina Hall on '{EVENT}' (2 Nov 2026, 09:00-17:00 UTC) "
        "was released because the event was cancelled."
    ]


def test_ac2_each_active_booking_gets_its_own_notice_and_a_pending_one_tells_everyone(client, db_session):
    w = _world(client, db_session, awaiting_safety=False)
    harbour = _venue(db_session, "Harbour Room")
    assert _submit_many(client, w["coord_h"], w["event_id"], [{"venue_id": harbour.id}]).status_code == 201
    db_session.query(Notification).delete()
    db_session.commit()

    _cancel(client, w)

    vic = _inbox(client, w["vic_h"], CANCELLED)
    assert len(vic) == 2 and "Marina Hall" in vic[0] and "Harbour Room" in vic[1]
    # Nobody decided the pending one, so its deciding staff member is everyone.
    assert [m for m in _inbox(client, w["staff_h"], CANCELLED) if "Harbour Room" in m]


def test_ac2_a_rejected_booking_is_not_active_and_tells_nobody(client, db_session):
    w = _world(client, db_session, awaiting_safety=False)
    harbour = _venue(db_session, "Harbour Room")
    booking_id = _submit_many(client, w["coord_h"], w["event_id"], [{"venue_id": harbour.id}]).json()[0]["id"]
    client.post(f"/venue-bookings/{booking_id}/reject", json={"reason": "Full"}, headers=w["staff_h"])
    db_session.query(Notification).delete()
    db_session.commit()

    _cancel(client, w)

    assert all("Harbour Room" not in m for m in _inbox(client, w["vic_h"], CANCELLED))


def test_ac2_only_venue_staff_get_the_venue_notice(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    db_session.expire_all()
    told = {
        n.user_id for n in db_session.query(Notification).filter_by(type=CANCELLED)
        if "is no longer needed" in n.message and "booking of" in n.message
    }
    venue_staff = {u.id for u in db_session.query(User).filter_by(role=Role.VENUE_STAFF.value)}
    assert told and told <= venue_staff


# --- AC3: Technical Support who reserved the equipment -----------------------


def test_ac3_the_staff_who_reserved_it_get_the_event_and_the_equipment(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    assert _inbox(client, w["tech_h"], CANCELLED) == [
        f"'{EVENT}' has been cancelled. Its reserved equipment is no longer needed: 2 x Projector."
    ]


def test_ac3_other_technical_support_staff_get_nothing(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    assert _inbox(client, w["tom_h"]) == []


def test_ac3_no_reserved_equipment_tells_technical_support_nothing(client, db_session):
    w = _world(client, db_session)
    db_session.get(Event, w["event_id"]).equipment_items[0].status = "requested"
    db_session.commit()

    _cancel(client, w)

    assert _inbox(client, w["tech_h"], CANCELLED) == []


# --- AC4: the Safety Officer, if it was awaiting its Safety Check ------------


def test_ac4_the_safety_officer_is_told_it_left_the_queue_and_why(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    [message] = _inbox(client, w["officer_h"], LEFT_QUEUE)
    assert f"'{EVENT}'" in message
    assert "has left your Safety Check queue because it was cancelled" in message
    assert message.endswith("Reason: Budget cut")


def test_ac4_an_event_not_awaiting_its_safety_check_tells_the_safety_officer_nothing(client, db_session):
    w = _world(client, db_session, awaiting_safety=False)

    _cancel(client, w)

    assert _inbox(client, w["officer_h"]) == []


# --- AC5: the Organiser and the Coordinator ----------------------------------


def test_ac5_the_organiser_gets_the_reason(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w, reason="The client withdrew")

    assert _inbox(client, w["org_h"], CANCELLED) == [
        f"Your event '{EVENT}' has been cancelled. Reason: The client withdrew"
    ]


def test_ac5_the_coordinator_gets_the_reason(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w, reason="The client withdrew")

    assert _inbox(client, w["coord_h"], CANCELLED) == [
        f"'{EVENT}', which you coordinate, has been cancelled. Reason: The client withdrew"
    ]


def test_ac5_another_organiser_gets_nothing(client, db_session):
    w = _world(client, db_session)

    _cancel(client, w)

    assert _inbox(client, w["other_org_h"]) == []


# --- refused cancellations, and what still happens ---------------------------


@pytest.mark.parametrize("who, body, code", [("coord_h", {"reason": "   "}, 422), ("staff_h", {"reason": "x"}, 403)])
def test_a_refused_cancellation_tells_nobody(client, db_session, who, body, code):
    w = _world(client, db_session)

    res = client.post(f"/events/{w['event_id']}/cancel", json=body, headers=w[who])

    assert res.status_code == code
    db_session.expire_all()
    assert db_session.query(Notification).count() == 0


def test_cancelling_still_cancels_and_releases(client, db_session):
    """Frozen: the cancel itself is unchanged."""
    w = _world(client, db_session)

    body = _cancel(client, w).json()

    assert body["status"] == EventStatus.event_cancelled.value
    db_session.expire_all()
    event = db_session.get(Event, w["event_id"])
    assert all(line.status != "reserved" for line in event.equipment_items)


# --- the classes --------------------------------------------------------------


def test_each_cancellation_notice_extends_its_roles_own_notice():
    assert issubclass(AttendeeCancelledNotice, AttendeeNotice)
    assert issubclass(VenueCancelledNotice, VenueStaffNotice)
    assert issubclass(EquipmentCancelledNotice, TechSupportNotice)
    assert issubclass(SafetyCheckCancelledNotice, SafetyOfficerNotice)
    assert issubclass(OrganiserCancelledNotice, OrganiserNotice)
    assert issubclass(CoordinatorCancelledNotice, CoordinatorNotice)
