import { describe, expect, it } from 'vitest'
import { canCreateSuccessor, findUnansweredClarification } from './workflowUi'
import type { HistoryEvent, Instrument } from '../types/api'

function historyEvent(id: string, action: string, related_event_id: string | null, occurred_at: string): HistoryEvent {
  return { id, source: 'workflow', occurred_at, actor_user_id: 'synthetic-user', action, from_status: 'submitted', to_status: action === 'clarification_requested' ? 'clarification_required' : 'submitted', summary: null, related_event_id, change_summary: null }
}

describe('workflow UI helpers', () => {
  it('selects the latest unanswered clarification rather than reusing an answered request', () => {
    const first = historyEvent('request-1', 'clarification_requested', null, '2026-10-24T10:00:00Z')
    const response = historyEvent('response-1', 'clarification_responded', first.id, '2026-10-24T11:00:00Z')
    const second = historyEvent('request-2', 'clarification_requested', null, '2026-10-25T10:00:00Z')

    expect(findUnansweredClarification([first, response, second])?.id).toBe('request-2')
    expect(findUnansweredClarification([first, response])).toBeUndefined()
  })

  it('allows a permitted successor to create the next link in a renewal chain', () => {
    const base = { id: 'successor', institution_id: 'institution', lifecycle_status: 'approved', supersedes_instrument_id: 'predecessor' } as Instrument
    expect(canCreateSuccessor('institution_user', base)).toBe(true)
    expect(canCreateSuccessor('auditor', base)).toBe(false)
    expect(canCreateSuccessor('institution_user', { ...base, lifecycle_status: 'draft' })).toBe(false)
  })
})
