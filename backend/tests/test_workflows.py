"""FDR APIs, lifecycle transitions, release policy, and audit integration tests."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    AuditEvent,
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    Institution,
    InstrumentDocument,
    InstrumentLifecycleStatus,
    OperationalPriority,
    RegulatoryObligation,
    RegulatoryRule,
    ReleaseApproval,
    ReleaseRequest,
    Role,
    User,
    VerificationCheck,
    VerificationCheckStatus,
    VerificationStatus,
    WorkflowEvent,
    WorkflowEventType,
)

TEST_PASSWORD = "workflow-test-password-long-enough"


def auth_headers(client, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def setup_roles(session_factory, institution_count: int = 1):
    with session_factory() as session:
        institutions = []
        for index in range(1, institution_count + 1):
            institution = Institution(code=f"WORKFLOW-{index}", name=f"Workflow Institute {index}")
            session.add(institution)
            institutions.append(institution)
        session.flush()
        password_hash = hash_password(TEST_PASSWORD)
        users = {}
        roles = [Role.INSTITUTION_USER, Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR, Role.ADMIN]
        for role in roles:
            user = User(
                institution_id=institutions[0].id if role == Role.INSTITUTION_USER else None,
                full_name=f"Workflow {role.value}",
                email=f"{role.value}@workflow.invalid",
                password_hash=password_hash,
                role=role,
            )
            session.add(user)
            users[role] = user
        session.commit()
        return [row.id for row in institutions], {role: row.id for role, row in users.items()}


def insert_instrument(
    session_factory,
    institution_id: str,
    *,
    status: InstrumentLifecycleStatus = InstrumentLifecycleStatus.DRAFT,
    maturity_date: date = date(2027, 1, 1),
    verification_status: VerificationStatus = VerificationStatus.NOT_CHECKED,
    amount: Decimal = Decimal("5000.00"),
    reference: str = "WORKFLOW-FDR-01",
) -> str:
    with session_factory() as session:
        instrument = FDRInstrument(
            institution_id=institution_id,
            issuer_name="Synthetic Workflow Issuer",
            reference_original=reference,
            amount=amount,
            issue_date=min(date(2025, 1, 1), maturity_date),
            maturity_date=maturity_date,
            lifecycle_status=status,
            verification_status=verification_status,
            priority=OperationalPriority.NORMAL,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
        )
        session.add(instrument)
        session.commit()
        return instrument.id


def test_institution_search_filter_pagination_detail_and_obligations(auth_client, test_session_factory):
    institution_ids, user_ids = setup_roles(test_session_factory, institution_count=3)
    with test_session_factory() as session:
        for idx in range(2):
            session.add(
                RegulatoryObligation(
                    institution_id=institution_ids[0],
                    code=f"OBL-{idx}",
                    title=f"Synthetic obligation {idx}",
                    effective_date=date(2025, 1, 1),
                    due_date=date(2027, 1, 1),
                )
            )
        session.commit()

    headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")
    page = auth_client.get("/api/v1/institutions?search=Workflow&limit=2&offset=1", headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    assert page.json()["offset"] == 1

    detail = auth_client.get(f"/api/v1/institutions/{institution_ids[0]}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["obligations"]) == 2
    obligation_page = auth_client.get(
        f"/api/v1/institutions/{institution_ids[0]}/obligations?limit=1", headers=headers
    )
    assert obligation_page.json()["total"] == 2
    assert len(obligation_page.json()["items"]) == 1

    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    hidden = auth_client.get(f"/api/v1/institutions/{institution_ids[1]}", headers=institution_headers)
    assert hidden.status_code == 404


def test_fdr_creation_filters_pagination_and_does_not_accept_client_status(auth_client, test_session_factory):
    institution_ids, _ = setup_roles(test_session_factory, institution_count=2)
    headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    payload = {
        "institution_id": institution_ids[0],
        "issuer_name": "Synthetic Bank-like Issuer",
        "reference_original": "SYN/API-100",
        "amount": "7000.00",
        "issue_date": "2025-01-01",
        "maturity_date": "2027-01-01",
        "lifecycle_status": "approved",
        "verification_status": "reviewed",
    }
    created = auth_client.post("/api/v1/fdrs", json=payload, headers=headers)
    assert created.status_code == 201
    assert created.json()["lifecycle_status"] == "draft"
    assert created.json()["verification_status"] == "not_checked"
    assert created.json()["reference_normalized"] == "SYNAPI100"

    second = {**payload, "reference_original": "SYN/API-101", "lifecycle_status": "rejected"}
    assert auth_client.post("/api/v1/fdrs", json=second, headers=headers).status_code == 201
    page = auth_client.get("/api/v1/fdrs?search=SYN&limit=1&offset=0", headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1
    other_tenant = auth_client.get(
        f"/api/v1/fdrs?institution_id={institution_ids[1]}", headers=headers
    )
    assert other_tenant.json()["total"] == 0


def test_invalid_transition_and_full_clarification_resubmission_history(auth_client, test_session_factory):
    institution_ids, _ = setup_roles(test_session_factory)
    instrument_id = insert_instrument(test_session_factory, institution_ids[0])
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    scrutiny_headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")

    invalid = auth_client.post(f"/api/v1/fdrs/{instrument_id}/scrutiny", json={"outcome": "recommend_approval"}, headers=scrutiny_headers)
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "invalid_transition"
    assert auth_client.post(f"/api/v1/fdrs/{instrument_id}/submit", headers=institution_headers).status_code == 200

    clarification = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/scrutiny",
        json={"outcome": "request_clarification", "clarification_question": "Please clarify the synthetic reference."},
        headers=scrutiny_headers,
    )
    assert clarification.status_code == 200
    clarification_event_id = clarification.json()["event_id"]
    assert clarification.json()["instrument"]["lifecycle_status"] == "clarification_required"

    response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/clarifications/{clarification_event_id}/respond",
        json={"response": "The fictional reference is an intentional test value."},
        headers=institution_headers,
    )
    assert response.status_code == 200
    assert response.json()["lifecycle_status"] == "submitted"
    repeated = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/clarifications/{clarification_event_id}/respond",
        json={"response": "Second response"},
        headers=institution_headers,
    )
    assert repeated.status_code == 409

    history = auth_client.get(f"/api/v1/fdrs/{instrument_id}/history", headers=institution_headers)
    actions = [item["action"] for item in history.json()["events"]]
    assert "submitted" in actions
    assert "clarification_requested" in actions
    assert "clarification_responded" in actions
    with test_session_factory() as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.action == "clarification_responded"))
        assert event.actor_user_id is not None
        assert event.entity_id == instrument_id
        assert event.after_values["response_length"] > 0
        assert "response" not in event.after_values


def test_scrutiny_recommendation_and_only_approver_can_record_final_decision(auth_client, test_session_factory):
    institution_ids, _ = setup_roles(test_session_factory)
    instrument_id = insert_instrument(test_session_factory, institution_ids[0])
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    scrutiny_headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")
    approver_headers = auth_headers(auth_client, "approving_authority@workflow.invalid")
    auth_client.post(f"/api/v1/fdrs/{instrument_id}/submit", headers=institution_headers)
    review = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/scrutiny",
        json={"outcome": "recommend_approval", "comment": "Synthetic checks reviewed."},
        headers=scrutiny_headers,
    )
    assert review.status_code == 200
    assert review.json()["instrument"]["lifecycle_status"] == "under_scrutiny"

    forbidden = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/decision",
        json={"decision": "approved", "rationale": "Not an approver."},
        headers=scrutiny_headers,
    )
    assert forbidden.status_code == 403
    final = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/decision",
        json={"decision": "approved", "rationale": "Authorized human decision for synthetic test."},
        headers=approver_headers,
    )
    assert final.status_code == 200
    assert final.json()["lifecycle_status"] == "approved"
    with test_session_factory() as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.action == "fdr_final_decision_recorded"))
        assert event.actor_user_id is not None
        assert event.after_values["lifecycle_status"] == "approved"


def test_renewal_lineage_and_predecessor_superseded_only_after_successor_approval(
    auth_client, test_session_factory
):
    institution_ids, _ = setup_roles(test_session_factory)
    old_id = insert_instrument(
        test_session_factory,
        institution_ids[0],
        status=InstrumentLifecycleStatus.APPROVED,
        maturity_date=date(2026, 1, 1),
        reference="SYN-OLD-FDR",
    )
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    payload = {
        "replacement_type": "renewal",
        "issuer_name": "Synthetic Replacement Issuer",
        "reference_original": "SYN-NEW-FDR",
        "amount": "5200.00",
        "issue_date": "2026-01-01",
        "maturity_date": "2028-01-01",
    }
    successor_response = auth_client.post(
        f"/api/v1/fdrs/{old_id}/successors", json=payload, headers=institution_headers
    )
    assert successor_response.status_code == 201
    successor_id = successor_response.json()["id"]
    assert successor_response.json()["supersedes_instrument_id"] == old_id
    assert successor_response.json()["lifecycle_status"] == "draft"
    assert auth_client.get(f"/api/v1/fdrs/{old_id}", headers=institution_headers).json()["lifecycle_status"] == "approved"
    assert auth_client.post(f"/api/v1/fdrs/{old_id}/successors", json=payload, headers=institution_headers).status_code == 409

    auth_client.post(f"/api/v1/fdrs/{successor_id}/submit", headers=institution_headers)
    scrutiny_headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")
    approver_headers = auth_headers(auth_client, "approving_authority@workflow.invalid")
    auth_client.post(
        f"/api/v1/fdrs/{successor_id}/scrutiny",
        json={"outcome": "recommend_approval"},
        headers=scrutiny_headers,
    )
    decided = auth_client.post(
        f"/api/v1/fdrs/{successor_id}/decision",
        json={"decision": "approved", "rationale": "Approved synthetic renewal."},
        headers=approver_headers,
    )
    assert decided.status_code == 200
    assert auth_client.get(f"/api/v1/fdrs/{old_id}", headers=institution_headers).json()["lifecycle_status"] == "superseded"


def test_successor_chain_can_continue_after_each_successor_is_approved(auth_client, test_session_factory):
    institution_ids, _ = setup_roles(test_session_factory)
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    scrutiny_headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")
    approver_headers = auth_headers(auth_client, "approving_authority@workflow.invalid")
    first_id = insert_instrument(test_session_factory, institution_ids[0], status=InstrumentLifecycleStatus.APPROVED, reference="CHAIN-ROOT")

    def create_and_approve(previous_id: str, reference: str) -> dict:
        created = auth_client.post(f"/api/v1/fdrs/{previous_id}/successors", headers=institution_headers, json={
            "replacement_type": "renewal", "issuer_name": "Synthetic Chain Issuer",
            "reference_original": reference, "amount": "5000.00", "issue_date": "2026-01-01", "maturity_date": "2028-01-01",
        })
        assert created.status_code == 201, created.text
        successor_id = created.json()["id"]
        assert created.json()["supersedes_instrument_id"] == previous_id
        assert auth_client.post(f"/api/v1/fdrs/{successor_id}/submit", headers=institution_headers).status_code == 200
        assert auth_client.post(f"/api/v1/fdrs/{successor_id}/scrutiny", headers=scrutiny_headers, json={"outcome": "recommend_approval"}).status_code == 200
        approved = auth_client.post(f"/api/v1/fdrs/{successor_id}/decision", headers=approver_headers, json={"decision": "approved", "rationale": "Approved synthetic renewal."})
        assert approved.status_code == 200, approved.text
        return approved.json()

    second = create_and_approve(first_id, "CHAIN-SECOND")
    assert auth_client.get(f"/api/v1/fdrs/{first_id}", headers=institution_headers).json()["successor_instrument_id"] == second["id"]
    third = create_and_approve(second["id"], "CHAIN-THIRD")
    assert third["supersedes_instrument_id"] == second["id"]
    assert auth_client.get(f"/api/v1/fdrs/{second['id']}", headers=institution_headers).json()["successor_instrument_id"] == third["id"]
    assert auth_client.get(f"/api/v1/fdrs/{third['id']}", headers=institution_headers).json()["supersedes_instrument_id"] == second["id"]


def test_draft_update_is_scoped_state_limited_and_audited(auth_client, test_session_factory):
    institution_ids, _ = setup_roles(test_session_factory, institution_count=2)
    instrument_id = insert_instrument(test_session_factory, institution_ids[0], reference="EDIT-ORIGINAL")
    own_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    patched = auth_client.patch(f"/api/v1/fdrs/{instrument_id}", headers=own_headers, json={"reference_original": " EDIT-CORRECTED ", "amount": "6100.00", "notes": "Synthetic note containing token=never-a-real-token"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["reference_original"] == "EDIT-CORRECTED"
    assert patched.json()["reference_normalized"] == "EDITCORRECTED"
    assert auth_client.patch(f"/api/v1/fdrs/{instrument_id}", headers=own_headers, json={"lifecycle_status": "approved"}).status_code == 422
    other = User(
        institution_id=institution_ids[1], full_name="Other institution", email="other@workflow.invalid",
        password_hash=hash_password(TEST_PASSWORD), role=Role.INSTITUTION_USER,
    )
    with test_session_factory() as session:
        session.add(other)
        session.commit()
    other_headers = auth_headers(auth_client, "other@workflow.invalid")
    assert auth_client.patch(f"/api/v1/fdrs/{instrument_id}", headers=other_headers, json={"amount": "1.00"}).status_code == 404
    scrutiny_headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")
    assert auth_client.patch(f"/api/v1/fdrs/{instrument_id}", headers=scrutiny_headers, json={"amount": "1.00"}).status_code == 404
    with test_session_factory() as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == instrument_id, AuditEvent.action == "fdr_draft_updated"))
        assert event is not None
        assert event.before_values == {"reference_original": "EDIT-ORIGINAL", "amount": "5000.00", "notes": {"present": False}}
        assert event.after_values == {"reference_original": "EDIT-CORRECTED", "amount": "6100.00", "notes": {"present": True}}
        assert "never-a-real-token" not in str(event.after_values)


def test_clarification_can_be_corrected_then_resubmitted_and_old_request_cannot_repeat(
    auth_client, test_session_factory
):
    institution_ids, _ = setup_roles(test_session_factory)
    instrument_id = insert_instrument(test_session_factory, institution_ids[0], reference="CLARIFY-CORRECTION")
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    scrutiny_headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")
    assert auth_client.post(f"/api/v1/fdrs/{instrument_id}/submit", headers=institution_headers).status_code == 200
    first = auth_client.post(f"/api/v1/fdrs/{instrument_id}/scrutiny", headers=scrutiny_headers, json={"outcome": "request_clarification", "clarification_question": "Correct the amount."})
    assert first.status_code == 200
    updated = auth_client.patch(f"/api/v1/fdrs/{instrument_id}", headers=institution_headers, json={"amount": "5100.00"})
    assert updated.status_code == 200 and updated.json()["amount"] == "5100.00"
    response = auth_client.post(f"/api/v1/fdrs/{instrument_id}/clarifications/{first.json()['event_id']}/respond", headers=institution_headers, json={"response": "Corrected as requested."})
    assert response.status_code == 200 and response.json()["lifecycle_status"] == "submitted"
    next_request = auth_client.post(f"/api/v1/fdrs/{instrument_id}/scrutiny", headers=scrutiny_headers, json={"outcome": "request_clarification", "clarification_question": "Second clarification."})
    assert next_request.status_code == 200
    repeated = auth_client.post(f"/api/v1/fdrs/{instrument_id}/clarifications/{first.json()['event_id']}/respond", headers=institution_headers, json={"response": "Must not be attached twice."})
    assert repeated.status_code == 409 and repeated.json()["error"]["code"] == "clarification_already_answered"
    assert auth_client.post(f"/api/v1/fdrs/{instrument_id}/clarifications/{next_request.json()['event_id']}/respond", headers=institution_headers, json={"response": "Second response."}).status_code == 200


def test_pending_scrutiny_endpoint_is_a_paginated_case_worklist(auth_client, test_session_factory):
    institution_ids, _ = setup_roles(test_session_factory)
    submitted = insert_instrument(test_session_factory, institution_ids[0], status=InstrumentLifecycleStatus.SUBMITTED, reference="WORKLIST-SUBMITTED")
    in_review = insert_instrument(test_session_factory, institution_ids[0], status=InstrumentLifecycleStatus.UNDER_SCRUTINY, reference="WORKLIST-REVIEW")
    insert_instrument(test_session_factory, institution_ids[0], status=InstrumentLifecycleStatus.CLARIFICATION_REQUIRED, reference="NOT-IN-WORKLIST")
    headers = auth_headers(auth_client, "scrutiny_officer@workflow.invalid")
    response = auth_client.get("/api/v1/dashboard/pending-scrutiny?limit=1", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    all_cases = auth_client.get("/api/v1/dashboard/pending-scrutiny?limit=10", headers=headers).json()["items"]
    assert {row["id"] for row in all_cases} == {submitted, in_review}
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    assert {row["institution_id"] for row in auth_client.get("/api/v1/dashboard/pending-scrutiny", headers=institution_headers).json()["items"]} == {institution_ids[0]}


def test_release_eligibility_blocks_missing_evidence_and_open_checks_then_requires_human_decision(
    auth_client, test_session_factory
):
    institution_ids, _ = setup_roles(test_session_factory)
    instrument_id = insert_instrument(
        test_session_factory,
        institution_ids[0],
        status=InstrumentLifecycleStatus.MATURED,
        maturity_date=date(2024, 1, 1),
        verification_status=VerificationStatus.PENDING_REVIEW,
        amount=Decimal("5000.00"),
    )
    with test_session_factory() as session:
        session.add(
            VerificationCheck(
                instrument_id=instrument_id,
                rule_code="SYN-REVIEW",
                title="Synthetic unresolved check",
                explanation="Human review is pending.",
            )
        )
        session.commit()
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    approver_headers = auth_headers(auth_client, "approving_authority@workflow.invalid")
    auditor_headers = auth_headers(auth_client, "auditor@workflow.invalid")
    created = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/release-requests",
        json={"requested_amount": "5000.00", "reason": "Synthetic release scenario."},
        headers=institution_headers,
    )
    assert created.status_code == 201
    request_id = created.json()["request"]["id"]
    eligibility = created.json()["eligibility"]
    assert eligibility["eligibility_status"] == "blocked"
    assert {item["code"] for item in eligibility["findings"]} >= {
        "mandatory_evidence_missing",
        "verification_unresolved",
    }
    assert auth_client.post(
        f"/api/v1/release-requests/{request_id}/decision",
        json={"decision": "approved", "rationale": "Cannot bypass eligibility.", "disposition": "No transfer."},
        headers=approver_headers,
    ).status_code == 409
    assert auth_client.post(
        f"/api/v1/release-requests/{request_id}/decision",
        json={"decision": "approved", "rationale": "Auditor cannot approve.", "disposition": "No transfer."},
        headers=auditor_headers,
    ).status_code == 403

    with test_session_factory() as session:
        document = InstrumentDocument(
            instrument_id=instrument_id,
            original_filename="synthetic-evidence.pdf",
            storage_key="synthetic/release/evidence.pdf",
            content_type="application/pdf",
            size_bytes=100,
            sha256_checksum="a" * 64,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
        )
        session.add(document)
        check = session.scalar(select(VerificationCheck).where(VerificationCheck.instrument_id == instrument_id))
        check.status = VerificationCheckStatus.REVIEWED
        instrument = session.get(FDRInstrument, instrument_id)
        instrument.verification_status = VerificationStatus.REVIEWED
        session.commit()

    reevaluated = auth_client.post(
        f"/api/v1/release-requests/{request_id}/evaluate", headers=institution_headers
    )
    assert reevaluated.status_code == 200
    assert reevaluated.json()["eligibility"]["eligible"] is True
    approved = auth_client.post(
        f"/api/v1/release-requests/{request_id}/decision",
        json={
            "decision": "approved",
            "rationale": "Authorized human approval.",
            "disposition": "Approved for release processing; no transfer performed.",
        },
        headers=approver_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["approval"]["disposition"].startswith("Approved for release")
    assert approved.json()["request"]["status"] == "approved"
    assert auth_client.get(f"/api/v1/fdrs/{instrument_id}", headers=institution_headers).json()["lifecycle_status"] == "release_pending"
    with test_session_factory() as session:
        approval = session.scalar(select(ReleaseApproval).where(ReleaseApproval.release_request_id == request_id))
        assert approval.approver_user_id is not None
        assert session.scalar(select(ReleaseRequest).where(ReleaseRequest.id == request_id)).status.value == "approved"
        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "release_decision_recorded")
        )
        assert audit.context["transfer_performed"] is False
        assert "rationale" not in (audit.after_values or {})


def test_release_rules_are_configurable_and_warnings_do_not_approve_or_release(
    auth_client, test_session_factory
):
    institution_ids, _ = setup_roles(test_session_factory)
    instrument_id = insert_instrument(
        test_session_factory,
        institution_ids[0],
        status=InstrumentLifecycleStatus.APPROVED,
        maturity_date=date(2028, 1, 1),
        verification_status=VerificationStatus.PENDING_REVIEW,
    )
    with test_session_factory() as session:
        session.add(
            RegulatoryRule(
                institution_id=institution_ids[0],
                code="release_eligibility",
                title="Synthetic permissive warning rule",
                description="Test that configured policies can turn conditions into warnings.",
                rule_config={
                    "must_be_matured": False,
                    "minimum_document_count": 0,
                    "block_unresolved_verifications": False,
                    "block_discrepancy_status": False,
                },
            )
        )
        session.commit()
    institution_headers = auth_headers(auth_client, "institution_user@workflow.invalid")
    created = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/release-requests",
        json={"requested_amount": "1000.00", "reason": "Policy config test."},
        headers=institution_headers,
    )
    assert created.status_code == 201
    assert created.json()["eligibility"]["eligible"] is True
    assert any(item["severity"] == "warning" for item in created.json()["eligibility"]["findings"])
    assert created.json()["request"]["status"] == "pending"
    assert auth_client.get(f"/api/v1/fdrs/{instrument_id}", headers=institution_headers).json()["lifecycle_status"] == "release_pending"
