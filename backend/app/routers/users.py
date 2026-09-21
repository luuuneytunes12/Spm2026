from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserOut, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserOut)
def update_my_profile(
    body: UserProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """Update the caller's own profile (name, organisation, contact
    details, communication preference).

    Format/range validation (email shape, phone digits-per-country,
    known communication preference) lives entirely in `UserProfileUpdate`
    -- a request that fails it never reaches here, so nothing is written.
    The one check that cannot live in the schema is email uniqueness,
    since it needs the database.

    exclude_unset means an omitted field is left alone; every field the
    client did send is applied in the same commit, so a save is all-or-
    nothing.
    """
    data = body.model_dump(exclude_unset=True)

    email = data.get("email")
    if email is not None:
        email = email.lower()
        existing = db.query(User).filter(User.email == email, User.id != user.id).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already in use"
            )
        data["email"] = email

    for field, value in data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
