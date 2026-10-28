import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const { login } = vi.hoisted(() => ({ login: vi.fn() }))
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ login }) }))

import { LoginPage } from './LoginPage'

describe('login page smoke flow', () => {
  beforeEach(() => { login.mockReset().mockResolvedValue(undefined) })

  it('submits credentials through the auth provider and navigates after success', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<h1>Authenticated dashboard</h1>} />
        </Routes>
      </MemoryRouter>,
    )

    await user.type(screen.getByLabelText('Email address'), 'reviewer@fdr-sentinel.invalid')
    await user.type(screen.getByLabelText('Password'), 'synthetic-demo-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(login).toHaveBeenCalledWith('reviewer@fdr-sentinel.invalid', 'synthetic-demo-password')
    expect(await screen.findByRole('heading', { name: 'Authenticated dashboard' })).toBeInTheDocument()
  })
})
