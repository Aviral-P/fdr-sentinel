"""Dashboard, reminder, report filtering, and export coverage."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    AuditEvent, FDRInstrument, Institution, IntegrityFinding, IntegrityFindingSeverity,
    IntegrityFindingType, InstrumentLifecycleStatus as Life, Notification,
    OperationalPriority, ReleaseRequest, Role, ReplacementType, User,
    VerificationCheck, VerificationCheckStatus,
)
from app.services.operations_service import (
    advance_matured_instruments, dashboard_summary, generate_maturity_reminders,
    generate_overdue_action_escalations,
)


def create_rows(factory, *, role=Role.ADMIN):
    today = date.today()
    with factory() as session:
        institution = Institution(code="OPS-ONE", name="Synthetic Ops Institute")
        session.add(institution)
        session.flush()
        user = User(
            institution_id=institution.id if role == Role.INSTITUTION_USER else None,
            full_name="Synthetic Operations User", email=f"ops-{role.value}@example.invalid",
            password_hash=hash_password("test-only-password-long-enough"), role=role,
        )
        session.add(user)
        session.flush()
        instruments = [
            FDRInstrument(institution_id=institution.id, issuer_name="Synthetic Issuer", reference_original="OPS-ACTIVE", amount=Decimal("1000.00"), issue_date=today - timedelta(days=100), maturity_date=today + timedelta(days=30), lifecycle_status=Life.APPROVED, priority=OperationalPriority.HIGH),
            FDRInstrument(institution_id=institution.id, issuer_name="Synthetic Issuer", reference_original="OPS-MATURED", amount=Decimal("2000.00"), issue_date=today - timedelta(days=300), maturity_date=today - timedelta(days=1), lifecycle_status=Life.APPROVED),
            FDRInstrument(institution_id=institution.id, issuer_name="Synthetic Issuer", reference_original="OPS-REVIEW", amount=Decimal("3000.00"), issue_date=today - timedelta(days=10), maturity_date=today + timedelta(days=100), lifecycle_status=Life.SUBMITTED),
        ]
        session.add_all(instruments)
        session.commit()
        return user.id, institution.id, [row.id for row in instruments]


def test_dashboard_date_boundaries_and_status_rules(test_session_factory):
    create_rows(test_session_factory)
    with test_session_factory() as session:
        result = dashboard_summary(session, session.get(User, session.scalar(select(User.id))), as_of=date.today())
    assert result["total_active_instruments"] == 3
    assert result["approaching_maturity"] == 1  # exactly the 30-day boundary is included
    assert result["matured_requiring_action"] == 1
    assert result["pending_scrutiny"] == 1


def test_maturity_reminder_is_deduplicated_and_tracks_due_date(monkeypatch, test_session_factory):
    get_settings.cache_clear()
    monkeypatch.setenv("MATURITY_REMINDER_WINDOWS_DAYS", "30,15,7")
    user_id, _, _ = create_rows(test_session_factory, role=Role.INSTITUTION_USER)
    with test_session_factory() as session:
        day = date.today()
        assert generate_maturity_reminders(session, today=day) == 1
        assert generate_maturity_reminders(session, today=day) == 0
        row = session.scalar(select(Notification))
        assert row.recipient_user_id == user_id
        assert row.reason == "maturity_30_days"
        assert row.due_date == day + timedelta(days=30)
        assert session.scalar(select(func.count(Notification.id))) == 1
    get_settings.cache_clear()



def test_scheduled_maturity_advancement_is_audited_and_idempotent(test_session_factory):
    _, _, instrument_ids = create_rows(test_session_factory)
    with test_session_factory() as session:
        current = date.today()
        # The fixture has one approved record that matured yesterday, one active
        # approved record that matures in 30 days, and one submitted record.
        assert advance_matured_instruments(session, today=current) == 1
        assert advance_matured_instruments(session, today=current) == 0
        matured = session.get(FDRInstrument, instrument_ids[1])
        not_yet_matured = session.get(FDRInstrument, instrument_ids[0])
        submitted = session.get(FDRInstrument, instrument_ids[2])
        assert matured.lifecycle_status == Life.MATURED
        assert not_yet_matured.lifecycle_status == Life.APPROVED
        assert submitted.lifecycle_status == Life.SUBMITTED
        events = list(session.scalars(select(AuditEvent).where(
            AuditEvent.entity_id == instrument_ids[1],
            AuditEvent.action == "instrument_maturity_status_advanced",
        )))
        assert len(events) == 1
        assert events[0].before_values["lifecycle_status"] == "approved"
        assert events[0].after_values["lifecycle_status"] == "matured"
        assert events[0].context["trigger"] == "scheduled_date_rule"

def test_dashboard_includes_findings_pending_renewal_release_and_unresolved(test_session_factory):
    _, _, instrument_ids = create_rows(test_session_factory)
    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.role == Role.ADMIN))
        review = session.get(FDRInstrument, instrument_ids[2])
        review.replacement_type = ReplacementType.RENEWAL
        review.supersedes_instrument_id = instrument_ids[0]
        session.add(VerificationCheck(
            instrument=review, rule_code="demo_required", title="Synthetic required check",
            explanation="Synthetic check remains open for dashboard testing.", status=VerificationCheckStatus.OPEN,
            is_required=True,
        ))
        session.add(IntegrityFinding(
            institution_id=review.institution_id, instrument_id=review.id,
            finding_type=IntegrityFindingType.AMOUNT_MISMATCH,
            severity=IntegrityFindingSeverity.MEDIUM, observed_values={"amount": "3000"},
            expected_values={"amount": "3500"}, explanation="Synthetic mismatch fixture.",
            rule_id="test_amount_rule", rule_version="1", dedupe_key="test-operations-finding",
        ))
        session.add(ReleaseRequest(
            instrument_id=instrument_ids[0], requested_amount=Decimal("1000.00"),
            reason="Synthetic dashboard test release.",
        ))
        session.commit()
        result = dashboard_summary(session, user, as_of=date.today())
    assert result["open_discrepancy_findings"] == 1
    assert result["renewals_replacements_pending_review"] == 1
    assert result["release_requests_pending_authorized_decision"] == 1
    assert result["unresolved_cases"] == 1


def test_notification_api_returns_and_marks_only_recipient_notifications(auth_client, test_session_factory):
    user_id, institution_id, instrument_ids = create_rows(test_session_factory, role=Role.INSTITUTION_USER)
    with test_session_factory() as session:
        other = User(
            institution_id=institution_id, full_name="Other Synthetic User", email="other-ops@example.invalid",
            password_hash=hash_password("test-only-password-long-enough"), role=Role.INSTITUTION_USER,
        )
        session.add(other)
        session.flush()
        instrument = session.get(FDRInstrument, instrument_ids[0])
        instrument.maturity_date = date.today() + timedelta(days=30)
        session.commit()
        other_email = other.email
        generate_maturity_reminders(session, today=date.today())
        notification = session.scalar(select(Notification).where(Notification.recipient_user_id == user_id))
        notification_id = notification.id
    own_login = auth_client.post("/api/v1/auth/login", json={"email": f"ops-institution_user@example.invalid", "password": "test-only-password-long-enough"})
    own_headers = {"Authorization": f"Bearer {own_login.json()['access_token']}"}
    listed = auth_client.get("/api/v1/notifications?unread_only=true", headers=own_headers)
    assert listed.status_code == 200 and listed.json()["total"] == 1
    marked = auth_client.post(f"/api/v1/notifications/{notification_id}/read", headers=own_headers)
    assert marked.status_code == 200 and marked.json()["notification"]["read_at"] is not None
    other_login = auth_client.post("/api/v1/auth/login", json={"email": other_email, "password": "test-only-password-long-enough"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    assert auth_client.post(f"/api/v1/notifications/{notification_id}/read", headers=other_headers).status_code == 404
def test_dashboard_institution_filter_and_cross_tenant_rejection(auth_client, test_session_factory):
    _, institution_id, _ = create_rows(test_session_factory, role=Role.INSTITUTION_USER)
    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.institution_id == institution_id))
        email = user.email
    response = auth_client.post("/api/v1/auth/login", json={"email": email, "password": "test-only-password-long-enough"})
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    summary = auth_client.get("/api/v1/dashboard/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total_active_instruments"] == 3
    assert auth_client.get("/api/v1/dashboard/summary?institution_id=elsewhere", headers=headers).status_code == 404


def test_report_filters_and_csv_export(auth_client, test_session_factory):
    create_rows(test_session_factory)
    with test_session_factory() as session:
        admin = session.scalar(select(User).where(User.role == Role.ADMIN))
        email = admin.email
    token_response = auth_client.post("/api/v1/auth/login", json={"email": email, "password": "test-only-password-long-enough"})
    headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
    filtered = auth_client.get("/api/v1/reports/instruments?priority=high", headers=headers)
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    csv_response = auth_client.get("/api/v1/reports/instruments.csv?priority=high", headers=headers)
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "OPS-ACTIVE" in csv_response.text
    assert "OPS-MATURED" not in csv_response.text



def test_overdue_escalations_notify_institution_and_internal_roles_once(monkeypatch, test_session_factory):
    get_settings.cache_clear()
    monkeypatch.setenv("ACTION_OVERDUE_DAYS", "7")
    institution_user_id, institution_id, instrument_ids = create_rows(test_session_factory, role=Role.INSTITUTION_USER)
    with test_session_factory() as session:
        internal = User(
            institution_id=None, full_name="Synthetic Scrutiny Officer", email="escalation-reviewer@example.invalid",
            password_hash=hash_password("test-only-password-long-enough"), role=Role.SCRUTINY_OFFICER,
        )
        session.add(internal)
        # Make the submitted case stale enough to trigger a workflow escalation.
        submitted = session.get(FDRInstrument, instrument_ids[2])
        submitted.updated_at = __import__("datetime").datetime.combine(date.today() - timedelta(days=8), __import__("datetime").time.min)
        session.commit()
        first = generate_overdue_action_escalations(session, today=date.today())
        second = generate_overdue_action_escalations(session, today=date.today())
        assert first >= 2  # institution account + internal reviewer for the overdue submitted case
        assert second == 0
        notifications = list(session.scalars(select(Notification).where(Notification.category == "overdue_escalation")))
        assert len(notifications) == first
        assert any(n.recipient_user_id == institution_user_id and n.reason == "workflow_action_overdue" for n in notifications)
        assert any(n.recipient_user_id == internal.id and n.reason == "workflow_action_overdue" for n in notifications)
        events = list(session.scalars(select(AuditEvent).where(
            AuditEvent.entity_id == instrument_ids[2], AuditEvent.action == "overdue_action_escalated"
        )))
        assert len(events) == 1
        assert events[0].context["trigger"] == "scheduled_overdue_rule"
    get_settings.cache_clear()


def test_overdue_escalation_skips_fresh_and_resolved_records(monkeypatch, test_session_factory):
    get_settings.cache_clear()
    monkeypatch.setenv("ACTION_OVERDUE_DAYS", "7")
    _, _, instrument_ids = create_rows(test_session_factory)
    with test_session_factory() as session:
        # Remove the fixture's intentionally matured approved instrument from the eligible set.
        session.get(FDRInstrument, instrument_ids[1]).lifecycle_status = Life.RELEASED
        session.commit()
        # The fresh submitted record is not overdue; released records are outside the eligible set.
        assert generate_overdue_action_escalations(session, today=date.today()) == 0
        submitted = session.get(FDRInstrument, instrument_ids[2])
        submitted.updated_at = __import__("datetime").datetime.combine(date.today() - timedelta(days=8), __import__("datetime").time.min)
        session.commit()
        assert generate_overdue_action_escalations(session, today=date.today()) > 0
        submitted.lifecycle_status = Life.REJECTED
        session.commit()
        assert generate_overdue_action_escalations(session, today=date.today()) == 0
    get_settings.cache_clear()
