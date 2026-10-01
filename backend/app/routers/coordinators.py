from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.coordinator_availability import CoordinatorAvailabilityHistory
from app.models.user import User
from app.schemas.event import OrganiserContact
from app.schemas.user import (
    AvailabilityHistoryEntry,
    AvailabilityUpdate,
    AvailableCoordinatorCount,
    UserOut,
)
from app.services.assignment import available_coordinators

router = APIRouter(prefix="/coordinators", tags=["coordinators"])


@router.get("/available-count", response_model=AvailableCoordinatorCount)
def get_available_coordinator_count(
    db: Session = Depends(get_db),
    _caller: User = Depends(require_role(Role.ORGANISER)),
) -> AvailableCoordinatorCount:
    """Who a newly submitted event could be assigned to, and how many.

    A debugging aid for Organisers -- it explains why a request is sitting
    "Not yet assigned" (the pool is empty) and which Coordinators are in it.
    Read straight from `available_coordinators`, the very query assignment
    picks from, so the list can never disagree with who actually gets
    chosen. Only name and email are exposed -- not what anyone holds.
    """
    pool = available_coordinators(db).order_by(User.id).all()
    return AvailableCoordinatorCount(
        available=len(pool),
        coordinators=[OrganiserContact.model_validate(c) for c in pool],
    )


@router.patch("/me/availability", response_model=UserOut)
def set_my_availability(
    body: AvailabilityUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_role(Role.COORDINATOR)),
) -> UserOut:
    """Toggle the caller's own availability.

    `require_role` only proves identity from the JWT (id + role); the row
    itself -- and the name a reassignment note needs -- still has to come
    from the database, the same way GET /auth/me re-fetches its profile.

    Availability only decides who is picked for NEW events: while it is off
    the caller is excluded from the assignment pool, and back in it once it
    is turned on again. Events already assigned to them are left exactly as
    they are -- turning it off never moves, unassigns or notifies about
    anything. Every actual change is recorded in the caller's availability
    history, even when they hold no events.
    """
    # Locked so two overlapping requests (two tabs, a double click) are
    # applied one after the other: the second re-reads the value the first
    # set, sees "no change", and records nothing -- rather than both reading
    # the old value and both logging a change.
    user = db.get(User, caller.id, with_for_update=True)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    if user.is_available != body.is_available:
        user.is_available = body.is_available
        # Stamped here, under the lock, not by the database's now(): in
        # Postgres now() is the moment the TRANSACTION began, so a request
        # that waited for the lock could carry an earlier time than the
        # change it followed and the history would read out of order.
        db.add(
            CoordinatorAvailabilityHistory(
                coordinator_id=user.id,
                is_available=user.is_available,
                created_at=datetime.now(timezone.utc),
            )
        )

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/me/availability-history", response_model=list[AvailabilityHistoryEntry])
def get_my_availability_history(
    db: Session = Depends(get_db),
    caller: User = Depends(require_role(Role.COORDINATOR)),
) -> list[AvailabilityHistoryEntry]:
    """The caller's own availability-toggle history, newest first.

    Written every time PATCH /coordinators/me/availability actually changes
    the value -- unlike the reassignment activity log, this fires even when
    the Coordinator had zero active events at the time.
    """
    rows = (
        db.query(CoordinatorAvailabilityHistory)
        .filter(CoordinatorAvailabilityHistory.coordinator_id == caller.id)
        .order_by(CoordinatorAvailabilityHistory.created_at.desc(), CoordinatorAvailabilityHistory.id.desc())
        .all()
    )
    return [AvailabilityHistoryEntry.model_validate(r) for r in rows]
