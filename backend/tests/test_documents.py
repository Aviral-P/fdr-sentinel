"""Private document upload, extraction, comparison, and access tests."""

from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import (
    AuditEvent,
    ExtractedDocumentField,
    FDRInstrument,
    Institution,
    InstrumentDocument,
    Role,
    User,
    VerificationCheck,
    VerificationStatus,
)
from app.services.storage_service import store_private_document

PASSWORD = "document-test-password-long-enough"


def _create_pdf(text: str | None) -> bytes:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((50, 50), text)
    else:
        image_buffer = BytesIO()
        Image.new("RGB", (80, 60), "white").save(image_buffer, format="PNG")
        page.insert_image(page.rect, stream=image_buffer.getvalue())
    data = document.tobytes()
    document.close()
    return data


def _setup_identity(session_factory, *, other_institution: bool = False):
    with session_factory() as session:
        institution = Institution(code="DOC-ONE", name="Synthetic Document Institute One")
        session.add(institution)
        session.flush()
        user = User(
            institution_id=institution.id,
            full_name="Synthetic Document User",
            email="document-user@documents.invalid",
            password_hash=hash_password(PASSWORD),
            role=Role.INSTITUTION_USER,
        )
        auditor = User(
            full_name="Synthetic Document Auditor",
            email="document-auditor@documents.invalid",
            password_hash=hash_password(PASSWORD),
            role=Role.AUDITOR,
        )
        scrutiny_officer = User(
            full_name="Synthetic Document Scrutiny Officer",
            email="document-officer@documents.invalid",
            password_hash=hash_password(PASSWORD),
            role=Role.SCRUTINY_OFFICER,
        )
        session.add_all([user, auditor, scrutiny_officer])
        other_id = None
        if other_institution:
            other = Institution(code="DOC-TWO", name="Synthetic Document Institute Two")
            session.add(other)
            session.flush()
            other_id = other.id
            session.add(
                User(
                    institution_id=other.id,
                    full_name="Synthetic Other Tenant",
                    email="other-document-user@documents.invalid",
                    password_hash=hash_password(PASSWORD),
                    role=Role.INSTITUTION_USER,
                )
            )
        instrument = FDRInstrument(
            institution_id=institution.id,
            issuer_name="Synthetic Community Bank",
            reference_original="DOC-REF-42",
            amount="12500.00",
            issue_date=date(2025, 1, 1),
            maturity_date=date(2028, 1, 1),
        )
        session.add(instrument)
        session.commit()
        return institution.id, instrument.id, other_id


def _login(client, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _configure_storage(monkeypatch, tmp_path, max_bytes: int = 1024 * 1024):
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path / "private-documents"))
    monkeypatch.setenv("MAX_DOCUMENT_SIZE_BYTES", str(max_bytes))
    get_settings.cache_clear()


def test_storage_refuses_frontend_public_directory(monkeypatch):
    public_directory = Path(__file__).resolve().parents[2] / "frontend" / "public"
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(public_directory))
    get_settings.cache_clear()
    with pytest.raises(AppError, match="cannot be inside the frontend public directory"):
        store_private_document(b"synthetic", ".pdf")


def test_upload_hash_private_storage_extraction_and_declared_comparison(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path)
    _, instrument_id, _ = _setup_identity(test_session_factory)
    headers = _login(auth_client, "document-user@documents.invalid")
    pdf = _create_pdf(
        "Bank Name: Synthetic Community Bank\n"
        "Branch: Demonstration Branch\n"
        "FDR Number: DOC-REF-42\n"
        "Amount: INR 12,500.00\n"
        "Issue Date: 01/01/2025\n"
        "Maturity Date: 01/01/2028\n"
        "Beneficiary: Synthetic Document Institute"
    )
    response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={"file": ("../../private/evidence.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["original_filename"] == "evidence.pdf"
    assert payload["sha256_checksum"] == sha256(pdf).hexdigest()
    assert payload["extraction_status"] == "completed"
    assert payload["extraction_method"] == "pymupdf_text_regex"
    assert "storage_key" not in payload
    field_values = {field["field_name"]: field for field in payload["fields"]}
    assert field_values["reference_number"]["matches_declared"] is True
    assert field_values["amount"]["matches_declared"] is True
    assert field_values["branch"]["matches_declared"] is None
    assert field_values["beneficiary"]["matches_declared"] is None
    assert field_values["branch"]["value_status"] == "found"

    with test_session_factory() as session:
        row = session.get(InstrumentDocument, payload["id"])
        private_file = tmp_path / "private-documents" / row.storage_key
        instrument = session.get(FDRInstrument, instrument_id)
        audits = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "instrument_document", AuditEvent.entity_id == row.id
                )
            )
        )
        assert private_file.is_file()
        assert row.storage_key == private_file.name
        assert private_file.stat().st_mode & 0o777 == 0o600
        assert instrument.reference_original == "DOC-REF-42"
        assert instrument.verification_status == VerificationStatus.NOT_CHECKED
        assert {audit.action for audit in audits} == {"document_uploaded", "document_extraction_completed"}
        assert all("extracted_text" not in (audit.after_values or {}) for audit in audits)

    history = auth_client.get(f"/api/v1/fdrs/{instrument_id}/history", headers=headers)
    assert history.status_code == 200
    assert "document_extraction_completed" in {event["action"] for event in history.json()["events"]}, history.text


