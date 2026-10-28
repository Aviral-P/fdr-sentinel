"""Login, logout, and authenticated identity endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.dependencies import AuthContext, get_auth_context
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import AuthSession, User
from app.schemas.auth import AuthenticatedUserRead, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.strip().lower()))
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    token, token_id, expires_at = create_access_token(user.id, settings)
    auth_session = AuthSession(
        user_id=user.id,
        token_id=token_id,
        expires_at=expires_at,
    )
    db.add(auth_session)
    db.commit()
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_access_token_minutes * 60,
    )


@router.post("/logout", status_code=204)
def logout(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> None:
    session = db.get(AuthSession, context.auth_session.id)
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="The access token is no longer active.")
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/me", response_model=AuthenticatedUserRead)
def read_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user
