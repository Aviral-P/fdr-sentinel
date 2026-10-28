"""Private upload and download routes for FDR evidence."""

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_scrutiny_officer
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models import User
from app.schemas.api import (
    DocumentFieldReviewRequest,
    DocumentFieldReviewResponse,
    InstrumentDocumentItem,
)
from app.services.document_service import (
    get_downloadable_document,
    list_instrument_documents,
    review_document_field,
    upload_instrument_document,
)

router = APIRouter(tags=["documents"])


@router.post("/fdrs/{fdr_id}/documents", response_model=InstrumentDocumentItem, status_code=201)
async def upload_document(
    fdr_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read(get_settings().max_document_size_bytes + 1)
    if len(content) > get_settings().max_document_size_bytes:
        raise AppError(
            413,
            "document_too_large",
            f"The uploaded document exceeds the {get_settings().max_document_size_bytes}-byte limit.",
        )
    return upload_instrument_document(
        db,
        user,
        fdr_id,
        filename=file.filename,
        content_type=file.content_type,
        content=content,
    )


@router.get("/fdrs/{fdr_id}/documents", response_model=list[InstrumentDocumentItem])
def read_documents(
    fdr_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_instrument_documents(db, user, fdr_id)


@router.get("/documents/{document_id}/download", response_class=FileResponse)
def download_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document, path = get_downloadable_document(db, user, document_id)
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="attachment",
    )


@router.post(
    "/documents/{document_id}/fields/{field_name}/review",
    response_model=DocumentFieldReviewResponse,
)
def review_extracted_field(
    document_id: str,
    field_name: str,
    payload: DocumentFieldReviewRequest,
    user: User = Depends(require_scrutiny_officer()),
    db: Session = Depends(get_db),
):
    document, check, event = review_document_field(
        db,
        user,
        document_id,
        field_name,
        decision=payload.decision,
        comment=payload.comment,
    )
    return DocumentFieldReviewResponse(
        document_id=document.id,
        field_name=field_name,
        decision=payload.decision,
        verification_check_status=check.status.value,
        verification_event_id=event.id,
    )
