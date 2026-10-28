"""Seed deterministic, clearly labeled fictional demonstration records."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AuditEvent,
    DataOrigin,
    ExtractedDocumentField,
    FDRInstrument,
    Institution,
    InstrumentDocument,
    InstrumentLifecycleStatus,
    Notification,
    ObligationStatus,
    OperationalPriority,
    RegulatoryObligation,
    RegulatoryRule,
    ReleaseRequest,
    ReleaseRequestStatus,
    ReplacementType,
    Role,
    User,
    VerificationCheck,
    VerificationCheckStatus,
    VerificationEvent,
    VerificationStatus,
)

SEED_LABEL = "Synthetic demo data — fictional institution and issuer; not independently verified."
SEED_TIME = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 24)


def stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"fdr-sentinel-demo:{kind}:{key}"))


def _add_once(session: Session, obj) -> None:
    if session.get(type(obj), obj.id) is None:
        session.add(obj)


def seed_demo(session: Session) -> dict[str, int]:
    """Insert a stable synthetic dataset; safe to rerun without duplicates."""
    institutions: list[Institution] = []
    for number in range(1, 6):
        institution = Institution(
            id=stable_id("institution", str(number)),
            code=f"SYN-IIT-{number:02d}",
            name=f"Synthetic Institute of Applied Studies {number}",
            address=f"Demo District {number}, Fictionland",
            active=True,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, institution)
        institutions.append(institution)
    session.flush()

    users: list[User] = []
    roles = [Role.INSTITUTION_USER, Role.SCRUTINY_OFFICER, Role.APPROVING_AUTHORITY, Role.AUDITOR]
    for number, role in enumerate(roles, start=1):
        user = User(
            id=stable_id("user", role.value),
            institution_id=institutions[number - 1].id if role == Role.INSTITUTION_USER else None,
            full_name=f"Synthetic Demo {role.value.replace('_', ' ').title()}",
            email=f"{role.value}@example.invalid",
            password_hash="synthetic-seed-user-has-no-login-credential",
            role=role,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, user)
        users.append(user)
    session.flush()
    institution_user = users[0]

    obligations: list[RegulatoryObligation] = []
    for index, institution in enumerate(institutions, start=1):
        obligation = RegulatoryObligation(
            id=stable_id("obligation", str(index)),
            institution_id=institution.id,
            code=f"SYN-OBL-{index:02d}",
            title=f"Synthetic deposit obligation {index}",
            description=SEED_LABEL,
            effective_date=date(2025, 1, 1),
            due_date=date(2027, 3, 31),
            required_amount=Decimal("500000.00"),
            status=ObligationStatus.OPEN,
            priority=OperationalPriority.NORMAL,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, obligation)
        obligations.append(obligation)
    session.flush()

    rule = RegulatoryRule(
        id=stable_id("rule", "minimum-amount"),
        institution_id=None,
        code="SYN-MIN-AMOUNT",
        title="Synthetic minimum amount example",
        description="Demonstration rule only; replace with reviewed local policy before use.",
        rule_config={"field": "amount", "operator": "gte", "value": "500000.00", "demo": True},
        version=1,
        active=True,
        created_at=SEED_TIME,
        updated_at=SEED_TIME,
    )
    _add_once(session, rule)
    session.flush()

    categories = [
        ("active", InstrumentLifecycleStatus.APPROVED, VerificationStatus.REVIEWED, OperationalPriority.NORMAL, 730),
        ("approaching_maturity", InstrumentLifecycleStatus.APPROVED, VerificationStatus.REVIEWED, OperationalPriority.HIGH, 21),
        ("matured", InstrumentLifecycleStatus.MATURED, VerificationStatus.NOT_CHECKED, OperationalPriority.URGENT, -10),
        ("renewal_old", InstrumentLifecycleStatus.SUPERSEDED, VerificationStatus.REVIEWED, OperationalPriority.NORMAL, -15),
        ("renewal_new", InstrumentLifecycleStatus.APPROVED, VerificationStatus.REVIEWED, OperationalPriority.NORMAL, 720),
        ("incomplete", InstrumentLifecycleStatus.DRAFT, VerificationStatus.NOT_CHECKED, OperationalPriority.HIGH, 300),
        ("discrepancy", InstrumentLifecycleStatus.UNDER_SCRUTINY, VerificationStatus.DISCREPANCY_FLAGGED, OperationalPriority.HIGH, 365),
        ("release_pending", InstrumentLifecycleStatus.RELEASE_PENDING, VerificationStatus.REVIEWED, OperationalPriority.NORMAL, 90),
    ]
    instruments: list[FDRInstrument] = []
    instrument_by_index: dict[int, FDRInstrument] = {}
    for index in range(1, 31):
        category, status, verification, priority, days_to_maturity = categories[(index - 1) % len(categories)]
        institution = institutions[(index - 1) % len(institutions)]
        # Deliberate normalized duplicate: two different instruments share a reference.
        reference = "SYN-DUP-0007" if index in (7, 19) else f"SYN-FDR-{index:04d}"
        predecessor = stable_id("instrument", str(index - 1)) if category == "renewal_new" else None
        instrument = FDRInstrument(
            id=stable_id("instrument", str(index)),
            institution_id=institution.id,
            obligation_id=obligations[(index - 1) % len(obligations)].id,
            submitted_by_user_id=institution_user.id,
            supersedes_instrument_id=predecessor,
            replacement_type=ReplacementType.RENEWAL if predecessor else None,
            issuer_name=f"Synthetic Issuer {((index - 1) % 5) + 1}",
            reference_original=reference,
            amount=Decimal("650000.00") + Decimal(index * 1000),
            issue_date=date(2025, 1, 1) + timedelta(days=index),
            maturity_date=TODAY + timedelta(days=days_to_maturity),
            lifecycle_status=status,
            verification_status=verification,
            priority=priority,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            notes=f"{SEED_LABEL} Scenario: {category}.",
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        if category == "renewal_new":
            instrument.reference_original = f"SYN-FDR-RENEWAL-{index:02d}"
        if category == "incomplete":
            instrument.notes += " Supporting evidence is intentionally absent in this draft scenario."
        _add_once(session, instrument)
        instruments.append(instrument)
        instrument_by_index[index] = instrument

    # One synthetic metadata-only document and declared/extracted mismatch per flagged record.
    for index in (7, 15, 23):
        instrument = instrument_by_index[index]
        document = InstrumentDocument(
            id=stable_id("document", str(index)),
            instrument_id=instrument.id,
            uploaded_by_user_id=institution_user.id,
            original_filename=f"synthetic-demo-evidence-{index:02d}.pdf",
            storage_key=f"synthetic-demo/{index:02d}/evidence.pdf",
            content_type="application/pdf",
            size_bytes=1024 + index,
            sha256_checksum=f"{index:064x}",
            extraction_status="demo_fixture_only",
            extraction_method="synthetic_fixture",
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, document)
        field = ExtractedDocumentField(
            id=stable_id("extracted-field", str(index)),
            document_id=document.id,
            field_name="reference_number",
            extracted_value=f"SYN-EXTRACTED-MISMATCH-{index:02d}",
            declared_value=instrument.reference_original,
            matches_declared=False,
            confidence=Decimal("0.9300"),
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, field)
        check = VerificationCheck(
            id=stable_id("verification-check", str(index)),
            instrument_id=instrument.id,
            rule_code="SYN-DECLARED-EXTRACTED-MISMATCH",
            title="Synthetic declared/extracted reference mismatch",
            explanation="Synthetic fixture only: extracted example value differs from the declared value; human review required.",
            compared_values={"declared": instrument.reference_original, "extracted": field.extracted_value},
            status=VerificationCheckStatus.OPEN,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, check)
        event = VerificationEvent(
            id=stable_id("verification-event", str(index)),
            check_id=check.id,
            actor_user_id=None,
            action="synthetic_flag_created",
            comment="Generated from synthetic demo values; this is not a fraud or authenticity determination.",
            event_metadata={"seed_label": SEED_LABEL},
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, event)

    for index in (8, 16, 24):
        instrument = instrument_by_index[index]
        request = ReleaseRequest(
            id=stable_id("release-request", str(index)),
            instrument_id=instrument.id,
            requested_by_user_id=institution_user.id,
            requested_amount=instrument.amount,
            eligibility_status="pending_manual_review",
            eligibility_findings={"demo": True, "checks": ["maturity", "obligation_status"]},
            status=ReleaseRequestStatus.PENDING,
            reason=f"{SEED_LABEL} No release action is executed by seed data.",
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, request)

    for index, user in enumerate(users, start=1):
        notification = Notification(
            id=stable_id("notification", str(index)),
            recipient_user_id=user.id,
            title="Synthetic demo queue item",
            message=SEED_LABEL,
            category="demo",
            related_entity_type="fdr_instrument",
            related_entity_id=instruments[index - 1].id,
            data_origin=DataOrigin.SYNTHETIC_DEMO,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        _add_once(session, notification)

    audit = AuditEvent(
        id=stable_id("audit", "seed-created"),
        actor_user_id=None,
        institution_id=None,
        entity_type="demo_dataset",
        entity_id="fdr-sentinel-demo-v1",
        action="synthetic_seed_created",
        before_values=None,
        after_values={"institutions": 5, "instruments": 30},
        context={"label": SEED_LABEL},
        data_origin=DataOrigin.SYNTHETIC_DEMO,
        created_at=SEED_TIME,
    )
    _add_once(session, audit)
    session.commit()

    return {
        "institutions": len(institutions),
        "users": len(users),
        "obligations": len(obligations),
        "instruments": len(instruments),
        "documents": 3,
        "mismatched_fields": 3,
        "release_requests": 3,
    }


def main() -> None:
    with SessionLocal() as session:
        counts = seed_demo(session)
    print("Synthetic demo data seeded (fictional; no real bank confirmations):")
    for name, count in counts.items():
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
