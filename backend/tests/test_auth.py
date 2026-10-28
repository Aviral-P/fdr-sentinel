"""Authentication, role authorization, and institution isolation tests."""

from datetime import date

import pytest
from fastapi import HTTPException

from app.api.dependencies import assert_roles, get_accessible_instrument
from app.core.security import hash_password
from app.core.config import get_settings
from app.models import FDRInstrument, Institution, Role, User
from scripts import seed_users as seed_users_module

DEMO_PASSWORD = "test-only-password-that-is-long-enough"


def test_dev_seed_users_creates_fictional_roles_without_printing_passwords(
    monkeypatch, test_session_factory, capsys
):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FDR_DEMO_PASSWORD", DEMO_PASSWORD)
    get_settings.cache_clear()
    monkeypatch.setattr(seed_users_module, "SessionLocal", test_session_factory)

    created_accounts = seed_users_module.seed_users()
    output = capsys.readouterr()
    with test_session_factory() as session:
        users = session.query(User).all()
        institutions = session.query(Institution).all()

    get_settings.cache_clear()
    assert len(created_accounts) == 9
    assert len(users) == 9
    assert len(institutions) == 5
    assert {user.role for user in users} == set(Role)
    assert all(user.password_hash.startswith("$argon2id$") for user in users)
    assert DEMO_PASSWORD not in output.out


def test_dev_user_seed_refuses_production_and_missing_password(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FDR_DEMO_PASSWORD", DEMO_PASSWORD)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="only be seeded"):
        seed_users_module.seed_users()

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("FDR_DEMO_PASSWORD")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="at least 12 characters"):
        seed_users_module.seed_users()
    get_settings.cache_clear()


def create_institution_user(session_factory, code: str, email: str, role: Role = Role.INSTITUTION_USER):
    with session_factory() as session:
        institution = Institution(code=code, name=f"Synthetic {code}")
        session.add(institution)
        session.flush()
        user = User(
            institution_id=institution.id,
            full_name="Synthetic Auth Test User",
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            role=role,
        )
        session.add(user)
        session.commit()
        return user.id, institution.id


def create_instrument(session_factory, institution_id: str, reference: str) -> str:
    with session_factory() as session:
        instrument = FDRInstrument(
            institution_id=institution_id,
            issuer_name="Synthetic Issuer",
            reference_original=reference,
            amount="1000.00",
            issue_date=date(2025, 1, 1),
            maturity_date=date(2027, 1, 1),
        )
        session.add(instrument)
        session.commit()
        return instrument.id


def login(client, email: str, password: str = DEMO_PASSWORD) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    assert "password_hash" not in response.json()
    return response.json()["access_token"]


