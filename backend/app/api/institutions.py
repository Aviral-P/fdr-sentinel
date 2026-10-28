"""Institution and regulatory obligation endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.api import InstitutionDetail, InstitutionItem, Page
from app.schemas.models import RegulatoryObligationRead
from app.services.institution_service import get_institution, list_institutions, list_obligations

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.get("", response_model=Page[InstitutionItem])
def read_institutions(
    search: str | None = Query(default=None, max_length=120),
    active: bool | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[InstitutionItem]:
    items, total = list_institutions(db, user, search=search, active=active, limit=limit, offset=offset)
    return Page[InstitutionItem](items=items, total=total, limit=limit, offset=offset)


@router.get("/{institution_id}", response_model=InstitutionDetail)
def read_institution(
    institution_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InstitutionDetail:
    institution = get_institution(db, user, institution_id)
    obligations, _ = list_obligations(db, user, institution_id, limit=100, offset=0)
    return InstitutionDetail(
        **InstitutionItem.model_validate(institution).model_dump(),
        obligations=[RegulatoryObligationRead.model_validate(item) for item in obligations],
    )


@router.get("/{institution_id}/obligations", response_model=Page[RegulatoryObligationRead])
def read_obligations(
    institution_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[RegulatoryObligationRead]:
    items, total = list_obligations(db, user, institution_id, limit=limit, offset=offset)
    return Page[RegulatoryObligationRead](items=items, total=total, limit=limit, offset=offset)
