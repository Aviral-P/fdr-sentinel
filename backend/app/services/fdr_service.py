"""Institution-scoped FDR record services."""

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AuditEvent,
    DataOrigin,
    FDRInstrument,
    Institution,
    InstrumentDocument,
    InstrumentLifecycleStatus,
    RegulatoryObligation,
    Role,
    User,
    VerificationStatus,
    WorkflowEvent,
    WorkflowEventType,
)
from app.schemas.api import FDRInstrumentCreateRequest, FDRInstrumentUpdateRequest
from app.services.audit_service import record_audit_event, record_workflow_event


READ_ROLES = {
    Role.INSTITUTION_USER,
    Role.SCRUTINY_OFFICER,
    Role.APPROVING_AUTHORITY,
    Role.AUDITOR,
    Role.ADMIN,
}


def create_instrument(session: Session, user: User, payload: FDRInstrumentCreateRequest) -> FDRInstrument:
    if user.role != Role.INSTITUTION_USER or not user.institution_id:
        raise AppError(403, "forbidden", "Only an institution user can create an FDR for their institution.")
    if payload.institution_id != user.institution_id:
        raise AppError(404, "not_found", "Institution not found.")
    institution = session.get(Institution, user.institution_id)
    if institution is None or not institution.active:
        raise AppError(404, "not_found", "Institution not found.")
    if payload.obligation_id:
        obligation = session.get(RegulatoryObligation, payload.obligation_id)
        if obligation is None or obligation.institution_id not in (None, user.institution_id):
            raise AppError(404, "not_found", "Regulatory obligation not found.")

    instrument = FDRInstrument(
        institution_id=user.institution_id,
        obligation_id=payload.obligation_id,
        submitted_by_user_id=user.id,
        issuer_name=payload.issuer_name,
        beneficiary=payload.beneficiary,
        reference_original=payload.reference_original,
        amount=payload.amount,
        issue_date=payload.issue_date,
        maturity_date=payload.maturity_date,
        lifecycle_status=InstrumentLifecycleStatus.DRAFT,
        verification_status=VerificationStatus.NOT_CHECKED,
        notes=payload.notes,
        data_origin=DataOrigin.USER_SUBMITTED,
    )
    session.add(instrument)
    session.flush()
    record_workflow_event(
        session,
        instrument_id=instrument.id,
        actor_user_id=user.id,
        event_type=WorkflowEventType.CREATED,
        from_status=None,
        to_status=instrument.lifecycle_status,
        comment="Draft created.",
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="fdr_instrument",
        entity_id=instrument.id,
        action="fdr_created",
        after_values={
            "institution_id": instrument.institution_id,
            "obligation_id": instrument.obligation_id,
            "reference_original": instrument.reference_original,
            "reference_normalized": instrument.reference_normalized,
            "beneficiary": instrument.beneficiary,
            "amount": instrument.amount,
            "issue_date": instrument.issue_date,
            "maturity_date": instrument.maturity_date,
            "lifecycle_status": instrument.lifecycle_status,
        },
    )
    session.commit()
    session.refresh(instrument)
    return instrument


def update_instrument(
    session: Session, user: User, instrument_id: str, payload: FDRInstrumentUpdateRequest
) -> FDRInstrument:
    """Update only institution-submitted fields while a record is editable."""
    instrument = get_instrument(session, user, instrument_id)
    if user.role != Role.INSTITUTION_USER or user.institution_id != instrument.institution_id:
        raise AppError(404, "not_found", "FDR instrument not found.")
    if instrument.lifecycle_status not in {
        InstrumentLifecycleStatus.DRAFT,
        InstrumentLifecycleStatus.CLARIFICATION_REQUIRED,
    }:
        raise AppError(
            409,
            "instrument_not_editable",
            "Only draft instruments or instruments awaiting clarification can be updated.",
            {"current_status": instrument.lifecycle_status.value},
        )

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise AppError(422, "invalid_update", "At least one permitted field must be supplied.")
    required_values = {"issuer_name", "reference_original", "amount", "issue_date", "maturity_date"}
    if any(field in updates and updates[field] is None for field in required_values):
        raise AppError(422, "invalid_update", "Required instrument fields cannot be cleared.")
    if "reference_original" in updates and not updates["reference_original"].strip():
        raise AppError(422, "invalid_update", "reference_original cannot be blank.")
    if "obligation_id" in updates and updates["obligation_id"] is not None:
        obligation = session.get(RegulatoryObligation, updates["obligation_id"])
        if obligation is None or obligation.institution_id not in (None, instrument.institution_id):
            raise AppError(404, "not_found", "Regulatory obligation not found.")

    new_issue_date = updates.get("issue_date", instrument.issue_date)
    new_maturity_date = updates.get("maturity_date", instrument.maturity_date)
    if new_maturity_date < new_issue_date:
        raise AppError(422, "invalid_dates", "maturity_date cannot precede issue_date.")

    allowed_audit_fields = {
        "obligation_id", "issuer_name", "beneficiary", "reference_original", "amount",
        "issue_date", "maturity_date", "notes",
    }
    before_values = {}
    after_values = {}
    for field, value in updates.items():
        previous = getattr(instrument, field)
        if previous != value:
            setattr(instrument, field, value)
            if field in allowed_audit_fields:
                current_value = getattr(instrument, field)
                if field == "notes":
                    # Notes are free text: keep a useful change summary without
                    # copying possible secrets or pasted document text into audit.
                    before_values[field] = {"present": bool(previous)}
                    after_values[field] = {"present": bool(current_value)}
                else:
                    before_values[field] = previous
                    after_values[field] = current_value

    if before_values:
        record_audit_event(
            session,
            actor_user_id=user.id,
            institution_id=instrument.institution_id,
            entity_type="fdr_instrument",
            entity_id=instrument.id,
            action="fdr_draft_updated",
            before_values=before_values,
            after_values=after_values,
            context={"lifecycle_status": instrument.lifecycle_status.value},
        )
    session.commit()
    session.refresh(instrument)
    return instrument