def test_successful_login_me_and_logout_invalidates_token(auth_client, test_session_factory):
    user_id, _ = create_institution_user(test_session_factory, "AUTH-ONE", "one@example.invalid")

    token = login(auth_client, "one@example.invalid")
    headers = {"Authorization": f"Bearer {token}"}
    me_response = auth_client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["id"] == user_id
    assert me_response.json()["role"] == Role.INSTITUTION_USER.value
    assert "password_hash" not in me_response.json()

    logout_response = auth_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 204
    assert auth_client.get("/api/v1/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize(
    ("email", "password"),
    [("missing@example.invalid", DEMO_PASSWORD), ("one@example.invalid", "wrong-password")],
)
def test_invalid_credentials_are_rejected(auth_client, test_session_factory, email, password):
    create_institution_user(test_session_factory, "AUTH-ONE", "one@example.invalid")

    response = auth_client.post("/api/v1/auth/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email or password is incorrect."


def test_unauthenticated_requests_are_rejected(auth_client, test_session_factory):
    _, institution_id = create_institution_user(test_session_factory, "AUTH-ONE", "one@example.invalid")
    fdr_id = create_instrument(test_session_factory, institution_id, "AUTH-FDR-1")

    assert auth_client.get("/api/v1/auth/me").status_code == 401
    assert auth_client.post("/api/v1/auth/logout").status_code == 401
    assert auth_client.get(f"/api/v1/fdrs/{fdr_id}").status_code == 401


def test_institution_user_cannot_read_another_institutions_fdr_by_changing_id(
    auth_client, test_session_factory
):
    _, own_institution_id = create_institution_user(
        test_session_factory, "AUTH-ONE", "one@example.invalid"
    )
    _, other_institution_id = create_institution_user(
        test_session_factory, "AUTH-TWO", "two@example.invalid"
    )
    own_fdr = create_instrument(test_session_factory, own_institution_id, "AUTH-FDR-OWN")
    other_fdr = create_instrument(test_session_factory, other_institution_id, "AUTH-FDR-OTHER")
    token = login(auth_client, "one@example.invalid")
    headers = {"Authorization": f"Bearer {token}"}

    own_response = auth_client.get(f"/api/v1/fdrs/{own_fdr}", headers=headers)
    changed_id_response = auth_client.get(f"/api/v1/fdrs/{other_fdr}", headers=headers)

    assert own_response.status_code == 200
    assert own_response.json()["institution_id"] == own_institution_id
    assert changed_id_response.status_code == 404
    assert changed_id_response.json()["error"]["message"] == "FDR instrument not found."


def test_admin_has_explicit_global_read_access(auth_client, test_session_factory):
    create_institution_user(
        test_session_factory, "ADMIN-HOME", "admin@fdr-sentinel.invalid", role=Role.ADMIN
    )
    _, other_institution_id = create_institution_user(
        test_session_factory, "ADMIN-OTHER", "other@example.invalid"
    )
    other_fdr = create_instrument(test_session_factory, other_institution_id, "ADMIN-READ-FDR")
    token = login(auth_client, "admin@fdr-sentinel.invalid")

    response = auth_client.get(f"/api/v1/fdrs/{other_fdr}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["institution_id"] == other_institution_id


@pytest.mark.parametrize(
    ("role", "allowed", "expected_status"),
    [
        (Role.SCRUTINY_OFFICER, Role.SCRUTINY_OFFICER, 200),
        (Role.INSTITUTION_USER, Role.SCRUTINY_OFFICER, 403),
        (Role.APPROVING_AUTHORITY, Role.APPROVING_AUTHORITY, 200),
        (Role.AUDITOR, Role.APPROVING_AUTHORITY, 403),
        (Role.ADMIN, Role.APPROVING_AUTHORITY, 403),
        (Role.ADMIN, Role.ADMIN, 200),
    ],
)
def test_role_guards_are_exact_and_admin_permissions_are_explicit(role, allowed, expected_status):
    user = User(
        full_name="Synthetic Authorization User",
        email=f"{role.value}@example.invalid",
        password_hash="unused-in-this-test",
        role=role,
    )

    if expected_status == 200:
        assert assert_roles(user, allowed) is user
    else:
        with pytest.raises(HTTPException) as error:
            assert_roles(user, allowed)
        assert error.value.status_code == 403


def test_auditor_and_admin_can_read_records_but_institution_users_are_scoped(test_session_factory):
    with test_session_factory() as session:
        first = Institution(code="SCOPE-ONE", name="Synthetic One")
        second = Institution(code="SCOPE-TWO", name="Synthetic Two")
        session.add_all([first, second])
        session.flush()
        fdr = FDRInstrument(
            institution_id=second.id,
            issuer_name="Synthetic Issuer",
            reference_original="SCOPE-FDR",
            amount="1000.00",
            issue_date=date(2025, 1, 1),
            maturity_date=date(2027, 1, 1),
        )
        session.add(fdr)
        session.flush()

        for role in (Role.AUDITOR, Role.ADMIN):
            user = User(
                full_name=f"Synthetic {role.value}",
                email=f"{role.value}@scope.invalid",
                password_hash="unused-in-this-test",
                role=role,
            )
            assert get_accessible_instrument(fdr.id, user, session).id == fdr.id

        institution_user = User(
            institution_id=first.id,
            full_name="Synthetic Institution User",
            email="institution@scope.invalid",
            password_hash="unused-in-this-test",
            role=Role.INSTITUTION_USER,
        )
        with pytest.raises(HTTPException) as error:
            get_accessible_instrument(fdr.id, institution_user, session)
        assert error.value.status_code == 404
