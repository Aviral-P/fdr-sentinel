"""Application SQLAlchemy models and enum definitions."""

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.base import Base, prevent_audit_event_mutation
from app.models.entities import (
    AuthSession,
    AuditEvent,
    ExtractedDocumentField,
    FDRInstrument,
    Institution,
    IntegrityFinding,
    InstrumentDocument,
    Notification,
    RegulatoryObligation,
    RegulatoryRule,
    ReleaseApproval,
    ReleaseRequest,
    User,
    VerificationCheck,
    VerificationEvent,
    WorkflowEvent,
)
from app.models.enums import (
    DataOrigin,
    IntegrityFindingSeverity,
    IntegrityFindingType,
    IntegrityReviewStatus,
    InstrumentLifecycleStatus,
    OperationalPriority,
    ObligationStatus,
    ReleaseApprovalDecision,
    ReleaseRequestStatus,
    ReplacementType,
    Role,
    VerificationCheckStatus,
    VerificationStatus,
    WorkflowEventType,
)

event.listen(AuditEvent, "before_update", prevent_audit_event_mutation)
event.listen(AuditEvent, "before_delete", prevent_audit_event_mutation)
event.listen(WorkflowEvent, "before_update", prevent_audit_event_mutation)
event.listen(WorkflowEvent, "before_delete", prevent_audit_event_mutation)


@event.listens_for(Session, "before_flush")
def prevent_audit_event_flush_mutation(session, flush_context, instances) -> None:
    """Also protect audit rows through normal unit-of-work flushes."""
    del flush_context, instances
    if any(isinstance(row, (AuditEvent, WorkflowEvent)) for row in session.dirty | session.deleted):
        raise ValueError("Audit and workflow history events are append-only.")

__all__ = [
    "AuthSession",
    "AuditEvent",
    "Base",
    "DataOrigin",
    "ExtractedDocumentField",
    "FDRInstrument",
    "Institution",
    "IntegrityFinding",
    "IntegrityFindingSeverity",
    "IntegrityFindingType",
    "IntegrityReviewStatus",
    "InstrumentDocument",
    "InstrumentLifecycleStatus",
    "Notification",
    "ObligationStatus",
    "OperationalPriority",
    "RegulatoryObligation",
    "RegulatoryRule",
    "ReleaseApproval",
    "ReleaseApprovalDecision",
    "ReleaseRequest",
    "ReleaseRequestStatus",
    "ReplacementType",
    "Role",
    "User",
    "VerificationCheck",
    "VerificationCheckStatus",
    "VerificationEvent",
    "VerificationStatus",
    "WorkflowEvent",
    "WorkflowEventType",
]
