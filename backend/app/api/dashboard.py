"""Operational dashboard metrics and explainable action queue."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import InstrumentLifecycleStatus, OperationalPriority, User
from app.schemas.api import FDRInstrumentItem, Page
from app.schemas.operations import DashboardSummary, QueueItem
from app.services.operations_service import action_queue, dashboard_summary, pending_scrutiny_cases

router = APIRouter(prefix="/dashboard", tags=["dashboard and action queue"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None,
    priority: OperationalPriority | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_summary(
        db, user, institution_id=institution_id, date_from=date_from, date_to=date_to,
        lifecycle_status=lifecycle_status, priority=priority,
    )


@router.get("/queue", response_model=Page[QueueItem])
def get_dashboard_queue(
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None,
    priority: OperationalPriority | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = action_queue(
        db, user, limit=limit, offset=offset, institution_id=institution_id,
        date_from=date_from, date_to=date_to, lifecycle_status=lifecycle_status, priority=priority,
    )
    return Page[QueueItem](items=items, total=total, limit=limit, offset=offset)


@router.get("/pending-scrutiny", response_model=Page[FDRInstrumentItem])
def get_pending_scrutiny(
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    priority: OperationalPriority | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = pending_scrutiny_cases(
        db, user, limit=limit, offset=offset, institution_id=institution_id,
        date_from=date_from, date_to=date_to, priority=priority,
    )
    return Page[FDRInstrumentItem](items=items, total=total, limit=limit, offset=offset)
