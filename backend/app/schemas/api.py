"""Schemas for institution, FDR, lifecycle, and release APIs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    DataOrigin,
    IntegrityFindingSeverity,
    IntegrityFindingType,
    IntegrityReviewStatus,
    InstrumentLifecycleStatus,
    OperationalPriority,
    ReleaseApprovalDecision,
    ReleaseRequestStatus,
    ReplacementType,
    VerificationStatus,
    WorkflowEventType,
)
from app.schemas.models import RegulatoryObligationRead

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class InstitutionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    address: str | None
    active: bool
    data_origin: DataOrigin
    created_at: datetime
    updated_at: datetime


class InstitutionDetail(InstitutionItem):
    obligations: list[RegulatoryObligationRead]


class FDRInstrumentCreateRequest(BaseModel):
    institution_id: str
    obligation_id: str | None = None
    issuer_name: str = Field(min_length=2, max_length=240)
    beneficiary: str | None = Field(default=None, max_length=300)
    reference_original: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    issue_date: date
    maturity_date: date
    notes: str | None = None

    @model_validator(mode="after")
    def validate_date_order(self):
        if self.maturity_date < self.issue_date:
            raise ValueError("maturity_date cannot precede issue_date")
        if not self.reference_original.strip():
            raise ValueError("reference_original cannot be blank")
        return self


class FDRInstrumentUpdateRequest(BaseModel):
    """Allowed institution edits for drafts and cases returned for clarification."""

    model_config = ConfigDict(extra="forbid")

    obligation_id: str | None = None
    issuer_name: str | None = Field(default=None, min_length=2, max_length=240)
    beneficiary: str | None = Field(default=None, max_length=300)
    reference_original: str | None = Field(default=None, min_length=1, max_length=120)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    issue_date: date | None = None
    maturity_date: date | None = None
    notes: str | None = None



class SuccessorInstrumentCreateRequest(BaseModel):
    replacement_type: ReplacementType
    obligation_id: str | None = None
    issuer_name: str = Field(min_length=2, max_length=240)
    beneficiary: str | None = Field(default=None, max_length=300)
    reference_original: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    issue_date: date
    maturity_date: date
    notes: str | None = None

    @model_validator(mode="after")
    def validate_fields(self):
        if self.maturity_date < self.issue_date:
            raise ValueError("maturity_date cannot precede issue_date")
        if not self.reference_original.strip():
            raise ValueError("reference_original cannot be blank")
        return self


class FDRInstrumentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    institution_id: str
    obligation_id: str | None
    submitted_by_user_id: str | None
    supersedes_instrument_id: str | None
    successor_instrument_id: str | None = None
    replacement_type: ReplacementType | None
    issuer_name: str
    beneficiary: str | None
    reference_original: str
    reference_normalized: str
    amount: Decimal
    issue_date: date
    maturity_date: date
    lifecycle_status: InstrumentLifecycleStatus
    verification_status: VerificationStatus
    priority: OperationalPriority
    data_origin: DataOrigin
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ExtractedDocumentFieldItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    field_name: str
    extracted_value: str | None
    declared_value: str | None
    value_status: Literal["found", "missing"]
    matches_declared: bool | None
    confidence: Decimal | None
    data_origin: DataOrigin


class InstrumentDocumentItem(BaseModel):
    id: str
    instrument_id: str
    uploaded_by_user_id: str | None
    original_filename: str
    content_type: str
    size_bytes: int
    sha256_checksum: str
    original_available: bool
    extraction_status: Literal["not_started", "processing", "completed", "ocr_required", "failed", "unavailable"]
    extraction_method: str | None
    extraction_error: str | None
    created_at: datetime
    updated_at: datetime
    fields: list[ExtractedDocumentFieldItem] = Field(default_factory=list)


class DocumentFieldReviewRequest(BaseModel):
    decision: Literal["confirm_discrepancy", "dismiss_discrepancy", "needs_clarification"]
    comment: str = Field(min_length=1, max_length=2000)


class DocumentFieldReviewResponse(BaseModel):
    document_id: str
    field_name: str
    decision: Literal["confirm_discrepancy", "dismiss_discrepancy", "needs_clarification"]
    verification_check_status: Literal["open", "reviewed", "dismissed"]
    verification_event_id: str


class IntegrityFindingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    institution_id: str
    instrument_id: str
    related_instrument_id: str | None
    document_id: str | None
    related_document_id: str | None
    release_request_id: str | None
    finding_type: IntegrityFindingType
    severity: IntegrityFindingSeverity
    data_origin: DataOrigin
    observed_values: dict[str, Any]
    expected_values: dict[str, Any]
    explanation: str
    rule_id: str
    rule_version: str
    detected_at: datetime
    review_status: IntegrityReviewStatus
    reviewed_by_user_id: str | None
    reviewed_at: datetime | None
    resolution_notes: str | None
    is_current: bool


class IntegrityQueueItem(BaseModel):
    finding: IntegrityFindingItem
    priority_score: int
    ranking_reasons: list[str]
    deadline_days_remaining: int | None
    supporting_evidence: dict[str, Any]
    ranking_notice: str


class IntegrityScanSummary(BaseModel):
    instruments_scanned: int
    candidates_detected: int
    findings_created: int
    findings_reopened: int
    findings_resolved: int
    current_findings: int


class IntegrityFindingReviewRequest(BaseModel):
    decision: Literal["reviewed", "dismissed"]
    resolution_notes: str = Field(min_length=1, max_length=2000)


class ScrutinyRequest(BaseModel):
    outcome: Literal["request_clarification", "recommend_approval", "recommend_rejection"]
    comment: str | None = Field(default=None, max_length=4000)
    clarification_question: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_clarification_question(self):
        if self.outcome == "request_clarification" and not (self.clarification_question or "").strip():
            raise ValueError("clarification_question is required for a clarification request")
        if self.outcome != "request_clarification" and self.clarification_question:
            raise ValueError("clarification_question is only valid for request_clarification")
        return self


class ClarificationResponseRequest(BaseModel):
    response: str = Field(min_length=1, max_length=4000)


class FinalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=1, max_length=4000)


class ReleaseRequestCreateRequest(BaseModel):
    requested_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=1, max_length=4000)


class EligibilityFinding(BaseModel):
    code: str
    severity: Literal["block", "warning"]
    message: str


class ReleaseEligibilityResponse(BaseModel):
    release_request_id: str
    eligible: bool
    eligibility_status: str
    findings: list[EligibilityFinding]
    rules_applied: dict[str, Any]
    evaluated_at: datetime


class ReleaseRequestItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    instrument_id: str
    requested_by_user_id: str | None
    requested_amount: Decimal
    eligibility_status: str
    eligibility_findings: dict[str, Any]
    status: ReleaseRequestStatus
    reason: str
    created_at: datetime
    updated_at: datetime


class ReleaseRequestCreated(BaseModel):
    request: ReleaseRequestItem
    eligibility: ReleaseEligibilityResponse


class ReleaseEvaluationResult(BaseModel):
    request: ReleaseRequestItem
    eligibility: ReleaseEligibilityResponse


class ReleaseDecisionRequest(BaseModel):
    decision: ReleaseApprovalDecision
    rationale: str = Field(min_length=1, max_length=4000)
    disposition: str = Field(min_length=1, max_length=1000)


class ReleaseApprovalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    release_request_id: str
    approver_user_id: str
    decision: ReleaseApprovalDecision
    rationale: str
    disposition: str
    created_at: datetime
    updated_at: datetime


class WorkflowHistoryItem(BaseModel):
    id: str
    source: Literal["workflow", "audit"]
    occurred_at: datetime
    actor_user_id: str | None
    action: str
    from_status: InstrumentLifecycleStatus | None = None
    to_status: InstrumentLifecycleStatus | None = None
    summary: str | None = None
    related_event_id: str | None = None
    change_summary: dict[str, Any] | None = None


class InstrumentHistoryResponse(BaseModel):
    instrument_id: str
    events: list[WorkflowHistoryItem]


class ReleaseDecisionResponse(BaseModel):
    request: ReleaseRequestItem
    approval: ReleaseApprovalItem


class ScrutinyResult(BaseModel):
    instrument: FDRInstrumentItem
    event_id: str
    outcome: Literal["request_clarification", "recommend_approval", "recommend_rejection"]
