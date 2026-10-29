"""The Event Request lifecycle on real PostgreSQL -- Sprint 1 stories:

    SCRUM-20  Draft an Event Request
    SCRUM-21  Submit an Event Request
    SCRUM-22  Edit Submitted Event Request Before Review (change requests)
    SCRUM-25  Approve Event Request
    SCRUM-26  Reject Event Request
    SCRUM-101 Receive Event Notification as Event Coordinator Lead

The SQLite tests (tests/test_approve_event_request.py, test_reject_event_request.py,
test_edit_submitted_event_request.py, test_lead_submission_notice.py) prove
the rules. These walk the real path -- Organiser -> Lead -> Coordinator --
through the API on the production engine, every request in its own session,
so the enum columns, timestamptz values, JSONB `proposed_changes` and the
activity-log foreign keys are exercised for real; and they fire the
double-click cases SQLite cannot show.
"""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, ChangeRequestStatus, EventStatus
from app.models.events import Event, EventChangeRequest, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import Venue, VenueBooking
from tests.integration.conftest import COMPLETE_EVENT, submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration


def _world(client, make_user):
    """An Organiser, a Lead and a Coordinator, with one request assigned
    and therefore Under Review."""
    organiser, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    lead, lead_h = make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    coordinator, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    event_id = submit_event(client, org_h)
    assigned = client.post(
        f"/lead/unassigned-queue/{event_id}/assign",
        json={"coordinator_id": coordinator.id},
        headers=lead_h,
    )
    assert assigned.status_code == 200, assigned.text
    return organiser, org_h, lead, lead_h, coordinator, coord_h, event_id


# --------------------------------------------------------------------------
# SCRUM-20 Draft an Event Request
# --------------------------------------------------------------------------


def test_scrum20_ac1_ac2_a_partial_draft_round_trips_every_field_across_sessions(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    partial = {
        "name": "Partner Day",
        "purpose": "Annual partner briefing",
        "event_type": "conference",
        "proposed_start": "2026-11-02T09:00:00+08:00",  # a non-UTC offset on purpose
        "expected_attendance": 80,
        "programme": "09:00 welcome; 10:00 keynote",
        "room_layout_preference": "theatre",
        "accessibility_needs": "Step-free access",
        "equipment_requirements": "2 projectors",
        "registration_enabled": True,
        "special_arrangements": "Halal catering",
    }

    created = client.post("/events", json=partial, headers=org_h)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]

    # Reopened by a NEW request (own session) -- what "reopen later" means.
    reopened = client.get(f"/events/{event_id}", headers=org_h).json()
    assert reopened["status"] == "draft"
    for field in ("name", "purpose", "event_type", "expected_attendance", "programme",
                  "room_layout_preference", "accessibility_needs", "equipment_requirements",
                  "special_arrangements", "registration_enabled"):
        assert reopened[field] == partial[field], field
    assert reopened["proposed_start"].startswith("2026-11-02T01:00")  # stored as one instant
    assert reopened["proposed_end"] is None and reopened["venue_requirements"] is None

    # Editing the draft later keeps what was not touched.
    edited = client.patch(f"/events/{event_id}", json={"venue_requirements": "Main hall"}, headers=org_h)
    assert edited.status_code == 200
    db.expire_all()
    row = db.get(Event, event_id)
    assert row.venue_requirements == "Main hall" and row.programme == partial["programme"]
    assert row.status == EventStatus.draft and row.submitted_at is None


def test_scrum20_ac3_a_draft_never_reaches_the_review_queue_or_the_leads_queue(client, make_user):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    _c, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    draft_id = client.post("/events", json={"name": "Still drafting"}, headers=org_h).json()["id"]
    submitted_id = submit_event(client, org_h)

    queue = [e["id"] for e in client.get("/events/queue", headers=coord_h).json()]
    lead_queue = [e["id"] for e in client.get("/lead/unassigned-queue", headers=lead_h).json()]
    assert submitted_id in queue and draft_id not in queue
    assert submitted_id in lead_queue and draft_id not in lead_queue


# --------------------------------------------------------------------------
# SCRUM-21 Submit an Event Request
# --------------------------------------------------------------------------


