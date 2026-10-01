from datetime import datetime, timezone


def as_utc(moment: datetime) -> datetime:
    """Normalise to UTC. A time sent without a zone is read as UTC -- the
    frontend always sends one, so this only matters for hand-typed calls."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
