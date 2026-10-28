"""Deterministic text extraction and declared-value comparison.

OCR is intentionally an adapter seam: scanned documents produce ``ocr_required``
until a separately configured OCR provider is implemented.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import shutil
import subprocess
from io import BytesIO
from typing import Any, Protocol

import fitz
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    InstrumentDocument,
    VerificationCheck,
    VerificationCheckStatus,
    VerificationStatus,
)


FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "bank_name": ("bank name", "issuing bank", "bank"),
    "branch": ("branch", "issuing branch"),
    "reference_number": ("instrument number", "fdr number", "fd number", "reference number", "reference no", "fdr no"),
    "amount": ("amount", "principal amount", "deposit amount"),
    "issue_date": ("issue date", "date of issue"),
    "maturity_date": ("maturity date", "date of maturity", "due date"),
    "beneficiary": ("beneficiary", "in favor of", "in favour of"),
}


class OCRProvider(Protocol):
    """Local OCR adapter contract. OCR output remains an unverified candidate."""

    name: str

    def extract_text(self, file_path: Path) -> str: ...


class TesseractCLIProvider:
    """Optional local Tesseract OCR; sends rendered pages through stdin, no temp files."""

    name = "tesseract_local"

    def __init__(self, executable: str | None = None, *, max_pdf_pages: int = 5, timeout_seconds: int = 45):
        self.executable = executable or shutil.which("tesseract") or "tesseract"
        self.max_pdf_pages = max(1, min(max_pdf_pages, 10))
        self.timeout_seconds = timeout_seconds

    def _recognize_png(self, png_bytes: bytes) -> str:
        result = subprocess.run(
            [self.executable, "stdin", "stdout", "--psm", "6"],
            input=png_bytes, capture_output=True, timeout=self.timeout_seconds, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Tesseract OCR returned a non-zero exit status.")
        return result.stdout.decode("utf-8", errors="replace").strip()

    def extract_text(self, file_path: Path) -> str:
        if shutil.which(self.executable) is None and not Path(self.executable).is_file():
            raise RuntimeError("Tesseract is not installed or is not on PATH.")
        if file_path.suffix.lower() == ".pdf":
            chunks: list[str] = []
            with fitz.open(file_path) as pdf:
                for page in pdf[: self.max_pdf_pages]:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    chunks.append(self._recognize_png(pixmap.tobytes("png")))
            return "\n".join(part for part in chunks if part)
        with Image.open(file_path) as image:
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
            return self._recognize_png(buffer.getvalue())


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    match = re.search(rf"(?im)^\s*(?:{label_pattern})\s*(?:no\.?\s*)?[:#\-]\s*(.*?)\s*$", text)
    value = match.group(1).strip() if match else ""
    return value or None


def _normalize_candidate(field_name: str, value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if field_name in {"issue_date", "maturity_date"}:
        for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(cleaned, pattern).date().isoformat()
            except ValueError:
                continue
    if field_name == "amount":
        numeric = re.sub(r"(?i)(?:INR|RS\.?|RUPEES?)|[₹,\s]", "", cleaned)
        try:
            return format(Decimal(numeric).quantize(Decimal("0.01")), "f")
        except InvalidOperation:
            return cleaned
    if field_name == "reference_number":
        normalized = re.sub(r"[^A-Za-z0-9]", "", cleaned).upper()
        return normalized or cleaned
    return re.sub(r"\s+", " ", cleaned).strip().casefold()


def _declared_values(instrument: FDRInstrument) -> dict[str, str | None]:
    return {
        "bank_name": instrument.issuer_name,
        "branch": None,
        "reference_number": instrument.reference_original,
        "amount": format(instrument.amount, ".2f"),
        "issue_date": instrument.issue_date.isoformat(),
        "maturity_date": instrument.maturity_date.isoformat(),
        "beneficiary": instrument.beneficiary,
    }


def _compare(field_name: str, extracted: str | None, declared: str | None) -> bool | None:
    if extracted is None or declared is None:
        # Unknown/missing values are not mismatches.
        return None
    return _normalize_candidate(field_name, extracted) == _normalize_candidate(field_name, declared)


def _store_fields(
    session: Session,
    document: InstrumentDocument,
    instrument: FDRInstrument,
    text: str,
) -> tuple[int, int, list[str]]:
    declared_values = _declared_values(instrument)
    found_count = 0
    mismatch_count = 0
    mismatch_names: list[str] = []
    for field_name, labels in FIELD_LABELS.items():
        extracted_value = _extract_labeled_value(text, labels)
        match_value = _compare(field_name, extracted_value, declared_values[field_name])
        field = ExtractedDocumentField(
            document_id=document.id,
            field_name=field_name,
            extracted_value=extracted_value,
            declared_value=declared_values[field_name],
            value_status="found" if extracted_value is not None else "missing",
            matches_declared=match_value,
            # Regex candidates have no calibrated confidence score.
            confidence=None,
            data_origin=DataOrigin.EXTRACTED,
        )
        session.add(field)
        if extracted_value is not None:
            found_count += 1
        if match_value is False:
            mismatch_count += 1
            mismatch_names.append(field_name)
            existing = next(
                (
                    check.id
                    for check in session.scalars(
                        select(VerificationCheck).where(
                            VerificationCheck.instrument_id == instrument.id,
                            VerificationCheck.rule_code == "DOCUMENT_FIELD_MISMATCH",
                        )
                    )
                    if check.compared_values.get("document_id") == document.id
                    and check.compared_values.get("field_name") == field_name
                ),
                None,
            )
            if existing is None:
                session.add(
                    VerificationCheck(
                        instrument_id=instrument.id,
                        rule_code="DOCUMENT_FIELD_MISMATCH",
                        title=f"Document value differs: {field_name.replace('_', ' ')}",
                        explanation=(
                            "The extracted candidate differs from the institution-submitted value. "
                            "This is a review flag and does not establish error or fraud."
                        ),
                        compared_values={
                            "document_id": document.id,
                            "field_name": field_name,
                            "declared_value": declared_values[field_name],
                            "extracted_value": extracted_value,
                        },
                        status=VerificationCheckStatus.OPEN,
                        data_origin=DataOrigin.SYSTEM_GENERATED,
                    )
                )
    if mismatch_count:
        instrument.verification_status = VerificationStatus.DISCREPANCY_FLAGGED
    return found_count, mismatch_count, mismatch_names


def extract_document(
    session: Session,
    document: InstrumentDocument,
    file_path: Path,
    ocr_provider: OCRProvider | None = None,
) -> dict[str, Any]:
    """Extract text/candidates without changing institution-submitted instrument values."""
    instrument = document.instrument
    if document.content_type != "application/pdf":
        if ocr_provider is None:
            document.extraction_status = "ocr_required"
            document.extraction_method = "ocr_unavailable"
            document.extraction_error = "OCR is not configured; image contents were not interpreted."
            text = ""
        else:
            try:
                text = ocr_provider.extract_text(file_path)
                document.extraction_status = "completed" if text.strip() else "ocr_required"
                document.extraction_method = ocr_provider.name
                document.extraction_error = None if text.strip() else "OCR returned no text."
            except Exception:
                text = ""
                document.extraction_status = "failed"
                document.extraction_method = ocr_provider.name
                document.extraction_error = "OCR processing failed. The original file was preserved."
    else:
        try:
            with fitz.open(file_path, filetype="pdf") as pdf:
                text = "\n".join(page.get_text("text") for page in pdf)
            document.extracted_text = text
            minimum_text_chars = max(20, len(text.splitlines()) * 2)
            if len(re.sub(r"\s", "", text)) < minimum_text_chars:
                if ocr_provider is None:
                    document.extraction_status = "ocr_required"
                    document.extraction_method = "pymupdf_text"
                    document.extraction_error = "This PDF contains little or no extractable text; OCR is required."
                else:
                    try:
                        ocr_text = ocr_provider.extract_text(file_path)
                        if ocr_text.strip():
                            text = ocr_text
                            document.extraction_status = "completed"
                            document.extraction_method = ocr_provider.name
                            document.extraction_error = None
                        else:
                            document.extraction_status = "ocr_required"
                            document.extraction_method = ocr_provider.name
                            document.extraction_error = "OCR returned no text."
                    except Exception:
                        document.extraction_status = "failed"
                        document.extraction_method = ocr_provider.name
                        document.extraction_error = "OCR processing failed. The original file was preserved."
            else:
                document.extraction_status = "completed"
                document.extraction_method = "pymupdf_text_regex"
                document.extraction_error = None
        except Exception:
            document.extraction_status = "failed"
            document.extraction_method = "pymupdf_text"
            document.extraction_error = "PDF text extraction failed. The original file was preserved."
            text = ""

    found_count, mismatch_count, mismatch_names = _store_fields(session, document, instrument, text)
    return {
        "status": document.extraction_status,
        "method": document.extraction_method,
        "found_fields": found_count,
        "missing_fields": len(FIELD_LABELS) - found_count,
        "mismatch_count": mismatch_count,
        "mismatch_fields": mismatch_names,
        "text_characters": len(text),
    }
