"""Times written into notification messages read in Singapore time."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.notifications import format_date, format_time, format_time_range
from app.services.safety_notices import describe

# 10:00-12:00 in Singapore.
START = datetime(2026, 11, 2, 2, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 4, tzinfo=timezone.utc)


def test_a_time_is_shown_in_singapore_time():
    assert format_time(START) == "2 Nov 2026, 10:00 SGT"


def test_a_naive_time_is_read_as_utc():
    # SQLite hands back naive datetimes.
    assert format_time(START.replace(tzinfo=None)) == "2 Nov 2026, 10:00 SGT"


def test_a_time_in_another_zone_is_converted():
    assert format_time(START.astimezone(timezone(timedelta(hours=-5)))) == "2 Nov 2026, 10:00 SGT"


def test_a_utc_evening_is_the_next_day_in_singapore():
    evening = datetime(2026, 11, 1, 23, tzinfo=timezone.utc)
    assert format_date(evening) == "2 Nov 2026"
    assert format_time(evening) == "2 Nov 2026, 07:00 SGT"


def test_a_range_on_one_singapore_day_shows_the_date_once():
    assert format_time_range(START, END) == "2 Nov 2026, 10:00-12:00 SGT"


def test_a_range_is_compared_by_singapore_days_not_utc_days():
    # Different UTC days, the same Singapore day.
    start = datetime(2026, 11, 1, 23, tzinfo=timezone.utc)
    end = datetime(2026, 11, 2, 1, tzinfo=timezone.utc)
    assert format_time_range(start, end) == "2 Nov 2026, 07:00-09:00 SGT"


def test_a_range_past_midnight_in_singapore_shows_both_dates():
    # The same UTC day, different Singapore days.
    start = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
    end = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)
    assert format_time_range(start, end) == "2 Nov 2026 17:00 - 3 Nov 2026 01:00 SGT"


def test_a_range_without_an_end_or_a_start():
    assert format_time_range(START, None) == "2 Nov 2026, 10:00 SGT"
    assert format_time_range(None, None) == "no date set"


def test_the_safety_notice_date_is_the_singapore_date():
    event = SimpleNamespace(
        name="Spring Fair",
        proposed_start=datetime(2026, 11, 1, 23, tzinfo=timezone.utc),
        coordinator=None,
    )
    assert describe(event) == "'Spring Fair' on 2 Nov 2026 (Event Coordinator: none assigned)"
