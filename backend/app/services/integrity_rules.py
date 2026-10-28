"""Independent deterministic integrity rules. Every match is a human-review lead."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
import re
from typing import Any, Iterable, Mapping, Sequence

from app.models import (
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    InstrumentDocument,
    InstrumentLifecycleStatus as Lifecycle,
    IntegrityFindingSeverity as Severity,
    IntegrityFindingType as FindingType,
    IntegrityReviewStatus,
    OperationalPriority,
    ReleaseRequest,
    ReleaseRequestStatus,
    ReplacementType,
    VerificationCheck,
    VerificationCheckStatus,
)


RULE_VERSION = "1.0.0"
MIN_NEAR_DUPLICATE_TEXT_CHARS = 160
NEAR_DUPLICATE_SIMILARITY_THRESHOLD = 0.88
DEFAULT_MATURITY_WARNING_DAYS = 30
DEFAULT_REQUIRED_DOCUMENT_COUNT = 1
DOCUMENT_REQUIRED_STATUSES = {
    Lifecycle.SUBMITTED,
    Lifecycle.UNDER_SCRUTINY,
    Lifecycle.CLARIFICATION_REQUIRED,
    Lifecycle.APPROVED,
    Lifecycle.MATURED,
    Lifecycle.RELEASE_PENDING,
}
MATURITY_MONITORED_STATUSES = {Lifecycle.APPROVED, Lifecycle.MATURED}


@dataclass(frozen=True)
class FindingCandidate:
    institution_id: str
    instrument_id: str
    finding_type: FindingType
    severity: Severity
    explanation: str
    rule_id: str
    rule_version: str = RULE_VERSION
    related_instrument_id: str | None = None
    document_id: str | None = None
    related_document_id: str | None = None
    release_request_id: str | None = None
    observed_values: Mapping[str, Any] | None = None
    expected_values: Mapping[str, Any] | None = None


def _pairs(items: Sequence[Any]):
    ordered = sorted(items, key=lambda item: item.id)
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            yield left, right


def exact_file_duplicate_rule(
    documents: Sequence[InstrumentDocument], instruments: Mapping[str, FDRInstrument]
) -> list[FindingCandidate]:
    groups: dict[str, list[InstrumentDocument]] = {}
    for document in documents:
        if document.sha256_checksum:
            groups.setdefault(document.sha256_checksum.lower(), []).append(document)
    findings: list[FindingCandidate] = []
    for checksum, group in sorted(groups.items()):
        for first, second in _pairs(group):
            primary = instruments[first.instrument_id]
            related = instruments[second.instrument_id]
            findings.append(
                FindingCandidate(
                    institution_id=primary.institution_id,
                    instrument_id=primary.id,
                    related_instrument_id=related.id,
                    document_id=first.id,
                    related_document_id=second.id,
                    finding_type=FindingType.EXACT_FILE_DUPLICATE,
                    severity=Severity.HIGH,
                    rule_id="exact_file_sha256",
                    explanation="Two separately uploaded documents have the same SHA-256 checksum; inspect whether the evidence was intentionally reused.",
                    observed_values={"sha256": checksum, "document_ids": [first.id, second.id]},
                    expected_values={"distinct_uploads": True},
                )
            )
    return findings


def repeated_reference_rule(instruments: Sequence[FDRInstrument]) -> list[FindingCandidate]:
    groups: dict[str, list[FDRInstrument]] = {}
    for instrument in instruments:
        reference = (instrument.reference_normalized or "").strip().upper()
        if reference:
            groups.setdefault(reference, []).append(instrument)
    findings: list[FindingCandidate] = []
    for reference, group in sorted(groups.items()):
        for first, second in _pairs(group):
            findings.append(
                FindingCandidate(
                    institution_id=first.institution_id,
                    instrument_id=first.id,
                    related_instrument_id=second.id,
                    finding_type=FindingType.REPEATED_REFERENCE,
                    severity=Severity.HIGH,
                    rule_id="normalized_instrument_reference",
                    explanation="Two instrument records share the same normalized reference; matching punctuation and case are ignored by this rule.",
                    observed_values={
                        "normalized_reference": reference,
                        "original_references": [first.reference_original, second.reference_original],
                    },
                    expected_values={"unique_instrument_reference": True},
                )
            )
    return findings


def _normalized_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def near_duplicate_document_rule(
    documents: Sequence[InstrumentDocument],
    instruments: Mapping[str, FDRInstrument],
    *,
    minimum_characters: int = MIN_NEAR_DUPLICATE_TEXT_CHARS,
    threshold: float = NEAR_DUPLICATE_SIMILARITY_THRESHOLD,
) -> list[FindingCandidate]:
    eligible = [
        document
        for document in documents
        if document.extracted_text and len(re.sub(r"\s", "", document.extracted_text)) >= minimum_characters
    ]
    findings: list[FindingCandidate] = []
    for first, second in _pairs(eligible):
        if first.instrument_id == second.instrument_id:
            continue
        if first.sha256_checksum and first.sha256_checksum.lower() == second.sha256_checksum.lower():
            continue
        first_text = _normalized_text(first.extracted_text)
        second_text = _normalized_text(second.extracted_text)
        similarity = SequenceMatcher(None, first_text, second_text, autojunk=False).ratio()
        if similarity < threshold:
            continue
        primary = instruments[first.instrument_id]
        related = instruments[second.instrument_id]
        findings.append(
            FindingCandidate(
                institution_id=primary.institution_id,
                instrument_id=primary.id,
                related_instrument_id=related.id,
                document_id=first.id,
                related_document_id=second.id,
                finding_type=FindingType.NEAR_DUPLICATE_DOCUMENT,
                severity=Severity.MEDIUM,
                rule_id="document_text_similarity_sequence_matcher",
                explanation="Extracted text similarity exceeded the configured candidate threshold; this is a candidate match that requires human review.",
                observed_values={
                    "similarity_score": round(similarity, 4),
                    "threshold": threshold,
                    "text_lengths": [len(first_text), len(second_text)],
                    "comparison": "normalized extracted text; whitespace and letter case ignored",
                },
                expected_values={"similarity_below_threshold": True},
            )
        )
    return findings


def _field_mismatch_rule(
    fields: Sequence[ExtractedDocumentField],
    instruments: Mapping[str, FDRInstrument],
    *,
    field_name: str,
    finding_type: FindingType,
    rule_id: str,
    display_name: str,
) -> list[FindingCandidate]:
    findings: list[FindingCandidate] = []
    documents_by_id = {field.document_id: field.document for field in fields if field.document is not None}
    for field in sorted(fields, key=lambda row: (row.document_id, row.id)):
        if field.field_name != field_name or field.matches_declared is not False:
            continue
        document = documents_by_id.get(field.document_id)
        if document is None or document.instrument_id not in instruments:
            continue
        instrument = instruments[document.instrument_id]
        findings.append(
            FindingCandidate(
                institution_id=instrument.institution_id,
                instrument_id=instrument.id,
                document_id=document.id,
                finding_type=finding_type,
                severity=Severity.HIGH,
                rule_id=rule_id,
                explanation=f"The extracted {display_name} candidate differs from the institution-declared value. Review the original evidence; this comparison is not an authenticity determination.",
                observed_values={"extracted_value": field.extracted_value},
                expected_values={"declared_value": field.declared_value},
            )
        )
    return findings


def amount_mismatch_rule(fields, instruments) -> list[FindingCandidate]:
    return _field_mismatch_rule(
        fields,
        instruments,
        field_name="amount",
        finding_type=FindingType.AMOUNT_MISMATCH,
        rule_id="declared_extracted_amount_compare",
        display_name="amount",
    )


def beneficiary_mismatch_rule(fields, instruments) -> list[FindingCandidate]:
    return _field_mismatch_rule(
        fields,
        instruments,
        field_name="beneficiary",
        finding_type=FindingType.BENEFICIARY_MISMATCH,
        rule_id="declared_extracted_beneficiary_compare",
        display_name="beneficiary",
    )


def date_inconsistency_rule(
    fields: Sequence[ExtractedDocumentField], instruments: Mapping[str, FDRInstrument]
) -> list[FindingCandidate]:
    mismatches = []
    for field_name in ("issue_date", "maturity_date"):
        mismatches.extend(
            _field_mismatch_rule(
                fields,
                instruments,
                field_name=field_name,
                finding_type=FindingType.DATE_INCONSISTENCY,
                rule_id=f"declared_extracted_{field_name}_compare",
                display_name=field_name.replace("_", " "),
            )
        )
    per_document: dict[str, dict[str, ExtractedDocumentField]] = {}
    for field in fields:
        if field.field_name in {"issue_date", "maturity_date"}:
            per_document.setdefault(field.document_id, {})[field.field_name] = field
    for document_id, pair in per_document.items():
        issue = pair.get("issue_date")
        maturity = pair.get("maturity_date")
        if not issue or not maturity or not issue.extracted_value or not maturity.extracted_value:
            continue
        issue_date = _parse_date(issue.extracted_value)
        maturity_date = _parse_date(maturity.extracted_value)
        if issue_date is None or maturity_date is None:
            continue
        if maturity_date >= issue_date:
            continue
        document = issue.document
        if document is None or document.instrument_id not in instruments:
            continue
        instrument = instruments[document.instrument_id]
        mismatches.append(
            FindingCandidate(
                institution_id=instrument.institution_id,
                instrument_id=instrument.id,
                document_id=document_id,
                finding_type=FindingType.DATE_INCONSISTENCY,
                severity=Severity.HIGH,
                rule_id="extracted_date_order",
                explanation="The extracted maturity date precedes the extracted issue date; check the source text and candidate parsing.",
                observed_values={"issue_date": issue.extracted_value, "maturity_date": maturity.extracted_value},
                expected_values={"maturity_date_on_or_after_issue_date": True},
            )
        )
    return mismatches


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None


def missing_required_document_rule(
    instruments: Sequence[FDRInstrument],
    documents: Sequence[InstrumentDocument],
    *,
    minimum_document_count: int = DEFAULT_REQUIRED_DOCUMENT_COUNT,
) -> list[FindingCandidate]:
    counts: dict[str, int] = {}
    for document in documents:
        counts[document.instrument_id] = counts.get(document.instrument_id, 0) + 1
    findings: list[FindingCandidate] = []
    for instrument in instruments:
        count = counts.get(instrument.id, 0)
        if instrument.lifecycle_status not in DOCUMENT_REQUIRED_STATUSES or count >= minimum_document_count:
            continue
        findings.append(
            FindingCandidate(
                institution_id=instrument.institution_id,
                instrument_id=instrument.id,
                finding_type=FindingType.MISSING_REQUIRED_DOCUMENT,
                severity=Severity.HIGH,
                rule_id="required_document_count",
                explanation=f"This instrument is in {instrument.lifecycle_status.value} and has {count} document record(s), below the configured minimum of {minimum_document_count}.",
                observed_values={"document_count": count},
                expected_values={"minimum_document_count": minimum_document_count},
            )
        )
    return findings


def approaching_maturity_without_successor_rule(
    instruments: Sequence[FDRInstrument],
    *,
    today: date,
    warning_days: int = DEFAULT_MATURITY_WARNING_DAYS,
) -> list[FindingCandidate]:
    findings: list[FindingCandidate] = []
    for instrument in instruments:
        days = (instrument.maturity_date - today).days
        if (
            instrument.lifecycle_status not in MATURITY_MONITORED_STATUSES
            or instrument.successor is not None
            or days < 0
            or days > warning_days
        ):
            continue
        findings.append(
            FindingCandidate(
                institution_id=instrument.institution_id,
                instrument_id=instrument.id,
                finding_type=FindingType.MATURITY_WITHOUT_SUCCESSOR,
                severity=Severity.HIGH if days <= 7 else Severity.MEDIUM,
                rule_id="maturity_without_successor_window",
                explanation=f"The instrument matures in {days} day(s), within the configured {warning_days}-day warning window, and no successor record is linked.",
                observed_values={"maturity_date": instrument.maturity_date.isoformat(), "days_remaining": days},
                expected_values={"successor_instrument_id": "recorded before maturity"},
            )
        )
    return findings


def replacement_lineage_rule(instruments: Sequence[FDRInstrument]) -> list[FindingCandidate]:
    by_id = {instrument.id: instrument for instrument in instruments}
    children: dict[str, list[FDRInstrument]] = {}
    for instrument in instruments:
        if instrument.supersedes_instrument_id:
            children.setdefault(instrument.supersedes_instrument_id, []).append(instrument)
    findings: list[FindingCandidate] = []
    for instrument in instruments:
        parent = by_id.get(instrument.supersedes_instrument_id) if instrument.supersedes_instrument_id else None
        issue: str | None = None
        if instrument.supersedes_instrument_id and parent is None:
            issue = "predecessor record is missing from the current dataset"
        elif instrument.supersedes_instrument_id == instrument.id:
            issue = "instrument points to itself as its predecessor"
        elif parent and parent.institution_id != instrument.institution_id:
            issue = "successor and predecessor belong to different institutions"
        elif instrument.supersedes_instrument_id and instrument.replacement_type is None:
            issue = "successor link has no renewal/replacement type"
        elif instrument.replacement_type is not None and instrument.supersedes_instrument_id is None:
            issue = "renewal/replacement type is set but no predecessor is linked"
        elif instrument.lifecycle_status == Lifecycle.SUPERSEDED and not children.get(instrument.id):
            issue = "instrument is marked superseded but has no linked successor"
        elif len(children.get(instrument.id, [])) > 1:
            issue = "predecessor has multiple linked successors"
        if issue is None:
            continue
        findings.append(
            FindingCandidate(
                institution_id=instrument.institution_id,
                instrument_id=instrument.id,
                related_instrument_id=instrument.supersedes_instrument_id,
                finding_type=FindingType.REPLACEMENT_LINEAGE_CONFLICT,
                severity=Severity.HIGH,
                rule_id="replacement_lineage_consistency",
                explanation=f"Replacement lineage is incomplete or conflicting: {issue}.",
                observed_values={
                    "supersedes_instrument_id": instrument.supersedes_instrument_id,
                    "replacement_type": instrument.replacement_type.value if instrument.replacement_type else None,
                    "lifecycle_status": instrument.lifecycle_status.value,
                },
                expected_values={"valid_predecessor_link": True, "replacement_type_required_for_successor": True},
            )
        )
    return findings


def unresolved_release_conditions_rule(
    requests: Sequence[ReleaseRequest],
    instruments: Mapping[str, FDRInstrument],
    checks: Sequence[VerificationCheck],
) -> list[FindingCandidate]:
    open_checks: dict[str, list[VerificationCheck]] = {}
    for check in checks:
        if check.status == VerificationCheckStatus.OPEN and check.is_required:
            open_checks.setdefault(check.instrument_id, []).append(check)
    findings: list[FindingCandidate] = []
    for request in requests:
        if request.status != ReleaseRequestStatus.PENDING or request.instrument_id not in instruments:
            continue
        instrument = instruments[request.instrument_id]
        eligibility = request.eligibility_findings or {}
        blocking = [
            item
            for item in eligibility.get("findings", [])
            if isinstance(item, dict) and item.get("severity") == "block"
        ]
        open_for_instrument = open_checks.get(instrument.id, [])
        unresolved = request.eligibility_status != "eligible" or bool(blocking) or bool(open_for_instrument)
        if not unresolved:
            continue
        findings.append(
            FindingCandidate(
                institution_id=instrument.institution_id,
                instrument_id=instrument.id,
                release_request_id=request.id,
                finding_type=FindingType.RELEASE_CONDITIONS_UNRESOLVED,
                severity=Severity.HIGH,
                rule_id="release_request_required_conditions",
                explanation="The pending release request has an ineligible/unevaluated status or unresolved verification conditions; an authorized human decision is still required.",
                observed_values={
                    "release_status": request.status.value,
                    "eligibility_status": request.eligibility_status,
                    "blocking_finding_codes": [item.get("code") for item in blocking],
                    "open_verification_rule_codes": sorted({check.rule_code for check in open_for_instrument}),
                },
                expected_values={"eligibility_status": "eligible", "open_required_conditions": 0},
            )
        )
    return findings


def run_all_rules(
    *,
    instruments: Sequence[FDRInstrument],
    documents: Sequence[InstrumentDocument],
    fields: Sequence[ExtractedDocumentField],
    checks: Sequence[VerificationCheck],
    release_requests: Sequence[ReleaseRequest],
    today: date,
    required_document_count: int = DEFAULT_REQUIRED_DOCUMENT_COUNT,
    maturity_warning_days: int = DEFAULT_MATURITY_WARNING_DAYS,
) -> list[FindingCandidate]:
    instrument_map = {instrument.id: instrument for instrument in instruments}
    rules = (
        exact_file_duplicate_rule(documents, instrument_map),
        repeated_reference_rule(instruments),
        near_duplicate_document_rule(documents, instrument_map),
        amount_mismatch_rule(fields, instrument_map),
        beneficiary_mismatch_rule(fields, instrument_map),
        date_inconsistency_rule(fields, instrument_map),
        missing_required_document_rule(instruments, documents, minimum_document_count=required_document_count),
        approaching_maturity_without_successor_rule(instruments, today=today, warning_days=maturity_warning_days),
        replacement_lineage_rule(instruments),
        unresolved_release_conditions_rule(release_requests, instrument_map, checks),
    )
    return [candidate for rule_candidates in rules for candidate in rule_candidates]
