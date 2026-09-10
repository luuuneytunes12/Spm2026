import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.roles import Permission, Role, ROLE_PERMISSIONS
from app.core.security import decode_token
from app.models.user import User

logger = logging.getLogger(__name__)

# auto_error=False so a MISSING Authorization header is handled here as a
# 401, not FastAPI's default 403. "No credentials" is unauthenticated, not
# forbidden, and the client's refresh-and-retry only triggers on 401 -- a
# 403 here would be treated as a permission failure instead.
_bearer_scheme = HTTPBearer(auto_error=False)


def permissions_for(role: str) -> frozenset[Permission]:
    """Resolve the permission set for a raw `role` string from the DB.

    A role value that isn't a recognized `Role` member (e.g. left over
    from a rename, or corrupted data) grants NO permissions rather than
    raising -- `Role(role)` would raise `ValueError` and turn into an
    unhandled 500 for every request from that user.
    """
    try:
        return ROLE_PERMISSIONS.get(Role(role), frozenset())
    except ValueError:
        logger.warning("Unrecognized role %r on user; granting no permissions", role)
        return frozenset()


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller from the access token, re-reading the User row
    from the database on every request so that a role change takes
    effect on the very next request, even with an already-issued token."""
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials, expected_typ="access")

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_permission(*perms: Permission) -> Callable:
    """Dependency factory: 403s unless the current user's role grants
    every permission in `perms`."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        granted = permissions_for(user.role)
        missing = [p for p in perms if p not in granted]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission(s): {', '.join(missing)}",
            )
        return user

    return _dependency


def require_role(*roles: Role) -> Callable:
    """Escape hatch for identity-based (rather than permission-based)
    checks, e.g. gating an action to a specific role regardless of its
    permission set."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        try:
            role = Role(user.role)
        except ValueError:
            role = None
        if role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return user

    return _dependency
