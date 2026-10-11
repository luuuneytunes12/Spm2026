"""When a venue is actually tied up for an event.

A venue is not free the moment an Event ends: it needs setting up before and
resetting after. Venue Staff record both in whole minutes; an Event from
10:00 to 12:00 with 30 minutes' setup and 45 minutes' turnaround occupies the
venue from 09:30 to 12:45. A venue with nothing recorded (None) uses 0.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.datetimes import as_utc


@dataclass(frozen=True)
class OccupiedWindow:
    """An Event's time widened by the venue's setup and turnaround."""

    start: datetime
    end: datetime

    def overlaps(self, other: "OccupiedWindow") -> bool:
        """Strict overlap: each starts before the other ends, so two windows
        that merely touch (one ends at 09:00, the next starts at 09:00) do
        not clash."""
        return self.start < other.end and self.end > other.start


def occupied_window(
    start: datetime,
    end: datetime,
    setup_minutes: int | None,
    turnaround_minutes: int | None,
) -> OccupiedWindow:
    """Event start minus setup, to Event end plus turnaround (UTC)."""
    return OccupiedWindow(
        start=as_utc(start) - timedelta(minutes=setup_minutes or 0),
        end=as_utc(end) + timedelta(minutes=turnaround_minutes or 0),
    )


def overlap_of(a: OccupiedWindow, b: OccupiedWindow) -> OccupiedWindow | None:
    """The time two windows share, or None when they only touch or are apart."""
    if not a.overlaps(b):
        return None
    return OccupiedWindow(start=max(a.start, b.start), end=min(a.end, b.end))