def test_extracted_mismatches_create_explainable_checks_without_overwriting_declared_values(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path)
    _, instrument_id, _ = _setup_identity(test_session_factory)
    headers = _login(auth_client, "document-user@documents.invalid")
    pdf = _create_pdf("FDR Number: DIFFERENT-REF\nAmount: 15,000.00\nMaturity Date: 01/01/2029")
    result = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={"file": ("mismatch.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert result.status_code == 201, result.text
    fields = {field["field_name"]: field for field in result.json()["fields"]}
    assert fields["reference_number"]["matches_declared"] is False
    assert fields["amount"]["matches_declared"] is False
    assert fields["branch"]["value_status"] == "missing"
    assert fields["branch"]["extracted_value"] is None
    assert fields["branch"]["matches_declared"] is None
    with test_session_factory() as session:
        instrument = session.get(FDRInstrument, instrument_id)
        checks = list(
            session.scalars(
                select(VerificationCheck).where(
                    VerificationCheck.instrument_id == instrument_id,
                    VerificationCheck.rule_code == "DOCUMENT_FIELD_MISMATCH",
                )
            )
        )
        assert instrument.reference_original == "DOC-REF-42"
        assert instrument.amount == 12500
        assert instrument.verification_status == VerificationStatus.DISCREPANCY_FLAGGED
        assert len(checks) == 3
        assert all("does not establish error or fraud" in check.explanation for check in checks)


def test_missing_candidates_are_unknown_and_scanned_pdf_reports_ocr_required(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path)
    _, instrument_id, _ = _setup_identity(test_session_factory)
    headers = _login(auth_client, "document-user@documents.invalid")
    no_fields = _create_pdf("Synthetic supporting document with no labeled candidate data included.")
    response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={"file": ("support.pdf", no_fields, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    field_rows = response.json()["fields"]
    assert all(field["value_status"] == "missing" for field in field_rows)
    assert all(field["matches_declared"] is None for field in field_rows)

    scanned = _create_pdf(None)
    scanned_response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={"file": ("scanned.pdf", scanned, "application/pdf")},
        headers=headers,
    )
    assert scanned_response.status_code == 201, scanned_response.text
    scanned_payload = scanned_response.json()
    assert scanned_payload["extraction_status"] == "ocr_required"
    assert "OCR is required" in scanned_payload["extraction_error"]
    assert all(field["value_status"] == "missing" for field in scanned_payload["fields"])


def test_file_validation_rejects_unsupported_malformed_and_oversized_uploads(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path, max_bytes=128)
    _, instrument_id, _ = _setup_identity(test_session_factory)
    headers = _login(auth_client, "document-user@documents.invalid")
    route = f"/api/v1/fdrs/{instrument_id}/documents"

    unsupported = auth_client.post(route, files={"file": ("evidence.txt", b"not evidence", "text/plain")}, headers=headers)
    malformed = auth_client.post(route, files={"file": ("evidence.pdf", b"%PDF-not-a-real-pdf", "application/pdf")}, headers=headers)
    oversized = auth_client.post(route, files={"file": ("large.pdf", b"x" * 300, "application/pdf")}, headers=headers)
    assert unsupported.status_code == 415
    assert malformed.status_code == 400
    assert oversized.status_code == 413
    assert unsupported.json()["error"]["code"] == "unsupported_document_type"


def test_authorized_download_and_cross_institution_denial(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path)
    _, instrument_id, other_institution_id = _setup_identity(test_session_factory, other_institution=True)
    owner_headers = _login(auth_client, "document-user@documents.invalid")
    content = _create_pdf("Synthetic download test evidence with no personal or bank data.")
    uploaded = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={"file": ("synthetic.pdf", content, "application/pdf")},
        headers=owner_headers,
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]

    auditor_headers = _login(auth_client, "document-auditor@documents.invalid")
    download = auth_client.get(f"/api/v1/documents/{document_id}/download", headers=auditor_headers)
    assert download.status_code == 200
    assert download.content == content

    with test_session_factory() as session:
        other_user = User(
            institution_id=other_institution_id,
            full_name="Synthetic Other User",
            email="other-user-docs@documents.invalid",
            password_hash=hash_password(PASSWORD),
            role=Role.INSTITUTION_USER,
        )
        session.add(other_user)
        session.commit()
    other_headers = _login(auth_client, "other-document-user@documents.invalid")
    denied = auth_client.get(f"/api/v1/documents/{document_id}/download", headers=other_headers)
    assert denied.status_code == 404
    with test_session_factory() as session:
        download_audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == document_id,
                AuditEvent.action == "document_downloaded",
            )
        )
        assert download_audit is not None
        assert "content" not in download_audit.context


