import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { appRoutes } from './app/router'
import weiboLogo from './assets/platforms/weibo.svg'
import { fetchAISettings } from './lib/api/ai-settings'
import {
  fetchHealth,
  HEALTH_SERVICE,
  type HealthResponse,
} from './lib/api/health'
import { fetchMediaPolicy } from './lib/api/media-cache'
import {
  fetchMonitoringRules,
  type MonitoringRulesResponse,
} from './lib/api/monitoring-rules'
import {
  fetchPlatformConnections,
  PlatformConnectionApiError,
  openManagedBrowser,
  startPlatformConnectionAttempt,
  type PlatformConnection,
  type PlatformConnectionsResponse,
  type PlatformId,
} from './lib/api/platform-connections'
import { fetchSearchRuns } from './lib/api/search-runs'

vi.mock('./lib/api/health', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/api/health')>()),
  fetchHealth: vi.fn(),
}))
vi.mock('./lib/api/ai-settings', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/api/ai-settings')>()),
  fetchAISettings: vi.fn(),
}))
vi.mock('./lib/api/media-cache', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/api/media-cache')>()),
  fetchMediaPolicy: vi.fn(),
}))
vi.mock('./lib/api/platform-connections', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/api/platform-connections')>()),
  fetchPlatformConnections: vi.fn(),
  openManagedBrowser: vi.fn(),
  startPlatformConnectionAttempt: vi.fn(),
}))
vi.mock('./lib/api/monitoring-rules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/api/monitoring-rules')>()),
  fetchMonitoringRules: vi.fn(),
}))
vi.mock('./lib/api/search-runs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/api/search-runs')>()),
  fetchSearchRuns: vi.fn(),
}))

const connectedResponse: HealthResponse = {
  status: 'ok',
  service: HEALTH_SERVICE,
}
const monitoringRulesResponse: MonitoringRulesResponse = {
  rules: [
    {
      id: 1,
      name: '龙田街道及四个社区',
      monitoring_objects: ['龙田街道', '龙田社区'],
      issue_keywords: [],
      terms: ['龙田街道', '龙田社区'],
      enabled: true,
    },
  ],
}
const attemptId = '2efb05b0-b1f7-4bbb-8b9f-9effa11cd355'

function connection(
  values: Partial<PlatformConnection> = {},
): PlatformConnection {
  return {
    platform: 'wb',
    display_name: '微博',
    availability: 'enabled',
    status: 'not_checked',
    guidance: 'none',
    last_checked_at: null,
    active_attempt_id: null,
    ...values,
  }
}

function catalog(
  values: Partial<PlatformConnection> = {},
): PlatformConnectionsResponse {
  return { platforms: [connection(values)] }
}

const mockedFetchHealth = vi.mocked(fetchHealth)
const mockedFetchAISettings = vi.mocked(fetchAISettings)
const mockedFetchMediaPolicy = vi.mocked(fetchMediaPolicy)
const mockedFetchPlatformConnections = vi.mocked(fetchPlatformConnections)
const mockedOpenManagedBrowser = vi.mocked(openManagedBrowser)
const mockedStartAttempt = vi.mocked(startPlatformConnectionAttempt)
const mockedFetchMonitoringRules = vi.mocked(fetchMonitoringRules)
const mockedFetchSearchRuns = vi.mocked(fetchSearchRuns)

