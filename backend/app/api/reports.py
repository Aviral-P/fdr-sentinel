"""Filtered JSON and CSV reports for local operations."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    FDRInstrument, IntegrityFinding, IntegrityReviewStatus, InstrumentLifecycleStatus,
    OperationalPriority, ReleaseRequest, ReleaseRequestStatus, User, VerificationCheck,
    VerificationCheckStatus,
)
from app.schemas.api import FDRInstrumentItem, Page
from app.schemas.operations import (
    PendingVerificationRow, ReleaseReportRow, ReportInstrumentRow, UpcomingMaturityRow,
)
from app.services.operations_service import _filtered_instruments

router = APIRouter(prefix="/reports", tags=["reports"])


def _csv_response(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        safe = []
        for value in row:
            text = "" if value is None else str(value)
            if text.startswith(("=", "+", "-", "@")):
                text = "'" + text
            safe.append(text)
        writer.writerow(safe)
    return Response(
        content="\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _instrument_filter_args(institution_id, date_from, date_to, lifecycle_status, priority):
    return dict(
        institution_id=institution_id, date_from=date_from, date_to=date_to,
        lifecycle_status=lifecycle_status, priority=priority,
    )


def _instrument_page(db, user, *, limit, offset, **filters):
    instruments = _filtered_instruments(db, user, **filters)
    total = len(instruments)
    page = instruments[offset:offset + limit]
    items = [ReportInstrumentRow.model_validate(
        FDRInstrumentItem.model_validate(row).model_dump() | {"institution_name": row.institution.name}
    ) for row in page]
    return Page[ReportInstrumentRow](items=items, total=total, limit=limit, offset=offset)


@router.get("/instruments", response_model=Page[ReportInstrumentRow])
def instrument_report(
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None,
    priority: OperationalPriority | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _instrument_page(db, user, limit=limit, offset=offset,
                            **_instrument_filter_args(institution_id, date_from, date_to, lifecycle_status, priority))


@router.get("/instruments.csv")
def instrument_csv(
    institution_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None, priority: OperationalPriority | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rows = _filtered_instruments(db, user, **_instrument_filter_args(institution_id, date_from, date_to, lifecycle_status, priority))
    return _csv_response("fdr-instruments.csv", ["instrument_id", "institution", "reference", "amount", "issue_date", "maturity_date", "lifecycle_status", "priority"], [
        [r.id, r.institution.name, r.reference_original, r.amount, r.issue_date, r.maturity_date, r.lifecycle_status.value, r.priority.value] for r in rows
    ])


def _upcoming_rows(db: Session, user: User, *, institution_id, date_from, date_to, lifecycle_status, priority):
    today = date.today()
    start = date_from or today
    end = date_to or today + timedelta(days=max(get_settings().maturity_reminder_window_list))
    records = _filtered_instruments(db, user, institution_id, start, end, lifecycle_status, priority)
    return [UpcomingMaturityRow(instrument=r, institution_name=r.institution.name,
                                days_to_maturity=(r.maturity_date - today).days, has_successor=r.successor is not None)
            for r in records if r.maturity_date >= today and r.lifecycle_status not in {
                InstrumentLifecycleStatus.RELEASED, InstrumentLifecycleStatus.REJECTED, InstrumentLifecycleStatus.SUPERSEDED
            }]


@router.get("/upcoming-maturities", response_model=Page[UpcomingMaturityRow])
def upcoming_maturities(
    institution_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None, priority: OperationalPriority | None = None,
    limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rows = _upcoming_rows(db, user, institution_id=institution_id, date_from=date_from, date_to=date_to,
                          lifecycle_status=lifecycle_status, priority=priority)
    return Page[UpcomingMaturityRow](items=rows[offset:offset+limit], total=len(rows), limit=limit, offset=offset)


@router.get("/upcoming-maturities.csv")
def upcoming_maturities_csv(
    institution_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None, priority: OperationalPriority | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rows = _upcoming_rows(db, user, institution_id=institution_id, date_from=date_from, date_to=date_to,
                          lifecycle_status=lifecycle_status, priority=priority)
    return _csv_response("upcoming-maturities.csv", ["instrument_id", "institution", "reference", "maturity_date", "days_to_maturity", "has_successor"], [
        [r.instrument.id, r.institution_name, r.instrument.reference_original, r.instrument.maturity_date, r.days_to_maturity, r.has_successor] for r in rows
    ])


def _verification_rows(db: Session, user: User, *, institution_id, date_from, date_to, lifecycle_status, priority):
    instruments = _filtered_instruments(db, user, institution_id, date_from, date_to, lifecycle_status, priority)
    ids = [r.id for r in instruments]
    checks = list(db.scalars(select(VerificationCheck).where(
        VerificationCheck.instrument_id.in_(ids), VerificationCheck.is_required.is_(True), VerificationCheck.status == VerificationCheckStatus.OPEN
    ))) if ids else []
    findings = list(db.scalars(select(IntegrityFinding).where(
        IntegrityFinding.instrument_id.in_(ids), IntegrityFinding.is_current.is_(True), IntegrityFinding.review_status == IntegrityReviewStatus.OPEN
    ))) if ids else []
    c_counts: dict[str, int] = {}; f_counts: dict[str, int] = {}
    for row in checks: c_counts[row.instrument_id] = c_counts.get(row.instrument_id, 0) + 1
    for row in findings: f_counts[row.instrument_id] = f_counts.get(row.instrument_id, 0) + 1
    return [PendingVerificationRow(instrument=r, institution_name=r.institution.name,
                                   open_required_checks=c_counts.get(r.id, 0), open_findings=f_counts.get(r.id, 0))
            for r in instruments if c_counts.get(r.id, 0) or f_counts.get(r.id, 0)]


@router.get("/pending-verification", response_model=Page[PendingVerificationRow])
def pending_verification(
    institution_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None, priority: OperationalPriority | None = None,
    limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rows = _verification_rows(db, user, institution_id=institution_id, date_from=date_from, date_to=date_to,
                              lifecycle_status=lifecycle_status, priority=priority)
    return Page[PendingVerificationRow](items=rows[offset:offset+limit], total=len(rows), limit=limit, offset=offset)


@router.get("/pending-verification.csv")
def pending_verification_csv(
    institution_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None, priority: OperationalPriority | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rows = _verification_rows(db, user, institution_id=institution_id, date_from=date_from, date_to=date_to,
                              lifecycle_status=lifecycle_status, priority=priority)
    return _csv_response("pending-verification.csv", ["instrument_id", "institution", "reference", "open_required_checks", "open_findings"], [
        [r.instrument.id, r.institution_name, r.instrument.reference_original, r.open_required_checks, r.open_findings] for r in rows
    ])


def _release_rows(db: Session, user: User, *, institution_id, date_from, date_to, lifecycle_status, priority):
    instruments = _filtered_instruments(db, user, institution_id, date_from, date_to, lifecycle_status, priority)
    by_id = {r.id: r for r in instruments}
    ids = list(by_id)
    requests = list(db.scalars(select(ReleaseRequest).where(
        ReleaseRequest.instrument_id.in_(ids), ReleaseRequest.status == ReleaseRequestStatus.PENDING
    ).order_by(ReleaseRequest.created_at))) if ids else []
    return [ReleaseReportRow(id=r.id, instrument_id=r.instrument_id, institution_id=by_id[r.instrument_id].institution_id,
                             institution_name=by_id[r.instrument_id].institution.name, requested_amount=str(r.requested_amount),
                             eligibility_status=r.eligibility_status, status=r.status.value, reason=r.reason,
                             created_at=r.created_at, updated_at=r.updated_at) for r in requests]


@router.get("/release-requests", response_model=Page[ReleaseReportRow])
def release_request_report(
    institution_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None, priority: OperationalPriority | None = None,
    limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rows = _release_rows(db, user, institution_id=institution_id, date_from=date_from, date_to=date_to,
                         lifecycle_status=lifecycle_status, priority=priority)
    return Page[ReleaseReportRow](items=rows[offset:offset+limit], total=len(rows), limit=limit, offset=offset)


@router.get("/release-requests.csv")
def release_request_csv(
    institution_id: str | None = None, date_from: date | None = None, date_to: date | None = None,
    lifecycle_status: InstrumentLifecycleStatus | None = None, priority: OperationalPriority | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rows = _release_rows(db, user, institution_id=institution_id, date_from=date_from, date_to=date_to,
                         lifecycle_status=lifecycle_status, priority=priority)
    return _csv_response("release-requests.csv", ["request_id", "instrument_id", "institution", "amount", "eligibility", "status", "created_at"], [
        [r.id, r.instrument_id, r.institution_name, r.requested_amount, r.eligibility_status, r.status, r.created_at.isoformat()] for r in rows
    ])
