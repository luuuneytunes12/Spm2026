from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.venues import Venue
from app.schemas.venue import VenueDetail, VenueSummary

router = APIRouter(prefix="/venues", tags=["venues"])

# Gated on role, not on VENUE_READ. The story is for INTERNAL users
# (Event Coordinators and Venue Staff), and VENUE_READ is also held by
# Attendees -- gating on the permission would show them internal venue
# details the story never meant them to see.
_internal = require_role(Role.COORDINATOR, Role.VENUE_STAFF)


@router.get("", response_model=list[VenueSummary])
def list_venues(
    db: Session = Depends(get_db),
    _: object = Depends(_internal),
) -> list[VenueSummary]:
    """Every venue, alphabetically.

    Inactive venues are still listed (flagged by `is_active`): Venue Staff
    need to see them, and a Coordinator is better told "inactive" than left
    wondering where a venue went.
    """
    venues = db.execute(select(Venue).order_by(Venue.name, Venue.id)).scalars()
    return [VenueSummary.model_validate(v) for v in venues]


@router.get("/{venue_id}", response_model=VenueDetail)
def get_venue(
    venue_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(_internal),
) -> VenueDetail:
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return VenueDetail.model_validate(venue)