function renderRoute(initialEntry = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [initialEntry],
  })
  return {
    router,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

function getConnectionPanel() {
  const panel = screen
    .getByText('登录状态', { exact: true })
    .closest<HTMLElement>('[data-slot="card"]')
  if (!panel) throw new Error('Platform connection panel was not rendered')
  return panel
}

describe('Longtian public opinion application', () => {
  beforeEach(() => {
    mockedFetchHealth.mockReset().mockResolvedValue(connectedResponse)
    mockedFetchAISettings.mockReset().mockResolvedValue({
      base_url: null,
      model: null,
      has_api_key: false,
      revision: 0,
    })
    mockedFetchMediaPolicy.mockReset().mockResolvedValue({
      retention_days: 30,
      capacity_mib: 1024,
      revision: 0,
      reserved_bytes: 0,
      files: 0,
      pending_files: 0,
    })
    mockedFetchPlatformConnections.mockReset().mockResolvedValue(catalog())
    mockedOpenManagedBrowser.mockReset().mockResolvedValue({
      outcome: 'opened_homepage',
    })
    mockedStartAttempt.mockReset().mockResolvedValue({
      attempt_id: attemptId,
      platform: connection({
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })
    mockedFetchMonitoringRules
      .mockReset()
      .mockResolvedValue(monitoringRulesResponse)
    mockedFetchSearchRuns
      .mockReset()
      .mockResolvedValue({ runs: [], next_before_id: null })
  })

  it('opens platform accounts directly from the application root', async () => {
    const { router } = renderRoute()
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/platform-accounts'),
    )
    expect(
      screen.getByRole('heading', { name: '平台账号', level: 1 }),
    ).toBeInTheDocument()
    expect(await screen.findByText('微博')).toBeInTheDocument()
    expect(screen.queryByText('抖音')).toBeNull()
    expect(screen.queryByText('快手')).toBeNull()
    expect(screen.queryByText('小红书')).toBeNull()
    expect(screen.queryByText('今日头条')).toBeNull()
  })

  it('keeps reports as one destination and settings as one unified page', async () => {
    const user = userEvent.setup()
    const { router } = renderRoute()
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/platform-accounts'),
    )
    const navigation = screen.getByRole('navigation', { name: '主导航' })
    expect(
      within(navigation)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual([
      '平台账号',
      '监控规则',
      '舆情爬取',
      '舆情报告',
      '自动任务',
      '设置',
    ])
    expect(
      within(navigation).getByRole('link', { name: '舆情报告' }),
    ).toHaveAttribute('href', '/reports')
    await user.click(within(navigation).getByRole('link', { name: '设置' }))
    expect(
      await screen.findByRole('heading', { name: '设置', level: 1 }),
    ).toBeVisible()
    expect(
      screen.getByRole('heading', { name: 'AI 配置', level: 2 }),
    ).toBeVisible()
    expect(
      screen.getByRole('heading', { name: '媒体缓存', level: 2 }),
    ).toBeVisible()
    expect(router.state.location.pathname).toBe('/settings')
  })

  it('redirects legacy settings paths to the unified settings page', async () => {
    const { router } = renderRoute('/settings/media?source=legacy')
    await waitFor(() =>
      expect(router.state.location).toMatchObject({
        pathname: '/settings',
        search: '?source=legacy',
        hash: '#media',
      }),
    )
  })

  it('renders only the Weibo connection and its logo', async () => {
    renderRoute('/platform-accounts')
    const row = (await screen.findByText('微博')).closest('li')
    expect(row).not.toBeNull()
    expect(row?.querySelector('img')).toHaveAttribute('src', weiboLogo)
    expect(screen.getAllByRole('button', { name: '检查状态' })).toHaveLength(1)
    expect(screen.getAllByText('待检查')).toHaveLength(1)
  })

  it('shows a clear not-logged-in instruction after a status check', async () => {
    mockedFetchPlatformConnections.mockResolvedValue(
      catalog({
        status: 'disconnected',
        guidance: 'retry',
      }),
    )
    renderRoute('/platform-accounts')
    expect(await screen.findByText('未登录')).toBeVisible()
    expect(
      screen.getByText('尚未登录，请在专用浏览器中登录后重新检查。'),
    ).toBeVisible()
  })

  it('does not let a legacy waiting status permanently block a new check', async () => {
    mockedFetchPlatformConnections.mockResolvedValue(
      catalog({
        status: 'action_required',
        guidance: 'complete_login',
        active_attempt_id: attemptId,
      }),
    )
    renderRoute('/platform-accounts')
    const retry = await screen.findByRole('button', { name: '重新检查' })
    expect(retry).toBeEnabled()
    expect(screen.getByRole('button', { name: '检查全部' })).toBeEnabled()
  })

  it('opens the dedicated browser without starting a status check', async () => {
    const user = userEvent.setup()
    renderRoute('/platform-accounts')
    await user.click(
      await screen.findByRole('button', { name: '打开专用浏览器' }),
    )
    await waitFor(() =>
      expect(mockedOpenManagedBrowser).toHaveBeenCalledExactlyOnceWith(
        undefined,
        expect.any(AbortSignal),
      ),
    )
    expect(mockedStartAttempt).not.toHaveBeenCalled()
  })

  it('opens a platform homepage without starting its status check', async () => {
    const user = userEvent.setup()
    renderRoute('/platform-accounts')
    await user.click(await screen.findByRole('button', { name: '打开平台' }))
    await waitFor(() =>
      expect(mockedOpenManagedBrowser).toHaveBeenCalledExactlyOnceWith(
        'wb',
        expect.any(AbortSignal),
      ),
    )
    expect(mockedStartAttempt).not.toHaveBeenCalled()
  })

  it('disables controls while the local service is unavailable', async () => {
    mockedFetchHealth.mockRejectedValueOnce(new Error('offline'))
    renderRoute('/platform-accounts')
    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('应用服务暂时不可用，请重新启动应用。')
    expect(screen.getByRole('button', { name: '检查状态' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '检查全部' })).toBeDisabled()
    expect(
      screen.getByRole('button', { name: '打开专用浏览器' }),
    ).toBeDisabled()
  })

  it('runs batch detection for Weibo only and prevents overlapping starts', async () => {
    const user = userEvent.setup()
    let resolveAttempt:
      | ((value: { attempt_id: string; platform: PlatformConnection }) => void)
      | undefined
    mockedStartAttempt.mockReturnValue(
      new Promise((resolve) => {
        resolveAttempt = resolve
      }),
    )
    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', { name: '检查全部' })
    await waitFor(() => expect(batchButton).toBeEnabled())
    await user.click(batchButton)
    await waitFor(() =>
      expect(mockedStartAttempt).toHaveBeenCalledExactlyOnceWith(
        'wb',
        expect.any(AbortSignal),
      ),
    )
    expect(screen.getByRole('status')).toHaveTextContent('正在检测微博 · 1/1')
    expect(screen.getByRole('button', { name: '检查中…' })).toBeDisabled()
    resolveAttempt?.({
      attempt_id: attemptId,
      platform: connection({
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })
  })

  it('ends a stalled batch at the bounded five-platform deadline', async () => {
    mockedStartAttempt.mockReturnValue(new Promise(() => undefined))
    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', { name: '检查全部' })

    vi.useFakeTimers()
    try {
      fireEvent.click(batchButton)
      await act(async () => {
        await Promise.resolve()
      })
      act(() => {
        vi.advanceTimersByTime(100_001)
      })
      expect(screen.getByText('检查失败，请稍后重试。')).toBeVisible()
      expect(screen.getByRole('button', { name: '检查状态' })).toBeEnabled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps a newer batch alive when an older request settles late', async () => {
    let rejectFirst: ((error: Error) => void) | undefined
    let rejectSecond: ((error: Error) => void) | undefined
    mockedStartAttempt
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectFirst = reject
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectSecond = reject
          }),
      )
    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', { name: '检查全部' })

    vi.useFakeTimers()
    try {
      fireEvent.click(batchButton)
      await act(async () => {
        await Promise.resolve()
      })
      expect(mockedStartAttempt).toHaveBeenCalledTimes(1)

      act(() => {
        vi.advanceTimersByTime(100_001)
      })
      expect(screen.getByText('检查失败，请稍后重试。')).toBeVisible()

      fireEvent.click(screen.getByRole('button', { name: '检查全部' }))
      await act(async () => {
        await Promise.resolve()
      })
      expect(mockedStartAttempt).toHaveBeenCalledTimes(2)
      expect(screen.getByRole('status')).toHaveTextContent('正在检测微博 · 1/1')

      await act(async () => {
        rejectFirst?.(new Error('late failure'))
        await Promise.resolve()
      })
      expect(screen.getByRole('status')).toHaveTextContent('正在检测微博 · 1/1')
    } finally {
      rejectSecond?.(new Error('cleanup'))
      vi.useRealTimers()
    }
  })

  it('continues the batch after a platform-scoped start error', async () => {
    mockedStartAttempt.mockRejectedValueOnce(
      new PlatformConnectionApiError(
        '该平台暂未接入。',
        'platform_not_available',
        409,
      ),
    )
    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', { name: '检查全部' })
    await userEvent.setup().click(batchButton)
    await waitFor(() => expect(mockedStartAttempt).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '检查全部' })).toBeEnabled(),
    )
    expect(screen.getByText('该平台暂未接入。')).toBeVisible()
  })

  it('checks all enabled platforms in the catalog order', async () => {
    const order: PlatformId[] = ['wb', 'dy', 'ks', 'xhs', 'toutiao']
    const names: Record<PlatformId, string> = {
      wb: '微博',
      dy: '抖音',
      ks: '快手',
      xhs: '小红书',
      toutiao: '今日头条',
    }
    const statuses: Record<PlatformId, 'not_checked' | 'connected'> = {
      wb: 'not_checked',
      dy: 'not_checked',
      ks: 'not_checked',
      xhs: 'not_checked',
      toutiao: 'not_checked',
    }
    const started: PlatformId[] = []
    mockedFetchPlatformConnections.mockImplementation(async () => ({
      platforms: order.map((platform) =>
        connection({
          platform,
          display_name: names[platform],
          status: statuses[platform],
          guidance: 'none',
        }),
      ),
    }))
    mockedStartAttempt.mockImplementation(async (platform) => {
      const id = `2efb05b0-b1f7-4bbb-8b9f-9effa11cd35${started.length}`
      started.push(platform)
      statuses[platform] = 'connected'
      return {
        attempt_id: id,
        platform: connection({
          platform,
          display_name: names[platform],
          status: 'checking',
          active_attempt_id: id,
        }),
      }
    })

    const user = userEvent.setup()
    renderRoute('/platform-accounts')
    await user.click(await screen.findByRole('button', { name: '检查全部' }))
    await waitFor(() => expect(started).toEqual(order))
    expect(screen.getByRole('button', { name: '检查全部' })).toBeEnabled()
  })

  it('ends a batch when the status service becomes unavailable', async () => {
    mockedFetchPlatformConnections
      .mockReset()
      .mockResolvedValueOnce(catalog())
      .mockRejectedValueOnce(
        new PlatformConnectionApiError(
          '无法连接本地服务，请确认服务已启动。',
          'service_unavailable',
        ),
      )
    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', { name: '检查全部' })
    fireEvent.click(batchButton)
    await waitFor(() =>
      expect(
        screen.getByText('无法连接本地服务，请确认服务已启动。'),
      ).toBeVisible(),
    )
    expect(screen.getByRole('button', { name: '检查全部' })).toBeEnabled()
  })

  it('keeps a connection conflict visible without starting another operation', async () => {
    const user = userEvent.setup()
    mockedStartAttempt.mockRejectedValue(
      new PlatformConnectionApiError(
        '专用浏览器正在执行任务，请稍后检查。',
        'connection_attempt_active',
        409,
      ),
    )
    renderRoute('/platform-accounts')
    await user.click(await screen.findByRole('button', { name: '检查状态' }))
    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('专用浏览器正在执行任务，请稍后检查。')
  })
})
