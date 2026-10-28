"""Cross-role API journeys for the FDR Sentinel local prototype."""

from datetime import date, timedelta
from io import BytesIO

import fitz
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    AuditEvent,
    DataOrigin,
    FDRInstrument,
    Institution,
    InstrumentLifecycleStatus,
    Notification,
    OperationalPriority,
    Role,
    User,
    WorkflowEvent,
)
from app.services.operations_service import generate_maturity_reminders

PASSWORD = "synthetic-e2e-password-long-enough"


def pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((40, 45), text)
    contents = document.tobytes()
    document.close()
    return contents


def identities(factory, prefix: str = "journey"):
    with factory() as session:
        first = Institution(code=f"{prefix.upper()}-ONE", name=f"Synthetic {prefix} Institute One")
        second = Institution(code=f"{prefix.upper()}-TWO", name=f"Synthetic {prefix} Institute Two")
        session.add_all([first, second])
        session.flush()
        users = {}
        for institution, suffix in ((first, "one"), (second, "two")):
            user = User(
                institution_id=institution.id,
                full_name=f"Synthetic Institution User {suffix}",
                email=f"{prefix}-{suffix}@journeys.invalid",
                password_hash=hash_password(PASSWORD),
                role=Role.INSTITUTION_USER,
                data_origin=DataOrigin.SYNTHETIC_DEMO,
            )
            session.add(user)
            users[suffix] = user.email
        for role in (Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR, Role.ADMIN):
            user = User(
                full_name=f"Synthetic {role.value}",
                email=f"{prefix}-{role.value}@journeys.invalid",
                password_hash=hash_password(PASSWORD),
                role=role,
                data_origin=DataOrigin.SYNTHETIC_DEMO,
            )
            session.add(user)
            users[role.value] = user.email
        session.commit()
        return {"one_id": first.id, "two_id": second.id, "emails": users}


def login(client, email: str) -> dict[str, str]:
    result = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert result.status_code == 200, result.text
    assert "password_hash" not in result.json()
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def create_fdr(client, headers, institution_id: str, reference: str, *, maturity: date | None = None):
    today = date.today()
    return client.post(
        "/api/v1/fdrs",
        headers=headers,
        json={
            "institution_id": institution_id,
            "issuer_name": "Synthetic Regional Deposit Issuer",
            "beneficiary": "Synthetic Institute Beneficiary",
            "reference_original": reference,
            "amount": "12500.00",
            "issue_date": (today - timedelta(days=365)).isoformat(),
            "maturity_date": (maturity or today + timedelta(days=180)).isoformat(),
        },
    )


def upload_pdf(
    client,
    headers,
    instrument_id: str,
    *,
    amount: str = "12,500.00",
    reference: str | None = None,
    issue_date: date | None = None,
    maturity_date: date | None = None,
):
    issue_date = issue_date or date.today() - timedelta(days=365)
    maturity_date = maturity_date or date.today() + timedelta(days=180)
    text = (
        "Bank Name: Synthetic Regional Deposit Issuer\n"
        f"FDR Number: {reference or 'E2E-REF'}\n"
        f"Amount: INR {amount}\n"
        f"Issue Date: {issue_date.strftime('%d/%m/%Y')}\n"
        f"Maturity Date: {maturity_date.strftime('%d/%m/%Y')}\n"
        "Beneficiary: Synthetic Institute Beneficiary"
    )
    return client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        headers=headers,
        files={"file": ("synthetic-fdr.pdf", pdf_bytes(text), "application/pdf")},
    )


def authorize_fdr(client, institution_headers, scrutiny_headers, approver_headers, instrument_id: str):
    assert client.post(f"/api/v1/fdrs/{instrument_id}/submit", headers=institution_headers).status_code == 200
    reviewed = client.post(
        f"/api/v1/fdrs/{instrument_id}/scrutiny",
        headers=scrutiny_headers,
        json={"outcome": "recommend_approval", "comment": "Synthetic review completed."},
    )
    assert reviewed.status_code == 200, reviewed.text
    decided = client.post(
        f"/api/v1/fdrs/{instrument_id}/decision",
        headers=approver_headers,
        json={"decision": "approved", "rationale": "Synthetic authorized approval."},
    )
    assert decided.status_code == 200, decided.text
    return decided.json()


