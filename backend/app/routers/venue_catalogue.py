"""Add and edit Venues in the catalogue (SCRUM-108). Venue Staff only.

Saving never removes a Venue Booking. When an edit reduces the capacity or
removes a supported room layout, the future bookings that relied on the old
value are kept and flagged for review (and their Coordinator is told). Every
add or edit is written to the venue Activity Log with the actor and the time.

Registered before the venues router so GET /venues/activity is not read as a
venue id.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.domain.activity_log import ActivityLog, EventHistoryLog
from app.models.enums import BookingStatus, NotificationType
from app.models.user import User
from app.models.venues import Venue, VenueActivity, VenueBooking
from app.schemas.venue_catalogue import FlaggedBookingOut, VenueActivityOut, VenueIn, VenueSaved
from app.services.notifications import notify
from app.services.venue_holds import active_hold_filter, expire_tentative_holds

router = APIRouter(prefix="/venues", tags=["venue catalogue"])

_venue_staff = require_role(Role.VENUE_STAFF)

# Bookings that hold, or are asking for, the venue.
_LIVE = (BookingStatus.pending, BookingStatus.approved, BookingStatus.tentative_hold)

_FIELDS = (
    ("name", "name"),
    ("location", "location"),
    ("capacity", "capacity"),
    ("facilities", "facilities"),
    ("accessibility_features", "accessibility features"),
    ("supported_layouts", "supported room layouts"),
    ("operating_hours", "operating hours"),
)


def _show(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(value) if value else "none"
    return str(value)


def _duplicate(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"A venue named '{name}' already exists. Venue names must be unique.",
    )


def _check_name_free(db: Session, name: str, own_id: int | None) -> None:
    query = select(Venue.id).where(func.lower(Venue.name) == name.casefold())
    if own_id is not None:
        query = query.where(Venue.id != own_id)
    if db.scalar(query.limit(1)) is not None:
        raise _duplicate(name)


class VenueReviewFlagger:
    """Finds the future bookings an edit leaves in doubt, flags them for
    review and tells the Coordinator. Never changes a booking's status."""

    def __init__(self, db: Session, actor: User, log: ActivityLog) -> None:
        self._db = db
        self._actor = actor
        self._log = log

    def flag(self, venue: Venue, old_capacity: int, old_layouts: list[str]) -> list[FlaggedBookingOut]:
        reduced = venue.capacity < old_capacity
        new_layouts = {x.casefold() for x in venue.supported_layouts}
        removed = {x.casefold(): x for x in old_layouts if x.casefold() not in new_layouts}
        if not reduced and not removed:
            return []
        now = datetime.now(timezone.utc)
        bookings = self._db.scalars(
            select(VenueBooking)
            .where(
                VenueBooking.venue_id == venue.id,
                VenueBooking.status.in_(_LIVE),
                active_hold_filter(now),
                VenueBooking.start_time > now,
                VenueBooking.review_flagged_at.is_(None),
            )
            .options(joinedload(VenueBooking.event))
            .order_by(VenueBooking.start_time, VenueBooking.id)
        ).unique()
        flagged: list[FlaggedBookingOut] = []
        for booking in bookings:
            event = booking.event
            reasons = []
            attendance = (
                booking.expected_attendance
                if booking.expected_attendance is not None
                else event.expected_attendance
            )
            if reduced and (attendance is None or attendance > venue.capacity):
                reasons.append(
                    f"capacity reduced from {old_capacity} to {venue.capacity}"
                    + (f" (expected attendance {attendance})" if attendance is not None else "")
                )
            layout = (booking.room_layout_preference or event.room_layout_preference or "").strip()
            if layout.casefold() in removed:
                reasons.append(f"room layout '{removed[layout.casefold()]}' is no longer supported")
            if not reasons:
                continue
            reason = "; ".join(reasons)
            booking.review_flagged_at = now
            booking.review_reason = reason
            self._log.record(
                event,
                self._actor,
                f"Venue booking '{venue.name}' flagged for review: {reason}. The booking is kept.",
            )
            if event.coordinator_id is not None:
                notify(
                    self._db,
                    user_id=event.coordinator_id,
                    event_id=event.id,
                    type=NotificationType.venue_booking_conflict,
                    message=(
                        f"Your venue booking '{venue.name}' for '{event.name or 'Untitled event'}' "
                        f"is flagged for review: {reason}. The booking is kept."
                    ),
                )
            flagged.append(
                FlaggedBookingOut(booking_id=booking.id, event_id=event.id, event_name=event.name, reason=reason)
            )
        return flagged


