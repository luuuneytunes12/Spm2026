"""Release an Event's Venue Bookings once it is cancelled or completed.

Hooked on the Session rather than on one endpoint, so whatever moves an Event
to 'Event Cancelled' or 'Event Completed' frees its venues in the same
transaction: `before_flush` notes which Events just became one of those, and
`before_commit` releases their pending, held and approved bookings. Each
released booking stays as history (status 'released'), the Activity Log
records it with the System as the actor, and the Coordinator and the Venue
Staff who decided the booking are notified. Other Events' bookings are never
touched.
"""

from sqlalchemy import event as sa_event
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import (
    EQUIPMENT_RELEASE_EVENT_STATUSES,
    BookingStatus,
    EventStatus,
    NotificationType,
)
from app.models.events import Event, EventStatusHistory
from app.models.venues import VenueBooking
from app.services.notifications import notify
from app.services.tech_support_notices import when

RELEASABLE_STATUSES = (BookingStatus.pending, BookingStatus.tentative_hold, BookingStatus.approved)

# Key on Session.info holding ids of Events that reached a release status
# and whose bookings are released at commit.
_PENDING_KEY = "events_to_release_venues"


def release_venue_bookings(db: Session, event: Event) -> int:
    """Release `event`'s live bookings; returns how many. Does not commit."""
    bookings = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.venue))
        .where(VenueBooking.event_id == event.id, VenueBooking.status.in_(RELEASABLE_STATUSES))
        .with_for_update(of=VenueBooking)
    ).unique().all()
    outcome = "cancelled" if event.status is EventStatus.event_cancelled else "completed"
    for booking in bookings:
        booking.status = BookingStatus.released
        booking.expires_at = None
        booking.conflict_flagged_at = None
        booking.decision_notes = f"Released because the event was {outcome}."
        message = (
            f"The venue booking for {booking.venue.name} on '{event.name or 'an event'}' "
            f"({when(booking.start_time, booking.end_time)}) was released because the event was {outcome}."
        )
        db.add(
            EventStatusHistory(
                event_id=event.id,
                changed_by=None,  # the System
                from_status=event.status,
                to_status=event.status,
                note=message,
            )
        )
        for user_id in {event.coordinator_id, booking.reviewed_by} - {None}:
            notify(
                db,
                user_id=user_id,
                type=NotificationType.venue_booking_released,
                message=message,
                event_id=event.id,
            )
    return len(bookings)


@sa_event.listens_for(Session, "before_flush")
def _note_released_events(session: Session, flush_context, instances) -> None:
    for obj in session.dirty:
        if not isinstance(obj, Event):
            continue
        added = inspect(obj).attrs.status.history.added
        if added and added[0] in EQUIPMENT_RELEASE_EVENT_STATUSES:
            session.info.setdefault(_PENDING_KEY, set()).add(obj.id)


@sa_event.listens_for(Session, "before_commit")
def _release_on_commit(session: Session) -> None:
    session.flush()  # so status changes not yet flushed are noted too
    for event_id in session.info.pop(_PENDING_KEY, set()):
        event = session.get(Event, event_id)
        if event is not None and event.status in EQUIPMENT_RELEASE_EVENT_STATUSES:
            release_venue_bookings(session, event)


@sa_event.listens_for(Session, "after_rollback")
def _discard_pending(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
