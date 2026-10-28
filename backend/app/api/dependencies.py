"""Authentication, role, and institution-scoping dependencies."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import get_signing_key
from app.db.session import get_db
from app.models import AuthSession, FDRInstrument, Role, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    auth_session: AuthSession


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Authentication is required or the access token is invalid.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()

    settings = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials,
            get_signing_key(settings),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "jti", "iat", "exp", "iss"]},
        )
    except AppError:
        raise
    except jwt.PyJWTError as exc:
        raise unauthorized() from exc

    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_id == claims["jti"],
            AuthSession.user_id == claims["sub"],
        )
    )
    if auth_session is None or auth_session.revoked_at is not None:
        raise unauthorized()
    expiry = auth_session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        raise unauthorized()
    user = db.get(User, auth_session.user_id)
    if user is None or not user.active:
        raise unauthorized()
    return AuthContext(user=user, auth_session=auth_session)


def get_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user


def assert_roles(user: User, *allowed_roles: Role) -> User:
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="This role is not permitted to perform this action.")
    return user


def require_roles(*allowed_roles: Role) -> Callable:
    """Build an exact role guard; admin is never implicitly elevated."""
    def role_dependency(user: User = Depends(get_current_user)) -> User:
        return assert_roles(user, *allowed_roles)

    return role_dependency


def require_scrutiny_officer() -> Callable:
    """Guard scrutiny and clarification actions; admin is not implicitly included."""
    return require_roles(Role.SCRUTINY_OFFICER)


def require_approving_authority() -> Callable:
    """Guard final decisions; only the approving-authority role is accepted."""
    return require_roles(Role.APPROVING_AUTHORITY)


def require_auditor() -> Callable:
    """Guard audit-only endpoints."""
    return require_roles(Role.AUDITOR)


def require_admin() -> Callable:
    """Guard administration endpoints with explicit admin-only access."""
    return require_roles(Role.ADMIN)


def assert_institution_access(user: User, institution_id: str) -> None:
    if user.role == Role.INSTITUTION_USER and user.institution_id != institution_id:
        # Hide whether a cross-institution identifier exists.
        raise HTTPException(status_code=404, detail="Record not found.")
    if user.role not in {
        Role.INSTITUTION_USER,
        Role.SCRUTINY_OFFICER,
        Role.APPROVING_AUTHORITY,
        Role.AUDITOR,
        Role.ADMIN,
    }:
        raise HTTPException(status_code=403, detail="This role is not permitted to access records.")


def get_accessible_instrument(
    fdr_id: str,
    user: User,
    db: Session,
) -> FDRInstrument:
    statement = select(FDRInstrument).where(FDRInstrument.id == fdr_id)
    if user.role == Role.INSTITUTION_USER:
        if user.institution_id is None:
            raise HTTPException(status_code=404, detail="Record not found.")
        statement = statement.where(FDRInstrument.institution_id == user.institution_id)
    elif user.role not in {
        Role.SCRUTINY_OFFICER,
        Role.APPROVING_AUTHORITY,
        Role.AUDITOR,
        Role.ADMIN,
    }:
        raise HTTPException(status_code=403, detail="This role is not permitted to access records.")
    instrument = db.scalar(statement)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    return instrument