def _apply(venue: Venue, body: VenueIn) -> None:
    venue.name = body.name
    venue.location = body.location
    venue.capacity = body.capacity
    venue.facilities = list(body.facilities)
    venue.accessibility_features = list(body.accessibility_features)
    venue.supported_layouts = list(body.supported_layouts)
    venue.operating_hours = body.operating_hours


@router.post("", response_model=VenueSaved, status_code=status.HTTP_201_CREATED)
def add_venue(
    body: VenueIn,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueSaved:
    """Add a Venue to the catalogue. Refused (nothing saved) when a detail is
    missing or invalid, or the name matches another Venue."""
    _check_name_free(db, body.name, None)
    venue = Venue(is_active=True)
    _apply(venue, body)
    db.add(venue)
    try:
        db.flush()
        db.add(VenueActivity(venue_id=venue.id, changed_by=user.id, note=f"Venue '{venue.name}' added."))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate(body.name) from None
    db.refresh(venue)
    return VenueSaved.model_validate(venue)


@router.put("/{venue_id}", response_model=VenueSaved)
def edit_venue(
    venue_id: int,
    body: VenueIn,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueSaved:
    """Replace a Venue's catalogue details. The venue row is locked, so a
    booking cannot slip in between the change and the review flagging."""
    expire_tentative_holds(db)  # commits, so do it before taking the lock
    venue = db.get(Venue, venue_id, with_for_update=True)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    _check_name_free(db, body.name, venue.id)
    before = {field: list(getattr(venue, field) or []) if field in _LISTS else getattr(venue, field) for field, _ in _FIELDS}
    old_capacity, old_layouts = venue.capacity, list(venue.supported_layouts or [])
    _apply(venue, body)
    changes = [
        f"{label}: {_show(before[field])} -> {_show(getattr(venue, field))}"
        for field, label in _FIELDS
        if before[field] != getattr(venue, field)
    ]
    flagged: list[FlaggedBookingOut] = []
    if changes:
        db.add(
            VenueActivity(
                venue_id=venue.id,
                changed_by=user.id,
                note=f"Venue '{venue.name}' edited. " + "; ".join(changes),
            )
        )
        flagged = VenueReviewFlagger(db, user, EventHistoryLog(db)).flag(venue, old_capacity, old_layouts)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate(body.name) from None
    db.refresh(venue)
    saved = VenueSaved.model_validate(venue)
    saved.flagged_bookings = flagged
    return saved


_LISTS = {"facilities", "accessibility_features", "supported_layouts"}


@router.get("/activity", response_model=list[VenueActivityOut])
def venue_activity_log(
    db: Session = Depends(get_db),
    _: User = Depends(_venue_staff),
) -> list[VenueActivityOut]:
    """The venue Activity Log, newest first: the change, who made it, when."""
    rows = db.scalars(
        select(VenueActivity)
        .options(joinedload(VenueActivity.actor))
        .order_by(VenueActivity.created_at.desc(), VenueActivity.id.desc())
        .limit(200)
    ).unique()
    names = {v.id: v.name for v in db.scalars(select(Venue))}
    return [
        VenueActivityOut(
            id=r.id,
            venue_id=r.venue_id,
            venue_name=names.get(r.venue_id, ""),
            note=r.note,
            changed_by=r.actor.name if r.actor else None,
            created_at=r.created_at,
        )
        for r in rows
    ]
