import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LifecycleStatusBadge, OriginBadge, PriorityBadge, StatusBadge, VerificationStatusBadge } from './ui'

describe('status and provenance labels', () => {
  it('shows readable lifecycle state labels', () => {
    render(<StatusBadge status="clarification_required" />)
    expect(screen.getByText('Clarification Required')).toBeInTheDocument()
  })

  it('distinguishes extracted from officially reviewed evidence', () => {
    render(<><OriginBadge origin="extracted" /><OriginBadge origin="independently_verified" /></>)
    expect(screen.getByText('Extracted')).toBeInTheDocument()
    expect(screen.getByText('Officially reviewed')).toBeInTheDocument()
  })

  it('keeps lifecycle, verification and priority labels in separate visual categories', () => {
    render(<><LifecycleStatusBadge status="submitted" /><VerificationStatusBadge status="pending_review" /><PriorityBadge status="high" /></>)
    expect(screen.getByText('Submitted')).toHaveAttribute('data-status-category', 'lifecycle')
    expect(screen.getByText('Pending Review')).toHaveAttribute('data-status-category', 'verification')
    expect(screen.getByText('High')).toHaveAttribute('data-status-category', 'priority')
  })
})
