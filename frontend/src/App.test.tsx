import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import {
  fetchHealth,
  HEALTH_SERVICE,
  type HealthResponse,
} from './lib/api/health'

vi.mock('./lib/api/health', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./lib/api/health')>()

  return {
    ...actual,
    fetchHealth: vi.fn(),
  }
})

const connectedResponse: HealthResponse = {
  status: 'ok',
  service: HEALTH_SERVICE,
}
const mockedFetchHealth = vi.mocked(fetchHealth)

describe('Longtian public opinion application', () => {
  beforeEach(() => {
    mockedFetchHealth.mockReset()
  })

  it('renders the initial route through the application providers', async () => {
    mockedFetchHealth.mockResolvedValue(connectedResponse)

    render(<App />)

    expect(
      screen.getByRole('heading', { name: /舆情值守.*从连通开始。/ }),
    ).toBeInTheDocument()
    expect(await screen.findByText('后端已连接')).toBeInTheDocument()
    expect(mockedFetchHealth).toHaveBeenCalledTimes(1)
  })

  it('allows an unavailable health check to be retried', async () => {
    const user = userEvent.setup()
    mockedFetchHealth
      .mockRejectedValueOnce(new Error('无法连接本机后端服务'))
      .mockResolvedValueOnce(connectedResponse)

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '无法连接本机后端服务',
    )

    await user.click(screen.getByRole('button', { name: '重新检测' }))

    expect(await screen.findByText('后端已连接')).toBeInTheDocument()
    expect(mockedFetchHealth).toHaveBeenCalledTimes(2)
  })
})
