"""Enumerated values shared by persistence and API schemas."""

from enum import Enum


class StringEnum(str, Enum):
    """Enum stored as stable lowercase strings in the database."""


class Role(StringEnum):
    INSTITUTION_USER = "institution_user"
    SCRUTINY_OFFICER = "scrutiny_officer"
    APPROVING_AUTHORITY = "approving_authority"
    AUDITOR = "auditor"
    ADMIN = "admin"


class InstrumentLifecycleStatus(StringEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_SCRUTINY = "under_scrutiny"
    CLARIFICATION_REQUIRED = "clarification_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    RELEASE_PENDING = "release_pending"
    RELEASED = "released"
    MATURED = "matured"
    SUPERSEDED = "superseded"


class WorkflowEventType(StringEnum):
    CREATED = "created"
    SUBMITTED = "submitted"
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_RESPONDED = "clarification_responded"
    SCRUTINY_RECOMMENDATION = "scrutiny_recommendation"
    FINAL_DECISION = "final_decision"
    SUCCESSOR_CREATED = "successor_created"
    RELEASE_REQUESTED = "release_requested"
    RELEASE_ELIGIBILITY_EVALUATED = "release_eligibility_evaluated"
    RELEASE_DECISION = "release_decision"


class VerificationStatus(StringEnum):
    NOT_CHECKED = "not_checked"
    PENDING_REVIEW = "pending_review"
    DISCREPANCY_FLAGGED = "discrepancy_flagged"
    REVIEWED = "reviewed"


class OperationalPriority(StringEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ObligationStatus(StringEnum):
    OPEN = "open"
    SUBMITTED = "submitted"
    SATISFIED = "satisfied"
    WAIVED = "waived"


class ReplacementType(StringEnum):
    RENEWAL = "renewal"
    REPLACEMENT = "replacement"


class VerificationCheckStatus(StringEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class IntegrityFindingType(StringEnum):
    EXACT_FILE_DUPLICATE = "exact_file_duplicate"
    REPEATED_REFERENCE = "repeated_reference"
    NEAR_DUPLICATE_DOCUMENT = "near_duplicate_document"
    AMOUNT_MISMATCH = "amount_mismatch"
    BENEFICIARY_MISMATCH = "beneficiary_mismatch"
    DATE_INCONSISTENCY = "date_inconsistency"
    MISSING_REQUIRED_DOCUMENT = "missing_required_document"
    MATURITY_WITHOUT_SUCCESSOR = "maturity_without_successor"
    REPLACEMENT_LINEAGE_CONFLICT = "replacement_lineage_conflict"
    RELEASE_CONDITIONS_UNRESOLVED = "release_conditions_unresolved"


class IntegrityFindingSeverity(StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntegrityReviewStatus(StringEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class ReleaseRequestStatus(StringEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"


class ReleaseApprovalDecision(StringEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"


class DataOrigin(StringEnum):
    USER_SUBMITTED = "user_submitted"
    EXTRACTED = "extracted"
    SYSTEM_GENERATED = "system_generated"
    INDEPENDENTLY_VERIFIED = "independently_verified"
    SYNTHETIC_DEMO = "synthetic_demo"
