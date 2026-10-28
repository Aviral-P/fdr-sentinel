"""Persistence, review, and explainable queue ranking for integrity findings."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models import (
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    IntegrityFinding,
    IntegrityFindingSeverity,
    IntegrityFindingType,
    IntegrityReviewStatus,
    InstrumentDocument,
    RegulatoryRule,
    ReleaseRequest,
    Role,
    User,
    VerificationCheck,
)
from app.models.entities import utcnow
from app.services.audit_service import record_audit_event
from app.services.integrity_rules import (
    FindingCandidate,
    approaching_maturity_without_successor_rule,
    missing_required_document_rule,
    run_all_rules,
)


RULE_IDS = {
    "exact_file_sha256",
    "normalized_instrument_reference",
    "document_text_similarity_sequence_matcher",
    "declared_extracted_amount_compare",
    "declared_extracted_beneficiary_compare",
    "declared_extracted_issue_date_compare",
    "declared_extracted_maturity_date_compare",
    "extracted_date_order",
    "required_document_count",
    "maturity_without_successor_window",
    "replacement_lineage_consistency",
    "release_request_required_conditions",
}

INTERNAL_READ_ROLES = {Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR, Role.ADMIN}


def _candidate_key(candidate: FindingCandidate) -> str:
    payload = {
        "rule_id": candidate.rule_id,
        "rule_version": candidate.rule_version,
        "instrument_id": candidate.instrument_id,
        "related_instrument_id": candidate.related_instrument_id,
        "document_id": candidate.document_id,
        "related_document_id": candidate.related_document_id,
        "release_request_id": candidate.release_request_id,
        "observed_values": candidate.observed_values or {},
        "expected_values": candidate.expected_values or {},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _effective_integrity_options(session: Session, institution_id: str) -> tuple[int, int]:
    rules = list(
        session.scalars(
            select(RegulatoryRule).where(
                RegulatoryRule.active.is_(True),
                RegulatoryRule.code == "integrity_monitoring",
                or_(RegulatoryRule.institution_id.is_(None), RegulatoryRule.institution_id == institution_id),
            )
        )
    )
    rules.sort(key=lambda row: (row.institution_id is not None, row.version))
    options: dict[str, Any] = {"required_document_count": 1, "maturity_warning_days": 30}
    for rule in rules:
        options.update(rule.rule_config)
    try:
        required_documents = int(options["required_document_count"])
        maturity_days = int(options["maturity_warning_days"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(503, "invalid_integrity_rule", "An integrity rule has invalid numeric configuration.") from exc
    if not 0 <= required_documents <= 10 or not 0 <= maturity_days <= 365:
        raise AppError(503, "invalid_integrity_rule", "Integrity rule values are outside their supported local-prototype range.")
    return required_documents, maturity_days


def _audit_finding(
    session: Session,
    actor: User,
    *,
    instrument_id: str,
    institution_id: str,
    finding_id: str,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    record_audit_event(
        session,
        actor_user_id=actor.id,
        institution_id=institution_id,
        entity_type="fdr_instrument",
        entity_id=instrument_id,
        action=action,
        before_values=before,
        after_values={"finding_id": finding_id, **after},
        context={"finding_entity_type": "integrity_finding"},
    )


def run_integrity_scan(session: Session, actor: User, *, today: date | None = None) -> dict[str, int]:
    if actor.role != Role.SCRUTINY_OFFICER:
        raise AppError(403, "forbidden", "Only a scrutiny officer may run the cross-record integrity scan.")
    scan_date = today or date.today()
    instruments = list(
        session.scalars(
            select(FDRInstrument).options(
                selectinload(FDRInstrument.documents),
                selectinload(FDRInstrument.successor),
            )
        )
    )
    documents = list(session.scalars(select(InstrumentDocument).order_by(InstrumentDocument.id)))
    fields = list(
        session.scalars(
            select(ExtractedDocumentField)
            .options(selectinload(ExtractedDocumentField.document))
            .order_by(ExtractedDocumentField.document_id, ExtractedDocumentField.field_name)
        )
    )
    checks = list(session.scalars(select(VerificationCheck)))
    requests = list(session.scalars(select(ReleaseRequest)))
    candidates = run_all_rules(
        instruments=instruments,
        documents=documents,
        fields=fields,
        checks=checks,
        release_requests=requests,
        today=scan_date,
        required_document_count=0,
        maturity_warning_days=0,
    )
    candidates = [
        candidate
        for candidate in candidates
        if candidate.rule_id not in {"required_document_count", "maturity_without_successor_window"}
    ]
    institution_ids = sorted({instrument.institution_id for instrument in instruments})
    for institution_id in institution_ids:
        required_document_count, maturity_warning_days = _effective_integrity_options(session, institution_id)
        institution_instruments = [row for row in instruments if row.institution_id == institution_id]
        instrument_ids = {row.id for row in institution_instruments}
        institution_documents = [row for row in documents if row.instrument_id in instrument_ids]
        candidates.extend(
            missing_required_document_rule(
                institution_instruments,
                institution_documents,
                minimum_document_count=required_document_count,
            )
        )
        candidates.extend(
            approaching_maturity_without_successor_rule(
                institution_instruments,
                today=scan_date,
                warning_days=maturity_warning_days,
            )
        )
    candidate_by_key = {_candidate_key(candidate): candidate for candidate in candidates}
    now = utcnow()
    existing_rows = list(session.scalars(select(IntegrityFinding)))
    existing_by_key = {finding.dedupe_key: finding for finding in existing_rows}
    new_count = reopened_count = resolved_count = 0

    for key, candidate in candidate_by_key.items():
        existing = existing_by_key.get(key)
        if existing is None:
            finding_id = str(uuid4())
            finding = IntegrityFinding(
                id=finding_id,
                institution_id=candidate.institution_id,
                instrument_id=candidate.instrument_id,
                related_instrument_id=candidate.related_instrument_id,
                document_id=candidate.document_id,
                related_document_id=candidate.related_document_id,
                release_request_id=candidate.release_request_id,
                finding_type=candidate.finding_type,
                severity=candidate.severity,
                data_origin=DataOrigin.SYSTEM_GENERATED,
                observed_values=dict(candidate.observed_values or {}),
                expected_values=dict(candidate.expected_values or {}),
                explanation=candidate.explanation,
                rule_id=candidate.rule_id,
                rule_version=candidate.rule_version,
                dedupe_key=key,
                detected_at=now,
                review_status=IntegrityReviewStatus.OPEN,
                is_current=True,
            )
            session.add(finding)
            _audit_finding(
                session,
                actor,
                instrument_id=candidate.instrument_id,
                institution_id=candidate.institution_id,
                finding_id=finding_id,
                action="integrity_finding_detected",
                before=None,
                after={
                    "finding_type": candidate.finding_type,
                    "severity": candidate.severity,
                    "rule_id": candidate.rule_id,
                    "rule_version": candidate.rule_version,
                    "observed_values": candidate.observed_values or {},
                    "expected_values": candidate.expected_values or {},
                    "related_instrument_id": candidate.related_instrument_id,
                    "document_id": candidate.document_id,
                    "related_document_id": candidate.related_document_id,
                    "release_request_id": candidate.release_request_id,
                },
            )
            new_count += 1
        elif not existing.is_current or existing.review_status == IntegrityReviewStatus.RESOLVED:
            previous_status = existing.review_status
            existing.is_current = True
            existing.review_status = IntegrityReviewStatus.OPEN
            existing.reviewed_by_user_id = None
            existing.reviewed_at = None
            existing.resolution_notes = None
            _audit_finding(
                session,
                actor,
                instrument_id=existing.instrument_id,
                institution_id=existing.institution_id,
                finding_id=existing.id,
                action="integrity_finding_reopened",
                before={"review_status": previous_status, "is_current": False},
                after={"review_status": IntegrityReviewStatus.OPEN, "is_current": True},
            )
            reopened_count += 1

    current_keys = set(candidate_by_key)
    active_rules = RULE_IDS
    for existing in existing_rows:
        if (
            existing.dedupe_key not in current_keys
            and existing.is_current
            and existing.rule_id in active_rules
        ):
            previous_status = existing.review_status
            existing.is_current = False
            if existing.review_status == IntegrityReviewStatus.OPEN:
                existing.review_status = IntegrityReviewStatus.RESOLVED
                existing.resolution_notes = "Condition was not detected during the latest integrity scan."
            _audit_finding(
                session,
                actor,
                instrument_id=existing.instrument_id,
                institution_id=existing.institution_id,
                finding_id=existing.id,
                action="integrity_finding_resolved_by_rescan",
                before={"review_status": previous_status, "is_current": True},
                after={"review_status": existing.review_status, "is_current": False},
            )
            resolved_count += 1

    session.commit()
    return {
        "instruments_scanned": len(instruments),
        "candidates_detected": len(candidates),
        "findings_created": new_count,
        "findings_reopened": reopened_count,
        "findings_resolved": resolved_count,
        "current_findings": len(candidate_by_key),
    }


def review_integrity_finding(
    session: Session,
    actor: User,
    finding_id: str,
    *,
    decision: IntegrityReviewStatus,
    resolution_notes: str,
) -> IntegrityFinding:
    if actor.role != Role.SCRUTINY_OFFICER:
        raise AppError(403, "forbidden", "Only a scrutiny officer may resolve an integrity finding.")
    if decision not in {IntegrityReviewStatus.REVIEWED, IntegrityReviewStatus.DISMISSED}:
        raise AppError(422, "invalid_review_status", "The requested finding review status is not supported.")
    finding = session.get(IntegrityFinding, finding_id)
    if finding is None or not finding.is_current:
        raise AppError(404, "not_found", "Current integrity finding not found.")
    if finding.review_status != IntegrityReviewStatus.OPEN:
        raise AppError(409, "finding_already_reviewed", "This integrity finding has already been reviewed.")
    before = {"review_status": finding.review_status, "resolution_notes": finding.resolution_notes}
    finding.review_status = decision
    finding.reviewed_by_user_id = actor.id
    finding.reviewed_at = utcnow()
    finding.resolution_notes = resolution_notes.strip()
    _audit_finding(
        session,
        actor,
        instrument_id=finding.instrument_id,
        institution_id=finding.institution_id,
        finding_id=finding.id,
        action="integrity_finding_reviewed",
        before=before,
        after={"review_status": decision, "resolution_notes": finding.resolution_notes},
    )
    session.commit()
    session.refresh(finding)
    return finding


def _queue_rank(finding: IntegrityFinding, instrument: FDRInstrument, today: date) -> dict[str, Any]:
    severity_points = {
        IntegrityFindingSeverity.CRITICAL: 400,
        IntegrityFindingSeverity.HIGH: 300,
        IntegrityFindingSeverity.MEDIUM: 200,
        IntegrityFindingSeverity.LOW: 100,
    }[finding.severity]
    score = severity_points
    reasons = [f"Severity is {finding.severity.value} (+{severity_points})."]
    unresolved_points = 100 if finding.review_status == IntegrityReviewStatus.OPEN else 0
    if unresolved_points:
        score += unresolved_points
        reasons.append("Finding is unresolved and open for scrutiny (+100).")
    deadline_days = (instrument.maturity_date - today).days
    deadline = deadline_days if 0 <= deadline_days <= 365 else None
    if deadline is not None:
        proximity_points = 70 if deadline <= 7 else 40 if deadline <= 30 else 0
        if proximity_points:
            score += proximity_points
            reasons.append(f"Instrument maturity is {deadline} day(s) away (+{proximity_points}).")
    if finding.finding_type == IntegrityFindingType.RELEASE_CONDITIONS_UNRESOLVED:
        score += 60
        reasons.append("Release request has unresolved eligibility conditions (+60).")
    reasons.append(f"Triggered by {finding.rule_id} version {finding.rule_version}.")
    return {
        "priority_score": score,
        "ranking_reasons": reasons,
        "deadline_days_remaining": deadline,
        "supporting_evidence": {
            "observed_values": finding.observed_values,
            "expected_values": finding.expected_values,
            "explanation": finding.explanation,
        },
        "ranking_notice": "Deterministic triage ranking only; it is not a calibrated probability of fraud or a decision.",
    }


def get_prioritized_scrutiny_queue(
    session: Session,
    actor: User,
    *,
    today: date | None = None,
    limit: int = 25,
    offset: int = 0,
    review_status: IntegrityReviewStatus = IntegrityReviewStatus.OPEN,
) -> tuple[list[dict[str, Any]], int]:
    if actor.role not in INTERNAL_READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view the cross-institution scrutiny queue.")
    filters = [IntegrityFinding.is_current.is_(True), IntegrityFinding.review_status == review_status]
    count = session.scalar(select(func.count(IntegrityFinding.id)).where(*filters)) or 0
    findings = list(
        session.scalars(
            select(IntegrityFinding)
            .where(*filters)
            .order_by(IntegrityFinding.detected_at.desc(), IntegrityFinding.id)
        )
    )
    current_day = today or date.today()
    ranked: list[dict[str, Any]] = []
    for finding in findings:
        instrument = session.get(FDRInstrument, finding.instrument_id)
        if instrument is None:
            continue
        ranked.append({"finding": finding, **_queue_rank(finding, instrument, current_day)})
    ranked.sort(key=lambda item: (-item["priority_score"], item["finding"].detected_at, item["finding"].id))
    return ranked[offset : offset + limit], count


def list_integrity_findings(
    session: Session,
    actor: User,
    *,
    limit: int = 25,
    offset: int = 0,
    review_status: IntegrityReviewStatus | None = None,
    instrument_id: str | None = None,
) -> tuple[list[IntegrityFinding], int]:
    if actor.role not in INTERNAL_READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view cross-institution integrity findings.")
    filters = []
    if review_status is not None:
        filters.append(IntegrityFinding.review_status == review_status)
    if instrument_id is not None:
        filters.append(IntegrityFinding.instrument_id == instrument_id)
    count = session.scalar(select(func.count(IntegrityFinding.id)).where(*filters)) or 0
    rows = list(
        session.scalars(
            select(IntegrityFinding)
            .where(*filters)
            .order_by(IntegrityFinding.detected_at.desc(), IntegrityFinding.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, count
