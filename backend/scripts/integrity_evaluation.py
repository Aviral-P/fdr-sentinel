"""Build and measure a deterministic synthetic integrity test dataset."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import create_database_engine
from app.models import (
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    Institution,
    InstrumentDocument,
    InstrumentLifecycleStatus as Lifecycle,
    IntegrityFindingType as FindingType,
    ReleaseRequest,
    ReleaseRequestStatus,
    ReplacementType,
    VerificationCheck,
    VerificationCheckStatus,
    VerificationStatus,
)
from app.services.integrity_rules import run_all_rules


SYNTHETIC_LABEL = "SYNTHETIC EVALUATION DATA — fictional records, no real banks or institutions."
EVALUATION_DATE = date(2026, 10, 25)
SEED_NAMESPACE = NAMESPACE_URL


def _id(kind: str) -> str:
    return str(uuid5(SEED_NAMESPACE, f"fdr-sentinel-integrity-eval:{kind}"))


def _text(kind: str, final_sentence: str) -> str:
    token_source = sha256(kind.encode()).hexdigest()
    distinguishing_tokens = " ".join(
        f"case{token_source[index:index + 5]}" for index in range(0, len(token_source), 5)
    )
    return (
        f"{SYNTHETIC_LABEL} Fictional record category {kind}. "
        f"Local extraction comparison fixture tokens {distinguishing_tokens}. "
        "These generated phrases test repeatability without representing any genuine party or financial instrument. "
        f"{final_sentence}"
    )


def _instrument(session: Session, institution: Institution, key: str, **values) -> FDRInstrument:
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    attributes = {
        "issuer_name": "Synthetic Demonstration Issuer",
        "beneficiary": "Synthetic Education Trust",
        "reference_original": f"SYN-{key.upper()}-REF",
        "amount": Decimal("10000.00"),
        "issue_date": date(2025, 1, 1),
        "maturity_date": date(2028, 1, 1),
        "lifecycle_status": Lifecycle.DRAFT,
        "verification_status": VerificationStatus.NOT_CHECKED,
        "data_origin": DataOrigin.SYNTHETIC_DEMO,
        "notes": SYNTHETIC_LABEL,
    }
    attributes.update(values)
    instrument = FDRInstrument(
        id=_id(f"instrument:{key}"),
        institution_id=institution.id,
        created_at=now,
        updated_at=now,
        **attributes,
    )
    session.add(instrument)
    session.flush()
    return instrument


def _document(
    session: Session,
    instrument: FDRInstrument,
    key: str,
    *,
    checksum_source: str | None = None,
    text: str | None = None,
) -> InstrumentDocument:
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    blob = checksum_source or key
    document = InstrumentDocument(
        id=_id(f"document:{key}"),
        instrument_id=instrument.id,
        original_filename=f"synthetic-{key}.pdf",
        storage_key=f"synthetic-evaluation/{key}.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        sha256_checksum=sha256(blob.encode()).hexdigest(),
        extracted_text=text,
        extraction_status="completed" if text else "ocr_required",
        extraction_method="synthetic-evaluation-text" if text else "none",
        data_origin=DataOrigin.SYNTHETIC_DEMO,
        created_at=now,
        updated_at=now,
    )
    session.add(document)
    session.flush()
    return document


def _field(session: Session, document: InstrumentDocument, name: str, extracted, declared, matches) -> None:
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    session.add(
        ExtractedDocumentField(
            id=_id(f"field:{document.id}:{name}"),
            document_id=document.id,
            field_name=name,
            extracted_value=extracted,
            declared_value=declared,
            value_status="found" if extracted is not None else "missing",
            matches_declared=matches,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=now,
            updated_at=now,
        )
    )


def build_synthetic_dataset(session: Session) -> dict[str, set[str] | set[tuple[str, str]]]:
    """Create exact-known positives and clean control records in an empty DB."""
    institution = Institution(
        id=_id("institution"),
        code="SYN-INTEGRITY-EVAL",
        name="Synthetic Integrity Evaluation Institute",
        data_origin=DataOrigin.SYNTHETIC_DEMO,
    )
    session.add(institution)
    session.flush()
    clean_ids: set[str] = set()
    known_discrepancies: dict[FindingType, set[str]] = {}

    clean_one = _instrument(session, institution, "clean-01", lifecycle_status=Lifecycle.APPROVED)
    clean_two = _instrument(session, institution, "clean-02", lifecycle_status=Lifecycle.APPROVED)
    clean_ids.update({clean_one.id, clean_two.id})
    clean_doc_one = _document(session, clean_one, "clean-01", text=_text("clean record one", "Control ending alpha."))
    clean_doc_two = _document(session, clean_two, "clean-02", text=_text("clean record two", "Control ending with unrelated words and a different paragraph."))
    for document in (clean_doc_one, clean_doc_two):
        _field(session, document, "amount", "10000.00", "10000.00", True)
        _field(session, document, "beneficiary", "Synthetic Education Trust", "Synthetic Education Trust", True)
        _field(session, document, "issue_date", "2025-01-01", "2025-01-01", True)
        _field(session, document, "maturity_date", "2028-01-01", "2028-01-01", True)

    duplicate_left = _instrument(session, institution, "duplicate-left", reference_original="SYN-DUP-REF")
    duplicate_right = _instrument(session, institution, "duplicate-right", reference_original="SYN DUP REF")
    duplicate_docs = (
        _document(session, duplicate_left, "exact-left", checksum_source="same synthetic bytes", text=_text("exact duplicate", "Same file checksum pair.")),
        _document(session, duplicate_right, "exact-right", checksum_source="same synthetic bytes", text=_text("exact duplicate", "Same file checksum pair.")),
    )
    known_duplicate_pairs: dict[FindingType, set[tuple[str, str]]] = {
        FindingType.EXACT_FILE_DUPLICATE: {tuple(sorted((duplicate_left.id, duplicate_right.id)))},
        FindingType.REPEATED_REFERENCE: {tuple(sorted((duplicate_left.id, duplicate_right.id)))},
    }

    near_left = _instrument(session, institution, "near-left")
    near_right = _instrument(session, institution, "near-right")
    near_base = _text("near duplicate", "The fictional certificate stores a stable principal and a named beneficiary.")
    near_one = _document(session, near_left, "near-left", text=near_base)
    near_two = _document(session, near_right, "near-right", text=near_base.replace("stable principal", "stable principal amount"))
    known_duplicate_pairs[FindingType.NEAR_DUPLICATE_DOCUMENT] = {tuple(sorted((near_left.id, near_right.id)))}
    del duplicate_docs, near_one, near_two

    amount_record = _instrument(session, institution, "amount-mismatch")
    amount_doc = _document(session, amount_record, "amount-mismatch", text=_text("amount mismatch", "Expected and observed amount differ."))
    _field(session, amount_doc, "amount", "11000.00", "10000.00", False)
    known_discrepancies.setdefault(FindingType.AMOUNT_MISMATCH, set()).add(amount_record.id)

    beneficiary_record = _instrument(session, institution, "beneficiary-mismatch")
    beneficiary_doc = _document(session, beneficiary_record, "beneficiary-mismatch", text=_text("beneficiary mismatch", "Expected and observed beneficiary labels differ."))
    _field(session, beneficiary_doc, "beneficiary", "Synthetic Alternate Trust", beneficiary_record.beneficiary, False)
    known_discrepancies.setdefault(FindingType.BENEFICIARY_MISMATCH, set()).add(beneficiary_record.id)

    date_record = _instrument(session, institution, "date-mismatch")
    date_doc = _document(session, date_record, "date-mismatch", text=_text("date mismatch", "Declared and extracted maturity date candidates differ."))
    _field(session, date_doc, "maturity_date", "2029-01-01", "2028-01-01", False)
    known_discrepancies.setdefault(FindingType.DATE_INCONSISTENCY, set()).add(date_record.id)

    missing_doc_record = _instrument(
        session,
        institution,
        "missing-document",
        lifecycle_status=Lifecycle.SUBMITTED,
    )
    known_discrepancies.setdefault(FindingType.MISSING_REQUIRED_DOCUMENT, set()).add(missing_doc_record.id)

    maturity_record = _instrument(
        session,
        institution,
        "maturity-window",
        lifecycle_status=Lifecycle.APPROVED,
        maturity_date=EVALUATION_DATE + timedelta(days=5),
    )
    _document(session, maturity_record, "maturity-window", text=_text("maturity control", "This record has a recorded supporting document."))
    known_discrepancies.setdefault(FindingType.MATURITY_WITHOUT_SUCCESSOR, set()).add(maturity_record.id)

    lineage_record = _instrument(
        session,
        institution,
        "lineage-incomplete",
        replacement_type=ReplacementType.RENEWAL,
    )
    known_discrepancies.setdefault(FindingType.REPLACEMENT_LINEAGE_CONFLICT, set()).add(lineage_record.id)

    release_record = _instrument(
        session,
        institution,
        "release-unresolved",
        lifecycle_status=Lifecycle.RELEASE_PENDING,
    )
    _document(session, release_record, "release-unresolved", text=_text("release control", "This record has a supporting document."))
    release_request = ReleaseRequest(
        id=_id("release-request:unresolved"),
        instrument_id=release_record.id,
        requested_amount=Decimal("10000.00"),
        eligibility_status="blocked",
        eligibility_findings={
            "findings": [{"code": "verification_unresolved", "severity": "block"}],
            "synthetic_label": SYNTHETIC_LABEL,
        },
        status=ReleaseRequestStatus.PENDING,
        reason=SYNTHETIC_LABEL,
    )
    session.add(release_request)
    session.add(
        VerificationCheck(
            id=_id("verification-check:release"),
            instrument_id=release_record.id,
            rule_code="SYNTHETIC-OPEN-CHECK",
            title="Synthetic unresolved condition",
            explanation=SYNTHETIC_LABEL,
            compared_values={"demo": True},
            status=VerificationCheckStatus.OPEN,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
        )
    )
    known_discrepancies.setdefault(FindingType.RELEASE_CONDITIONS_UNRESOLVED, set()).add(release_record.id)

    session.flush()
    return {
        "clean_instrument_ids": clean_ids,
        "known_discrepancies": known_discrepancies,
        "known_duplicate_pairs": known_duplicate_pairs,
    }


def evaluate_dataset() -> dict:
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with session_factory() as session:
            expectations = build_synthetic_dataset(session)
            session.flush()
            instruments = list(session.query(FDRInstrument).all())
            documents = list(session.query(InstrumentDocument).all())
            fields = list(session.query(ExtractedDocumentField).all())
            checks = list(session.query(VerificationCheck).all())
            releases = list(session.query(ReleaseRequest).all())
            candidates = run_all_rules(
                instruments=instruments,
                documents=documents,
                fields=fields,
                checks=checks,
                release_requests=releases,
                today=EVALUATION_DATE,
            )
            detected_discrepancies = {
                finding_type: {
                    candidate.instrument_id
                    for candidate in candidates
                    if candidate.finding_type == finding_type
                }
                & expected_ids
                for finding_type, expected_ids in expectations["known_discrepancies"].items()
            }
            detected_duplicates = {
                finding_type: {
                    tuple(sorted((candidate.instrument_id, candidate.related_instrument_id)))
                    for candidate in candidates
                    if candidate.finding_type == finding_type and candidate.related_instrument_id
                }
                & expected_pairs
                for finding_type, expected_pairs in expectations["known_duplicate_pairs"].items()
            }
            clean_ids = expectations["clean_instrument_ids"]
            false_positive_candidates = [
                candidate
                for candidate in candidates
                if candidate.instrument_id in clean_ids or candidate.related_instrument_id in clean_ids
            ]
            known_discrepancy_total = sum(len(ids) for ids in expectations["known_discrepancies"].values())
            known_discrepancy_detected = sum(len(ids) for ids in detected_discrepancies.values())
            known_duplicate_total = sum(len(ids) for ids in expectations["known_duplicate_pairs"].values())
            known_duplicate_detected = sum(len(ids) for ids in detected_duplicates.values())
            return {
                "synthetic_label": SYNTHETIC_LABEL,
                "evaluation_date": EVALUATION_DATE.isoformat(),
                "instruments": len(instruments),
                "documents": len(documents),
                "clean_control_records": len(clean_ids),
                "known_discrepancies_total": known_discrepancy_total,
                "known_discrepancies_detected": known_discrepancy_detected,
                "known_discrepancy_recall_on_planted_cases": round(
                    known_discrepancy_detected / known_discrepancy_total, 4
                ) if known_discrepancy_total else None,
                "known_discrepancy_by_rule": {
                    key.value: {"expected": len(expectations["known_discrepancies"][key]), "detected": len(value)}
                    for key, value in detected_discrepancies.items()
                },
                "known_duplicate_pairs_total": known_duplicate_total,
                "known_duplicate_pairs_detected": known_duplicate_detected,
                "known_duplicate_pair_recall_on_planted_cases": round(
                    known_duplicate_detected / known_duplicate_total, 4
                ) if known_duplicate_total else None,
                "known_duplicates_by_rule": {
                    key.value: {"expected": len(expectations["known_duplicate_pairs"][key]), "detected": len(value)}
                    for key, value in detected_duplicates.items()
                },
                "false_positive_candidates_on_clean_records": len(false_positive_candidates),
                "clean_control_records_flagged": len({
                    instrument_id
                    for candidate in false_positive_candidates
                    for instrument_id in (candidate.instrument_id, candidate.related_instrument_id)
                    if instrument_id in clean_ids
                }),
                "false_positive_types_on_clean_records": [item.finding_type.value for item in false_positive_candidates],
                "all_candidates_by_type": {
                    kind.value: sum(candidate.finding_type == kind for candidate in candidates)
                    for kind in FindingType
                },
            }
    finally:
        engine.dispose()


def render_report(results: dict) -> str:
    discrepancy_rows = "\n".join(
        f"| `{rule}` | {counts['detected']} | {counts['expected']} |"
        for rule, counts in results["known_discrepancy_by_rule"].items()
    )
    duplicate_rows = "\n".join(
        f"| `{rule}` | {counts['detected']} | {counts['expected']} |"
        for rule, counts in results["known_duplicates_by_rule"].items()
    )
    all_rows = "\n".join(
        f"| `{rule}` | {count} |" for rule, count in results["all_candidates_by_type"].items()
    )
    return f"""# Integrity rule synthetic evaluation

