"""Review-only integrity scan, findings, and prioritized scrutiny queue."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_scrutiny_officer
from app.core.errors import AppError
from app.db.session import get_db
from app.models import IntegrityReviewStatus, Role, User
from app.schemas.api import (
    IntegrityFindingItem,
    IntegrityFindingReviewRequest,
    IntegrityQueueItem,
    IntegrityScanSummary,
    Page,
)
from app.services.integrity_service import (
    get_prioritized_scrutiny_queue,
    list_integrity_findings,
    review_integrity_finding,
    run_integrity_scan,
)

router = APIRouter(prefix="/integrity", tags=["integrity review"])
READ_ROLES = {Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR, Role.ADMIN}


@router.post("/scan", response_model=IntegrityScanSummary)
def scan_integrity(
    user: User = Depends(require_scrutiny_officer()),
    db: Session = Depends(get_db),
):
    return run_integrity_scan(db, user)


@router.get("/queue", response_model=Page[IntegrityQueueItem])
def read_scrutiny_queue(
    review_status: IntegrityReviewStatus = IntegrityReviewStatus.OPEN,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view the cross-institution scrutiny queue.")
    items, total = get_prioritized_scrutiny_queue(
        db, user, limit=limit, offset=offset, review_status=review_status
    )
    return Page[IntegrityQueueItem](items=items, total=total, limit=limit, offset=offset)


@router.get("/findings", response_model=Page[IntegrityFindingItem])
def read_findings(
    review_status: IntegrityReviewStatus | None = None,
    instrument_id: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view cross-institution integrity findings.")
    findings, total = list_integrity_findings(
        db, user, limit=limit, offset=offset, review_status=review_status, instrument_id=instrument_id
    )
    return Page[IntegrityFindingItem](items=findings, total=total, limit=limit, offset=offset)


@router.post("/findings/{finding_id}/review", response_model=IntegrityFindingItem)
def review_finding(
    finding_id: str,
    payload: IntegrityFindingReviewRequest,
    user: User = Depends(require_scrutiny_officer()),
    db: Session = Depends(get_db),
):
    return review_integrity_finding(
        db,
        user,
        finding_id,
        decision=IntegrityReviewStatus(payload.decision),
        resolution_notes=payload.resolution_notes,
    )
