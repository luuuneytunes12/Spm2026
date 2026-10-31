"""SCRUM-41 AC01, AC03 and AC05: venue occupied-time boundaries.

These database-free unit tests check the interval calculations behind a
booking conflict. API and calendar tests separately verify the complete
review workflow and that only relevant booking statuses are considered.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.venue_occupancy import occupied_window, overlap_of


@pytest.mark.parametrize(
    ("offset", "expected_overlap"),
    [
        pytest.param(-1, True, id="one-second-before-end-conflicts"),
        pytest.param(0, False, id="exactly-at-end-does-not-conflict"),
        pytest.param(1, False, id="one-second-after-end-does-not-conflict"),
    ],
)
def test_scrum41_ac3_occupied_window_end_boundary(offset, expected_overlap):
    """Compare starts just before, exactly at, and just after occupied end.

    The first event ends at 12:00 but has a 15-minute turnaround, so the
    relevant boundary is 12:15 rather than the event's advertised end.
    """
    first_start = datetime(2099, 11, 2, 10, tzinfo=timezone.utc)
    first_end = datetime(2099, 11, 2, 12, tzinfo=timezone.utc)
    first = occupied_window(first_start, first_end, 0, 15)
    next_start = datetime(2099, 11, 2, 12, 15, tzinfo=timezone.utc) + timedelta(seconds=offset)
    second = occupied_window(next_start, next_start + timedelta(hours=1), 0, 0)

    assert first.overlaps(second) is expected_overlap
    assert second.overlaps(first) is expected_overlap


def test_scrum41_ac5_setup_conflict_reports_the_shared_period():
    """Include setup in a conflict and return the exact shared interval."""
    first = occupied_window(
        datetime(2099, 11, 2, 10, tzinfo=timezone.utc),
        datetime(2099, 11, 2, 12, tzinfo=timezone.utc),
        0,
        0,
    )
    second = occupied_window(
        datetime(2099, 11, 2, 12, 15, tzinfo=timezone.utc),
        datetime(2099, 11, 2, 13, tzinfo=timezone.utc),
        30,
        0,
    )

    overlap = overlap_of(first, second)
    assert overlap is not None
    assert overlap.start == datetime(2099, 11, 2, 11, 45, tzinfo=timezone.utc)
    assert overlap.end == datetime(2099, 11, 2, 12, tzinfo=timezone.utc)


def test_scrum41_ac3_touching_windows_have_no_shared_period():
    """A back-to-back booking must not produce a zero-length conflict."""
    start = datetime(2099, 11, 2, 10, tzinfo=timezone.utc)
    first = occupied_window(start, start + timedelta(hours=1), 0, 0)
    second = occupied_window(start + timedelta(hours=1), start + timedelta(hours=2), 0, 0)

    assert overlap_of(first, second) is None