def list_instruments(
    session: Session,
    user: User,
    *,
    institution_id: str | None,
    search: str | None,
    lifecycle_status: InstrumentLifecycleStatus | None,
    verification_status: VerificationStatus | None,
    maturity_before: date | None,
    limit: int,
    offset: int,
) -> tuple[list[FDRInstrument], int]:
    if user.role not in READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view FDR records.")
    statement = select(FDRInstrument)
    count_statement = select(func.count(FDRInstrument.id))
    conditions = []
    if user.role == Role.INSTITUTION_USER:
        if not user.institution_id:
            return [], 0
        conditions.append(FDRInstrument.institution_id == user.institution_id)
        if institution_id:
            # Honor the requested filter while keeping it intersected with the
            # authenticated user's tenant scope.
            conditions.append(FDRInstrument.institution_id == institution_id)
    elif institution_id:
        conditions.append(FDRInstrument.institution_id == institution_id)
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                FDRInstrument.reference_original.ilike(pattern),
                FDRInstrument.reference_normalized.ilike(pattern),
                FDRInstrument.issuer_name.ilike(pattern),
            )
        )
    if lifecycle_status:
        conditions.append(FDRInstrument.lifecycle_status == lifecycle_status)
    if verification_status:
        conditions.append(FDRInstrument.verification_status == verification_status)
    if maturity_before:
        conditions.append(FDRInstrument.maturity_date <= maturity_before)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    total = session.scalar(count_statement) or 0
    items = list(
        session.scalars(
            statement.order_by(FDRInstrument.updated_at.desc(), FDRInstrument.id).limit(limit).offset(offset)
        )
    )
    return items, total


def get_instrument(session: Session, user: User, instrument_id: str) -> FDRInstrument:
    if user.role not in READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view FDR records.")
    statement = select(FDRInstrument).where(FDRInstrument.id == instrument_id)
    if user.role == Role.INSTITUTION_USER:
        if not user.institution_id:
            raise AppError(404, "not_found", "FDR instrument not found.")
        statement = statement.where(FDRInstrument.institution_id == user.institution_id)
    instrument = session.scalar(statement)
    if instrument is None:
        raise AppError(404, "not_found", "FDR instrument not found.")
    return instrument


def get_instrument_history(session: Session, user: User, instrument_id: str) -> list[dict]:
    instrument = get_instrument(session, user, instrument_id)
    workflow_events = session.scalars(
        select(WorkflowEvent).where(WorkflowEvent.instrument_id == instrument.id)
    ).all()
    audit_events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == "fdr_instrument", AuditEvent.entity_id == instrument.id)
    ).all()
    document_ids = list(
        session.scalars(select(InstrumentDocument.id).where(InstrumentDocument.instrument_id == instrument.id))
    )
    document_audit_events = session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "instrument_document",
            AuditEvent.entity_id.in_(document_ids),
        )
    ).all()
    items = [
        {
            "id": event.id,
            "source": "workflow",
            "occurred_at": event.created_at,
            "actor_user_id": event.actor_user_id,
            "action": event.event_type.value,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "summary": event.comment,
            "related_event_id": event.related_event_id,
            "change_summary": event.event_metadata,
        }
        for event in workflow_events
    ]
    items.extend(
        {
            "id": event.id,
            "source": "audit",
            "occurred_at": event.created_at,
            "actor_user_id": event.actor_user_id,
            "action": event.action,
            "change_summary": {
                "before": event.before_values,
                "after": event.after_values,
                "context": event.context,
            },
        }
        for event in audit_events
    )
    items.extend(
        {
            "id": event.id,
            "source": "audit",
            "occurred_at": event.created_at,
            "actor_user_id": event.actor_user_id,
            "action": event.action,
            "change_summary": {
                "before": event.before_values,
                "after": event.after_values,
                "context": event.context,
            },
        }
        for event in document_audit_events
    )
    return sorted(items, key=lambda item: (item["occurred_at"], item["id"]))
