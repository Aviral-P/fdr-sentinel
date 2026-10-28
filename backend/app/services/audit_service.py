"""Safe audit and append-only workflow event helpers."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent, DataOrigin, WorkflowEvent, WorkflowEventType
from app.models.entities import utcnow
from app.models.enums import InstrumentLifecycleStatus


def _safe_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        redacted_names = {"password", "password_hash", "token", "access_token", "secret", "content", "binary"}
        return {
            str(key): "[redacted]" if any(term in str(key).lower() for term in redacted_names)
            else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:1000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:1000]


def record_audit_event(
    session: Session,
    *,
    actor_user_id: str | None,
    institution_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before_values: dict[str, Any] | None = None,
    after_values: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        institution_id=institution_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_values=_safe_value(before_values) if before_values is not None else None,
        after_values=_safe_value(after_values) if after_values is not None else None,
        context=_safe_value(context or {}),
        data_origin=DataOrigin.SYSTEM_GENERATED,
        created_at=utcnow(),
    )
    session.add(event)
    return event


def record_workflow_event(
    session: Session,
    *,
    instrument_id: str,
    actor_user_id: str | None,
    event_type: WorkflowEventType,
    from_status: InstrumentLifecycleStatus | None,
    to_status: InstrumentLifecycleStatus | None,
    comment: str | None = None,
    related_event_id: str | None = None,
    event_metadata: dict[str, Any] | None = None,
) -> WorkflowEvent:
    workflow_event = WorkflowEvent(
        instrument_id=instrument_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        comment=comment,
        related_event_id=related_event_id,
        event_metadata=_safe_value(event_metadata or {}),
        created_at=utcnow(),
    )
    session.add(workflow_event)
    session.flush()
    return workflow_event
