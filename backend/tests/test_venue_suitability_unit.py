"""SCRUM-104 AC1–AC2: unit test of per-booking suitability decisions.

The coordinator must see an independent result for each venue booking, based
on that booking's attendance, layout, accessibility and facilities. A failed
booking must show its unmet requirements without affecting another booking.

This file exercises the suitability calculation with small in-memory objects;
it does not connect to a database or make HTTP requests. The companion
test_venue_suitability.py checks the API, access rules and recheck workflow.
"""

from types import SimpleNamespace

from app.routers.venues import _booking_suitability_checks


def _venue(*, capacity: int, layouts: list[str], accessibility: list[str], facilities: list[str]):
    """Build the venue attributes read by the calculation, without database setup."""
    return SimpleNamespace(
        capacity=capacity,
        supported_layouts=layouts,
        accessibility_features=accessibility,
        facilities=facilities,
    )


def _booking(venue, *, attendance: int, layout: str, accessibility: str, facilities: str):
    """Build one booking with its own venue and requirements for the calculation."""
    return SimpleNamespace(
        venue=venue,
        expected_attendance=attendance,
        room_layout_preference=layout,
        accessibility_needs=accessibility,
        facilities_needs=facilities,
    )


def test_suitability_checks_each_booking_against_its_own_attendance_and_needs():
    """SCRUM-104 AC1–AC2: one booking fails capacity, the other still passes.

    The event's general requirements intentionally differ from both bookings:
    comparing against those defaults instead would give misleading results.
    The failed booking must name the concrete capacity and attendance values.
    """
    event = SimpleNamespace(
        expected_attendance=100,
        room_layout_preference="Theatre",
        accessibility_needs="Wheelchair access",
        venue_requirements="Projector",
    )
    breakout = _booking(
        _venue(
            capacity=30,
            layouts=["Classroom"],
            accessibility=["Step-free access"],
            facilities=["Whiteboard"],
        ),
        attendance=40,
        layout="Classroom",
        accessibility="Step-free access",
        facilities="Whiteboard",
    )
    main_hall = _booking(
        _venue(
            capacity=60,
            layouts=["Boardroom"],
            accessibility=["Hearing loop"],
            facilities=["Video conferencing"],
        ),
        attendance=50,
        layout="Boardroom",
        accessibility="Hearing loop",
        facilities="Video conferencing",
    )

    breakout_checks = _booking_suitability_checks(event, breakout)
    main_hall_checks = _booking_suitability_checks(event, main_hall)

    assert [(check.category, check.met) for check in breakout_checks] == [
        ("capacity", False),
        ("layout", True),
        ("accessibility", True),
        ("facility", True),
    ]
    assert breakout_checks[0].message == "Insufficient capacity: Capacity 30 < attendance 40."
    assert all(check.met for check in main_hall_checks)
