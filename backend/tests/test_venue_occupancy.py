"""Occupancy window (SCRUM-78 AC5): Event start minus setup, to end plus turnaround."""

from datetime import datetime, timezone

from app.domain.venue_occupancy import occupied_window


def _t(h, m=0):
    return datetime(2026, 11, 2, h, m, tzinfo=timezone.utc)


def test_ac5_event_10_to_12_with_30_setup_and_45_turnaround_occupies_0930_to_1245():
    w = occupied_window(_t(10), _t(12), 30, 45)
    assert (w.start, w.end) == (_t(9, 30), _t(12, 45))


def test_ac3_not_set_is_treated_as_zero():
    w = occupied_window(_t(10), _t(12), None, None)
    assert (w.start, w.end) == (_t(10), _t(12))
    assert occupied_window(_t(10), _t(12), 0, 0) == w


def test_naive_datetimes_are_read_as_utc():
    w = occupied_window(datetime(2026, 11, 2, 10), datetime(2026, 11, 2, 12), 30, 0)
    assert w.start == _t(9, 30)


def test_overlap_is_strict_touching_edges_do_not_clash():
    a = occupied_window(_t(10), _t(12), 0, 0)
    assert not a.overlaps(occupied_window(_t(12), _t(14), 0, 0))
    assert not a.overlaps(occupied_window(_t(8), _t(10), 0, 0))
    assert a.overlaps(occupied_window(_t(11), _t(14), 0, 0))