Generated by `backend/.venv/bin/python -m scripts.integrity_evaluation` on evaluation date `{results['evaluation_date']}`.

> {results['synthetic_label']}

This is a deterministic rule check against a small, planted dataset. Counts describe this fixture only; they are not real-world accuracy, a calibrated fraud probability, or evidence of document authenticity.

Dataset: **{results['instruments']} instruments**, **{results['documents']} document metadata records**, and **{results['clean_control_records']} clean control records**.

## Planted discrepancy cases

| Rule / finding type | Detected | Known |
|---|---:|---:|
{discrepancy_rows}

**Known discrepancies detected: {results['known_discrepancies_detected']} / {results['known_discrepancies_total']}**

## Planted duplicate pairs

| Rule / finding type | Detected | Known |
|---|---:|---:|
{duplicate_rows}

**Known duplicate pairs detected: {results['known_duplicate_pairs_detected']} / {results['known_duplicate_pairs_total']}**

## Clean control results

False-positive candidates linked to either clean control record: **{results['false_positive_candidates_on_clean_records']}**. Clean control records flagged: **{results['clean_control_records_flagged']} / {results['clean_control_records']}**.

## Fixture-only summary metrics

- Planted discrepancy recall: **{results['known_discrepancy_recall_on_planted_cases']:.1%}** ({results['known_discrepancies_detected']} / {results['known_discrepancies_total']}).
- Planted duplicate-pair recall: **{results['known_duplicate_pair_recall_on_planted_cases']:.1%}** ({results['known_duplicate_pairs_detected']} / {results['known_duplicate_pairs_total']}).
- Clean controls flagged: **{results['clean_control_records_flagged']} / {results['clean_control_records']}**.

These are fixture-only recall values over intentionally planted cases. They are not production precision/recall, prevalence-adjusted accuracy, or a fraud probability. The fixture is small and not representative of real-world distributions.

## All emitted candidates

| Finding type | Candidate count |
|---|---:|
{all_rows}

To regenerate, run the command above. Values are measured from the fixture and generated rules; no accuracy percentage is hardcoded.
"""


def main() -> None:
    results = evaluate_dataset()
    docs_dir = Path(__file__).resolve().parents[2] / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "INTEGRITY_EVALUATION.md"
    json_path = docs_dir / "INTEGRITY_EVALUATION.json"
    report_path.write_text(render_report(results), encoding="utf-8")
    json_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {report_path}")
    print(f"Wrote {json_path}")
    print(render_report(results))


if __name__ == "__main__":
    main()
