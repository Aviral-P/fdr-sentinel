"""Backend-only release eligibility evaluation and authorized decision recording."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AuditEvent,
    FDRInstrument,
    InstrumentLifecycleStatus as Status,
    OperationalPriority,
    RegulatoryRule,
    ReleaseApproval,
    ReleaseApprovalDecision,
    ReleaseRequest,
    ReleaseRequestStatus,
    Role,
    User,
    VerificationCheck,
    VerificationCheckStatus,
    VerificationStatus,
    WorkflowEventType,
)
from app.schemas.api import ReleaseDecisionRequest, ReleaseRequestCreateRequest
from app.services.audit_service import record_audit_event, record_workflow_event
from app.services.fdr_service import get_instrument

DEFAULT_ELIGIBILITY_RULES: dict[str, Any] = {
    "must_be_matured": True,
    "minimum_document_count": 1,
    "block_unresolved_verifications": True,
    "block_discrepancy_status": True,
    "require_obligation_satisfied": False,
}


def _effective_rules(session: Session, institution_id: str) -> tuple[dict[str, Any], list[str]]:
    statement = select(RegulatoryRule).where(
        RegulatoryRule.active.is_(True),
        RegulatoryRule.code == "release_eligibility",
        or_(RegulatoryRule.institution_id.is_(None), RegulatoryRule.institution_id == institution_id),
    )
    rules = list(session.scalars(statement))
    rules.sort(key=lambda rule: (rule.institution_id is not None, rule.code, rule.version))
    effective = dict(DEFAULT_ELIGIBILITY_RULES)
    for rule in rules:
        effective.update(rule.rule_config)
    try:
        minimum_documents = int(effective["minimum_document_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(503, "invalid_release_rule", "A release eligibility rule has an invalid document count.") from exc
    if minimum_documents < 0:
        raise AppError(503, "invalid_release_rule", "minimum_document_count cannot be negative.")
    effective["minimum_document_count"] = minimum_documents
    return effective, [rule.code for rule in rules]


def _scope_release_request(session: Session, user: User, request_id: str) -> ReleaseRequest:
    request = session.get(ReleaseRequest, request_id)
    if request is None:
        raise AppError(404, "not_found", "Release request not found.")
    instrument = request.instrument
    if user.role == Role.INSTITUTION_USER:
        if user.institution_id != instrument.institution_id:
            raise AppError(404, "not_found", "Release request not found.")
    elif user.role not in {Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR, Role.ADMIN}:
        raise AppError(403, "forbidden", "This role cannot access release requests.")
    return request


def evaluate_eligibility(
    session: Session,
    request: ReleaseRequest,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    instrument = request.instrument
    rules, applied_rules = _effective_rules(session, instrument.institution_id)
    findings: list[dict[str, str]] = []

    def finding(code: str, message: str, should_block: bool) -> None:
        findings.append({"code": code, "severity": "block" if should_block else "warning", "message": message})

    if instrument.lifecycle_status not in {Status.APPROVED, Status.MATURED, Status.RELEASE_PENDING}:
        finding("instrument_not_approved", "The instrument is not in an approved or mature lifecycle state.", True)
    if rules["must_be_matured"] and instrument.maturity_date > today:
        finding("not_matured", "The instrument maturity date has not been reached.", True)
    if request.requested_amount > instrument.amount:
        finding("amount_exceeds_instrument", "Requested release exceeds the instrument amount.", True)

    document_count = len(instrument.documents)
    minimum_documents = rules["minimum_document_count"]
    if document_count < minimum_documents:
        finding(
            "mandatory_evidence_missing",
            f"At least {minimum_documents} document record(s) are required; {document_count} found.",
            True,
        )

    open_checks = list(
        session.scalars(
            select(VerificationCheck).where(
                VerificationCheck.instrument_id == instrument.id,
                VerificationCheck.status == VerificationCheckStatus.OPEN,
                VerificationCheck.is_required.is_(True),
            )
        )
    )
    unresolved_verification = bool(open_checks) or instrument.verification_status in {
        VerificationStatus.PENDING_REVIEW,
        VerificationStatus.DISCREPANCY_FLAGGED,
    }
    if unresolved_verification:
        finding(
            "verification_unresolved",
            "One or more required verification items remain unresolved.",
            bool(rules["block_unresolved_verifications"]),
        )
    if instrument.verification_status == VerificationStatus.DISCREPANCY_FLAGGED:
        finding(
            "discrepancy_flagged",
            "A discrepancy is flagged and requires human review.",
            bool(rules["block_discrepancy_status"]),
        )

    if rules.get("require_obligation_satisfied"):
        if instrument.obligation is None or instrument.obligation.status.value != "satisfied":
            finding("obligation_not_satisfied", "The linked obligation is not marked satisfied.", True)

    eligible = not any(item["severity"] == "block" for item in findings)
    return {
        "release_request_id": request.id,
        "eligible": eligible,
        "eligibility_status": "eligible" if eligible else "blocked",
        "findings": findings,
        "rules_applied": {**rules, "active_rule_codes": applied_rules},
        # Keep the persisted JSON payload portable across PostgreSQL and SQLite.
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def _persist_evaluation(session: Session, request: ReleaseRequest, result: dict[str, Any], user: User) -> None:
    request.eligibility_status = result["eligibility_status"]
    request.eligibility_findings = result
    record_workflow_event(
        session,
        instrument_id=request.instrument_id,
        actor_user_id=user.id,
        event_type=WorkflowEventType.RELEASE_ELIGIBILITY_EVALUATED,
        from_status=request.instrument.lifecycle_status,
        to_status=request.instrument.lifecycle_status,
        comment="Release eligibility evaluated; no release or transfer was performed.",
        event_metadata={
            "release_request_id": request.id,
            "eligibility_status": result["eligibility_status"],
            "finding_codes": [finding["code"] for finding in result["findings"]],
        },
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=request.instrument.institution_id,
        entity_type="release_request",
        entity_id=request.id,
        action="release_eligibility_evaluated",
        before_values=None,
        after_values={
            "eligibility_status": result["eligibility_status"],
            "finding_codes": [finding["code"] for finding in result["findings"]],
        },
        context={"instrument_id": request.instrument_id},
    )


def create_release_request(
    session: Session,
    user: User,
    instrument_id: str,
    payload: ReleaseRequestCreateRequest,
) -> tuple[ReleaseRequest, dict[str, Any]]:
    instrument = get_instrument(session, user, instrument_id)
    if user.role != Role.INSTITUTION_USER or user.institution_id != instrument.institution_id:
        raise AppError(403, "forbidden", "Only the institution user may submit a release request.")
    if instrument.lifecycle_status not in {Status.APPROVED, Status.MATURED}:
        raise AppError(409, "invalid_transition", "Release requests require an approved or matured instrument.")
    if session.scalar(
        select(ReleaseRequest.id).where(
            ReleaseRequest.instrument_id == instrument.id,
            ReleaseRequest.status == ReleaseRequestStatus.PENDING,
        )
    ):
        raise AppError(409, "release_request_exists", "This instrument already has a pending release request.")
    prior_status = instrument.lifecycle_status
    request = ReleaseRequest(
        instrument_id=instrument.id,
        requested_by_user_id=user.id,
        requested_amount=payload.requested_amount,
        eligibility_status="not_evaluated",
        eligibility_findings={},
        status=ReleaseRequestStatus.PENDING,
        prior_instrument_status=prior_status,
        reason=payload.reason,
    )
    session.add(request)
    instrument.lifecycle_status = Status.RELEASE_PENDING
    session.flush()
    result = evaluate_eligibility(session, request)
    _persist_evaluation(session, request, result, user)
    record_workflow_event(
        session,
        instrument_id=instrument.id,
        actor_user_id=user.id,
        event_type=WorkflowEventType.RELEASE_REQUESTED,
        from_status=prior_status,
        to_status=instrument.lifecycle_status,
        comment="Release/refund request submitted for authorized review.",
        event_metadata={"release_request_id": request.id, "eligibility_status": result["eligibility_status"]},
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="release_request",
        entity_id=request.id,
        action="release_request_created",
        after_values={
            "instrument_id": instrument.id,
            "requested_amount": request.requested_amount,
            "status": request.status,
            "eligibility_status": request.eligibility_status,
            "instrument_lifecycle_status": instrument.lifecycle_status,
        },
    )
    session.commit()
    session.refresh(request)
    return request, result


def reevaluate_release_request(
    session: Session,
    user: User,
    request_id: str,
) -> tuple[ReleaseRequest, dict[str, Any]]:
    if user.role not in {Role.INSTITUTION_USER, Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY}:
        raise AppError(403, "forbidden", "This role cannot evaluate release eligibility.")
    request = _scope_release_request(session, user, request_id)
    if request.status != ReleaseRequestStatus.PENDING:
        raise AppError(409, "invalid_transition", "Only a pending release request can be evaluated.")
    result = evaluate_eligibility(session, request)
    _persist_evaluation(session, request, result, user)
    session.commit()
    session.refresh(request)
    return request, result


def record_release_decision(
    session: Session,
    user: User,
    request_id: str,
    payload: ReleaseDecisionRequest,
) -> tuple[ReleaseRequest, ReleaseApproval]:
    if user.role != Role.APPROVING_AUTHORITY:
        raise AppError(403, "forbidden", "Only an approving authority may decide a release request.")
    request = _scope_release_request(session, user, request_id)
    if request.status != ReleaseRequestStatus.PENDING:
        raise AppError(409, "invalid_transition", "This release request has already been decided.")
    if payload.decision == ReleaseApprovalDecision.APPROVED and request.eligibility_status != "eligible":
        raise AppError(
            409,
            "release_not_eligible",
            "A blocked or unevaluated release request cannot be approved.",
            {"eligibility_status": request.eligibility_status},
        )
    instrument = request.instrument
    if instrument.lifecycle_status != Status.RELEASE_PENDING:
        raise AppError(409, "invalid_transition", "The instrument is no longer pending release review.")

    before_request = request.status
    before_instrument = instrument.lifecycle_status
    approval = ReleaseApproval(
        release_request_id=request.id,
        approver_user_id=user.id,
        decision=payload.decision,
        rationale=payload.rationale,
        disposition=payload.disposition,
    )
    session.add(approval)
    request.status = {
        ReleaseApprovalDecision.APPROVED: ReleaseRequestStatus.APPROVED,
        ReleaseApprovalDecision.REJECTED: ReleaseRequestStatus.REJECTED,
        ReleaseApprovalDecision.RETURNED: ReleaseRequestStatus.RETURNED,
    }[payload.decision]
    # An approval records the authorized decision and disposition only. It does
    # not mark funds transferred or the instrument released.
    if payload.decision != ReleaseApprovalDecision.APPROVED:
        instrument.lifecycle_status = request.prior_instrument_status or Status.APPROVED
    session.flush()
    record_workflow_event(
        session,
        instrument_id=instrument.id,
        actor_user_id=user.id,
        event_type=WorkflowEventType.RELEASE_DECISION,
        from_status=before_instrument,
        to_status=instrument.lifecycle_status,
        comment=payload.rationale,
        event_metadata={
            "release_request_id": request.id,
            "decision": payload.decision.value,
            "approval_id": approval.id,
        },
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="release_request",
        entity_id=request.id,
        action="release_decision_recorded",
        before_values={"request_status": before_request, "instrument_lifecycle_status": before_instrument},
        after_values={
            "request_status": request.status,
            "instrument_lifecycle_status": instrument.lifecycle_status,
            "decision": payload.decision,
            "approval_id": approval.id,
        },
        context={"disposition_recorded": True, "transfer_performed": False},
    )
    session.commit()
    session.refresh(request)
    session.refresh(approval)
    return request, approval


def get_release_request(session: Session, user: User, request_id: str) -> ReleaseRequest:
    return _scope_release_request(session, user, request_id)
