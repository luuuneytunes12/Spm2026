"""Tentative venue holds: which are still active, and releasing the expired ones.

Lives in a service, not the venues router, so the conflict-flag service can use
it without importing a router.

`expire_tentative_holds` COMMITS. Call it before taking any row lock, never
after: the commit would release the lock.
"""

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import BookingStatus, NotificationType
from app.models.events import EventStatusHistory
from app.models.venues import VenueBooking
from app.services.notifications import notify


def active_hold_filter(now: datetime):
    return or_(
        VenueBooking.status != BookingStatus.tentative_hold,
        and_(
            VenueBooking.expires_at.is_not(None),
            VenueBooking.expires_at > now,
        ),
    )


def expire_tentative_holds(db: Session, now: datetime | None = None) -> int:
    """Release expired holds and notify their Coordinators on the next API use."""
    current = now or datetime.now(timezone.utc)
    # TODO(confirm): Schedule this operation periodically so notifications
    # are delivered at expiry even when no venue page is being requested.
    holds = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.event))
        .where(
            VenueBooking.status == BookingStatus.tentative_hold,
            or_(
                VenueBooking.expires_at.is_(None),
                VenueBooking.expires_at <= current,
            ),
        )
    ).unique().all()
    for hold in holds:
        hold.status = BookingStatus.cancelled
        # A cancelled hold has nothing left to resolve (SCRUM-92).
        hold.conflict_flagged_at = None
        hold.decision_notes = "Tentative hold expired."
        coordinator_id = hold.event.coordinator_id
        if coordinator_id is not None:
            notify(
                db,
                user_id=coordinator_id,
                type=NotificationType.venue_hold_expired,
                message=(
                    f"The tentative hold for {hold.venue.name} on "
                    f"'{hold.event.name or 'your event'}' expired."
                ),
                event_id=hold.event_id,
            )
        # Venue Staff who placed the hold are told too (SCRUM-98 AC3), and the
        # Event's Activity Log keeps the expiry (AC4).
        if hold.reviewed_by is not None:
            notify(
                db,
                user_id=hold.reviewed_by,
                type=NotificationType.venue_hold_expired,
                message=(
                    f"Your tentative hold on {hold.venue.name} for "
                    f"'{hold.event.name or 'an event'}' expired and the venue is free again."
                ),
                event_id=hold.event_id,
            )
        db.add(
            EventStatusHistory(
                event_id=hold.event_id,
                changed_by=hold.reviewed_by or hold.requested_by,
                from_status=hold.event.status,
                to_status=hold.event.status,
                note=f"Tentative hold on '{hold.venue.name}' expired.",
            )
        )
    if holds:
        db.commit()
    return len(holds)
