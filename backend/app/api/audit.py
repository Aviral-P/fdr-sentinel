"""Authorized, read-only global audit feed."""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models import AuditEvent, Institution, Role, User
from app.schemas.api import Page
from app.schemas.operations import AuditFeedItem

router = APIRouter(prefix="/audit", tags=["audit"])
_INTERNAL_AUDIT_ROLES = (Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR, Role.ADMIN)


@router.get("/events", response_model=Page[AuditFeedItem])
def list_audit_events(
    institution_id: str | None = None,
    entity_type: str | None = Query(default=None, max_length=100),
    action: str | None = Query(default=None, max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_roles(*_INTERNAL_AUDIT_ROLES)),
    db: Session = Depends(get_db),
):
    """Return redacted audit metadata; sensitive before/after payloads are never exposed."""
    if date_from and date_to and date_to < date_from:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="date_to must be on or after date_from")

    actor = aliased(User)
    institution = aliased(Institution)
    statement = select(AuditEvent, actor.full_name, institution.name).outerjoin(
        actor, AuditEvent.actor_user_id == actor.id
    ).outerjoin(institution, AuditEvent.institution_id == institution.id)
    count_statement = select(func.count(AuditEvent.id))
    filters = []
    if institution_id:
        filters.append(AuditEvent.institution_id == institution_id)
    if entity_type:
        filters.append(AuditEvent.entity_type == entity_type)
    if action:
        filters.append(AuditEvent.action == action)
    if date_from:
        filters.append(AuditEvent.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        filters.append(AuditEvent.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    if filters:
        statement = statement.where(*filters)
        count_statement = count_statement.where(*filters)
    total = db.scalar(count_statement) or 0
    rows = db.execute(statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset(offset).limit(limit)).all()
    items = [AuditFeedItem(
        id=event.id, actor_user_id=event.actor_user_id, actor_name=actor_name,
        institution_id=event.institution_id, institution_name=institution_name,
        entity_type=event.entity_type, entity_id=event.entity_id, action=event.action,
        created_at=event.created_at,
    ) for event, actor_name, institution_name in rows]
    return Page[AuditFeedItem](items=items, total=total, limit=limit, offset=offset)
