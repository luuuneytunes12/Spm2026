"""Reads a Venue's free-text operating hours and compares a time against them.

Venue Staff type one entry per line, e.g. "Mon-Fri 08:00-22:00". Hours are the
venue's own clock while bookings are stored in UTC, so a time is converted
before it is compared. All venues are in Singapore, which has no daylight
saving, so a fixed offset is enough and needs no timezone data package.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import re

from app.core.datetimes import as_utc

VENUE_TIMEZONE = timezone(timedelta(hours=8))

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_EVERY_DAY = frozenset(range(7))
_MINUTES_IN_DAY = 24 * 60
_ENTRY = re.compile(
    r"^(?:(?P<days>.*?)[\s:]+)?"
    r"(?P<open>\d{1,2}:\d{2})\s*(?:-|–|—|to)\s*(?P<close>\d{1,2}:\d{2})$",
    re.IGNORECASE,
)


class UnreadableOperatingHours(ValueError):
    """The text is recorded but cannot be understood as opening times."""


def _day(token: str) -> int:
    name = token.strip().casefold()
    if len(name) < 3 or name[:3] not in _DAYS:
        raise UnreadableOperatingHours(token)
    return _DAYS.index(name[:3])


def _days(text: str | None) -> frozenset[int]:
    """Which weekdays an entry covers. An entry naming none covers them all."""
    if not text or text.strip().casefold() in {"daily", "everyday", "every day"}:
        return _EVERY_DAY
    days: set[int] = set()
    for part in re.split(r"[,/&]", text):
        ends = re.split(r"\s*(?:-|–|—|to)\s*", part.strip())
        if len(ends) == 1:
            days.add(_day(ends[0]))
        elif len(ends) == 2:
            first, last = _day(ends[0]), _day(ends[1])
            # (last - first) % 7 lets a range wrap the week, e.g. Fri-Mon.
            days.update((first + step) % 7 for step in range((last - first) % 7 + 1))
        else:
            raise UnreadableOperatingHours(part)
    return frozenset(days)


def _minutes(text: str) -> int:
    hours, minutes = (int(piece) for piece in text.split(":"))
    if minutes > 59 or hours * 60 + minutes > _MINUTES_IN_DAY:
        raise UnreadableOperatingHours(text)
    return hours * 60 + minutes


class OperatingHours:
    """The periods a venue is open, as (weekdays, opens, closes) in minutes."""

    def __init__(self, entries: list[tuple[frozenset[int], int, int]]) -> None:
        self._entries = entries

    @classmethod
    def parse(cls, text: str) -> OperatingHours:
        entries = []
        for line in re.split(r"[\n;]", text):
            line = line.strip()
            # "Closed Mondays" records no opening, so there is nothing to add:
            # a day no entry covers is already closed.
            if not line or line.casefold().startswith("closed"):
                continue
            match = _ENTRY.match(line)
            if match is None:
                raise UnreadableOperatingHours(line)
            entries.append(
                (_days(match["days"]), _minutes(match["open"]), _minutes(match["close"]))
            )
        # "Closed Sundays" alone says when it is shut, not when it is open.
        if not entries:
            raise UnreadableOperatingHours(text)
        return cls(entries)

    def covers(self, start: datetime, end: datetime) -> bool:
        """True when the venue is open for the WHOLE of start to end.

        Boundaries count as inside: an event may end exactly at closing time.
        """
        local_start = as_utc(start).astimezone(VENUE_TIMEZONE)
        local_end = as_utc(end).astimezone(VENUE_TIMEZONE)
        reached = local_start
        for opens, closes in self._periods(local_start, local_end):
            if opens > reached:
                return False
            reached = max(reached, closes)
            if reached >= local_end:
                return True
        return False

    def _periods(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        periods = []
        # From the day before: its overnight hours may run into this one.
        day = datetime.combine(start.date() - timedelta(days=1), time.min, VENUE_TIMEZONE)
        while day.date() <= end.date():
            for weekdays, opens, closes in self._entries:
                if day.weekday() in weekdays:
                    # A closing time at or before opening is the next morning,
                    # e.g. 17:00-01:00.
                    length = closes - opens if closes > opens else closes - opens + _MINUTES_IN_DAY
                    opening = day + timedelta(minutes=opens)
                    periods.append((opening, opening + timedelta(minutes=length)))
            day += timedelta(days=1)
        return sorted(periods)


def outside_operating_hours(text: str | None, start: datetime, end: datetime) -> bool:
    """True when a time falls partly or fully outside the recorded hours.

    No hours recorded means the venue is treated as open. Raises
    UnreadableOperatingHours when the text cannot be understood.
    """
    if not text or not text.strip():
        return False
    return not OperatingHours.parse(text).covers(start, end)