def configure_private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path / "private-evidence"))
    get_settings.cache_clear()


def test_scenarios_a_b_c_and_f_submission_scrutiny_successor_and_auditor(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    configure_private_storage(monkeypatch, tmp_path)
    identity = identities(test_session_factory, "abc")
    institution_headers = login(auth_client, identity["emails"]["one"])
    scrutiny_headers = login(auth_client, identity["emails"][Role.SCRUTINY_OFFICER.value])
    approver_headers = login(auth_client, identity["emails"][Role.APPROVING_AUTHORITY.value])
    auditor_headers = login(auth_client, identity["emails"][Role.AUDITOR.value])

    created = create_fdr(auth_client, institution_headers, identity["one_id"], "E2E-ORIGINAL-001")
    assert created.status_code == 201, created.text
    original_id = created.json()["id"]
    assert created.json()["lifecycle_status"] == "draft"

    uploaded = upload_pdf(
        auth_client, institution_headers, original_id, amount="13,500.00", reference="E2E-ORIGINAL-001"
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["extraction_status"] == "completed"
    fields = {field["field_name"]: field for field in document["fields"]}
    assert fields["amount"]["matches_declared"] is False
    assert fields["beneficiary"]["matches_declared"] is True
    assert len(document["sha256_checksum"]) == 64

    submitted = auth_client.post(f"/api/v1/fdrs/{original_id}/submit", headers=institution_headers)
    assert submitted.status_code == 200 and submitted.json()["lifecycle_status"] == "submitted"
    scan = auth_client.post("/api/v1/integrity/scan", headers=scrutiny_headers)
    assert scan.status_code == 200, scan.text
    findings = auth_client.get("/api/v1/integrity/findings?review_status=open", headers=scrutiny_headers)
    amount_findings = [row for row in findings.json()["items"] if row["instrument_id"] == original_id and row["finding_type"] == "amount_mismatch"]
    assert amount_findings, findings.text

    field_review = auth_client.post(
        f"/api/v1/documents/{document['id']}/fields/amount/review",
        headers=scrutiny_headers,
        json={"decision": "confirm_discrepancy", "comment": "The extracted candidate differs; request issuer clarification."},
    )
    assert field_review.status_code == 200, field_review.text
    clarification = auth_client.post(
        f"/api/v1/fdrs/{original_id}/scrutiny",
        headers=scrutiny_headers,
        json={"outcome": "request_clarification", "clarification_question": "Please clarify the amount shown in the synthetic evidence."},
    )
    assert clarification.status_code == 200, clarification.text
    clarification_event_id = clarification.json()["event_id"]
    response = auth_client.post(
        f"/api/v1/fdrs/{original_id}/clarifications/{clarification_event_id}/respond",
        headers=institution_headers,
        json={"response": "This synthetic test case confirms the amount discrepancy is intentional."},
    )
    assert response.status_code == 200 and response.json()["lifecycle_status"] == "submitted"
    assert auth_client.post(
        f"/api/v1/fdrs/{original_id}/scrutiny",
        headers=scrutiny_headers,
        json={"outcome": "recommend_approval", "comment": "Clarification reviewed; synthetic case can proceed."},
    ).status_code == 200
    approved = auth_client.post(
        f"/api/v1/fdrs/{original_id}/decision",
        headers=approver_headers,
        json={"decision": "approved", "rationale": "Explicit synthetic approval for lineage scenario."},
    )
    assert approved.status_code == 200 and approved.json()["lifecycle_status"] == "approved"

    successor = auth_client.post(
        f"/api/v1/fdrs/{original_id}/successors",
        headers=institution_headers,
        json={
            "replacement_type": "replacement",
            "issuer_name": "Synthetic Regional Deposit Issuer",
            "beneficiary": "Synthetic Institute Beneficiary",
            "reference_original": "E2E-REPLACEMENT-001",
            "amount": "12500.00",
            "issue_date": date.today().isoformat(),
            "maturity_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    assert successor.status_code == 201, successor.text
    successor_id = successor.json()["id"]
    assert successor.json()["supersedes_instrument_id"] == original_id
    assert auth_client.post(f"/api/v1/fdrs/{successor_id}/submit", headers=institution_headers).status_code == 200

    original_history = auth_client.get(f"/api/v1/fdrs/{original_id}/history", headers=institution_headers)
    successor_history = auth_client.get(f"/api/v1/fdrs/{successor_id}/history", headers=institution_headers)
    assert original_history.status_code == successor_history.status_code == 200
    original_actions = {row["action"] for row in original_history.json()["events"]}
    successor_actions = {row["action"] for row in successor_history.json()["events"]}
    assert {"clarification_requested", "clarification_responded", "fdr_final_decision_recorded", "fdr_successor_linked"} <= original_actions
    assert {"successor_created", "submitted"} <= successor_actions
    assert any(row["action"] == "document_field_reviewed" for row in original_history.json()["events"])

    # Auditors can read both timelines but have no lifecycle or final-decision powers.
    assert auth_client.get(f"/api/v1/fdrs/{original_id}/history", headers=auditor_headers).status_code == 200
    assert auth_client.get(f"/api/v1/fdrs/{successor_id}/history", headers=auditor_headers).status_code == 200
    assert auth_client.post(f"/api/v1/fdrs/{successor_id}/submit", headers=auditor_headers).status_code == 404
    assert auth_client.post(
        f"/api/v1/fdrs/{successor_id}/decision",
        headers=auditor_headers,
        json={"decision": "approved", "rationale": "Unauthorized auditor attempt."},
    ).status_code == 403
    denied_create = auth_client.post(
        "/api/v1/fdrs",
        headers=auditor_headers,
        json={
            "institution_id": identity["one_id"],
            "issuer_name": "Synthetic Issuer",
            "reference_original": "AUDITOR-MUST-NOT-CREATE",
            "amount": "1000.00",
            "issue_date": date.today().isoformat(),
            "maturity_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert denied_create.status_code == 403


def test_scenario_d_release_blocked_and_explicit_authorized_approval(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    configure_private_storage(monkeypatch, tmp_path)
    identity = identities(test_session_factory, "release")
    institution_headers = login(auth_client, identity["emails"]["one"])
    scrutiny_headers = login(auth_client, identity["emails"][Role.SCRUTINY_OFFICER.value])
    approver_headers = login(auth_client, identity["emails"][Role.APPROVING_AUTHORITY.value])
    matured = date.today() - timedelta(days=1)

    blocked = create_fdr(auth_client, institution_headers, identity["one_id"], "E2E-RELEASE-BLOCKED", maturity=matured)
    assert blocked.status_code == 201, blocked.text
    blocked_id = blocked.json()["id"]
    authorize_fdr(auth_client, institution_headers, scrutiny_headers, approver_headers, blocked_id)
    blocked_request = auth_client.post(
        f"/api/v1/fdrs/{blocked_id}/release-requests",
        headers=institution_headers,
        json={"requested_amount": "12500.00", "reason": "Synthetic refund request with missing evidence."},
    )
    assert blocked_request.status_code == 201, blocked_request.text
    blocked_body = blocked_request.json()
    assert not blocked_body["eligibility"]["eligible"]
    assert "mandatory_evidence_missing" in {row["code"] for row in blocked_body["eligibility"]["findings"]}
    request_id = blocked_body["request"]["id"]
    unauthorized = auth_client.post(
        f"/api/v1/release-requests/{request_id}/decision",
        headers=institution_headers,
        json={"decision": "approved", "rationale": "Institution cannot approve.", "disposition": "none"},
    )
    assert unauthorized.status_code == 403
    blocked_approval = auth_client.post(
        f"/api/v1/release-requests/{request_id}/decision",
        headers=approver_headers,
        json={"decision": "approved", "rationale": "Blocked request cannot be approved.", "disposition": "none"},
    )
    assert blocked_approval.status_code == 409

    valid = create_fdr(auth_client, institution_headers, identity["one_id"], "E2E-RELEASE-VALID", maturity=matured)
    assert valid.status_code == 201, valid.text
    valid_id = valid.json()["id"]
    authorize_fdr(auth_client, institution_headers, scrutiny_headers, approver_headers, valid_id)
    document = upload_pdf(
        auth_client,
        institution_headers,
        valid_id,
        reference="E2E-RELEASE-VALID",
        issue_date=date.today() - timedelta(days=365),
        maturity_date=matured,
    )
    assert document.status_code == 201, document.text
    valid_request = auth_client.post(
        f"/api/v1/fdrs/{valid_id}/release-requests",
        headers=institution_headers,
        json={"requested_amount": "12500.00", "reason": "Synthetic eligible release request."},
    )
    assert valid_request.status_code == 201, valid_request.text
    valid_body = valid_request.json()
    assert valid_body["eligibility"]["eligible"]
    approved = auth_client.post(
        f"/api/v1/release-requests/{valid_body['request']['id']}/decision",
        headers=approver_headers,
        json={"decision": "approved", "rationale": "Authorized synthetic decision.", "disposition": "Record only; no transfer."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["request"]["status"] == "approved"
    assert approved.json()["request"]["instrument_id"] == valid_id
    assert approved.json()["approval"]["approver_user_id"]
    assert approved.json()["request"]["eligibility_status"] == "eligible"
    # An approval records authorization/disposition, never a simulated bank transfer.
    with test_session_factory() as session:
        instrument = session.get(FDRInstrument, valid_id)
        event = session.scalar(select(AuditEvent).where(AuditEvent.action == "release_decision_recorded", AuditEvent.entity_id == valid_body["request"]["id"]))
        assert instrument.lifecycle_status == InstrumentLifecycleStatus.RELEASE_PENDING
        assert event.context["transfer_performed"] is False


def test_scenario_e_maturity_dashboard_queue_and_notification(auth_client, test_session_factory, monkeypatch):
    monkeypatch.setenv("MATURITY_REMINDER_WINDOWS_DAYS", "30,15,7")
    get_settings.cache_clear()
    identity = identities(test_session_factory, "maturity")
    institution_headers = login(auth_client, identity["emails"]["one"])
    due_in_seven_days = date.today() + timedelta(days=7)
    record = create_fdr(
        auth_client, institution_headers, identity["one_id"], "E2E-MATURITY-007", maturity=due_in_seven_days
    )
    assert record.status_code == 201, record.text
    instrument_id = record.json()["id"]
    # An active submitted record is visible in maturity counts and actionable queues.
    assert auth_client.post(f"/api/v1/fdrs/{instrument_id}/submit", headers=institution_headers).status_code == 200
    dashboard = auth_client.get("/api/v1/dashboard/summary", headers=institution_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["approaching_maturity"] == 1
    queue = auth_client.get("/api/v1/dashboard/queue", headers=institution_headers)
    queued_ids = {row["instrument"]["id"] for row in queue.json()["items"]}
    assert instrument_id in queued_ids
    assert "maturity_approaching_without_successor" in next(
        row["triggered_rules"] for row in queue.json()["items"] if row["instrument"]["id"] == instrument_id
    )
    with test_session_factory() as session:
        assert generate_maturity_reminders(session, today=date.today()) == 1
        assert generate_maturity_reminders(session, today=date.today()) == 0
        assert session.scalar(select(Notification).where(Notification.reason == "maturity_7_days")) is not None
    notifications = auth_client.get("/api/v1/notifications?unread_only=true", headers=institution_headers)
    assert notifications.status_code == 200
    assert any(row["related_entity_id"] == instrument_id for row in notifications.json()["items"])
    get_settings.cache_clear()


def test_scenario_g_institution_id_filters_and_document_routes_are_tenant_scoped(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    configure_private_storage(monkeypatch, tmp_path)
    identity = identities(test_session_factory, "scope")
    first_headers = login(auth_client, identity["emails"]["one"])
    second_headers = login(auth_client, identity["emails"]["two"])
    own = create_fdr(auth_client, first_headers, identity["one_id"], "SCOPE-OWN")
    other = create_fdr(auth_client, second_headers, identity["two_id"], "SCOPE-OTHER")
    assert own.status_code == other.status_code == 201
    other_id = other.json()["id"]
    other_doc = upload_pdf(auth_client, second_headers, other_id, reference="SCOPE-OTHER")
    assert other_doc.status_code == 201, other_doc.text
    other_document_id = other_doc.json()["id"]

    assert auth_client.get(f"/api/v1/fdrs/{other_id}", headers=first_headers).status_code == 404
    assert auth_client.get(f"/api/v1/fdrs/{other_id}/history", headers=first_headers).status_code == 404
    assert auth_client.get(f"/api/v1/fdrs/{other_id}/documents", headers=first_headers).status_code == 404
    assert auth_client.get(f"/api/v1/documents/{other_document_id}/download", headers=first_headers).status_code == 404
    scoped_list = auth_client.get(f"/api/v1/fdrs?institution_id={identity['two_id']}", headers=first_headers)
    assert scoped_list.status_code == 200 and scoped_list.json()["total"] == 0
    assert auth_client.get(f"/api/v1/institutions/{identity['two_id']}", headers=first_headers).status_code == 404
    assert auth_client.get(f"/api/v1/institutions/{identity['two_id']}/obligations", headers=first_headers).status_code == 404
    assert auth_client.get(f"/api/v1/dashboard/summary?institution_id={identity['two_id']}", headers=first_headers).status_code == 404
    assert auth_client.get(f"/api/v1/reports/instruments?institution_id={identity['two_id']}", headers=first_headers).status_code == 404


def test_admin_has_explicit_read_only_release_detail_and_audit_events_are_append_only(
    auth_client, test_session_factory
):
    identity = identities(test_session_factory, "admin-read")
    institution_headers = login(auth_client, identity["emails"]["one"])
    admin_headers = login(auth_client, identity["emails"][Role.ADMIN.value])
    today = date.today()
    instrument = FDRInstrument(
        institution_id=identity["one_id"],
        issuer_name="Synthetic Issuer",
        reference_original="ADMIN-READ-ONLY",
        amount="1000.00",
        issue_date=today - timedelta(days=20),
        maturity_date=today - timedelta(days=1),
        lifecycle_status=InstrumentLifecycleStatus.APPROVED,
        data_origin=DataOrigin.SYNTHETIC_DEMO,
        priority=OperationalPriority.NORMAL,
    )
    with test_session_factory() as session:
        session.add(instrument)
        session.commit()
        instrument_id = instrument.id
    request_response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/release-requests",
        headers=institution_headers,
        json={"requested_amount": "1000.00", "reason": "Synthetic admin read permission test."},
    )
    assert request_response.status_code == 201, request_response.text
    request_id = request_response.json()["request"]["id"]
    assert auth_client.get(f"/api/v1/release-requests/{request_id}", headers=admin_headers).status_code == 200
    assert auth_client.post(
        f"/api/v1/release-requests/{request_id}/decision",
        headers=admin_headers,
        json={"decision": "rejected", "rationale": "Admin is not an approver.", "disposition": "none"},
    ).status_code == 403

    with test_session_factory() as session:
        audit = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == request_id))
        audit.action = "tampered"
        try:
            session.flush()
            assert False, "AuditEvent update unexpectedly succeeded"
        except ValueError as exc:
            assert "append-only" in str(exc)
        session.rollback()


def test_acceptance_repeated_clarification_rounds_are_distinct_and_audited(
    auth_client, test_session_factory
):
    """A second clarification must not reuse or overwrite the first request."""
    identity = identities(test_session_factory, "clarify-twice")
    institution_headers = login(auth_client, identity["emails"]["one"])
    scrutiny_headers = login(auth_client, identity["emails"][Role.SCRUTINY_OFFICER.value])
    approver_headers = login(auth_client, identity["emails"][Role.APPROVING_AUTHORITY.value])

    created = create_fdr(auth_client, institution_headers, identity["one_id"], "E2E-CLARIFY-TWICE")
    assert created.status_code == 201, created.text
    instrument_id = created.json()["id"]
    assert auth_client.post(f"/api/v1/fdrs/{instrument_id}/submit", headers=institution_headers).status_code == 200

    first_request = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/scrutiny",
        headers=scrutiny_headers,
        json={"outcome": "request_clarification", "comment": "Round one", "clarification_question": "Please confirm the reference."},
    )
    assert first_request.status_code == 200, first_request.text
    first_event_id = first_request.json()["event_id"]
    first_response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/clarifications/{first_event_id}/respond",
        headers=institution_headers,
        json={"response": "The reference is confirmed for synthetic testing."},
    )
    assert first_response.status_code == 200, first_response.text

    second_request = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/scrutiny",
        headers=scrutiny_headers,
        json={"outcome": "request_clarification", "comment": "Round two", "clarification_question": "Please explain the beneficiary designation."},
    )
    assert second_request.status_code == 200, second_request.text
    second_event_id = second_request.json()["event_id"]
    assert second_event_id != first_event_id

    # The first request stays answered; attempting to reuse it cannot consume round two.
    reused = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/clarifications/{first_event_id}/respond",
        headers=institution_headers,
        json={"response": "This must not answer round two."},
    )
    assert reused.status_code == 409, reused.text
    second_response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/clarifications/{second_event_id}/respond",
        headers=institution_headers,
        json={"response": "The beneficiary designation is a fictional demo value."},
    )
    assert second_response.status_code == 200, second_response.text

    recommended = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/scrutiny",
        headers=scrutiny_headers,
        json={"outcome": "recommend_approval", "comment": "Both clarification rounds reviewed."},
    )
    assert recommended.status_code == 200, recommended.text
    final = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/decision",
        headers=approver_headers,
        json={"decision": "approved", "rationale": "Synthetic acceptance test completed."},
    )
    assert final.status_code == 200 and final.json()["lifecycle_status"] == "approved"

    history = auth_client.get(f"/api/v1/fdrs/{instrument_id}/history", headers=institution_headers)
    assert history.status_code == 200
    actions = [row["action"] for row in history.json()["events"]]
    assert actions.count("clarification_requested") >= 2
    assert actions.count("clarification_responded") >= 2


def test_acceptance_successor_chain_supports_multiple_generations(
    auth_client, test_session_factory
):
    """An approved successor can itself be renewed/replaced without losing ancestry."""
    identity = identities(test_session_factory, "lineage-chain")
    institution_headers = login(auth_client, identity["emails"]["one"])
    scrutiny_headers = login(auth_client, identity["emails"][Role.SCRUTINY_OFFICER.value])
    approver_headers = login(auth_client, identity["emails"][Role.APPROVING_AUTHORITY.value])

    original = create_fdr(auth_client, institution_headers, identity["one_id"], "CHAIN-ORIGINAL")
    assert original.status_code == 201, original.text
    original_id = original.json()["id"]
    authorize_fdr(auth_client, institution_headers, scrutiny_headers, approver_headers, original_id)

    def make_successor(predecessor_id: str, reference: str):
        response = auth_client.post(
            f"/api/v1/fdrs/{predecessor_id}/successors",
            headers=institution_headers,
            json={
                "replacement_type": "renewal",
                "issuer_name": "Synthetic Regional Deposit Issuer",
                "beneficiary": "Synthetic Institute Beneficiary",
                "reference_original": reference,
                "amount": "12500.00",
                "issue_date": date.today().isoformat(),
                "maturity_date": (date.today() + timedelta(days=365)).isoformat(),
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    second = make_successor(original_id, "CHAIN-SECOND")
    second_id = second["id"]
    assert second["supersedes_instrument_id"] == original_id
    authorize_fdr(auth_client, institution_headers, scrutiny_headers, approver_headers, second_id)

    third = make_successor(second_id, "CHAIN-THIRD")
    third_id = third["id"]
    assert third["supersedes_instrument_id"] == second_id

    second_detail = auth_client.get(f"/api/v1/fdrs/{second_id}", headers=institution_headers)
    original_detail = auth_client.get(f"/api/v1/fdrs/{original_id}", headers=institution_headers)
    assert second_detail.status_code == original_detail.status_code == 200
    assert second_detail.json()["supersedes_instrument_id"] == original_id
    assert second_detail.json()["successor_instrument_id"] == third_id
    assert original_detail.json()["successor_instrument_id"] == second_id

    third_history = auth_client.get(f"/api/v1/fdrs/{third_id}/history", headers=institution_headers)
    assert third_history.status_code == 200
    assert any(row["action"] == "successor_created" for row in third_history.json()["events"])
