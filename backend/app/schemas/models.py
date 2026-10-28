"""Pydantic schemas mirroring the initial persistence model."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    DataOrigin,
    InstrumentLifecycleStatus,
    ObligationStatus,
    OperationalPriority,
    ReleaseApprovalDecision,
    ReleaseRequestStatus,
    ReplacementType,
    Role,
    VerificationCheckStatus,
    VerificationStatus,
)
from app.models.entities import normalize_instrument_reference


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InstitutionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=240)
    address: str | None = None


class InstitutionRead(ORMModel, InstitutionCreate):
    id: str
    active: bool
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    institution_id: str | None = None
    full_name: str = Field(min_length=2, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    password_hash: str = Field(min_length=20, max_length=255)
    role: Role


class UserRead(ORMModel):
    id: str
    institution_id: str | None
    full_name: str
    email: str
    role: Role
    active: bool
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class RegulatoryObligationCreate(BaseModel):
    institution_id: str | None = None
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=2, max_length=240)
    description: str | None = None
    effective_date: date
    due_date: date | None = None
    required_amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    status: ObligationStatus = ObligationStatus.OPEN
    priority: OperationalPriority = OperationalPriority.NORMAL

    @model_validator(mode="after")
    def check_date_order(self):
        if self.due_date is not None and self.due_date < self.effective_date:
            raise ValueError("due_date cannot precede effective_date")
        return self


class RegulatoryObligationRead(ORMModel, RegulatoryObligationCreate):
    id: str
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class FDRInstrumentCreate(BaseModel):
    institution_id: str
    obligation_id: str | None = None
    submitted_by_user_id: str | None = None
    supersedes_instrument_id: str | None = None
    replacement_type: ReplacementType | None = None
    issuer_name: str = Field(min_length=2, max_length=240)
    reference_original: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    issue_date: date
    maturity_date: date
    lifecycle_status: InstrumentLifecycleStatus = InstrumentLifecycleStatus.DRAFT
    verification_status: VerificationStatus = VerificationStatus.NOT_CHECKED
    priority: OperationalPriority = OperationalPriority.NORMAL
    notes: str | None = None

    @field_validator("reference_original")
    @classmethod
    def reference_has_matchable_characters(cls, value: str) -> str:
        if not normalize_instrument_reference(value.strip()):
            raise ValueError("reference_original must contain at least one letter or digit")
        return value.strip()

    @field_validator("amount")
    @classmethod
    def amount_has_two_decimal_places(cls, value: Decimal) -> Decimal:
        if value.as_tuple().exponent < -2:
            raise ValueError("amount supports at most two decimal places")
        return value

    @model_validator(mode="after")
    def check_dates_and_replacement(self):
        if self.maturity_date < self.issue_date:
            raise ValueError("maturity_date cannot precede issue_date")
        if (self.supersedes_instrument_id is None) != (self.replacement_type is None):
            raise ValueError("supersedes_instrument_id and replacement_type must be provided together")
        return self


class FDRInstrumentRead(ORMModel, FDRInstrumentCreate):
    id: str
    reference_normalized: str
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class InstrumentDocumentCreate(BaseModel):
    original_filename: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0)
    sha256_checksum: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class InstrumentDocumentRead(ORMModel, InstrumentDocumentCreate):
    id: str
    instrument_id: str
    uploaded_by_user_id: str | None
    extraction_status: str
    extraction_method: str | None
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class ExtractedDocumentFieldCreate(BaseModel):
    field_name: str = Field(min_length=1, max_length=100)
    extracted_value: str | None = None
    declared_value: str | None = None
    matches_declared: bool | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1, max_digits=5, decimal_places=4)


class ExtractedDocumentFieldRead(ORMModel, ExtractedDocumentFieldCreate):
    id: str
    document_id: str
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class VerificationCheckCreate(BaseModel):
    rule_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1)
    compared_values: dict[str, Any] = Field(default_factory=dict)
    status: VerificationCheckStatus = VerificationCheckStatus.OPEN


class VerificationCheckRead(ORMModel, VerificationCheckCreate):
    id: str
    instrument_id: str
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class VerificationEventCreate(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    comment: str | None = None
    event_metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationEventRead(ORMModel, VerificationEventCreate):
    id: str
    check_id: str
    actor_user_id: str | None
    created_at: datetime
    updated_at: datetime


class ReleaseRequestCreate(BaseModel):
    requested_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=1)


class ReleaseRequestRead(ORMModel, ReleaseRequestCreate):
    id: str
    instrument_id: str
    requested_by_user_id: str | None
    eligibility_status: str
    eligibility_findings: dict[str, Any]
    status: ReleaseRequestStatus
    created_at: datetime
    updated_at: datetime


class ReleaseApprovalCreate(BaseModel):
    decision: ReleaseApprovalDecision
    rationale: str = Field(min_length=1)


class ReleaseApprovalRead(ORMModel, ReleaseApprovalCreate):
    id: str
    release_request_id: str
    approver_user_id: str
    created_at: datetime
    updated_at: datetime


class NotificationCreate(BaseModel):
    recipient_user_id: str
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=80)
    related_entity_type: str | None = None
    related_entity_id: str | None = None


class NotificationRead(ORMModel, NotificationCreate):
    id: str
    read_at: datetime | None
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class AuditEventRead(ORMModel):
    id: str
    actor_user_id: str | None
    institution_id: str | None
    entity_type: str
    entity_id: str
    action: str
    before_values: dict[str, Any] | None
    after_values: dict[str, Any] | None
    context: dict[str, Any]
    data_origin: DataOrigin
    created_at: datetime


class RegulatoryRuleCreate(BaseModel):
    institution_id: str | None = None
    code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1)
    rule_config: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, gt=0)
    active: bool = True


class RegulatoryRuleRead(ORMModel, RegulatoryRuleCreate):
    id: str
    created_at: datetime
    updated_at: datetime
