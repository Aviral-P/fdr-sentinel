"""Explicit FDR lifecycle transitions and their audit/history records."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    DataOrigin,
    FDRInstrument,
    InstrumentLifecycleStatus as Status,
    ReleaseApprovalDecision,
    ReplacementType,
    Role,
    User,
    WorkflowEvent,
    WorkflowEventType as EventType,
    VerificationStatus,
)
from app.schemas.api import FinalDecisionRequest, ScrutinyRequest, SuccessorInstrumentCreateRequest
from app.services.audit_service import record_audit_event, record_workflow_event
from app.services.fdr_service import get_instrument


def _require_role(user: User, role: Role) -> None:
    if user.role != role:
        raise AppError(403, "forbidden", f"This action requires the {role.value} role.")


def _require_institution_user(user: User, instrument: FDRInstrument) -> None:
    if user.role != Role.INSTITUTION_USER or user.institution_id != instrument.institution_id:
        raise AppError(404, "not_found", "FDR instrument not found.")


def _transition_error(current: Status, action: str) -> AppError:
    return AppError(
        409,
        "invalid_transition",
        f"Cannot {action} an FDR instrument while it is in '{current.value}' status.",
        {"current_status": current.value, "action": action},
    )


def submit_instrument(session: Session, user: User, instrument_id: str) -> FDRInstrument:
    instrument = get_instrument(session, user, instrument_id)
    _require_institution_user(user, instrument)
    if instrument.lifecycle_status not in {Status.DRAFT, Status.CLARIFICATION_REQUIRED}:
        raise _transition_error(instrument.lifecycle_status, "submit")
    previous = instrument.lifecycle_status
    instrument.lifecycle_status = Status.SUBMITTED
    record_workflow_event(
        session,
        instrument_id=instrument.id,
        actor_user_id=user.id,
        event_type=EventType.SUBMITTED,
        from_status=previous,
        to_status=instrument.lifecycle_status,
        comment="Instrument submitted for scrutiny.",
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="fdr_instrument",
        entity_id=instrument.id,
        action="fdr_submitted",
        before_values={"lifecycle_status": previous},
        after_values={"lifecycle_status": instrument.lifecycle_status},
    )
    session.commit()
    session.refresh(instrument)
    return instrument


def record_scrutiny(
    session: Session,
    user: User,
    instrument_id: str,
    payload: ScrutinyRequest,
) -> tuple[FDRInstrument, WorkflowEvent]:
    _require_role(user, Role.SCRUTINY_OFFICER)
    instrument = get_instrument(session, user, instrument_id)
    if instrument.lifecycle_status not in {Status.SUBMITTED, Status.UNDER_SCRUTINY}:
        raise _transition_error(instrument.lifecycle_status, "record scrutiny")
    previous = instrument.lifecycle_status
    if payload.outcome == "request_clarification":
        instrument.lifecycle_status = Status.CLARIFICATION_REQUIRED
        event_type = EventType.CLARIFICATION_REQUESTED
        comment = payload.clarification_question.strip()
        metadata = {"officer_comment": payload.comment, "outcome": payload.outcome}
        audit_action = "clarification_requested"
    else:
        instrument.lifecycle_status = Status.UNDER_SCRUTINY
        event_type = EventType.SCRUTINY_RECOMMENDATION
        comment = payload.comment
        metadata = {"recommendation": payload.outcome}
        audit_action = "scrutiny_recommendation_recorded"
    workflow_event = record_workflow_event(
        session,
        instrument_id=instrument.id,
        actor_user_id=user.id,
        event_type=event_type,
        from_status=previous,
        to_status=instrument.lifecycle_status,
        comment=comment,
        event_metadata=metadata,
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="fdr_instrument",
        entity_id=instrument.id,
        action=audit_action,
        before_values={"lifecycle_status": previous},
        after_values={
            "lifecycle_status": instrument.lifecycle_status,
            "workflow_event_id": workflow_event.id,
            "outcome": payload.outcome,
        },
    )
    session.commit()
    session.refresh(instrument)
    return instrument, workflow_event


def respond_to_clarification(
    session: Session,
    user: User,
    instrument_id: str,
    clarification_event_id: str,
    response: str,
) -> FDRInstrument:
    instrument = get_instrument(session, user, instrument_id)
    _require_institution_user(user, instrument)
    if instrument.lifecycle_status != Status.CLARIFICATION_REQUIRED:
        raise _transition_error(instrument.lifecycle_status, "respond to clarification")
    request_event = session.get(WorkflowEvent, clarification_event_id)
    if (
        request_event is None
        or request_event.instrument_id != instrument.id
        or request_event.event_type != EventType.CLARIFICATION_REQUESTED
    ):
        raise AppError(404, "not_found", "Clarification request not found.")
    already_responded = session.scalar(
        select(WorkflowEvent.id).where(WorkflowEvent.related_event_id == request_event.id)
    )
    if already_responded is not None:
        raise AppError(409, "clarification_already_answered", "This clarification has already been answered.")
    previous = instrument.lifecycle_status
    instrument.lifecycle_status = Status.SUBMITTED
    workflow_event = record_workflow_event(
        session,
        instrument_id=instrument.id,
        actor_user_id=user.id,
        event_type=EventType.CLARIFICATION_RESPONDED,
        from_status=previous,
        to_status=instrument.lifecycle_status,
        comment=response.strip(),
        related_event_id=request_event.id,
        event_metadata={"response_length": len(response.strip())},
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="fdr_instrument",
        entity_id=instrument.id,
        action="clarification_responded",
        before_values={"lifecycle_status": previous},
        after_values={
            "lifecycle_status": instrument.lifecycle_status,
            "workflow_event_id": workflow_event.id,
            "response_length": len(response.strip()),
        },
        context={"clarification_event_id": request_event.id},
    )
    session.commit()
    session.refresh(instrument)
    return instrument


def record_final_decision(
    session: Session,
    user: User,
    instrument_id: str,
    payload: FinalDecisionRequest,
) -> FDRInstrument:
    _require_role(user, Role.APPROVING_AUTHORITY)
    instrument = get_instrument(session, user, instrument_id)
    if instrument.lifecycle_status != Status.UNDER_SCRUTINY:
        raise _transition_error(instrument.lifecycle_status, "record a final decision")
    recommendation = session.scalar(
        select(WorkflowEvent)
        .where(
            WorkflowEvent.instrument_id == instrument.id,
            WorkflowEvent.event_type == EventType.SCRUTINY_RECOMMENDATION,
        )
        .order_by(WorkflowEvent.created_at.desc())
    )
    if recommendation is None:
        raise AppError(409, "scrutiny_required", "A scrutiny recommendation is required before the final decision.")
    previous = instrument.lifecycle_status
    instrument.lifecycle_status = Status.APPROVED if payload.decision == "approved" else Status.REJECTED
    workflow_event = record_workflow_event(
        session,
        instrument_id=instrument.id,
        actor_user_id=user.id,
        event_type=EventType.FINAL_DECISION,
        from_status=previous,
        to_status=instrument.lifecycle_status,
        comment=payload.rationale,
        event_metadata={"decision": payload.decision, "recommendation_event_id": recommendation.id},
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=instrument.institution_id,
        entity_type="fdr_instrument",
        entity_id=instrument.id,
        action="fdr_final_decision_recorded",
        before_values={"lifecycle_status": previous},
        after_values={"lifecycle_status": instrument.lifecycle_status, "workflow_event_id": workflow_event.id},
        context={"decision": payload.decision},
    )
    if instrument.lifecycle_status == Status.APPROVED and instrument.supersedes is not None:
        predecessor = instrument.supersedes
        predecessor_before = predecessor.lifecycle_status
        predecessor.lifecycle_status = Status.SUPERSEDED
        record_workflow_event(
            session,
            instrument_id=predecessor.id,
            actor_user_id=user.id,
            event_type=EventType.FINAL_DECISION,
            from_status=predecessor_before,
            to_status=predecessor.lifecycle_status,
            comment="Superseded by an approved renewal/replacement.",
            event_metadata={"successor_instrument_id": instrument.id},
        )
        record_audit_event(
            session,
            actor_user_id=user.id,
            institution_id=predecessor.institution_id,
            entity_type="fdr_instrument",
            entity_id=predecessor.id,
            action="fdr_superseded_by_successor",
            before_values={"lifecycle_status": predecessor_before},
            after_values={"lifecycle_status": predecessor.lifecycle_status, "successor_id": instrument.id},
        )
    session.commit()
    session.refresh(instrument)
    return instrument


def create_successor(
    session: Session,
    user: User,
    instrument_id: str,
    payload: SuccessorInstrumentCreateRequest,
) -> FDRInstrument:
    previous = get_instrument(session, user, instrument_id)
    _require_institution_user(user, previous)
    if previous.lifecycle_status not in {Status.APPROVED, Status.MATURED}:
        raise _transition_error(previous.lifecycle_status, "renew or replace")
    if previous.successor is not None:
        raise AppError(409, "successor_exists", "This instrument already has a renewal or replacement.")
    if payload.obligation_id:
        from app.models import RegulatoryObligation

        obligation = session.get(RegulatoryObligation, payload.obligation_id)
        if obligation is None or obligation.institution_id not in (None, previous.institution_id):
            raise AppError(404, "not_found", "Regulatory obligation not found.")
    successor = FDRInstrument(
        institution_id=previous.institution_id,
        obligation_id=payload.obligation_id or previous.obligation_id,
        submitted_by_user_id=user.id,
        supersedes_instrument_id=previous.id,
        replacement_type=payload.replacement_type,
        issuer_name=payload.issuer_name,
        beneficiary=payload.beneficiary,
        reference_original=payload.reference_original,
        amount=payload.amount,
        issue_date=payload.issue_date,
        maturity_date=payload.maturity_date,
        lifecycle_status=Status.DRAFT,
        verification_status=VerificationStatus.NOT_CHECKED,
        notes=payload.notes,
        data_origin=DataOrigin.USER_SUBMITTED,
    )
    session.add(successor)
    session.flush()
    event = record_workflow_event(
        session,
        instrument_id=successor.id,
        actor_user_id=user.id,
        event_type=EventType.SUCCESSOR_CREATED,
        from_status=None,
        to_status=successor.lifecycle_status,
        comment=f"{payload.replacement_type.value.title()} draft created.",
        event_metadata={"predecessor_instrument_id": previous.id},
    )
    record_workflow_event(
        session,
        instrument_id=previous.id,
        actor_user_id=user.id,
        event_type=EventType.SUCCESSOR_CREATED,
        from_status=previous.lifecycle_status,
        to_status=previous.lifecycle_status,
        comment="Renewal/replacement draft linked.",
        event_metadata={"successor_instrument_id": successor.id, "replacement_type": payload.replacement_type.value},
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=successor.institution_id,
        entity_type="fdr_instrument",
        entity_id=successor.id,
        action="fdr_successor_created",
        after_values={
            "lifecycle_status": successor.lifecycle_status,
            "supersedes_instrument_id": previous.id,
            "replacement_type": payload.replacement_type,
            "workflow_event_id": event.id,
        },
    )
    record_audit_event(
        session,
        actor_user_id=user.id,
        institution_id=previous.institution_id,
        entity_type="fdr_instrument",
        entity_id=previous.id,
        action="fdr_successor_linked",
        before_values={"successor_id": None},
        after_values={"successor_id": successor.id},
    )
    session.commit()
    session.refresh(successor)
    return successor
