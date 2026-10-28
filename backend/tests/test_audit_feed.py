"""Authorization, filtering, and redaction tests for the global audit feed."""

from datetime import datetime, timezone

from app.core.security import hash_password
from app.models import AuditEvent, Institution, Role, User

PASSWORD = "audit-test-password-long-enough"


def _make_user(session_factory, email, role, institution_id=None):
    with session_factory() as session:
        user = User(
            institution_id=institution_id, full_name="Synthetic Audit User", email=email,
            password_hash=hash_password(PASSWORD), role=role,
        )
        session.add(user)
        session.commit()
        return user.id


def _login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_global_audit_feed_is_internal_only_and_redacts_payloads(auth_client, test_session_factory):
    with test_session_factory() as session:
        institution = Institution(code="AUDIT-ORG", name="Synthetic Audit Institution")
        session.add(institution)
        session.flush()
        institution_id = institution.id
        session.add(AuditEvent(
            institution_id=institution_id, entity_type="fdr", entity_id="synthetic-fdr-id",
            action="updated", before_values={"amount": "100.00"},
            after_values={"amount": "200.00", "token": "must-not-leak"},
            context={}, created_at=datetime.now(timezone.utc),
        ))
        session.commit()
    _make_user(test_session_factory, "auditor@example.invalid", Role.AUDITOR)
    _make_user(test_session_factory, "institution@example.invalid", Role.INSTITUTION_USER, institution_id)

    auditor_headers = _login(auth_client, "auditor@example.invalid")
    response = auth_client.get("/api/v1/audit/events", headers=auditor_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["action"] == "updated"
    assert payload["items"][0]["institution_name"] == "Synthetic Audit Institution"
    assert "before_values" not in payload["items"][0]
    assert "after_values" not in payload["items"][0]

    institution_headers = _login(auth_client, "institution@example.invalid")
    denied = auth_client.get("/api/v1/audit/events", headers=institution_headers)
    assert denied.status_code == 403


def test_global_audit_feed_supports_filters_and_validates_date_range(auth_client, test_session_factory):
    _make_user(test_session_factory, "auditor@example.invalid", Role.AUDITOR)
    headers = _login(auth_client, "auditor@example.invalid")
    with test_session_factory() as session:
        session.add(AuditEvent(entity_type="fdr", entity_id="x", action="created", context={}, created_at=datetime(2026, 1, 1)))
        session.add(AuditEvent(entity_type="document", entity_id="y", action="uploaded", context={}, created_at=datetime(2026, 1, 2)))
        session.commit()
    response = auth_client.get("/api/v1/audit/events?entity_type=fdr&limit=1", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    invalid = auth_client.get("/api/v1/audit/events?date_from=2026-02-01&date_to=2026-01-01", headers=headers)
    assert invalid.status_code == 422
