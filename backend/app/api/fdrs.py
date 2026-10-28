"""FDR instrument and workflow endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    require_approving_authority,
    require_scrutiny_officer,
)
from app.db.session import get_db
from app.models import InstrumentLifecycleStatus, User, VerificationStatus
from app.schemas.api import (
    ClarificationResponseRequest,
    FDRInstrumentCreateRequest,
    FDRInstrumentItem,
    FDRInstrumentUpdateRequest,
    FinalDecisionRequest,
    InstrumentHistoryResponse,
    Page,
    ReleaseDecisionRequest,
    ReleaseDecisionResponse,
    ReleaseEligibilityResponse,
    ReleaseEvaluationResult,
    ReleaseRequestCreateRequest,
    ReleaseRequestCreated,
    ReleaseRequestItem,
    ScrutinyRequest,
    ScrutinyResult,
    SuccessorInstrumentCreateRequest,
)
from app.services.fdr_service import (
    create_instrument,
    get_instrument,
    get_instrument_history,
    list_instruments,
    update_instrument,
)
from app.services.release_service import (
    create_release_request,
    get_release_request,
    record_release_decision,
    reevaluate_release_request,
)
from app.services.workflow_service import (
    create_successor,
    record_final_decision,
    record_scrutiny,
    respond_to_clarification,
    submit_instrument,
)

router = APIRouter(tags=["FDR instruments"])


@router.post("/fdrs", response_model=FDRInstrumentItem, status_code=201)
def create_fdr(
    payload: FDRInstrumentCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_instrument(db, user, payload)


@router.patch("/fdrs/{fdr_id}", response_model=FDRInstrumentItem)
def update_fdr(
    fdr_id: str,
    payload: FDRInstrumentUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_instrument(db, user, fdr_id, payload)


@router.get("/fdrs", response_model=Page[FDRInstrumentItem])
def read_fdrs(
    institution_id: str | None = None,
    search: str | None = Query(default=None, max_length=120),
    lifecycle_status: InstrumentLifecycleStatus | None = None,
    verification_status: VerificationStatus | None = None,
    maturity_before: date | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = list_instruments(
        db,
        user,
        institution_id=institution_id,
        search=search,
        lifecycle_status=lifecycle_status,
        verification_status=verification_status,
        maturity_before=maturity_before,
        limit=limit,
        offset=offset,
    )
    return Page[FDRInstrumentItem](items=items, total=total, limit=limit, offset=offset)


@router.get("/fdrs/{fdr_id}", response_model=FDRInstrumentItem)
def read_fdr(
    fdr_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_instrument(db, user, fdr_id)


@router.get("/fdrs/{fdr_id}/history", response_model=InstrumentHistoryResponse)
def read_fdr_history(
    fdr_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InstrumentHistoryResponse(instrument_id=fdr_id, events=get_instrument_history(db, user, fdr_id))


@router.post("/fdrs/{fdr_id}/submit", response_model=FDRInstrumentItem)
def submit_fdr(
    fdr_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return submit_instrument(db, user, fdr_id)


@router.post("/fdrs/{fdr_id}/scrutiny", response_model=ScrutinyResult)
def scrutiny_action(
    fdr_id: str,
    payload: ScrutinyRequest,
    user: User = Depends(require_scrutiny_officer()),
    db: Session = Depends(get_db),
):
    instrument, event = record_scrutiny(db, user, fdr_id, payload)
    return ScrutinyResult(instrument=instrument, event_id=event.id, outcome=payload.outcome)


@router.post(
    "/fdrs/{fdr_id}/clarifications/{clarification_event_id}/respond",
    response_model=FDRInstrumentItem,
)
def respond_clarification(
    fdr_id: str,
    clarification_event_id: str,
    payload: ClarificationResponseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return respond_to_clarification(db, user, fdr_id, clarification_event_id, payload.response)


@router.post("/fdrs/{fdr_id}/decision", response_model=FDRInstrumentItem)
def final_decision(
    fdr_id: str,
    payload: FinalDecisionRequest,
    user: User = Depends(require_approving_authority()),
    db: Session = Depends(get_db),
):
    return record_final_decision(db, user, fdr_id, payload)


@router.post("/fdrs/{fdr_id}/successors", response_model=FDRInstrumentItem, status_code=201)
def create_fdr_successor(
    fdr_id: str,
    payload: SuccessorInstrumentCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_successor(db, user, fdr_id, payload)


@router.post(
    "/fdrs/{fdr_id}/release-requests",
    response_model=ReleaseRequestCreated,
    status_code=201,
)
def submit_release_request(
    fdr_id: str,
    payload: ReleaseRequestCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request, eligibility = create_release_request(db, user, fdr_id, payload)
    return ReleaseRequestCreated(request=request, eligibility=eligibility)


@router.get("/release-requests/{request_id}", response_model=ReleaseRequestItem)
def read_release_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_release_request(db, user, request_id)


@router.post("/release-requests/{request_id}/evaluate", response_model=ReleaseEvaluationResult)
def evaluate_release_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request, eligibility = reevaluate_release_request(db, user, request_id)
    return ReleaseEvaluationResult(request=request, eligibility=eligibility)


@router.post("/release-requests/{request_id}/decision", response_model=ReleaseDecisionResponse)
def decide_release_request(
    request_id: str,
    payload: ReleaseDecisionRequest,
    user: User = Depends(require_approving_authority()),
    db: Session = Depends(get_db),
):
    request, approval = record_release_decision(db, user, request_id, payload)
    return ReleaseDecisionResponse(request=request, approval=approval)
