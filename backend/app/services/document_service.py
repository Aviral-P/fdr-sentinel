"""Authorized document management services."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.config import get_settings
from app.models import (
    AuditEvent,
    DataOrigin,
    FDRInstrument,
    InstrumentDocument,
    Role,
    User,
    VerificationCheck,
    VerificationCheckStatus,
    VerificationEvent,
    VerificationStatus,
)
from app.services.audit_service import record_audit_event
from app.services.extraction_service import TesseractCLIProvider, extract_document
from app.services.fdr_service import get_instrument
from app.services.storage_service import resolve_private_document, store_private_document, validate_document


def upload_instrument_document(
    session: Session,
    user: User,
    instrument_id: str,
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> InstrumentDocument:
    instrument = get_instrument(session, user, instrument_id)
    if user.role != Role.INSTITUTION_USER or user.institution_id != instrument.institution_id:
        raise AppError(403, "forbidden", "Only the owning institution user may upload instrument evidence.")

    metadata = validate_document(filename, content_type, content)
    storage_key, file_path = store_private_document(content, metadata.extension)
    try:
        verification_before = instrument.verification_status
        document = InstrumentDocument(
            instrument_id=instrument.id,
            uploaded_by_user_id=user.id,
            original_filename=metadata.display_filename,
            storage_key=storage_key,
            content_type=metadata.content_type,
            size_bytes=metadata.size_bytes,
            sha256_checksum=metadata.sha256_checksum,
            extraction_status="processing",
            data_origin=DataOrigin.USER_SUBMITTED,
        )
        session.add(document)
        session.flush()

        record_audit_event(
            session,
            actor_user_id=user.id,
            institution_id=instrument.institution_id,
            entity_type="instrument_document",
            entity_id=document.id,
            action="document_uploaded",
            after_values={
                "instrument_id": instrument.id,
                "original_filename": metadata.display_filename,
                "content_type": metadata.content_type,
                "size_bytes": metadata.size_bytes,
                "sha256_checksum": metadata.sha256_checksum,
            },
        )
        try:
            # Keep extraction writes isolated. A parser failure should preserve
            # the upload record and original bytes with an honest failed state.
            with session.begin_nested():
                ocr_provider = TesseractCLIProvider() if get_settings().local_ocr_enabled else None
                result = extract_document(session, document, file_path, ocr_provider=ocr_provider)
            extraction_action = "document_extraction_completed"
            extraction_values = {
                "status": result["status"],
                "method": result["method"],
                "found_fields": result["found_fields"],
                "missing_fields": result["missing_fields"],
                "mismatch_count": result["mismatch_count"],
                "mismatch_fields": result["mismatch_fields"],
            }
        except Exception:
            document.extracted_text = None
            document.extraction_status = "failed"
            document.extraction_method = "processing_error"
            document.extraction_error = "Document processing failed unexpectedly. The original file was preserved."
            result = {
                "status": document.extraction_status,
                "method": document.extraction_method,
                "found_fields": 0,
                "missing_fields": 0,
                "mismatch_count": 0,
                "mismatch_fields": [],
            }
            extraction_action = "document_extraction_failed"
            extraction_values = {
                "status": result["status"],
                "method": result["method"],
                "error": document.extraction_error,
            }
        record_audit_event(
            session,
            actor_user_id=user.id,
            institution_id=instrument.institution_id,
            entity_type="instrument_document",
            entity_id=document.id,
            action=extraction_action,
            after_values=extraction_values,
        )
        if instrument.verification_status != verification_before:
            record_audit_event(
                session,
                actor_user_id=user.id,
                institution_id=instrument.institution_id,
                entity_type="fdr_instrument",
                entity_id=instrument.id,
                action="document_discrepancy_flagged",
                before_values={"verification_status": verification_before},
                after_values={
                    "verification_status": instrument.verification_status,
                    "document_id": document.id,
                    "finding_codes": [
                        "DOCUMENT_FIELD_MISMATCH"
                    ] if result["mismatch_count"] else [],
                },
                context={"mismatch_fields": result["mismatch_fields"]},
            )
        session.commit()
        session.refresh(document)
        return document
    except Exception:
        session.rollback()
        # Uploaded bytes are immutable evidence. A persistence failure may
        # leave an orphan for local operator cleanup, but never erases the file.
        raise


def list_instrument_documents(session: Session, user: User, instrument_id: str) -> list[InstrumentDocument]:
    instrument = get_instrument(session, user, instrument_id)
    return list(
        session.scalars(
            select(InstrumentDocument)
            .where(InstrumentDocument.instrument_id == instrument.id)
            .order_by(InstrumentDocument.created_at, InstrumentDocument.id)
        )
    )


def get_downloadable_document(session: Session, user: User, document_id: str) -> tuple[InstrumentDocument, Path]:
    document = session.get(InstrumentDocument, document_id)
    if document is None:
        raise AppError(404, "not_found", "Document not found.")
    instrument = get_instrument(session, user, document.instrument_id)
    if user.role not in {
        Role.INSTITUTION_USER,
        Role.SCRUTINY_OFFICER,
        Role.APPROVING_AUTHORITY,
        Role.AUDITOR,
        Role.ADMIN,
    }:
        raise AppError(403, "forbidden", "This role cannot download documents.")
    path = resolve_private_document(document.storage_key)
    actual_hash = sha256(path.read_bytes()).hexdigest()
    if actual_hash != document.sha256_checksum:
        raise AppError(409, "document_integrity_error", "The stored document checksum does not match its upload record.")
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="instrument_document",
        entity_id=document.id,
        action="document_downloaded",
        context={"instrument_id": instrument.id, "sha256_checksum": document.sha256_checksum},
    )
    session.commit()
    return document, path


def review_document_field(
    session: Session,
    user: User,
    document_id: str,
    field_name: str,
    *,
    decision: str,
    comment: str,
) -> tuple[InstrumentDocument, VerificationCheck, VerificationEvent]:
    if user.role != Role.SCRUTINY_OFFICER:
        raise AppError(403, "forbidden", "Only a scrutiny officer may review document discrepancies.")
    document = session.get(InstrumentDocument, document_id)
    if document is None:
        raise AppError(404, "not_found", "Document not found.")
    instrument = get_instrument(session, user, document.instrument_id)
    field = next((row for row in document.fields if row.field_name == field_name), None)
    if field is None or field.matches_declared is not False:
        raise AppError(404, "discrepancy_not_found", "No extracted-versus-declared discrepancy exists for that field.")
    checks = list(
        session.scalars(
            select(VerificationCheck).where(
                VerificationCheck.instrument_id == instrument.id,
                VerificationCheck.rule_code == "DOCUMENT_FIELD_MISMATCH",
                VerificationCheck.status == VerificationCheckStatus.OPEN,
            )
        )
    )
    check = next(
        (
            row
            for row in checks
            if row.compared_values.get("document_id") == document.id
            and row.compared_values.get("field_name") == field_name
        ),
        None,
    )
    if check is None:
        raise AppError(409, "discrepancy_already_reviewed", "This discrepancy no longer has an open review finding.")

    previous_status = check.status
    if decision == "confirm_discrepancy":
        check.status = VerificationCheckStatus.REVIEWED
    elif decision == "dismiss_discrepancy":
        check.status = VerificationCheckStatus.DISMISSED
    elif decision != "needs_clarification":
        raise AppError(422, "invalid_review_decision", "The document review decision is not supported.")
    review_event = VerificationEvent(
        check_id=check.id,
        actor_user_id=user.id,
        action=decision,
        comment=comment.strip(),
        event_metadata={"document_id": document.id, "field_name": field_name},
    )
    session.add(review_event)
    if decision == "dismiss_discrepancy" and instrument.verification_status == VerificationStatus.DISCREPANCY_FLAGGED:
        other_open = session.scalar(
            select(VerificationCheck.id).where(
                VerificationCheck.instrument_id == instrument.id,
                VerificationCheck.status == VerificationCheckStatus.OPEN,
                VerificationCheck.id != check.id,
            )
        )
        if other_open is None:
            instrument.verification_status = VerificationStatus.REVIEWED
    session.flush()
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="instrument_document",
        entity_id=document.id,
        action="document_field_reviewed",
        before_values={"field_name": field_name, "verification_check_status": previous_status},
        after_values={
            "field_name": field_name,
            "decision": decision,
            "verification_check_status": check.status,
            "verification_event_id": review_event.id,
        },
        context={"comment_length": len(comment.strip()), "instrument_id": instrument.id},
    )
    session.commit()
    session.refresh(check)
    session.refresh(review_event)
    return document, check, review_event


def get_document_audit_events(session: Session, document_ids: list[str]) -> list[AuditEvent]:
    if not document_ids:
        return []
    return list(
        session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "instrument_document",
                AuditEvent.entity_id.in_(document_ids),
            )
        )
    )
