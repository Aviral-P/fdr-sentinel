"""SQLAlchemy declarative base for application models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def prevent_audit_event_mutation(mapper, connection, target) -> None:
    """Reject updates and deletes of audit records through the ORM."""
    del mapper, connection, target
    raise ValueError("Audit events are append-only and cannot be changed or deleted.")
