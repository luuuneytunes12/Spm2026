"""Unit tests for suitability checks scoped to an individual venue booking."""

from types import SimpleNamespace

from app.routers.venues import _booking_suitability_checks


def _venue(*, capacity: int, layouts: list[str], accessibility: list[str], facilities: list[str]):
    return SimpleNamespace(
        capacity=capacity,
        supported_layouts=layouts,
        accessibility_features=accessibility,
        facilities=facilities,
        operating_hours=None,
    )


def _booking(venue, *, attendance: int, layout: str, accessibility: str, facilities: str):
    return SimpleNamespace(
        venue=venue,
        start_time=None,
        end_time=None,
        expected_attendance=attendance,
        room_layout_preference=layout,
        accessibility_needs=accessibility,
        facilities_needs=facilities,
    )


def test_suitability_checks_each_booking_against_its_own_attendance_and_needs():
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
