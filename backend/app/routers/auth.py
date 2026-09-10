from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, permissions_for
from app.core.roles import DEFAULT_ROLE
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut
from app.schemas.user import MeOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/auth"

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
)


def _set_refresh_cookie(response: Response, user: User) -> None:
    refresh_token = create_refresh_token(user.id, user.role)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=False,
        path=REFRESH_COOKIE_PATH,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Registration always assigns DEFAULT_ROLE; a client can never supply
    # its own role here.
    user = User(
        name=body.name,
        email=email,
        password_hash=hash_password(body.password),
        role=DEFAULT_ROLE.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _set_refresh_cookie(response, user)
    return TokenOut(access_token=create_access_token(user.id, user.role))


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()
    # One generic message for both "no such user" and "wrong password".
    if user is None or not verify_password(body.password, user.password_hash):
        raise _INVALID_CREDENTIALS

    _set_refresh_cookie(response, user)
    return TokenOut(access_token=create_access_token(user.id, user.role))


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    payload = decode_token(token, expected_typ="refresh")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from None

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    _set_refresh_cookie(response, user)
    return TokenOut(access_token=create_access_token(user.id, user.role))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    permissions = sorted(permissions_for(user.role))
    return MeOut(user=UserOut.model_validate(user), permissions=permissions)