def test_scrum21_ac1_missing_fields_block_submit_and_are_each_named(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    event_id = client.post("/events", json={"name": "Half done", "purpose": "  "}, headers=org_h).json()["id"]

    res = client.post(f"/events/{event_id}/submit", headers=org_h)

    assert res.status_code == 422
    flagged = {item["loc"][-1] for item in res.json()["detail"]}
    assert flagged == {"purpose", "event_type", "proposed_start", "proposed_end",
                       "expected_attendance", "venue_requirements", "accessibility_needs"}
    db.expire_all()
    assert db.get(Event, event_id).status == EventStatus.draft
    assert db.query(EventStatusHistory).filter_by(event_id=event_id).count() == 0


def test_scrum21_ac2_to_ac4_submit_moves_it_from_drafts_to_submitted_and_logs_it(client, make_user, db):
    organiser, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    event_id = client.post("/events", json=COMPLETE_EVENT, headers=org_h).json()["id"]

    res = client.post(f"/events/{event_id}/submit", headers=org_h)

    assert res.status_code == 200 and res.json()["status"] == "submitted_awaiting_coordinator"
    drafts = client.get("/events?status=draft", headers=org_h).json()
    submitted = client.get("/events?status=submitted_awaiting_coordinator", headers=org_h).json()
    assert [e["id"] for e in drafts] == [] and [e["id"] for e in submitted] == [event_id]
    db.expire_all()
    row = db.get(Event, event_id)
    assert row.submitted_at is not None and row.submitted_at.tzinfo is not None
    [line] = db.query(EventStatusHistory).filter_by(event_id=event_id).all()
    assert (line.from_status, line.to_status, line.changed_by) == (
        EventStatus.draft, EventStatus.submitted_awaiting_coordinator, organiser.id)


def test_scrum21_a_submitted_request_can_no_longer_be_edited_as_a_draft(client, make_user):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    event_id = submit_event(client, org_h)

    assert client.patch(f"/events/{event_id}", json={"name": "Sneaky"}, headers=org_h).status_code == 409
    assert client.post(f"/events/{event_id}/submit", headers=org_h).status_code == 409
    assert client.get(f"/events/{event_id}", headers=org_h).json()["name"] == COMPLETE_EVENT["name"]


def test_scrum21_another_organiser_cannot_see_or_submit_my_draft(client, make_user):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    _x, other_h = make_user(Role.ORGANISER, "other@connectsphere.test", "Oscar Other")
    event_id = client.post("/events", json=COMPLETE_EVENT, headers=org_h).json()["id"]

    assert client.get(f"/events/{event_id}", headers=other_h).status_code == 404
    assert client.post(f"/events/{event_id}/submit", headers=other_h).status_code == 404
    assert client.get(f"/events/{event_id}", headers=org_h).json()["status"] == "draft"


# --------------------------------------------------------------------------
# SCRUM-101 Lead notified of a new submission
# --------------------------------------------------------------------------


def test_scrum101_ac1_each_lead_is_told_once_with_name_organiser_and_time(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    lead_a, lead_a_h = make_user(Role.COORDINATOR_LEAD, "lead-a@connectsphere.test", "Lena Lead")
    lead_b, _ = make_user(Role.COORDINATOR_LEAD, "lead-b@connectsphere.test", "Leo Lead")
    coordinator, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")

    event_id = submit_event(client, org_h)

    [note] = [n for n in client.get("/notifications", headers=lead_a_h).json() if n["type"] == "event_submitted"]
    assert note["event_id"] == event_id
    assert COMPLETE_EVENT["name"] in note["message"] and "Olivia Organiser" in note["message"]
    assert "UTC" in note["message"]
    recipients = sorted(n.user_id for n in db.query(Notification).filter_by(type="event_submitted"))
    assert recipients == sorted([lead_a.id, lead_b.id])
    assert client.get("/notifications", headers=coord_h).json() == []


def test_scrum101_ac2_ac3_drafts_and_blocked_submits_tell_nobody(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    event_id = client.post("/events", json={"name": "Incomplete"}, headers=org_h).json()["id"]
    client.patch(f"/events/{event_id}", json={"purpose": "Something"}, headers=org_h)

    assert client.post(f"/events/{event_id}/submit", headers=org_h).status_code == 422
    assert db.query(Notification).count() == 0


def test_scrum101_a_double_clicked_submit_tells_the_lead_once(make_client, client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    event_id = client.post("/events", json=COMPLETE_EVENT, headers=org_h).json()["id"]

    results = race(make_client, THREADS, lambda c: c.post(f"/events/{event_id}/submit", headers=org_h).status_code)

    assert sorted(results) == [200] + [409] * (THREADS - 1)
    assert db.query(Notification).filter_by(type="event_submitted").count() == 1


# --------------------------------------------------------------------------
# SCRUM-25 Approve Event Request
# --------------------------------------------------------------------------


def test_scrum25_ac1_ac4_approval_persists_logs_and_reaches_the_organisers_inbox(client, make_user, db):
    organiser, org_h, _l, _lh, coordinator, coord_h, event_id = _world(client, make_user)

    res = client.post(f"/events/{event_id}/approve", headers=coord_h)

    assert res.status_code == 200 and res.json()["status"] == "event_approved"
    db.expire_all()
    assert db.get(Event, event_id).status == EventStatus.event_approved
    [line] = db.query(EventStatusHistory).filter_by(event_id=event_id, to_status=EventStatus.event_approved).all()
    assert line.from_status == EventStatus.under_review and line.changed_by == coordinator.id
    inbox = client.get("/notifications", headers=org_h).json()
    approved = [n for n in inbox if n["type"] == "event_approved"]
    assert len(approved) == 1 and approved[0]["event_id"] == event_id and not approved[0]["is_read"]


@pytest.mark.parametrize("status", [EventStatus.draft, EventStatus.event_approved,
                                    EventStatus.event_rejected, EventStatus.event_cancelled])
def test_scrum25_ac3_approving_outside_review_is_refused_and_changes_nothing(client, make_user, db, status):
    _o, _oh, _l, _lh, _c, coord_h, event_id = _world(client, make_user)
    db.get(Event, event_id).status = status
    db.commit()
    lines_before = db.query(EventStatusHistory).filter_by(event_id=event_id).count()

    res = client.post(f"/events/{event_id}/approve", headers=coord_h)

    assert res.status_code == 409
    db.expire_all()
    assert db.get(Event, event_id).status == status
    assert db.query(EventStatusHistory).filter_by(event_id=event_id).count() == lines_before
    assert db.query(Notification).filter_by(type="event_approved").count() == 0


def test_scrum25_only_the_assigned_coordinator_may_approve(client, make_user, db):
    _o, org_h, _l, lead_h, _c, _ch, event_id = _world(client, make_user)
    _x, other_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")

    assert client.post(f"/events/{event_id}/approve", headers=other_h).status_code == 403
    assert client.post(f"/events/{event_id}/approve", headers=org_h).status_code == 403
    assert client.post(f"/events/{event_id}/approve", headers=lead_h).status_code == 403
    db.expire_all()
    assert db.get(Event, event_id).status == EventStatus.under_review


def test_scrum25_a_double_clicked_approve_decides_once_and_notifies_once(make_client, client, make_user, db):
    _o, _oh, _l, _lh, _c, coord_h, event_id = _world(client, make_user)

    results = race(make_client, THREADS, lambda c: c.post(f"/events/{event_id}/approve", headers=coord_h).status_code)

    assert sorted(results) == [200] + [409] * (THREADS - 1)
    assert db.query(EventStatusHistory).filter_by(event_id=event_id, to_status=EventStatus.event_approved).count() == 1
    assert db.query(Notification).filter_by(type="event_approved").count() == 1


# --------------------------------------------------------------------------
# SCRUM-26 Reject Event Request
# --------------------------------------------------------------------------


def test_scrum26_ac1_a_blank_reason_is_refused_and_nothing_is_written(client, make_user, db):
    _o, _oh, _l, _lh, _c, coord_h, event_id = _world(client, make_user)

    for body in ({"reason": "   "}, {}):
        assert client.post(f"/events/{event_id}/reject", json=body, headers=coord_h).status_code == 422
    db.expire_all()
    assert db.get(Event, event_id).status == EventStatus.under_review
    assert db.query(Notification).filter_by(type="event_rejected").count() == 0


def test_scrum26_ac2_to_ac4_rejection_persists_notifies_with_reason_and_logs_everyone(client, make_user, db):
    organiser, org_h, _l, _lh, coordinator, coord_h, event_id = _world(client, make_user)
    reason = "The requested date clashes with the annual audit."

    res = client.post(f"/events/{event_id}/reject", json={"reason": reason}, headers=coord_h)

    assert res.status_code == 200 and res.json()["status"] == "event_rejected"
    [note] = [n for n in client.get("/notifications", headers=org_h).json() if n["type"] == "event_rejected"]
    assert reason in note["message"] and COMPLETE_EVENT["name"] in note["message"]
    activity = client.get(f"/events/{event_id}/activity", headers=org_h).json()
    rejection = next(a for a in activity if a["to_status"] == "event_rejected")
    assert rejection["note"] == reason and rejection["changed_by_name"] == "Sam Tan"
    # The log carries the Organiser's own submit line too, so both people are on record.
    assert any(a["changed_by_name"] == "Olivia Organiser" for a in activity)
    # Newest first, by a real timestamptz.
    assert [a["created_at"] for a in activity] == sorted((a["created_at"] for a in activity), reverse=True)


def test_scrum26_rejecting_releases_the_events_live_venue_bookings(client, make_user, db):
    organiser, _oh, _l, _lh, coordinator, coord_h, event_id = _world(client, make_user)
    # One live booking per (event, venue) is a database rule, so each sits in its own venue.
    for i, status in enumerate((BookingStatus.pending, BookingStatus.tentative_hold, BookingStatus.rejected)):
        venue = Venue(name=f"Hall {i}", location="Block A", capacity=300)
        db.add(venue)
        db.flush()
        db.add(VenueBooking(event_id=event_id, venue_id=venue.id, requested_by=coordinator.id,
                            start_time="2026-11-02T09:00:00Z", end_time="2026-11-02T17:00:00Z", status=status,
                            expires_at="2026-10-30T00:00:00Z" if status == BookingStatus.tentative_hold else None))
    db.commit()

    assert client.post(f"/events/{event_id}/reject", json={"reason": "No budget"}, headers=coord_h).status_code == 200

    db.expire_all()
    statuses = sorted(b.status for b in db.query(VenueBooking).filter_by(event_id=event_id))
    assert statuses == sorted([BookingStatus.cancelled, BookingStatus.cancelled, BookingStatus.rejected])


def test_scrum26_approve_and_reject_at_the_same_moment_leave_one_decision(make_client, client, make_user, db):
    _o, _oh, _l, _lh, _c, coord_h, event_id = _world(client, make_user)
    calls = iter([True, False] * THREADS)

    def decide(c):
        if next(calls):
            return c.post(f"/events/{event_id}/approve", headers=coord_h).status_code
        return c.post(f"/events/{event_id}/reject", json={"reason": "No"}, headers=coord_h).status_code

    results = race(make_client, 2, decide)

    assert sorted(results) == [200, 409]
    db.expire_all()
    decisions = db.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == event_id,
        EventStatusHistory.to_status.in_([EventStatus.event_approved, EventStatus.event_rejected]),
    ).all()
    assert len(decisions) == 1 and db.get(Event, event_id).status == decisions[0].to_status


# --------------------------------------------------------------------------
# SCRUM-22 Change requests on a submitted Event
# --------------------------------------------------------------------------


def _request_change(client, org_h, event_id, changes, description="Please update"):
    return client.post(f"/events/{event_id}/change-requests",
                       json={"description": description, "proposed_changes": changes}, headers=org_h)


def test_scrum22_ac1_a_change_request_is_pending_in_jsonb_and_the_event_is_untouched(client, make_user, db):
    _o, org_h, _l, _lh, _c, coord_h, event_id = _world(client, make_user)

    res = _request_change(client, org_h, event_id,
                          {"expected_attendance": 160, "proposed_start": "2026-11-02T08:00:00Z"})

    assert res.status_code == 201 and res.json()["status"] == "pending"
    db.expire_all()
    stored = db.query(EventChangeRequest).one()
    assert stored.status == ChangeRequestStatus.pending
    assert stored.proposed_changes["expected_attendance"] == 160  # JSON survives the round trip
    event = db.get(Event, event_id)
    assert event.expected_attendance == COMPLETE_EVENT["expected_attendance"]
    detail = client.get(f"/events/assigned/{event_id}", headers=coord_h).json()
    assert [c["status"] for c in detail["change_requests"]] == ["pending"]


def test_scrum22_ac2_approval_applies_the_values_and_the_organiser_sees_it(client, make_user, db):
    _o, org_h, _l, _lh, _c, coord_h, event_id = _world(client, make_user)
    cr = _request_change(client, org_h, event_id, {"name": "Partner Day 2026"}).json()

    res = client.post(f"/events/change-requests/{cr['id']}/approve", json={"review_notes": "Fine"}, headers=coord_h)

    assert res.status_code == 200 and res.json()["status"] == "approved"
    assert client.get(f"/events/{event_id}", headers=org_h).json()["name"] == "Partner Day 2026"
    outcome = client.get(f"/events/{event_id}/change-requests", headers=org_h).json()
    assert outcome[0]["status"] == "approved" and outcome[0]["reviewed_at"] is not None
    assert any(n["type"] == "event_change_approved" for n in client.get("/notifications", headers=org_h).json())


def test_scrum22_ac3_rejection_keeps_the_event_and_shows_the_reason(client, make_user, db):
    _o, org_h, _l, _lh, _c, coord_h, event_id = _world(client, make_user)
    cr = _request_change(client, org_h, event_id, {"venue_requirements": "Rooftop"}).json()

    res = client.post(f"/events/change-requests/{cr['id']}/reject",
                      json={"review_notes": "Rooftop is closed in November"}, headers=coord_h)

    assert res.status_code == 200
    assert client.get(f"/events/{event_id}", headers=org_h).json()["venue_requirements"] == COMPLETE_EVENT["venue_requirements"]
    [outcome] = client.get(f"/events/{event_id}/change-requests", headers=org_h).json()
    assert outcome["status"] == "rejected" and outcome["review_notes"] == "Rooftop is closed in November"
    [note] = [n for n in client.get("/notifications", headers=org_h).json() if n["type"] == "event_change_rejected"]
    assert "Rooftop is closed in November" in note["message"]


def test_scrum22_ac4_an_important_change_lists_the_bookings_to_reconsider(client, make_user, db):
    _o, org_h, _l, _lh, coordinator, coord_h, event_id = _world(client, make_user)
    venue = Venue(name="Main Hall", location="Block A", capacity=300)
    db.add(venue)
    db.commit()
    db.add(VenueBooking(event_id=event_id, venue_id=venue.id, requested_by=coordinator.id,
                        start_time="2026-11-02T09:00:00Z", end_time="2026-11-02T17:00:00Z",
                        status=BookingStatus.approved))
    db.commit()

    important = _request_change(client, org_h, event_id, {"expected_attendance": 400}).json()
    assert important["important_change"] is True
    assert [b["venue_name"] for b in important["venue_bookings_to_reconsider"]] == ["Main Hall"]

    client.post(f"/events/change-requests/{important['id']}/reject", json={}, headers=coord_h)
    cosmetic = _request_change(client, org_h, event_id, {"description": "Typo fix"}).json()
    assert cosmetic["important_change"] is False


@pytest.mark.parametrize("status", [EventStatus.event_completed, EventStatus.event_cancelled,
                                    EventStatus.event_rejected])
def test_scrum22_ac5_finished_events_take_no_change_requests(client, make_user, db, status):
    _o, org_h, _l, _lh, _c, _ch, event_id = _world(client, make_user)
    db.get(Event, event_id).status = status
    db.commit()

    assert _request_change(client, org_h, event_id, {"name": "Too late"}).status_code == 409
    assert db.query(EventChangeRequest).count() == 0


def test_scrum22_ac6_nobody_but_the_organiser_may_request_a_change(client, make_user, db):
    _o, _oh, _l, lead_h, _c, coord_h, event_id = _world(client, make_user)
    _x, other_org_h = make_user(Role.ORGANISER, "other@connectsphere.test", "Oscar Other")

    for headers in (other_org_h, coord_h, lead_h):
        assert _request_change(client, headers, event_id, {"name": "Hijack"}).status_code in (403, 404)
    assert db.query(EventChangeRequest).count() == 0


# Not strict: the bug only shows when the threads actually collide, which a
# small CI runner does not always manage -- an XPASS there is luck, not a fix.
@pytest.mark.xfail(strict=False, reason=(
    "BUG: POST /events/{id}/change-requests reads the Event without a row lock, so "
    "simultaneous requests all pass the 'already pending' check and several pending "
    "change requests are stored. Fix: _get_own_event(..., lock=True) in request_event_changes."
))
def test_scrum22_a_double_clicked_change_request_is_recorded_once(make_client, client, make_user, db):
    _o, org_h, _l, _lh, _c, _ch, event_id = _world(client, make_user)

    results = race(make_client, THREADS,
                   lambda c: _request_change(c, org_h, event_id, {"expected_attendance": 150}).status_code)

    assert sorted(results) == [201] + [409] * (THREADS - 1)
    assert db.query(EventChangeRequest).filter_by(status=ChangeRequestStatus.pending).count() == 1


@pytest.mark.xfail(strict=False, reason=(  # not strict: see above
    "BUG: _get_change_request_for_coordinator loads the change request BEFORE locking "
    "the Event, so each waiting request still sees 'pending' after the first commits: "
    "the change is applied and the Organiser notified once per click. Fix: load the "
    "change request with_for_update=True (or db.refresh it after the Event lock)."
))
def test_scrum22_a_double_clicked_approval_applies_and_notifies_once(make_client, client, make_user, db):
    _o, org_h, _l, _lh, _c, coord_h, event_id = _world(client, make_user)
    cr = _request_change(client, org_h, event_id, {"name": "Renamed"}).json()

    results = race(make_client, THREADS,
                   lambda c: c.post(f"/events/change-requests/{cr['id']}/approve", json={}, headers=coord_h).status_code)

    assert sorted(results) == [200] + [409] * (THREADS - 1)
    assert db.query(Notification).filter_by(type="event_change_approved").count() == 1
