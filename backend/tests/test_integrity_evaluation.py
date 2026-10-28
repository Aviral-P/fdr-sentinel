"""Regression checks for the deterministic synthetic evaluation harness."""

from app.models import IntegrityFindingType as FindingType
from scripts.integrity_evaluation import evaluate_dataset


def test_synthetic_evaluation_detects_all_planted_cases_and_duplicates():
    results = evaluate_dataset()

    assert results["instruments"] == 13
    assert results["documents"] == 11
    assert results["clean_control_records"] == 2
    assert results["known_discrepancies_detected"] == results["known_discrepancies_total"] == 7
    assert results["known_duplicate_pairs_detected"] == results["known_duplicate_pairs_total"] == 3
    assert results["known_discrepancy_recall_on_planted_cases"] == 1.0
    assert results["known_duplicate_pair_recall_on_planted_cases"] == 1.0
    assert results["clean_control_records_flagged"] == 0
    assert results["false_positive_candidates_on_clean_records"] == 0


def test_synthetic_evaluation_covers_expected_rule_families():
    results = evaluate_dataset()
    discrepancy_types = set(results["known_discrepancy_by_rule"])
    duplicate_types = set(results["known_duplicates_by_rule"])

    assert discrepancy_types == {
        FindingType.AMOUNT_MISMATCH.value,
        FindingType.BENEFICIARY_MISMATCH.value,
        FindingType.DATE_INCONSISTENCY.value,
        FindingType.MISSING_REQUIRED_DOCUMENT.value,
        FindingType.MATURITY_WITHOUT_SUCCESSOR.value,
        FindingType.REPLACEMENT_LINEAGE_CONFLICT.value,
        FindingType.RELEASE_CONDITIONS_UNRESOLVED.value,
    }
    assert duplicate_types == {
        FindingType.EXACT_FILE_DUPLICATE.value,
        FindingType.REPEATED_REFERENCE.value,
        FindingType.NEAR_DUPLICATE_DOCUMENT.value,
    }
