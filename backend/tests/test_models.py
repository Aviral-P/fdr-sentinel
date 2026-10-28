"""Schema constraints, relationships, and deterministic demo seed tests."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    AuditEvent,
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    Institution,
    InstrumentDocument,
    InstrumentLifecycleStatus,
    OperationalPriority,
    ReleaseRequest,
    ReleaseRequestStatus,
    ReplacementType,
    Role,
    User,
    VerificationStatus,
    VerificationCheck,
)
from app.schemas.models import FDRInstrumentCreate
from scripts.seed_demo import seed_demo


def make_institution(session, code="TEST-INST"):
    institution = Institution(code=code, name="Synthetic Test Institution")
    session.add(institution)
    session.flush()
    return institution


def make_instrument(institution_id, **overrides):
    values = {
        "institution_id": institution_id,
        "issuer_name": "Synthetic Issuer",
        "reference_original": " syn- 0001/a ",
        "amount": Decimal("125000.50"),
        "issue_date": date(2025, 1, 1),
        "maturity_date": date(2027, 1, 1),
    }
    values.update(overrides)
    return FDRInstrument(**values)


def test_instrument_preserves_original_and_normalizes_reference(test_session_factory):
    with test_session_factory() as session:
        institution = make_institution(session)
        instrument = make_instrument(institution.id)
        session.add(instrument)
        session.commit()

        assert instrument.reference_original == "syn- 0001/a"
        assert instrument.reference_normalized == "SYN0001A"
        assert instrument.amount == Decimal("125000.50")
        assert instrument.lifecycle_status == InstrumentLifecycleStatus.DRAFT
        assert instrument.verification_status == VerificationStatus.NOT_CHECKED
        assert instrument.priority == OperationalPriority.NORMAL


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": Decimal("0.00")},
        {"amount": Decimal("-1.00")},
        {"maturity_date": date(2024, 12, 31)},
        {"reference_original": "---"},
    ],
)
def test_instrument_model_rejects_invalid_amount_date_or_reference(test_session_factory, overrides):
    with test_session_factory() as session:
        institution = make_institution(session)
        with pytest.raises(ValueError):
            make_instrument(institution.id, **overrides)


def test_pydantic_schema_validates_amount_scale_and_date_order():
    required = {
        "institution_id": "institution-id",
        "issuer_name": "Synthetic Issuer",
        "reference_original": "SYN-001",
        "amount": Decimal("100.00"),
        "issue_date": date(2025, 1, 2),
        "maturity_date": date(2026, 1, 2),
    }
    assert FDRInstrumentCreate(**required).amount == Decimal("100.00")
    with pytest.raises(ValueError):
        FDRInstrumentCreate(**{**required, "amount": Decimal("100.001")})
    with pytest.raises(ValueError):
        FDRInstrumentCreate(**{**required, "maturity_date": date(2025, 1, 1)})


def test_database_rejects_invalid_amount_and_date_order(test_session_factory):
    with test_session_factory() as session:
        institution = make_institution(session)
        with pytest.raises(IntegrityError):
            session.execute(
                insert(FDRInstrument.__table__).values(
                    id="10000000-0000-0000-0000-000000000001",
                    institution_id=institution.id,
                    issuer_name="Synthetic Issuer",
                    reference_original="BAD-AMOUNT",
                    reference_normalized="BADAMOUNT",
                    amount=0,
                    issue_date=date(2025, 1, 1),
                    maturity_date=date(2026, 1, 1),
                    lifecycle_status="draft",
                    verification_status="not_checked",
                    priority="normal",
                    data_origin="synthetic_demo",
                    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            )
        session.rollback()

        with pytest.raises(IntegrityError):
            session.execute(
                insert(FDRInstrument.__table__).values(
                    id="10000000-0000-0000-0000-000000000002",
                    institution_id=institution.id,
                    issuer_name="Synthetic Issuer",
                    reference_original="BAD-DATE",
                    reference_normalized="BADDATE",
                    amount=100,
                    issue_date=date(2026, 1, 1),
                    maturity_date=date(2025, 1, 1),
                    lifecycle_status="draft",
                    verification_status="not_checked",
                    priority="normal",
                    data_origin="synthetic_demo",
                    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            )


def test_unique_institution_code_and_user_email_are_enforced(test_session_factory):
    with test_session_factory() as session:
        institution = make_institution(session)
        session.commit()
        session.add(Institution(code="TEST-INST", name="Duplicate Code"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        user = User(
            institution_id=institution.id,
            full_name="Synthetic Test User",
            email="test@example.invalid",
            password_hash="not-a-real-password-hash",
            role=Role.INSTITUTION_USER,
        )
        session.add(user)
        session.commit()
        session.add(
            User(
                institution_id=institution.id,
                full_name="Another Synthetic User",
                email="test@example.invalid",
                password_hash="not-a-real-password-hash",
                role=Role.INSTITUTION_USER,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_instrument_supports_multiple_documents_and_fields(test_session_factory):
    with test_session_factory() as session:
        institution = make_institution(session)
        instrument = make_instrument(institution.id)
        instrument.documents = [
            InstrumentDocument(
                original_filename=f"synthetic-{index}.pdf",
                storage_key=f"synthetic/{index}.pdf",
                content_type="application/pdf",
                size_bytes=100,
                sha256_checksum=f"{index:064x}",
                data_origin=DataOrigin.SYNTHETIC_DEMO,
            )
            for index in (1, 2)
        ]
        session.add(instrument)
        session.commit()

        loaded = session.get(FDRInstrument, instrument.id)
        assert len(loaded.documents) == 2
        field = ExtractedDocumentField(
            document=loaded.documents[0],
            field_name="reference_number",
            extracted_value="SYN-EXTRACTED",
            declared_value=loaded.reference_original,
            matches_declared=False,
        )
        session.add(field)
        session.commit()
        assert loaded.documents[0].fields[0].matches_declared is False


def test_audit_events_cannot_be_updated_or_deleted_via_orm(test_session_factory):
    with test_session_factory() as session:
        event = AuditEvent(entity_type="test", entity_id="one", action="created")
        session.add(event)
        session.commit()
        event.action = "rewritten"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()

        event = session.scalar(select(AuditEvent))
        session.delete(event)
        with pytest.raises(ValueError, match="append-only"):
            session.flush()


def snapshot_demo(session_factory):
    with session_factory() as session:
        summary = seed_demo(session)
        rows = session.execute(
            select(
                FDRInstrument.id,
                FDRInstrument.reference_original,
                FDRInstrument.reference_normalized,
                FDRInstrument.amount,
                FDRInstrument.lifecycle_status,
                FDRInstrument.verification_status,
                FDRInstrument.priority,
                FDRInstrument.data_origin,
            ).order_by(FDRInstrument.id)
        ).all()
        status_counts = dict(
            session.query(FDRInstrument.lifecycle_status, func.count(FDRInstrument.id))
            .group_by(FDRInstrument.lifecycle_status)
            .all()
        )
        return summary, rows, status_counts


def test_seed_is_reproducible_and_covers_requested_scenarios(test_session_factory):
    summary_1, rows_1, statuses_1 = snapshot_demo(test_session_factory)
    summary_2, rows_2, statuses_2 = snapshot_demo(test_session_factory)

    assert summary_1 == summary_2
    assert len(rows_1) == len(rows_2) == 30
    assert rows_1 == rows_2
    assert statuses_1 == statuses_2
    assert summary_1["institutions"] == 5
    assert summary_1["instruments"] == 30
    assert sum(1 for row in rows_1 if row.data_origin == DataOrigin.SYNTHETIC_DEMO) == 30
    assert {InstrumentLifecycleStatus.MATURED, InstrumentLifecycleStatus.SUPERSEDED,
            InstrumentLifecycleStatus.RELEASE_PENDING, InstrumentLifecycleStatus.DRAFT} <= set(statuses_1)
    assert VerificationStatus.DISCREPANCY_FLAGGED in {row.verification_status for row in rows_1}
    duplicated = [row.reference_normalized for row in rows_1]
    assert duplicated.count("SYNDUP0007") == 2
    assert {InstrumentLifecycleStatus.APPROVED, InstrumentLifecycleStatus.CLARIFICATION_REQUIRED,
            InstrumentLifecycleStatus.UNDER_SCRUTINY} & set(statuses_1)


def test_seed_links_renewals_and_contains_reviewable_discrepancy_and_release_cases(test_session_factory):
    with test_session_factory() as session:
        seed_demo(session)
        instruments = session.scalars(select(FDRInstrument)).all()
        renewal_children = [item for item in instruments if item.replacement_type == ReplacementType.RENEWAL]
        assert len(renewal_children) == 4
        assert all(item.supersedes is not None for item in renewal_children)
        assert all(item.supersedes.successor.id == item.id for item in renewal_children)

        assert session.scalar(select(func.count()).select_from(VerificationCheck)) == 3
        assert session.scalar(
            select(func.count()).select_from(ReleaseRequest).where(ReleaseRequest.status == ReleaseRequestStatus.PENDING)
        ) == 3
        assert session.scalar(
            select(func.count()).select_from(FDRInstrument).where(
                FDRInstrument.lifecycle_status == InstrumentLifecycleStatus.APPROVED,
                FDRInstrument.maturity_date <= date(2026, 11, 14),
            )
        ) >= 1
