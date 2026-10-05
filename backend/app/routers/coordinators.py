from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.user import User
from app.schemas.event import OrganiserContact
from app.schemas.user import AvailableCoordinatorCount
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
