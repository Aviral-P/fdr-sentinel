export type Role = 'institution_user' | 'scrutiny_officer' | 'approving_authority' | 'auditor' | 'admin'
export type LifecycleStatus = 'draft' | 'submitted' | 'under_scrutiny' | 'clarification_required' | 'approved' | 'rejected' | 'release_pending' | 'released' | 'matured' | 'superseded'
export type VerificationStatus = 'not_checked' | 'pending_review' | 'discrepancy_flagged' | 'reviewed'
export type Priority = 'low' | 'normal' | 'high' | 'urgent'
export type FindingSeverity = 'low' | 'medium' | 'high' | 'critical'
export type FindingType = 'exact_file_duplicate' | 'repeated_reference' | 'near_duplicate_document' | 'amount_mismatch' | 'beneficiary_mismatch' | 'date_inconsistency' | 'missing_required_document' | 'maturity_without_successor' | 'replacement_lineage_conflict' | 'release_conditions_unresolved'
export type ReplacementType = 'renewal' | 'replacement'
export type Decision = 'approved' | 'rejected' | 'returned'
export type DataOrigin = 'user_submitted' | 'extracted' | 'system_generated' | 'independently_verified' | 'synthetic_demo'

export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface User { id: string; institution_id: string | null; full_name: string; email: string; role: Role; active: boolean; created_at: string }
export interface TokenResponse { access_token: string; token_type: string; expires_in: number }
export interface Institution { id: string; code: string; name: string; address: string | null; active: boolean; data_origin: DataOrigin; created_at: string; updated_at: string }
export interface Obligation { id: string; institution_id: string | null; code: string; title: string; description: string | null; effective_date: string; due_date: string | null; required_amount: string | null; status: string; priority: Priority; data_origin: DataOrigin; created_at: string; updated_at: string }
export interface InstitutionDetail extends Institution { obligations: Obligation[] }
export interface Instrument {
  id: string; institution_id: string; obligation_id: string | null; submitted_by_user_id: string | null; supersedes_instrument_id: string | null; successor_instrument_id: string | null; replacement_type: ReplacementType | null;
  issuer_name: string; beneficiary: string | null; reference_original: string; reference_normalized: string; amount: string; issue_date: string; maturity_date: string;
  lifecycle_status: LifecycleStatus; verification_status: VerificationStatus; priority: Priority; data_origin: DataOrigin; notes: string | null; created_at: string; updated_at: string
}
export interface HistoryEvent { id: string; source: 'workflow' | 'audit'; occurred_at: string; actor_user_id: string | null; action: string; from_status: LifecycleStatus | null; to_status: LifecycleStatus | null; summary: string | null; related_event_id: string | null; change_summary: Record<string, unknown> | null }
export interface InstrumentHistory { instrument_id: string; events: HistoryEvent[] }
export interface ExtractedField { id: string; field_name: string; extracted_value: string | null; declared_value: string | null; value_status: 'found' | 'missing'; matches_declared: boolean | null; confidence: string | null; data_origin: DataOrigin }
export interface Document { id: string; instrument_id: string; uploaded_by_user_id: string | null; original_filename: string; content_type: string; size_bytes: number; sha256_checksum: string; original_available: boolean; extraction_status: 'not_started' | 'processing' | 'completed' | 'ocr_required' | 'failed' | 'unavailable'; extraction_method: string | null; extraction_error: string | null; created_at: string; updated_at: string; fields: ExtractedField[] }
export interface IntegrityFinding { id: string; institution_id: string; instrument_id: string; related_instrument_id: string | null; document_id: string | null; related_document_id: string | null; release_request_id: string | null; finding_type: FindingType; severity: FindingSeverity; data_origin: string; observed_values: Record<string, unknown>; expected_values: Record<string, unknown>; explanation: string; rule_id: string; rule_version: string; detected_at: string; review_status: string; reviewed_by_user_id: string | null; reviewed_at: string | null; resolution_notes: string | null; is_current: boolean }
export interface IntegrityQueueItem { finding: IntegrityFinding; priority_score: number; ranking_reasons: string[]; deadline_days_remaining: number | null; supporting_evidence: Record<string, unknown>; ranking_notice: string }
export interface Dashboard { as_of: string; maturity_reminder_windows_days: number[]; total_active_instruments: number; approaching_maturity: number; matured_requiring_action: number; pending_scrutiny: number; open_discrepancy_findings: number; renewals_replacements_pending_review: number; release_requests_pending_authorized_decision: number; overdue_actions: number; unresolved_cases: number }
export interface QueueItem { instrument: Instrument; reasons: string[]; triggered_rules: string[]; days_to_maturity: number | null; overdue: boolean; unresolved: boolean; evidence: Record<string, unknown>[] }
export interface Notification { id: string; recipient_user_id: string; title: string; message: string; category: string; reason: string; due_date: string | null; read_at: string | null; related_entity_type: string | null; related_entity_id: string | null; created_at: string }
export interface ReportInstrument extends Instrument { institution_name: string }
export interface ReleaseReportRow { id: string; instrument_id: string; institution_id: string; institution_name: string; requested_amount: string; eligibility_status: string; status: 'pending' | 'approved' | 'rejected' | 'returned'; reason: string; created_at: string; updated_at: string }
export interface UpcomingMaturity { instrument: Instrument; institution_name: string; days_to_maturity: number; has_successor: boolean }
export interface PendingVerification { instrument: Instrument; institution_name: string; open_required_checks: number; open_findings: number }
export interface ReleaseRequest { id: string; instrument_id: string; requested_by_user_id: string | null; requested_amount: string; eligibility_status: string; eligibility_findings: Record<string, unknown>; status: 'pending' | 'approved' | 'rejected' | 'returned'; reason: string; created_at: string; updated_at: string }
export interface ReleaseEligibility { release_request_id: string; eligible: boolean; eligibility_status: string; findings: { code: string; severity: string; message: string }[]; rules_applied: Record<string, unknown>; evaluated_at: string }
export interface ApiErrorBody { error?: { code?: string; message?: string; details?: unknown } }
export interface CreateInstrumentRequest { institution_id: string; obligation_id?: string | null; issuer_name: string; beneficiary?: string | null; reference_original: string; amount: string; issue_date: string; maturity_date: string; notes?: string | null }
export interface UpdateInstrumentRequest { obligation_id?: string | null; issuer_name?: string; beneficiary?: string | null; reference_original?: string; amount?: string; issue_date?: string; maturity_date?: string; notes?: string | null }
export interface ScrutinyRequest { outcome: 'request_clarification' | 'recommend_approval' | 'recommend_rejection'; comment?: string | null; clarification_question?: string | null }
export interface ScrutinyResult { instrument: Instrument; event_id: string; outcome: ScrutinyRequest['outcome'] }
export interface FinalDecisionRequest { decision: 'approved' | 'rejected'; rationale: string }
export interface SuccessorInstrumentRequest { replacement_type: ReplacementType; obligation_id?: string | null; issuer_name: string; beneficiary?: string | null; reference_original: string; amount: string; issue_date: string; maturity_date: string; notes?: string | null }
export interface ReleaseRequestCreateRequest { requested_amount: string; reason: string }
export interface ReleaseRequestCreated { request: ReleaseRequest; eligibility: ReleaseEligibility }
export interface ReleaseDecisionResponse { request: ReleaseRequest; approval: { id: string; release_request_id: string; approver_user_id: string; decision: Decision; rationale: string; disposition: string; created_at: string; updated_at: string } }
export interface FieldReviewRequest { decision: 'confirm_discrepancy' | 'dismiss_discrepancy' | 'needs_clarification'; comment: string }
export interface FieldReviewResponse { document_id: string; field_name: string; decision: FieldReviewRequest['decision']; verification_check_status: 'open' | 'reviewed' | 'dismissed'; verification_event_id: string }


export interface AuditFeedItem {
  id: string; actor_user_id: string | null; actor_name: string | null;
  institution_id: string | null; institution_name: string | null;
  entity_type: string; entity_id: string; action: string; created_at: string;
}
