"""Authenticated in-app notifications."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Notification, User
from app.schemas.api import Page
from app.schemas.operations import NotificationItem, NotificationReadResult

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationItem])
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(Notification).where(Notification.recipient_user_id == user.id)
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    total = len(list(db.scalars(statement)))
    rows = list(db.scalars(statement.order_by(Notification.created_at.desc(), Notification.id).limit(limit).offset(offset)))
    return Page[NotificationItem](items=rows, total=total, limit=limit, offset=offset)


@router.post("/{notification_id}/read", response_model=NotificationReadResult)
def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalar(select(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_user_id == user.id,
    ))
    if row is None:
        raise AppError(404, "not_found", "Notification not found.")
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return {"notification": row}
