from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.user import User
from app.schemas.user import AvailabilityUpdate, UserOut
from app.services.assignment import events_needing_reassignment, reassign_event

router = APIRouter(prefix="/coordinators", tags=["coordinators"])


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

    Turning availability OFF immediately reassigns every event currently
    active under this Coordinator to another available one (or leaves it
    unassigned if none exists) -- the whole point of the story is that an
    Organiser's event does not sit stuck with a Coordinator who cannot work
    on it.
    """
    user = db.get(User, caller.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    if user.is_available != body.is_available:
        user.is_available = body.is_available
        if body.is_available is False:
            for event in events_needing_reassignment(db, user.id):
                reassign_event(db, event, outgoing=user)

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
