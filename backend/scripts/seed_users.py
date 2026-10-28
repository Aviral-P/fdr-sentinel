"""Create fictional local-development accounts without storing credentials in source."""

import os
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import DataOrigin, Institution, Role, User


def stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"fdr-sentinel-demo:{kind}:{key}"))


def seed_users() -> list[tuple[str, Role]]:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise RuntimeError("Demo accounts can only be seeded with APP_ENV=development.")
    password = os.environ.get("FDR_DEMO_PASSWORD", "")
    if len(password) < 12:
        raise RuntimeError("Set FDR_DEMO_PASSWORD to a local password of at least 12 characters.")

    accounts: list[tuple[str, str, Role, str | None]] = [
        (f"institution{number:02d}@fdr-sentinel.invalid", f"Synthetic Institution User {number}",
         Role.INSTITUTION_USER, f"SYN-IIT-{number:02d}")
        for number in range(1, 6)
    ]
    accounts.extend(
        [
            ("reviewer@fdr-sentinel.invalid", "Synthetic Scrutiny Officer", Role.SCRUTINY_OFFICER, None),
            ("approver@fdr-sentinel.invalid", "Synthetic Approving Authority", Role.APPROVING_AUTHORITY, None),
            ("auditor@fdr-sentinel.invalid", "Synthetic Auditor", Role.AUDITOR, None),
            ("admin@fdr-sentinel.invalid", "Synthetic Local Administrator", Role.ADMIN, None),
        ]
    )

    with SessionLocal() as session:
        institutions: dict[str, Institution] = {}
        for number in range(1, 6):
            code = f"SYN-IIT-{number:02d}"
            institution = session.scalar(select(Institution).where(Institution.code == code))
            if institution is None:
                institution = Institution(
                    id=stable_id("institution", str(number)),
                    code=code,
                    name=f"Synthetic Institute of Applied Studies {number}",
                    address=f"Demo District {number}, Fictionland",
                    data_origin=DataOrigin.SYNTHETIC_DEMO,
                )
                session.add(institution)
            institutions[code] = institution
        session.flush()

        for email, full_name, role, institution_code in accounts:
            institution = institutions.get(institution_code) if institution_code else None
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    id=stable_id("demo-user", email),
                    email=email,
                    full_name=full_name,
                    role=role,
                    institution=institution,
                    active=True,
                    data_origin=DataOrigin.SYNTHETIC_DEMO,
                )
                session.add(user)
            user.password_hash = hash_password(password)
            user.institution = institution
            user.role = role
            user.full_name = full_name
            user.active = True
            user.data_origin = DataOrigin.SYNTHETIC_DEMO
        session.commit()

    return [(email, role) for email, _, role, _ in accounts]


def main() -> None:
    accounts = seed_users()
    print("Fictional development accounts are ready (password is read from FDR_DEMO_PASSWORD):")
    for email, role in accounts:
        print(f"  {email} — {role.value}")
    print("These accounts are for local development only; no passwords are printed.")


if __name__ == "__main__":
    main()
