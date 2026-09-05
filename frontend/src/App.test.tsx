import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
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
  startPlatformConnectionAttempt,
  type PlatformConnection,
  type PlatformConnectionsResponse,
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

  it('shows login guidance when the native browser needs user action', async () => {
    mockedFetchPlatformConnections.mockResolvedValue(
      catalog({
        status: 'action_required',
        guidance: 'complete_login',
        active_attempt_id: attemptId,
      }),
    )
    renderRoute('/platform-accounts')
    expect(await screen.findByText('需要操作')).toBeVisible()
    expect(
      screen.getByText('请在应用打开的专用谷歌浏览器中登录微博。'),
    ).toBeVisible()
  })

  it('disables controls while the local service is unavailable', async () => {
    mockedFetchHealth.mockRejectedValueOnce(new Error('offline'))
    renderRoute('/platform-accounts')
    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('应用服务暂时不可用，请重新启动应用。')
    expect(screen.getByRole('button', { name: '检查状态' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '一键检测' })).toBeDisabled()
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
    const batchButton = await screen.findByRole('button', { name: '一键检测' })
    await waitFor(() => expect(batchButton).toBeEnabled())
    await user.click(batchButton)
    await waitFor(() =>
      expect(mockedStartAttempt).toHaveBeenCalledExactlyOnceWith(
        'wb',
        expect.any(AbortSignal),
      ),
    )
    expect(screen.getByRole('status')).toHaveTextContent('正在检测微博 · 1/1')
    expect(screen.getByRole('button', { name: '检测中…' })).toBeDisabled()
    resolveAttempt?.({
      attempt_id: attemptId,
      platform: connection({
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })
  })

  it('keeps a connection conflict visible without starting another operation', async () => {
    const user = userEvent.setup()
    mockedStartAttempt.mockRejectedValue(
      new PlatformConnectionApiError(
        '已有平台连接任务正在运行，请完成后再试。',
        'connection_attempt_active',
        409,
      ),
    )
    renderRoute('/platform-accounts')
    await user.click(await screen.findByRole('button', { name: '检查状态' }))
    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('已有平台连接任务正在运行，请完成后再试。')
  })
})
