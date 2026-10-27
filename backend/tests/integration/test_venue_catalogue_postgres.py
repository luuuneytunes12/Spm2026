"""Venue catalogue management (SCRUM-108) on real PostgreSQL: the new columns,
the venue_activity table and the case-insensitive unique name index in
db/schema.sql, plus two Venue Staff adding the same name at the same instant."""

import pytest

from app.core.roles import Role
from app.models.venues import Venue, VenueActivity
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

GOOD = {
    "name": "Harbour Hall",
    "location": "5 Quay Road",
    "capacity": 200,
    "facilities": ["Projector"],
    "accessibility_features": [],
    "supported_layouts": ["Theatre"],
    "operating_hours": "Mon-Fri 08:00-22:00",
}


def test_ac1_ac5_add_persists_arrays_and_logs_actor(client, make_user, db):
    _s, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera")
    res = client.post("/venues", json=GOOD, headers=staff_h)
    assert res.status_code == 201, res.text
    db.expire_all()
    venue = db.query(Venue).one()
    assert venue.supported_layouts == ["Theatre"] and venue.facilities == ["Projector"]
    log = client.get("/venues/activity", headers=staff_h).json()
    assert [(r["changed_by"], "added" in r["note"]) for r in log] == [("Vera", True)]


def test_ac3_same_name_added_at_once_saves_exactly_one(make_client, client, make_user, db):
    _s, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera")
    results = race(make_client, THREADS, lambda c: c.post("/venues", json=GOOD, headers=staff_h))
    codes = sorted(r.status_code for r in results)
    assert codes == [201] + [409] * (THREADS - 1), codes
    db.expire_all()
    assert db.query(Venue).count() == 1
    assert db.query(VenueActivity).count() == 1


def test_ac3_database_refuses_a_name_differing_only_by_case(client, make_user, db):
    _s, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera")
    assert client.post("/venues", json=GOOD, headers=staff_h).status_code == 201
    res = client.post("/venues", json={**GOOD, "name": "harbour hall"}, headers=staff_h)
    assert res.status_code == 409
    db.expire_all()
    assert db.query(Venue).count() == 1