def test_image_upload_is_preserved_and_reports_ocr_unavailable(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path)
    _, instrument_id, _ = _setup_identity(test_session_factory)
    headers = _login(auth_client, "document-user@documents.invalid")
    buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    result = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={"file": ("synthetic.png", buffer.getvalue(), "image/png")},
        headers=headers,
    )
    assert result.status_code == 201, result.text
    assert result.json()["extraction_status"] == "ocr_required"
    assert result.json()["extraction_method"] == "ocr_unavailable"
    assert result.json()["content_type"] == "image/png"
    with test_session_factory() as session:
        assert session.scalar(select(ExtractedDocumentField).where(
            ExtractedDocumentField.document_id == result.json()["id"],
            ExtractedDocumentField.value_status == "missing",
        )) is not None


def test_scrutiny_officer_reviews_mismatch_and_review_is_audited(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path)
    _, instrument_id, _ = _setup_identity(test_session_factory)
    owner_headers = _login(auth_client, "document-user@documents.invalid")
    upload = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={
            "file": (
                "synthetic-mismatch.pdf",
                _create_pdf("FDR Number: DIFFERENT-REF\nAmount: 12,500.00"),
                "application/pdf",
            )
        },
        headers=owner_headers,
    )
    document_id = upload.json()["id"]
    forbidden = auth_client.post(
        f"/api/v1/documents/{document_id}/fields/reference_number/review",
        json={"decision": "dismiss_discrepancy", "comment": "Unauthorized test user."},
        headers=owner_headers,
    )
    assert forbidden.status_code == 403

    officer_headers = _login(auth_client, "document-officer@documents.invalid")
    reviewed = auth_client.post(
        f"/api/v1/documents/{document_id}/fields/reference_number/review",
        json={"decision": "dismiss_discrepancy", "comment": "Synthetic fixture label was malformed."},
        headers=officer_headers,
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["verification_check_status"] == "dismissed"
    with test_session_factory() as session:
        review_event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "instrument_document",
                AuditEvent.entity_id == document_id,
                AuditEvent.action == "document_field_reviewed",
            )
        )
        assert review_event.actor_user_id is not None
        assert review_event.before_values["verification_check_status"] == "open"
        assert review_event.after_values["verification_check_status"] == "dismissed"
        assert "comment" not in review_event.context


def test_unexpected_extraction_failure_keeps_original_and_records_failed_state(
    auth_client, test_session_factory, monkeypatch, tmp_path
):
    _configure_storage(monkeypatch, tmp_path)
    _, instrument_id, _ = _setup_identity(test_session_factory)
    headers = _login(auth_client, "document-user@documents.invalid")
    original = _create_pdf("Synthetic evidence retained after injected extraction failure.")

    def fail_extraction(*args, **kwargs):
        raise RuntimeError("Synthetic parser crash")

    monkeypatch.setattr("app.services.document_service.extract_document", fail_extraction)
    response = auth_client.post(
        f"/api/v1/fdrs/{instrument_id}/documents",
        files={"file": ("preserve-this.pdf", original, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["extraction_status"] == "failed"
    assert payload["extraction_method"] == "processing_error"
    assert "original file was preserved" in payload["extraction_error"]
    with test_session_factory() as session:
        row = session.get(InstrumentDocument, payload["id"])
        saved_file = tmp_path / "private-documents" / row.storage_key
        assert saved_file.read_bytes() == original
        actions = set(session.scalars(
            select(AuditEvent.action).where(
                AuditEvent.entity_type == "instrument_document",
                AuditEvent.entity_id == row.id,
            )
        ))
        assert actions == {"document_uploaded", "document_extraction_failed"}


def test_tesseract_provider_uses_stdin_without_temp_files(monkeypatch, tmp_path):
    from app.services.extraction_service import TesseractCLIProvider
    from types import SimpleNamespace

    image_path = tmp_path / "synthetic.png"
    from PIL import Image
    Image.new("RGB", (40, 20), "white").save(image_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"FDR Number: DEMO-123\nAmount: 1000.00", stderr=b"")

    monkeypatch.setattr("app.services.extraction_service.shutil.which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr("app.services.extraction_service.subprocess.run", fake_run)
    text = TesseractCLIProvider().extract_text(image_path)
    assert "DEMO-123" in text
    assert calls[0][0][:3] == ["/usr/bin/tesseract", "stdin", "stdout"]
    assert isinstance(calls[0][1]["input"], bytes)
    assert calls[0][1]["timeout"] > 0
