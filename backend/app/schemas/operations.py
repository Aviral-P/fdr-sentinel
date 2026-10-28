"""Schemas for dashboard, action queue, reports, and in-app notifications."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import InstrumentLifecycleStatus, OperationalPriority
from app.schemas.api import FDRInstrumentItem


class DashboardSummary(BaseModel):
    as_of: date
    maturity_reminder_windows_days: list[int]
    total_active_instruments: int
    approaching_maturity: int
    matured_requiring_action: int
    pending_scrutiny: int
    open_discrepancy_findings: int
    renewals_replacements_pending_review: int
    release_requests_pending_authorized_decision: int
    overdue_actions: int
    unresolved_cases: int


class QueueItem(BaseModel):
    instrument: FDRInstrumentItem
    reasons: list[str]
    triggered_rules: list[str]
    days_to_maturity: int | None
    overdue: bool
    unresolved: bool
    evidence: list[dict[str, Any]]


class NotificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recipient_user_id: str
    title: str
    message: str
    category: str
    reason: str
    due_date: date | None
    read_at: datetime | None
    related_entity_type: str | None
    related_entity_id: str | None
    created_at: datetime


class NotificationReadResult(BaseModel):
    notification: NotificationItem


class ReportInstrumentRow(FDRInstrumentItem):
    institution_name: str


class UpcomingMaturityRow(BaseModel):
    instrument: FDRInstrumentItem
    institution_name: str
    days_to_maturity: int
    has_successor: bool


class PendingVerificationRow(BaseModel):
    instrument: FDRInstrumentItem
    institution_name: str
    open_required_checks: int
    open_findings: int


class ReleaseReportRow(BaseModel):
    id: str
    instrument_id: str
    institution_id: str
    institution_name: str
    requested_amount: str
    eligibility_status: str
    status: str
    reason: str
    created_at: datetime
    updated_at: datetime


class ReportFilters(BaseModel):
    institution_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    lifecycle_status: InstrumentLifecycleStatus | None = None
    priority: OperationalPriority | None = None



class AuditFeedItem(BaseModel):
    """Read-only, redacted summary of an audit event for authorized officials."""

    id: str
    actor_user_id: str | None
    actor_name: str | None
    institution_id: str | None
    institution_name: str | None
    entity_type: str
    entity_id: str
    action: str
    created_at: datetime
