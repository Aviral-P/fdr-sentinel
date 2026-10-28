"""Database-backed dashboard, queue, report, and reminder operations."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AuditEvent,
    FDRInstrument,
    IntegrityFinding,
    IntegrityReviewStatus,
    InstrumentLifecycleStatus as Life,
    Notification,
    OperationalPriority,
    ReleaseRequest,
    ReleaseRequestStatus,
    Role,
    User,
    VerificationCheck,
    VerificationCheckStatus,
)
from app.services.audit_service import record_audit_event

ACTIVE_STATUSES = {
    Life.SUBMITTED, Life.UNDER_SCRUTINY, Life.CLARIFICATION_REQUIRED,
    Life.APPROVED, Life.RELEASE_PENDING, Life.MATURED,
}
SCRUTINY_STATUSES = {Life.SUBMITTED, Life.UNDER_SCRUTINY}
REVIEW_STATUSES = {Life.SUBMITTED, Life.UNDER_SCRUTINY, Life.CLARIFICATION_REQUIRED}
MATURITY_ACTION_STATUSES = {Life.APPROVED, Life.MATURED, Life.RELEASE_PENDING}
INTERNAL_ROLES = {Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR, Role.ADMIN}


def _filtered_instruments(
    db: Session,
    user: User,
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    lifecycle_status: Life | None = None,
    priority: OperationalPriority | None = None,
) -> list[FDRInstrument]:
    if date_from and date_to and date_from > date_to:
        raise AppError(422, "invalid_date_range", "date_from cannot be later than date_to.")
    if user.role == Role.INSTITUTION_USER:
        if user.institution_id is None or (institution_id and institution_id != user.institution_id):
            raise AppError(404, "not_found", "Record not found.")
        institution_id = user.institution_id
    elif user.role not in INTERNAL_ROLES:
        raise AppError(403, "forbidden", "This role cannot view operational records.")
    statement = select(FDRInstrument).options(joinedload(FDRInstrument.institution))
    if institution_id:
        statement = statement.where(FDRInstrument.institution_id == institution_id)
    if date_from:
        statement = statement.where(FDRInstrument.maturity_date >= date_from)
    if date_to:
        statement = statement.where(FDRInstrument.maturity_date <= date_to)
    if lifecycle_status:
        statement = statement.where(FDRInstrument.lifecycle_status == lifecycle_status)
    if priority:
        statement = statement.where(FDRInstrument.priority == priority)
    return list(db.scalars(statement.order_by(FDRInstrument.maturity_date, FDRInstrument.id)).unique())


def _open_finding_query(instrument_ids: list[str]):
    if not instrument_ids:
        return select(IntegrityFinding).where(False)
    return select(IntegrityFinding).where(
        IntegrityFinding.instrument_id.in_(instrument_ids),
        IntegrityFinding.is_current.is_(True),
        IntegrityFinding.review_status == IntegrityReviewStatus.OPEN,
    )


def _open_check_query(instrument_ids: list[str]):
    if not instrument_ids:
        return select(VerificationCheck).where(False)
    return select(VerificationCheck).where(
        VerificationCheck.instrument_id.in_(instrument_ids),
        VerificationCheck.is_required.is_(True),
        VerificationCheck.status == VerificationCheckStatus.OPEN,
    )


def dashboard_summary(
    db: Session,
    user: User,
    *,
    as_of: date | None = None,
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    lifecycle_status: Life | None = None,
    priority: OperationalPriority | None = None,
) -> dict[str, Any]:
    today = as_of or date.today()
    settings = get_settings()
    instruments = _filtered_instruments(db, user, institution_id, date_from, date_to, lifecycle_status, priority)
    ids = [row.id for row in instruments]
    findings = list(db.scalars(_open_finding_query(ids)))
    checks = list(db.scalars(_open_check_query(ids)))
    releases = list(db.scalars(select(ReleaseRequest).where(
        ReleaseRequest.instrument_id.in_(ids), ReleaseRequest.status == ReleaseRequestStatus.PENDING
    ))) if ids else []
    by_id = {row.id: row for row in instruments}
    unresolved_ids = {f.instrument_id for f in findings} | {c.instrument_id for c in checks}
    unresolved_ids |= {row.id for row in instruments if row.lifecycle_status == Life.CLARIFICATION_REQUIRED}
    pending_review_ids = {
        row.id for row in instruments
        if row.lifecycle_status in REVIEW_STATUSES and row.replacement_type is not None
    }
    overdue_days = settings.action_overdue_days
    overdue_ids: set[str] = set()
    for row in instruments:
        if row.lifecycle_status in MATURITY_ACTION_STATUSES and row.maturity_date < today:
            overdue_ids.add(row.id)
        elif row.lifecycle_status in {
            Life.SUBMITTED, Life.UNDER_SCRUTINY, Life.CLARIFICATION_REQUIRED, Life.RELEASE_PENDING,
        } and row.updated_at.date() <= today - timedelta(days=overdue_days):
            overdue_ids.add(row.id)
    active = [row for row in instruments if row.lifecycle_status in ACTIVE_STATUSES]
    end_of_window = today + timedelta(days=max(settings.maturity_reminder_window_list))
    return {
        "as_of": today,
        "maturity_reminder_windows_days": settings.maturity_reminder_window_list,
        "total_active_instruments": len(active),
        "approaching_maturity": sum(today <= row.maturity_date <= end_of_window and row.lifecycle_status in ACTIVE_STATUSES for row in instruments),
        "matured_requiring_action": sum(row.maturity_date < today and row.lifecycle_status in MATURITY_ACTION_STATUSES for row in instruments),
        "pending_scrutiny": sum(row.lifecycle_status in SCRUTINY_STATUSES for row in instruments),
        "open_discrepancy_findings": len(findings),
        "renewals_replacements_pending_review": len(pending_review_ids),
        "release_requests_pending_authorized_decision": len(releases),
        "overdue_actions": len(overdue_ids),
        "unresolved_cases": len(unresolved_ids),
    }


def pending_scrutiny_cases(
    db: Session,
    user: User,
    *,
    limit: int = 25,
    offset: int = 0,
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    priority: OperationalPriority | None = None,
) -> tuple[list[FDRInstrument], int]:
    """Return submitted/under-scrutiny cases, separate from finding review."""
    cases = [
        row for row in _filtered_instruments(
            db, user, institution_id, date_from, date_to, None, priority
        )
        if row.lifecycle_status in SCRUTINY_STATUSES
    ]
    return cases[offset : offset + limit], len(cases)


def action_queue(
    db: Session,
    user: User,
    *,
    as_of: date | None = None,
    limit: int = 25,
    offset: int = 0,
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    lifecycle_status: Life | None = None,
    priority: OperationalPriority | None = None,
) -> tuple[list[dict[str, Any]], int]:
    today = as_of or date.today()
    settings = get_settings()
    instruments = _filtered_instruments(db, user, institution_id, date_from, date_to, lifecycle_status, priority)
    ids = [row.id for row in instruments]
    findings = list(db.scalars(_open_finding_query(ids)))
    checks = list(db.scalars(_open_check_query(ids)))
    releases = list(db.scalars(select(ReleaseRequest).where(
        ReleaseRequest.instrument_id.in_(ids), ReleaseRequest.status == ReleaseRequestStatus.PENDING
    ))) if ids else []
    finding_by_instrument: dict[str, list[IntegrityFinding]] = {}
    checks_by_instrument: dict[str, list[VerificationCheck]] = {}
    release_ids: set[str] = set()
    for finding in findings:
        finding_by_instrument.setdefault(finding.instrument_id, []).append(finding)
    for check in checks:
        checks_by_instrument.setdefault(check.instrument_id, []).append(check)
    for release in releases:
        release_ids.add(release.instrument_id)
    cutoff = today - timedelta(days=settings.action_overdue_days)
    queued: list[dict[str, Any]] = []
    for row in instruments:
        reasons: list[str] = []
        rules: list[str] = []
        evidence: list[dict[str, Any]] = []
        days = (row.maturity_date - today).days
        is_overdue = False
        if row.maturity_date < today and row.lifecycle_status in MATURITY_ACTION_STATUSES:
            reasons.append("Maturity date has passed and the instrument still requires action.")
            rules.append("maturity_overdue")
            evidence.append({"maturity_date": row.maturity_date.isoformat(), "days_overdue": -days})
            is_overdue = True
        elif 0 <= days <= max(settings.maturity_reminder_window_list) and row.lifecycle_status in ACTIVE_STATUSES and row.successor is None:
            reasons.append("Maturity is approaching and no successor instrument is recorded.")
            rules.append("maturity_approaching_without_successor")
            evidence.append({"maturity_date": row.maturity_date.isoformat(), "days_to_maturity": days})
        if row.lifecycle_status in SCRUTINY_STATUSES:
            reasons.append("Instrument is awaiting scrutiny.")
            rules.append("pending_scrutiny")
        elif row.lifecycle_status == Life.CLARIFICATION_REQUIRED:
            reasons.append("Institution clarification is outstanding.")
            rules.append("clarification_outstanding")
        if row.id in release_ids:
            reasons.append("Release request is awaiting an authorized decision.")
            rules.append("release_decision_pending")
        row_findings = finding_by_instrument.get(row.id, [])
        row_checks = checks_by_instrument.get(row.id, [])
        for f in row_findings:
            evidence.append({"finding_id": f.id, "type": f.finding_type.value, "severity": f.severity.value, "explanation": f.explanation})
        for check in row_checks:
            evidence.append({"verification_check_id": check.id, "rule_code": check.rule_code, "explanation": check.explanation})
        if row_findings:
            reasons.append(f"{len(row_findings)} unresolved integrity finding(s) require review.")
            rules.append("open_integrity_findings")
        if row_checks:
            reasons.append(f"{len(row_checks)} required verification check(s) remain open.")
            rules.append("required_verification_open")
        unresolved = bool(row_findings or row_checks or row.lifecycle_status == Life.CLARIFICATION_REQUIRED)
        if row.lifecycle_status in {
            Life.SUBMITTED, Life.UNDER_SCRUTINY, Life.CLARIFICATION_REQUIRED, Life.RELEASE_PENDING,
        } and row.updated_at.date() <= cutoff:
            is_overdue = True
            evidence.append({"last_updated": row.updated_at.isoformat(), "overdue_after_days": settings.action_overdue_days})
        if reasons:
            queued.append({
                "instrument": row,
                "reasons": reasons,
                "triggered_rules": rules,
                "days_to_maturity": days,
                "overdue": is_overdue,
                "unresolved": unresolved,
                "evidence": evidence,
            })
    queued.sort(key=lambda item: (not item["overdue"], not item["unresolved"], item["days_to_maturity"] if item["days_to_maturity"] is not None else 10**9, item["instrument"].id))
    total = len(queued)
    return queued[offset:offset + limit], total


def advance_matured_instruments(db: Session, *, today: date | None = None) -> int:
    """Move approved instruments past maturity into matured state and audit each transition.

    Maturity is a deterministic date-based lifecycle event, not an approval decision.
    Only approved instruments are transitioned; released, rejected, superseded, and
    already-matured records are left unchanged. Repeated runs are idempotent.
    """
    current = today or date.today()
    instruments = list(db.scalars(
        select(FDRInstrument).where(
            FDRInstrument.lifecycle_status == Life.APPROVED,
            FDRInstrument.maturity_date < current,
        ).order_by(FDRInstrument.maturity_date, FDRInstrument.id)
    ))
    for instrument in instruments:
        previous = instrument.lifecycle_status
        instrument.lifecycle_status = Life.MATURED
        record_audit_event(
            db,
            actor_user_id=None,
            institution_id=instrument.institution_id,
            entity_type="fdr_instrument",
            entity_id=instrument.id,
            action="instrument_maturity_status_advanced",
            before_values={"lifecycle_status": previous, "maturity_date": instrument.maturity_date},
            after_values={"lifecycle_status": Life.MATURED, "as_of_date": current},
            context={"trigger": "scheduled_date_rule", "human_decision_required": False},
        )
    if instruments:
        db.commit()
    return len(instruments)


def generate_maturity_reminders(db: Session, *, today: date | None = None) -> int:
    """Create due reminders once; unique keys make repeated local runs idempotent."""
    current = today or date.today()
    settings = get_settings()
    windows = settings.maturity_reminder_window_list
    instruments = list(db.scalars(
        select(FDRInstrument).options(joinedload(FDRInstrument.institution)).where(
            FDRInstrument.maturity_date.in_([current + timedelta(days=n) for n in windows]),
            FDRInstrument.lifecycle_status.in_(ACTIVE_STATUSES),
        )
    ).unique())
    created = 0
    for instrument in instruments:
        days_left = (instrument.maturity_date - current).days
        recipients = list(db.scalars(select(User).where(
            User.institution_id == instrument.institution_id,
            User.role == Role.INSTITUTION_USER,
            User.active.is_(True),
        )))
        for recipient in recipients:
            key = f"maturity:{recipient.id}:{instrument.id}:{instrument.maturity_date.isoformat()}:{days_left}"
            exists = db.scalar(select(Notification.id).where(Notification.dedupe_key == key))
            if exists:
                continue
            db.add(Notification(
                recipient_user_id=recipient.id,
                title=f"FDR maturity in {days_left} days",
                message=f"Instrument {instrument.reference_original} reaches maturity on {instrument.maturity_date.isoformat()}. Review renewal or replacement status.",
                category="maturity_reminder",
                reason=f"maturity_{days_left}_days",
                due_date=instrument.maturity_date,
                dedupe_key=key,
                related_entity_type="fdr_instrument",
                related_entity_id=instrument.id,
            ))
            created += 1
    if created:
        db.commit()
    return created



def generate_overdue_action_escalations(db: Session, *, today: date | None = None) -> int:
    """Notify responsible institution users and internal decision-makers about overdue work.

    Escalations are based on the same rules exposed in the action queue: maturity actions
    are overdue after the instrument maturity date; submitted, scrutiny, clarification,
    and release-pending cases are overdue after ``ACTION_OVERDUE_DAYS`` without an update.
    Stable deduplication keys make the job safe to run repeatedly. This creates in-app
    notifications only; it does not claim to send email or external alerts.
    """
    current = today or date.today()
    settings = get_settings()
    cutoff = current - timedelta(days=settings.action_overdue_days)
    instruments = list(db.scalars(
        select(FDRInstrument).options(joinedload(FDRInstrument.institution)).where(
            FDRInstrument.lifecycle_status.in_(
                MATURITY_ACTION_STATUSES | {Life.SUBMITTED, Life.UNDER_SCRUTINY, Life.CLARIFICATION_REQUIRED}
            )
        ).order_by(FDRInstrument.institution_id, FDRInstrument.maturity_date, FDRInstrument.id)
    ).unique())

    internal_recipients = list(db.scalars(select(User).where(
        User.role.in_([Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.ADMIN]),
        User.active.is_(True),
    )))
    created = 0
    for instrument in instruments:
        if instrument.lifecycle_status in MATURITY_ACTION_STATUSES and instrument.maturity_date < current:
            reason = "maturity_overdue"
            due_date = instrument.maturity_date
            detail = f"Maturity passed on {due_date.isoformat()} and the instrument still requires action."
            threshold_date = due_date.isoformat()
        elif instrument.lifecycle_status in {Life.SUBMITTED, Life.UNDER_SCRUTINY, Life.CLARIFICATION_REQUIRED, Life.RELEASE_PENDING} and instrument.updated_at.date() <= cutoff:
            reason = "workflow_action_overdue"
            due_date = instrument.updated_at.date() + timedelta(days=settings.action_overdue_days)
            detail = f"No workflow update has been recorded for at least {settings.action_overdue_days} days."
            threshold_date = due_date.isoformat()
        else:
            continue

        institution_recipients = list(db.scalars(select(User).where(
            User.institution_id == instrument.institution_id,
            User.role == Role.INSTITUTION_USER,
            User.active.is_(True),
        )))
        recipients_by_id = {user.id: user for user in institution_recipients + internal_recipients}
        made_for_instrument = 0
        for recipient in recipients_by_id.values():
            key = f"overdue:{reason}:{recipient.id}:{instrument.id}:{threshold_date}"
            if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
                continue
            db.add(Notification(
                recipient_user_id=recipient.id,
                title="Overdue FDR action requires attention",
                message=f"Instrument {instrument.reference_original}: {detail} Please review the case queue and record the required action.",
                category="overdue_escalation",
                reason=reason,
                due_date=due_date,
                dedupe_key=key,
                related_entity_type="fdr_instrument",
                related_entity_id=instrument.id,
            ))
            created += 1
            made_for_instrument += 1

        if made_for_instrument:
            prior = list(db.scalars(select(AuditEvent).where(
                AuditEvent.entity_type == "fdr_instrument",
                AuditEvent.entity_id == instrument.id,
                AuditEvent.action == "overdue_action_escalated",
            )))
            already_audited = any((event.context or {}).get("reason") == reason and (event.context or {}).get("threshold_date") == threshold_date for event in prior)
            if not already_audited:
                record_audit_event(
                    db, actor_user_id=None, institution_id=instrument.institution_id,
                    entity_type="fdr_instrument", entity_id=instrument.id,
                    action="overdue_action_escalated",
                    before_values={"lifecycle_status": instrument.lifecycle_status, "updated_at": instrument.updated_at},
                    after_values={"escalation_reason": reason, "due_date": due_date},
                    context={"trigger": "scheduled_overdue_rule", "reason": reason, "threshold_date": threshold_date, "notifications_created": made_for_instrument},
                )

    if created:
        db.commit()
    return created
