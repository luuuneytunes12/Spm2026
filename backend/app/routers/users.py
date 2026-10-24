from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.roles import INTERNAL_ROLES, is_internal_staff
from app.models.user import User
from app.schemas.user import StaffMemberOut, UserOut, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/staff", response_model=list[StaffMemberOut])
def list_staff(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[StaffMemberOut]:
    """Internal staff and their departments / responsibilities, so a
    colleague can tell who the right point of contact is. Internal staff
    only -- the role is re-read from the database, not trusted from the token."""
    row = db.get(User, user.id)
    if row is None or not is_internal_staff(row.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    staff = (
        db.query(User)
        .filter(User.role.in_([r.value for r in INTERNAL_ROLES]))
        .order_by(User.name, User.id)
        .all()
    )
    return [StaffMemberOut.model_validate(u) for u in staff]


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

    # get_current_user returns a transient object built from the JWT claims,
    # not a row in this session -- load the real one before writing to it.
    row = db.get(User, user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
        )

    internal = is_internal_staff(row.role)
    if not internal and (
        data.get("department") is not None or data.get("responsibilities") is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only internal staff can record a department or responsibilities",
        )
    if internal:
        # An omitted department keeps the saved one; an explicit null (or
        # none ever chosen) leaves nothing, and staff must have one.
        resulting = data["department"] if "department" in data else row.department
        if resulting is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[
                    {
                        "loc": ["body", "department"],
                        "msg": "Choose your department.",
                        "type": "value_error",
                    }
                ],
            )

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
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return UserOut.model_validate(row)
