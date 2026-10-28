"""Health and database readiness endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError(
            status_code=503,
            code="database_unavailable",
            message="The database is unavailable.",
        ) from exc
    return {"status": "ok", "database": "connected"}
