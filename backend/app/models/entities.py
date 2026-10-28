"""Relational models for the initial FDR Sentinel data layer."""

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.models.enums import (
    DataOrigin,
    IntegrityFindingSeverity,
    IntegrityFindingType,
    IntegrityReviewStatus,
    InstrumentLifecycleStatus,
    ObligationStatus,
    OperationalPriority,
    ReleaseApprovalDecision,
    ReleaseRequestStatus,
    ReplacementType,
    Role,
    VerificationCheckStatus,
    VerificationStatus,
    WorkflowEventType,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


def enum_column(enum_type: type, name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
        create_constraint=True,
    )


def normalize_instrument_reference(value: str) -> str:
    """Normalize references for matching while retaining the entered form."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = (UniqueConstraint("code", name="uq_institutions_code"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.USER_SUBMITTED, nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="institution")
    obligations: Mapped[list["RegulatoryObligation"]] = relationship(back_populates="institution")
    instruments: Mapped[list["FDRInstrument"]] = relationship(back_populates="institution")
    rules: Mapped[list["RegulatoryRule"]] = relationship(back_populates="institution")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(enum_column(Role, "user_role"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.USER_SUBMITTED, nullable=False
    )

    institution: Mapped[Institution | None] = relationship(back_populates="users")
    submitted_instruments: Mapped[list["FDRInstrument"]] = relationship(
        back_populates="submitted_by", foreign_keys="FDRInstrument.submitted_by_user_id"
    )
    auth_sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @validates("email")
    def normalize_email(self, key: str, value: str) -> str:
        del key
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Email cannot be blank.")
        return normalized


class AuthSession(Base):
    """Persisted token session to support explicit logout/revocation."""

    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_expiry", "user_id", "expires_at"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="auth_sessions")


class RegulatoryObligation(TimestampMixin, Base):
    __tablename__ = "regulatory_obligations"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_obligation_institution_code"),
        CheckConstraint("due_date IS NULL OR due_date >= effective_date", name="ck_obligation_date_order"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    required_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[ObligationStatus] = mapped_column(
        enum_column(ObligationStatus, "obligation_status"), default=ObligationStatus.OPEN, nullable=False
    )
    priority: Mapped[OperationalPriority] = mapped_column(
        enum_column(OperationalPriority, "operational_priority"), default=OperationalPriority.NORMAL, nullable=False
    )
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.USER_SUBMITTED, nullable=False
    )

    institution: Mapped[Institution | None] = relationship(back_populates="obligations")
    instruments: Mapped[list["FDRInstrument"]] = relationship(back_populates="obligation")


class FDRInstrument(TimestampMixin, Base):
    __tablename__ = "fdr_instruments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_fdr_amount_positive"),
        CheckConstraint("maturity_date >= issue_date", name="ck_fdr_maturity_after_issue"),
        UniqueConstraint("supersedes_instrument_id", name="uq_fdr_single_successor"),
        Index("ix_fdr_reference_normalized", "reference_normalized"),
        Index("ix_fdr_institution_status", "institution_id", "lifecycle_status"),
        Index("ix_fdr_maturity", "maturity_date"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    obligation_id: Mapped[str | None] = mapped_column(ForeignKey("regulatory_obligations.id", ondelete="SET NULL"), index=True)
    submitted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    supersedes_instrument_id: Mapped[str | None] = mapped_column(
        ForeignKey("fdr_instruments.id", ondelete="RESTRICT"), index=True
    )
    replacement_type: Mapped[ReplacementType | None] = mapped_column(
        enum_column(ReplacementType, "replacement_type")
    )
    issuer_name: Mapped[str] = mapped_column(String(240), nullable=False)
    beneficiary: Mapped[str | None] = mapped_column(String(300))
    reference_original: Mapped[str] = mapped_column(String(120), nullable=False)
    reference_normalized: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    lifecycle_status: Mapped[InstrumentLifecycleStatus] = mapped_column(
        enum_column(InstrumentLifecycleStatus, "instrument_lifecycle_status"),
        default=InstrumentLifecycleStatus.DRAFT,
        nullable=False,
        index=True,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "verification_status"),
        default=VerificationStatus.NOT_CHECKED,
        nullable=False,
        index=True,
    )
    priority: Mapped[OperationalPriority] = mapped_column(
        enum_column(OperationalPriority, "operational_priority"),
        default=OperationalPriority.NORMAL,
        nullable=False,
        index=True,
    )
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.USER_SUBMITTED, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)

    institution: Mapped[Institution] = relationship(back_populates="instruments")
    obligation: Mapped[RegulatoryObligation | None] = relationship(back_populates="instruments")
    submitted_by: Mapped[User | None] = relationship(
        back_populates="submitted_instruments", foreign_keys=[submitted_by_user_id]
    )
    supersedes: Mapped["FDRInstrument | None"] = relationship(
        remote_side="FDRInstrument.id", back_populates="successor", foreign_keys=[supersedes_instrument_id]
    )
    successor: Mapped["FDRInstrument | None"] = relationship(
        back_populates="supersedes", foreign_keys=[supersedes_instrument_id], uselist=False
    )

    @property
    def successor_instrument_id(self) -> str | None:
        return self.successor.id if self.successor is not None else None
    documents: Mapped[list["InstrumentDocument"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )
    verification_checks: Mapped[list["VerificationCheck"]] = relationship(back_populates="instrument")
    release_requests: Mapped[list["ReleaseRequest"]] = relationship(back_populates="instrument")
    workflow_events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan", order_by="WorkflowEvent.created_at"
    )

    @validates("reference_original")
    def update_normalized_reference(self, key: str, value: str) -> str:
        del key
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Instrument reference cannot be blank.")
        self.reference_normalized = normalize_instrument_reference(cleaned)
        if not self.reference_normalized:
            raise ValueError("Instrument reference must contain at least one letter or digit.")
        return cleaned

    @validates("amount")
    def validate_amount(self, key: str, value: Decimal) -> Decimal:
        del key
        amount = Decimal(value)
        if amount <= 0:
            raise ValueError("Instrument amount must be greater than zero.")
        return amount.quantize(Decimal("0.01"))

    @validates("maturity_date")
    def validate_maturity_date(self, key: str, value: date) -> date:
        del key
        issue_date = getattr(self, "issue_date", None)
        if issue_date is not None and value < issue_date:
            raise ValueError("Maturity date cannot precede issue date.")
        return value

    @validates("issue_date")
    def validate_issue_date(self, key: str, value: date) -> date:
        del key
        maturity_date = getattr(self, "maturity_date", None)
        if maturity_date is not None and maturity_date < value:
            raise ValueError("Issue date cannot follow maturity date.")
        return value


class InstrumentDocument(TimestampMixin, Base):
    __tablename__ = "instrument_documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_document_size_positive"),
        UniqueConstraint("storage_key", name="uq_document_storage_key"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("fdr_instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[str] = mapped_column(String(32), default="not_started", nullable=False)
    extraction_method: Mapped[str | None] = mapped_column(String(80))
    extraction_error: Mapped[str | None] = mapped_column(String(500))
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.USER_SUBMITTED, nullable=False
    )

    instrument: Mapped[FDRInstrument] = relationship(back_populates="documents")
    fields: Mapped[list["ExtractedDocumentField"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    @property
    def original_available(self) -> bool:
        """Whether the private original exists (seed metadata may not have a file)."""
        from app.core.config import get_settings

        root = get_settings().resolved_document_storage_dir.resolve()
        path = (root / self.storage_key).resolve()
        return path.parent == root and path.is_file()


class ExtractedDocumentField(TimestampMixin, Base):
    __tablename__ = "extracted_document_fields"
    __table_args__ = (
        Index("ix_extracted_field_document_name", "document_id", "field_name"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_field_confidence_range"),
        CheckConstraint("value_status IN ('unknown', 'found', 'missing')", name="ck_extracted_field_value_status"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("instrument_documents.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extracted_value: Mapped[str | None] = mapped_column(Text)
    declared_value: Mapped[str | None] = mapped_column(Text)
    value_status: Mapped[str] = mapped_column(
        String(16), default="unknown", server_default="unknown", nullable=False
    )
    matches_declared: Mapped[bool | None] = mapped_column(Boolean)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.EXTRACTED, nullable=False
    )

    document: Mapped[InstrumentDocument] = relationship(back_populates="fields")


class VerificationCheck(TimestampMixin, Base):
    __tablename__ = "verification_checks"
    __table_args__ = (
        Index("ix_verification_check_instrument_status", "instrument_id", "status"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("fdr_instruments.id", ondelete="CASCADE"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    compared_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[VerificationCheckStatus] = mapped_column(
        enum_column(VerificationCheckStatus, "verification_check_status"),
        default=VerificationCheckStatus.OPEN,
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.SYSTEM_GENERATED, nullable=False
    )

    instrument: Mapped[FDRInstrument] = relationship(back_populates="verification_checks")
    events: Mapped[list["VerificationEvent"]] = relationship(
        back_populates="check", cascade="all, delete-orphan", order_by="VerificationEvent.created_at"
    )


class VerificationEvent(TimestampMixin, Base):
    __tablename__ = "verification_events"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    check_id: Mapped[str] = mapped_column(
        ForeignKey("verification_checks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    check: Mapped[VerificationCheck] = relationship(back_populates="events")


class IntegrityFinding(Base):
    """Persisted deterministic review finding; never a fraud probability or decision."""

    __tablename__ = "integrity_findings"
    __table_args__ = (
        Index("ix_integrity_finding_institution_status", "institution_id", "review_status"),
        Index("ix_integrity_finding_instrument_type", "instrument_id", "finding_type"),
        CheckConstraint(
            "data_origin IN ('user_submitted', 'extracted', 'system_generated', 'independently_verified', 'synthetic_demo')",
            name="ck_integrity_finding_data_origin",
        ),
        UniqueConstraint("dedupe_key", name="uq_integrity_finding_dedupe_key"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("fdr_instruments.id", ondelete="CASCADE"), nullable=False)
    related_instrument_id: Mapped[str | None] = mapped_column(
        ForeignKey("fdr_instruments.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(ForeignKey("instrument_documents.id", ondelete="SET NULL"), index=True)
    related_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("instrument_documents.id", ondelete="SET NULL"), index=True
    )
    release_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("release_requests.id", ondelete="SET NULL"), index=True
    )
    finding_type: Mapped[IntegrityFindingType] = mapped_column(
        enum_column(IntegrityFindingType, "integrity_finding_type"), nullable=False, index=True
    )
    severity: Mapped[IntegrityFindingSeverity] = mapped_column(
        enum_column(IntegrityFindingSeverity, "integrity_finding_severity"), nullable=False, index=True
    )
    data_origin: Mapped[str] = mapped_column(
        String(22),
        default=DataOrigin.SYSTEM_GENERATED,
        server_default=DataOrigin.SYSTEM_GENERATED.value,
        nullable=False,
    )
    observed_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expected_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    review_status: Mapped[IntegrityReviewStatus] = mapped_column(
        enum_column(IntegrityReviewStatus, "integrity_review_status"), default=IntegrityReviewStatus.OPEN,
        nullable=False, index=True,
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    instrument: Mapped[FDRInstrument] = relationship(foreign_keys=[instrument_id])
    related_instrument: Mapped[FDRInstrument | None] = relationship(foreign_keys=[related_instrument_id])


class ReleaseRequest(TimestampMixin, Base):
    __tablename__ = "release_requests"
    __table_args__ = (
        CheckConstraint("requested_amount > 0", name="ck_release_amount_positive"),
        Index("ix_release_instrument_status", "instrument_id", "status"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("fdr_instruments.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(32), default="not_checked", nullable=False)
    eligibility_findings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[ReleaseRequestStatus] = mapped_column(
        enum_column(ReleaseRequestStatus, "release_request_status"),
        default=ReleaseRequestStatus.PENDING,
        nullable=False,
    )
    prior_instrument_status: Mapped[InstrumentLifecycleStatus | None] = mapped_column(
        enum_column(InstrumentLifecycleStatus, "instrument_lifecycle_status"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    instrument: Mapped[FDRInstrument] = relationship(back_populates="release_requests")
    approvals: Mapped[list["ReleaseApproval"]] = relationship(
        back_populates="release_request", cascade="all, delete-orphan", order_by="ReleaseApproval.created_at"
    )


class ReleaseApproval(TimestampMixin, Base):
    __tablename__ = "release_approvals"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    release_request_id: Mapped[str] = mapped_column(
        ForeignKey("release_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approver_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision: Mapped[ReleaseApprovalDecision] = mapped_column(
        enum_column(ReleaseApprovalDecision, "release_approval_decision"), nullable=False
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    disposition: Mapped[str] = mapped_column(Text, nullable=False)

    release_request: Mapped[ReleaseRequest] = relationship(back_populates="approvals")


class WorkflowEvent(Base):
    """Append-only instrument workflow history; comments are not copied to audit payloads."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint("related_event_id", name="uq_workflow_event_single_response"),
        Index("ix_workflow_instrument_created", "instrument_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("fdr_instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    related_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_events.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[WorkflowEventType] = mapped_column(
        enum_column(WorkflowEventType, "workflow_event_type"), nullable=False, index=True
    )
    from_status: Mapped[InstrumentLifecycleStatus | None] = mapped_column(
        enum_column(InstrumentLifecycleStatus, "workflow_from_status")
    )
    to_status: Mapped[InstrumentLifecycleStatus | None] = mapped_column(
        enum_column(InstrumentLifecycleStatus, "workflow_to_status")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    instrument: Mapped[FDRInstrument] = relationship(back_populates="workflow_events")
    related_event: Mapped["WorkflowEvent | None"] = relationship(
        remote_side="WorkflowEvent.id", foreign_keys=[related_event_id]
    )


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_user_read", "recipient_user_id", "read_at"),
        UniqueConstraint("dedupe_key", name="uq_notification_dedupe_key"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(String(120), default="legacy", server_default="legacy", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(180))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    related_entity_type: Mapped[str | None] = mapped_column(String(80))
    related_entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.SYSTEM_GENERATED, nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id", ondelete="SET NULL"), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    before_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(
        enum_column(DataOrigin, "data_origin"), default=DataOrigin.SYSTEM_GENERATED, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class RegulatoryRule(TimestampMixin, Base):
    __tablename__ = "regulatory_rules"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_regulatory_rule_institution_code"),
        CheckConstraint("version > 0", name="ck_regulatory_rule_version_positive"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    institution: Mapped[Institution | None] = relationship(back_populates="rules")


@event.listens_for(Base, "before_insert", propagate=True)
def populate_reference_normalized(mapper, connection, target) -> None:
    del mapper, connection
    if isinstance(target, FDRInstrument):
        target.reference_normalized = normalize_instrument_reference(target.reference_original)


@event.listens_for(FDRInstrument, "before_update")
def refresh_reference_normalized(mapper, connection, target) -> None:
    del mapper, connection
    target.reference_normalized = normalize_instrument_reference(target.reference_original)


def _reject_append_only_mutation(mapper, connection, target) -> None:
    del mapper, connection, target
    raise ValueError("Audit and history events are append-only.")


for _append_only_model in (AuditEvent, WorkflowEvent, VerificationEvent):
    event.listen(_append_only_model, "before_update", _reject_append_only_mutation)
    event.listen(_append_only_model, "before_delete", _reject_append_only_mutation)
