import type { HistoryEvent, Instrument, Role } from '../types/api'

export function findUnansweredClarification(events: HistoryEvent[]): HistoryEvent | undefined {
  const answeredRequestIds = new Set(
    events
      .filter(event => event.source === 'workflow' && event.action === 'clarification_responded' && event.related_event_id)
      .map(event => event.related_event_id as string),
  )
  return [...events].reverse().find(event =>
    event.source === 'workflow' &&
    event.action === 'clarification_requested' &&
    event.to_status === 'clarification_required' &&
    !answeredRequestIds.has(event.id),
  )
}

export function canCreateSuccessor(role: Role | undefined, instrument: Instrument): boolean {
  return role === 'institution_user' && ['approved', 'matured'].includes(instrument.lifecycle_status)
}
