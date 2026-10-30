"""Tentative venue holds: which are still active, reminding before expiry,
and expiring the lapsed ones.

Lives in a service, not the venues router, so the conflict-flag service can use
it without importing a router.

`expire_tentative_holds` and `send_hold_reminders` COMMIT. Call them before
taking any row lock, never after: the commit would release the lock. Both run
on the background sweeper (app/services/hold_sweeper.py), so they happen on
time even when nobody is using the app; the expiry also runs on each venue
request, so no request ever sees a lapsed hold as active.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.datetimes import as_utc
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
    """Expire lapsed holds: status 'hold_expired', the venue free again for
    that window, the Coordinator and the Venue Staff who placed it notified,
    and the Event's Activity Log keeps it."""
    current = now or datetime.now(timezone.utc)
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
        # The sweeper and a request can expire at the same moment: whoever
        # gets a hold first expires it, the other skips it, so nobody is told twice.
        .with_for_update(of=VenueBooking, skip_locked=True)
    ).unique().all()
    for hold in holds:
        hold.status = BookingStatus.hold_expired
        # An expired hold has nothing left to resolve (SCRUM-92).
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
                changed_by=None,
                from_status=hold.event.status,
                to_status=hold.event.status,
                note=f"Tentative hold on '{hold.venue.name}' expired.",
                actor_name="System",
            )
        )
    if holds:
        db.commit()
    return len(holds)


def reminder_lead() -> timedelta:
    """How long before expiry the Coordinator is reminded (configurable)."""
    return timedelta(hours=settings.hold_reminder_hours)


def send_hold_reminders(db: Session, now: datetime | None = None) -> int:
    """Remind the Coordinator of each active hold that expires within the
    reminder lead and has not been reminded yet. A hold that is approved or
    rejected first is no longer a hold -- its required action is done -- so
    it is never reminded. Each hold is reminded once."""
    current = now or datetime.now(timezone.utc)
    holds = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.event), joinedload(VenueBooking.venue))
        .where(
            VenueBooking.status == BookingStatus.tentative_hold,
            VenueBooking.hold_reminder_sent_at.is_(None),
            VenueBooking.expires_at > current,
            VenueBooking.expires_at <= current + reminder_lead(),
        )
        .with_for_update(of=VenueBooking, skip_locked=True)
    ).unique().all()
    for hold in holds:
        hold.hold_reminder_sent_at = current
        coordinator_id = hold.event.coordinator_id
        if coordinator_id is None:
            continue
        notify(
            db,
            user_id=coordinator_id,
            type=NotificationType.venue_hold_expiring,
            message=(
                f"Reminder: your tentative hold on {hold.venue.name} for "
                f"'{hold.event.name or 'your event'}' expires at "
                f"{as_utc(hold.expires_at):%d %b %Y %H:%M} UTC. Required action: "
                f"{hold.hold_action or 'none given'}. If it is not done by then the hold expires "
                "and the venue is released."
            ),
            event_id=hold.event_id,
        )
    if holds:
        db.commit()
    return len(holds)
