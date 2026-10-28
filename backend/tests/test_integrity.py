"""Independent rule, idempotency, queue, review, and evaluation tests."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.models import (
    AuditEvent,
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    Institution,
    InstrumentDocument,
    IntegrityFinding,
    IntegrityFindingType as FindingType,
    IntegrityReviewStatus,
    InstrumentLifecycleStatus,
    Role,
    User,
    VerificationCheck,
    ReleaseRequest,
)
from app.services.integrity_rules import (
    amount_mismatch_rule,
    approaching_maturity_without_successor_rule,
    beneficiary_mismatch_rule,
    date_inconsistency_rule,
    exact_file_duplicate_rule,
    missing_required_document_rule,
    near_duplicate_document_rule,
    replacement_lineage_rule,
    repeated_reference_rule,
    unresolved_release_conditions_rule,
    run_all_rules,
)
from app.services.integrity_service import (
    get_prioritized_scrutiny_queue,
    list_integrity_findings,
    review_integrity_finding,
    run_integrity_scan,
)
from app.services.fdr_service import get_instrument_history
from scripts.integrity_evaluation import EVALUATION_DATE, build_synthetic_dataset, evaluate_dataset


@pytest.fixture
def synthetic_state(test_session_factory):
    with test_session_factory() as session:
        expectations = build_synthetic_dataset(session)
        session.flush()
        instruments = list(session.scalars(select(FDRInstrument)))
        documents = list(session.scalars(select(InstrumentDocument)))
        fields = list(session.scalars(select(ExtractedDocumentField)))
        checks = list(session.scalars(select(VerificationCheck)))
        releases = list(session.scalars(select(ReleaseRequest)))
        yield session, expectations, instruments, documents, fields, checks, releases


def _count(rows, finding_type):
    return sum(item.finding_type == finding_type for item in rows)


def test_integrity_findings_can_be_filtered_to_one_instrument(synthetic_state):
    session, _, instruments, *_ = synthetic_state
    officer = User(
        full_name="Synthetic Scrutiny Officer",
        email="scope-test-reviewer@fdr-sentinel.invalid",
        password_hash=hash_password("test-only-password-123"),
        role=Role.SCRUTINY_OFFICER,
        institution_id=None,
    )
    session.add(officer)
    session.flush()
    run_integrity_scan(session, officer, today=EVALUATION_DATE)

    all_rows, all_total = list_integrity_findings(session, officer, limit=100, offset=0)
    assert all_total == len(all_rows)
    assert all_rows
    target_id = all_rows[0].instrument_id
    rows, total = list_integrity_findings(
        session, officer, limit=100, offset=0, instrument_id=target_id
    )
    assert total == len(rows)
    assert rows
    assert all(row.instrument_id == target_id for row in rows)


def test_exact_sha256_duplicate_rule(synthetic_state):
    _, _, instruments, documents, _, _, _ = synthetic_state
    by_id = {instrument.id: instrument for instrument in instruments}
    assert len(exact_file_duplicate_rule(documents, by_id)) == 1


def test_normalized_repeated_reference_rule(synthetic_state):
    _, _, instruments, *_ = synthetic_state
    assert len(repeated_reference_rule(instruments)) == 1


def test_near_duplicate_text_candidate_rule(synthetic_state):
    _, _, instruments, documents, *_ = synthetic_state
    by_id = {instrument.id: instrument for instrument in instruments}
    assert len(near_duplicate_document_rule(documents, by_id)) == 1


def test_amount_mismatch_rule(synthetic_state):
    _, _, instruments, _, fields, *_ = synthetic_state
    by_id = {instrument.id: instrument for instrument in instruments}
    assert len(amount_mismatch_rule(fields, by_id)) == 1


def test_beneficiary_mismatch_rule(synthetic_state):
    _, _, instruments, _, fields, *_ = synthetic_state
    by_id = {instrument.id: instrument for instrument in instruments}
    assert len(beneficiary_mismatch_rule(fields, by_id)) == 1


def test_date_inconsistency_rule(synthetic_state):
    _, _, instruments, _, fields, *_ = synthetic_state
    by_id = {instrument.id: instrument for instrument in instruments}
    candidates = date_inconsistency_rule(fields, by_id)
    assert len(candidates) == 1
    assert candidates[0].finding_type == FindingType.DATE_INCONSISTENCY


def test_missing_required_document_rule(synthetic_state):
    _, _, instruments, documents, *_ = synthetic_state
    candidates = missing_required_document_rule(instruments, documents)
    assert len(candidates) == 1


def test_maturity_without_successor_rule(synthetic_state):
    _, _, instruments, *_ = synthetic_state
    candidates = approaching_maturity_without_successor_rule(instruments, today=EVALUATION_DATE)
    assert len(candidates) == 1
    assert candidates[0].observed_values["days_remaining"] == 5


def test_replacement_lineage_consistency_rule(synthetic_state):
    _, _, instruments, *_ = synthetic_state
    assert len(replacement_lineage_rule(instruments)) == 1


def test_unresolved_release_conditions_rule(synthetic_state):
    _, _, instruments, _, _, checks, releases = synthetic_state
    by_id = {instrument.id: instrument for instrument in instruments}
    assert len(unresolved_release_conditions_rule(releases, by_id, checks)) == 1


def _scrutiny_user(session, institution_id: str) -> User:
    user = User(
        institution_id=institution_id,
        full_name="Synthetic Integrity Scrutiny Officer",
        email="integrity-officer@integrity.invalid",
        password_hash=hash_password("integrity-test-password-long-enough"),
        role=Role.SCRUTINY_OFFICER,
        data_origin=DataOrigin.SYNTHETIC_DEMO,
    )
    session.add(user)
    session.flush()
    return user


def test_repeated_scans_are_idempotent_and_audit_only_first_detection(synthetic_state):
    session, _, instruments, *_ = synthetic_state
    actor = _scrutiny_user(session, instruments[0].institution_id)
    first = run_integrity_scan(session, actor, today=EVALUATION_DATE)
    first_count = session.scalar(select(func.count(IntegrityFinding.id)))
    first_audits = session.scalar(select(func.count(AuditEvent.id)))
    second = run_integrity_scan(session, actor, today=EVALUATION_DATE)
    second_count = session.scalar(select(func.count(IntegrityFinding.id)))
    second_audits = session.scalar(select(func.count(AuditEvent.id)))
    assert first["findings_created"] == first["candidates_detected"]
    assert second["findings_created"] == 0
    assert second["findings_reopened"] == 0
    assert second["findings_resolved"] == 0
    assert first_count == second_count
    assert first_audits == second_audits


def test_queue_explains_rank_and_human_review_records_audit(synthetic_state):
    session, _, instruments, *_ = synthetic_state
    actor = _scrutiny_user(session, instruments[0].institution_id)
    run_integrity_scan(session, actor, today=EVALUATION_DATE)
    queue, count = get_prioritized_scrutiny_queue(session, actor, today=EVALUATION_DATE, limit=100)
    assert count > 0
    first = queue[0]
    assert first["priority_score"] > 0
    assert any("unresolved and open" in reason for reason in first["ranking_reasons"])
    assert "not a calibrated probability" in first["ranking_notice"]
    maturity_item = next(item for item in queue if item["finding"].finding_type == FindingType.MATURITY_WITHOUT_SUCCESSOR)
    assert maturity_item["deadline_days_remaining"] == 5
    assert any("maturity is 5 day(s) away" in reason for reason in maturity_item["ranking_reasons"])
    assert maturity_item["supporting_evidence"]["observed_values"]["days_remaining"] == 5

    finding = first["finding"]
    reviewed = review_integrity_finding(
        session,
        actor,
        finding.id,
        decision=IntegrityReviewStatus.REVIEWED,
        resolution_notes="Reviewed against the synthetic source fixture.",
    )
    assert reviewed.reviewed_by_user_id == actor.id
    assert reviewed.reviewed_at is not None
    audit = session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == reviewed.instrument_id,
            AuditEvent.action == "integrity_finding_reviewed",
        )
    )
    assert audit is not None
    assert audit.actor_user_id == actor.id
    assert audit.after_values["review_status"] == "reviewed"
    history_actions = {
        event["action"]
        for event in get_instrument_history(session, actor, finding.instrument_id)
    }
    assert "integrity_finding_detected" in history_actions
    assert "integrity_finding_reviewed" in history_actions


def test_measured_synthetic_dataset_has_planted_cases_and_clean_controls():
    results = evaluate_dataset()
    assert results["known_discrepancies_detected"] == results["known_discrepancies_total"]
    assert results["known_duplicate_pairs_detected"] == results["known_duplicate_pairs_total"]
    assert results["false_positive_candidates_on_clean_records"] == 0


def test_integrity_scan_and_queue_are_restricted_to_internal_roles(auth_client, test_session_factory):
    with test_session_factory() as session:
        institution = Institution(code="INTEGRITY-API", name="Synthetic Integrity API Institution")
        session.add(institution)
        session.flush()
        session.add_all(
            [
                User(
                    institution_id=institution.id,
                    full_name="Synthetic Integrity Institution User",
                    email="integrity-inst@api.invalid",
                    password_hash=hash_password("integrity-api-password-long-enough"),
                    role=Role.INSTITUTION_USER,
                ),
                User(
                    full_name="Synthetic Integrity Officer",
                    email="integrity-scrutiny@api.invalid",
                    password_hash=hash_password("integrity-api-password-long-enough"),
                    role=Role.SCRUTINY_OFFICER,
                ),
            ]
        )
        session.add(
            FDRInstrument(
                institution_id=institution.id,
                issuer_name="Synthetic API Queue Issuer",
                reference_original="SYN-API-QUEUE-1",
                amount=Decimal("1000.00"),
                issue_date=date(2025, 1, 1),
                maturity_date=date(2028, 1, 1),
                lifecycle_status=InstrumentLifecycleStatus.SUBMITTED,
                data_origin=DataOrigin.SYNTHETIC_DEMO,
            )
        )
        session.commit()

    def headers(email: str):
        result = auth_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "integrity-api-password-long-enough"},
        )
        assert result.status_code == 200
        return {"Authorization": f"Bearer {result.json()['access_token']}"}

    institution_headers = headers("integrity-inst@api.invalid")
    assert auth_client.post("/api/v1/integrity/scan", headers=institution_headers).status_code == 403
    assert auth_client.get("/api/v1/integrity/queue", headers=institution_headers).status_code == 403

    officer_headers = headers("integrity-scrutiny@api.invalid")
    scan = auth_client.post("/api/v1/integrity/scan", headers=officer_headers)
    assert scan.status_code == 200, scan.text
    queue = auth_client.get("/api/v1/integrity/queue", headers=officer_headers)
    assert queue.status_code == 200, queue.text
    assert "items" in queue.json()
    assert queue.json()["items"]
    assert "priority_score" in queue.json()["items"][0]
    assert queue.json()["items"][0]["finding"]["finding_type"] == "missing_required_document"
