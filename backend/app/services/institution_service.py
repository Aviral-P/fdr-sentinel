"""Institution and obligation query services with tenant-aware filtering."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Institution, RegulatoryObligation, Role, User


READ_ROLES = {
    Role.INSTITUTION_USER,
    Role.SCRUTINY_OFFICER,
    Role.APPROVING_AUTHORITY,
    Role.AUDITOR,
    Role.ADMIN,
}


def list_institutions(
    session: Session,
    user: User,
    *,
    search: str | None,
    active: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Institution], int]:
    if user.role not in READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view institutions.")
    statement = select(Institution)
    count_statement = select(func.count(Institution.id))
    if user.role == Role.INSTITUTION_USER:
        if user.institution_id is None:
            return [], 0
        statement = statement.where(Institution.id == user.institution_id)
        count_statement = count_statement.where(Institution.id == user.institution_id)
    if active is not None:
        statement = statement.where(Institution.active.is_(active))
        count_statement = count_statement.where(Institution.active.is_(active))
    if search:
        pattern = f"%{search.strip()}%"
        criterion = or_(Institution.name.ilike(pattern), Institution.code.ilike(pattern))
        statement = statement.where(criterion)
        count_statement = count_statement.where(criterion)
    total = session.scalar(count_statement) or 0
    items = list(session.scalars(statement.order_by(Institution.name, Institution.id).limit(limit).offset(offset)))
    return items, total


def get_institution(session: Session, user: User, institution_id: str) -> Institution:
    if user.role not in READ_ROLES:
        raise AppError(403, "forbidden", "This role cannot view institutions.")
    statement = select(Institution).where(Institution.id == institution_id)
    if user.role == Role.INSTITUTION_USER:
        statement = statement.where(Institution.id == user.institution_id)
    institution = session.scalar(statement)
    if institution is None:
        raise AppError(404, "not_found", "Institution not found.")
    return institution


def list_obligations(
    session: Session,
    user: User,
    institution_id: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[RegulatoryObligation], int]:
    get_institution(session, user, institution_id)
    base = select(RegulatoryObligation).where(RegulatoryObligation.institution_id == institution_id)
    count = select(func.count(RegulatoryObligation.id)).where(RegulatoryObligation.institution_id == institution_id)
    total = session.scalar(count) or 0
    rows = list(session.scalars(base.order_by(RegulatoryObligation.due_date, RegulatoryObligation.code).limit(limit).offset(offset)))
    return rows, total
