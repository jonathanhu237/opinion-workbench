import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { appRoutes } from './app/router'
import douyinLogo from './assets/platforms/douyin.svg'
import kuaishouLogo from './assets/platforms/kuaishou.svg'
import toutiaoLogo from './assets/platforms/toutiao.svg'
import weiboLogo from './assets/platforms/weibo.svg'
import xiaohongshuLogo from './assets/platforms/xiaohongshu.svg'
import { fetchAISettings } from './lib/api/ai-settings'
import {
  fetchHealth,
  HEALTH_SERVICE,
  type HealthResponse,
} from './lib/api/health'
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
import { fetchWorkbench } from './lib/api/workbench'
import { workbenchFixture } from './lib/api/workbench.fixtures'

vi.mock('./lib/api/health', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./lib/api/health')>()

  return {
    ...actual,
    fetchHealth: vi.fn(),
  }
})

vi.mock('./lib/api/ai-settings', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./lib/api/ai-settings')>()
  return { ...actual, fetchAISettings: vi.fn() }
})

vi.mock('./lib/api/platform-connections', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('./lib/api/platform-connections')>()

  return {
    ...actual,
    fetchPlatformConnections: vi.fn(),
    startPlatformConnectionAttempt: vi.fn(),
  }
})

vi.mock('./lib/api/monitoring-rules', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('./lib/api/monitoring-rules')>()

  return {
    ...actual,
    fetchMonitoringRules: vi.fn(),
  }
})

vi.mock('./lib/api/search-runs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./lib/api/search-runs')>()

  return {
    ...actual,
    fetchSearchRuns: vi.fn(),
  }
})

vi.mock('./lib/api/workbench', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./lib/api/workbench')>()
  return { ...actual, fetchWorkbench: vi.fn() }
})

const connectedResponse: HealthResponse = {
  status: 'ok',
  service: HEALTH_SERVICE,
}
const monitoringRulesResponse: MonitoringRulesResponse = {
  rules: [
    {
      id: 1,
      name: '龙田街道及四个社区',
      monitoring_objects: [
        '龙田街道',
        '龙田社区',
        '老坑社区',
        '竹坑社区',
        '南布社区',
      ],
      issue_keywords: [],
      terms: ['龙田街道', '龙田社区', '老坑社区', '竹坑社区', '南布社区'],
      enabled: true,
    },
  ],
}
const attemptId = '2efb05b0-b1f7-4bbb-8b9f-9effa11cd355'

function connection(
  values: Partial<PlatformConnection> &
    Pick<PlatformConnection, 'platform' | 'display_name'>,
): PlatformConnection {
  return {
    availability: 'enabled',
    status: 'not_checked',
    guidance: 'none',
    last_checked_at: null,
    active_attempt_id: null,
    ...values,
  }
}

function catalog(
  weibo: Partial<PlatformConnection> = {},
  kuaishou: Partial<PlatformConnection> = {},
  douyin: Partial<PlatformConnection> = {},
  toutiao: Partial<PlatformConnection> = {},
  xiaohongshu: Partial<PlatformConnection> = {},
): PlatformConnectionsResponse {
  return {
    platforms: [
      connection({ platform: 'wb', display_name: '微博', ...weibo }),
      connection({
        platform: 'dy',
        display_name: '抖音',
        ...douyin,
      }),
      connection({
        platform: 'ks',
        display_name: '快手',
        ...kuaishou,
      }),
      connection({
        platform: 'xhs',
        display_name: '小红书',
        ...xiaohongshu,
      }),
      connection({
        platform: 'toutiao',
        display_name: '今日头条',
        ...toutiao,
      }),
    ],
  }
}

const mockedFetchHealth = vi.mocked(fetchHealth)
const mockedFetchAISettings = vi.mocked(fetchAISettings)
const mockedFetchPlatformConnections = vi.mocked(fetchPlatformConnections)
const mockedStartAttempt = vi.mocked(startPlatformConnectionAttempt)
const mockedFetchMonitoringRules = vi.mocked(fetchMonitoringRules)
const mockedFetchSearchRuns = vi.mocked(fetchSearchRuns)
const mockedFetchWorkbench = vi.mocked(fetchWorkbench)
const defaultMatchMedia = window.matchMedia

function renderRoute(initialEntry = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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

  if (panel === null) {
    throw new Error('Platform connection panel was not rendered')
  }

  return panel
}

describe('Longtian public opinion application', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1024,
    })
    window.matchMedia = defaultMatchMedia
    mockedFetchHealth.mockReset()
    mockedFetchAISettings.mockReset().mockResolvedValue({
      base_url: null,
      model: null,
      has_api_key: false,
      revision: 0,
    })
    mockedFetchPlatformConnections.mockReset()
    mockedStartAttempt.mockReset()
    mockedFetchMonitoringRules.mockReset()
    mockedFetchSearchRuns.mockReset()
    mockedFetchWorkbench.mockReset().mockResolvedValue(workbenchFixture())
    mockedFetchHealth.mockResolvedValue(connectedResponse)
    mockedFetchPlatformConnections.mockResolvedValue(catalog())
    mockedFetchMonitoringRules.mockResolvedValue(monitoringRulesResponse)
    mockedFetchSearchRuns.mockResolvedValue({
      runs: [],
      next_before_id: null,
    })
  })

  it('renders the read-only workbench through the application providers', async () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { name: '工作台', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveAccessibleName('工作台')
    expect(
      await screen.findByRole('heading', { name: '当前状态尚未完全确认' }),
    ).toBeInTheDocument()
    expect(screen.getByText('还没有可阅读的舆情报告')).toBeInTheDocument()
    expect(screen.getByText('平台准备情况')).toBeInTheDocument()
    expect(screen.queryByText('今日发现', { exact: true })).toBeNull()
    expect(screen.queryByText('待跟进', { exact: true })).toBeNull()
    expect(screen.queryByText('已处理', { exact: true })).toBeNull()
    expect(mockedFetchWorkbench).toHaveBeenCalledTimes(1)
    expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(1)
    expect(mockedFetchMonitoringRules).not.toHaveBeenCalled()
  })

  it('groups report and settings destinations while marking the active page', async () => {
    const user = userEvent.setup()
    const { router } = renderRoute()

    expect(router.state.location.pathname).toBe('/')
    expect(
      screen.getByRole('heading', { name: '工作台', level: 1 }),
    ).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: '主导航' })
    const links = within(navigation).getAllByRole('link')
    expect(links).toHaveLength(5)
    expect(links.map((link) => link.textContent)).toEqual([
      '工作台',
      '平台账号',
      '监控规则',
      '自动任务',
      '舆情爬取',
    ])
    const workbenchLink = within(navigation).getByRole('link', {
      name: '工作台',
    })
    const platformAccountsLink = within(navigation).getByRole('link', {
      name: '平台账号',
    })
    const monitoringRulesLink = within(navigation).getByRole('link', {
      name: '监控规则',
    })
    expect(workbenchLink).toHaveAttribute('aria-current', 'page')
    expect(platformAccountsLink).not.toHaveAttribute('aria-current')
    expect(monitoringRulesLink).not.toHaveAttribute('aria-current')
    for (const label of [
      '舆情信息',
      '监控关键词',
      '舆情日报',
      '系统设置',
      '规划中',
    ]) {
      expect(within(navigation).queryByText(label)).toBeNull()
    }
    const sidebar = navigation.closest<HTMLElement>('[data-slot="sidebar"]')
    if (sidebar === null) {
      throw new Error('Desktop sidebar was not rendered')
    }
    expect(within(sidebar).getAllByRole('separator')).toHaveLength(2)
    expect(screen.queryByText('单机值守模式')).toBeNull()
    expect(screen.queryByText('数据与浏览器操作仅留在本机')).toBeNull()

    await user.click(platformAccountsLink)

    expect(router.state.location.pathname).toBe('/platform-accounts')
    expect(
      await screen.findByRole('heading', { name: '平台账号', level: 1 }),
    ).toBeInTheDocument()
    expect(platformAccountsLink).toHaveAttribute('aria-current', 'page')
    expect(workbenchLink).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('main')).toHaveAccessibleName('平台账号')
    expect(screen.getByRole('main')).toHaveFocus()

    await user.click(within(navigation).getByRole('link', { name: '监控规则' }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/monitoring-rules'),
    )
    expect(
      await screen.findByRole('heading', { name: '监控规则', level: 1 }),
    ).toBeInTheDocument()
    expect(
      within(navigation).getByRole('link', { name: '监控规则' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(
      within(navigation).getByRole('link', { name: '平台账号' }),
    ).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('main')).toHaveAccessibleName('监控规则')
    expect(screen.getByRole('main')).toHaveFocus()

    await user.click(within(navigation).getByRole('link', { name: '舆情爬取' }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/collection-runs'),
    )
    expect(
      await screen.findByRole('heading', { name: '舆情爬取', level: 1 }),
    ).toBeInTheDocument()
    expect(
      within(navigation).getByRole('link', { name: '舆情爬取' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('main')).toHaveAccessibleName('舆情爬取')
    expect(screen.getByRole('main')).toHaveFocus()

    const reportGroup = within(navigation).getByRole('button', {
      name: '舆情报告',
    })
    expect(reportGroup).toHaveAttribute('aria-expanded', 'false')
    await user.click(reportGroup)
    expect(reportGroup).toHaveAttribute('aria-expanded', 'true')
    expect(
      within(navigation).getByRole('link', { name: '生成报告' }),
    ).toHaveAttribute('href', '/reports/new')
    expect(
      within(navigation).getByRole('link', { name: '报告记录' }),
    ).toHaveAttribute('href', '/reports/history')

    const settingsGroup = within(navigation).getByRole('button', {
      name: '设置',
    })
    expect(settingsGroup).toHaveAttribute('aria-expanded', 'false')
    await user.click(settingsGroup)
    expect(settingsGroup).toHaveAttribute('aria-expanded', 'true')
    await user.click(within(navigation).getByRole('link', { name: 'AI 配置' }))
    expect(await screen.findByLabelText('API Key')).toBeVisible()
    expect(router.state.location.pathname).toBe('/settings/ai')
    expect(
      screen.getByRole('heading', { name: 'AI 配置', level: 1 }),
    ).toBeVisible()
    expect(
      within(navigation).getByRole('link', { name: 'AI 配置' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('main')).toHaveAccessibleName('AI 配置')
    expect(screen.getByRole('main')).toHaveFocus()
  })

  it('offers a keyboard skip link to the named main content region', () => {
    renderRoute()

    expect(screen.getByRole('link', { name: '跳到主要内容' })).toHaveAttribute(
      'href',
      '#main-content',
    )
    expect(screen.getByRole('main')).toHaveAccessibleName('工作台')
  })

  it('labels platform readiness as loading until the catalog arrives', async () => {
    let resolveCatalog:
      ((value: PlatformConnectionsResponse) => void) | undefined
    mockedFetchHealth.mockReturnValue(new Promise(() => undefined))
    mockedFetchPlatformConnections.mockReturnValue(
      new Promise((resolve) => {
        resolveCatalog = resolve
      }),
    )

    renderRoute('/platform-accounts')

    expect(await screen.findByText('正在读取登录状态…')).toBeInTheDocument()
    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(screen.getByRole('button', { name: '一键检测' })).toBeDisabled()
    expect(screen.queryByText('微博')).toBeNull()
    expect(screen.queryByText('服务检测中')).toBeNull()
    expect(screen.queryByText('服务正常')).toBeNull()
    expect(screen.queryByText('服务异常')).toBeNull()

    resolveCatalog?.(catalog())

    expect(await screen.findByText('微博')).toBeInTheDocument()
  })

  it('closes the shadcn mobile sidebar after real navigation actions', async () => {
    const user = userEvent.setup()
    window.innerWidth = 375
    renderRoute()

    await user.click(screen.getByRole('button', { name: '切换主导航' }))
    const dialog = await screen.findByRole('dialog', { name: '主导航' })
    const navigation = within(dialog).getByRole('navigation', {
      name: '主导航',
    })
    const links = within(navigation).getAllByRole('link')
    expect(links).toHaveLength(5)
    expect(links.map((link) => link.textContent)).toEqual([
      '工作台',
      '平台账号',
      '监控规则',
      '自动任务',
      '舆情爬取',
    ])
    expect(within(dialog).getAllByRole('separator')).toHaveLength(2)
    expect(within(dialog).queryByText('单机值守模式')).toBeNull()
    expect(within(dialog).queryByText('数据与浏览器操作仅留在本机')).toBeNull()

    await user.click(within(dialog).getByRole('button', { name: '舆情报告' }))
    await user.click(within(dialog).getByRole('link', { name: '生成报告' }))

    expect(
      await screen.findByRole('heading', { name: '生成报告', level: 1 }),
    ).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    await user.click(screen.getByRole('button', { name: '切换主导航' }))
    const reopenedDialog = await screen.findByRole('dialog', {
      name: '主导航',
    })
    await user.click(
      within(reopenedDialog).getByRole('link', { name: '工作台' }),
    )

    expect(
      await screen.findByRole('heading', { name: '工作台', level: 1 }),
    ).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('keeps sidebar mode aligned with the CSS breakpoint at fractional zoom widths', async () => {
    const user = userEvent.setup()
    window.innerWidth = 768
    window.matchMedia = vi.fn((query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }))

    renderRoute()

    await user.click(screen.getByRole('button', { name: '切换主导航' }))

    expect(
      await screen.findByRole('dialog', { name: '主导航' }),
    ).toBeInTheDocument()
  })

  it('shows five enabled platform states', async () => {
    renderRoute('/platform-accounts')

    expect(
      screen.getByRole('heading', { name: '平台账号', level: 1 }),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(
        '需要登录、扫码或安全验证时，请在应用打开的专用谷歌浏览器中完成。首次使用需要在该窗口登录，登录状态会由浏览器保留。',
      ),
    ).toBeNull()
    expect(screen.queryByText('龙田街道舆情值守')).toBeNull()
    expect(screen.getByText('登录状态', { exact: true })).toBeInTheDocument()
    expect(screen.queryByText('账号接入')).toBeNull()
    expect(screen.queryByText('本机浏览器通道')).toBeNull()
    expect(await screen.findByText('微博')).toBeInTheDocument()
    expect(screen.getByText('抖音')).toBeInTheDocument()
    expect(screen.getByText('快手')).toBeInTheDocument()
    expect(screen.getByText('小红书')).toBeInTheDocument()
    expect(screen.getByText('今日头条')).toBeInTheDocument()
    for (const [platformName, logoSource] of [
      ['微博', weiboLogo],
      ['抖音', douyinLogo],
      ['快手', kuaishouLogo],
      ['小红书', xiaohongshuLogo],
      ['今日头条', toutiaoLogo],
    ] as const) {
      const platformRow = screen.getByText(platformName).closest('li')
      if (platformRow === null) {
        throw new Error(`${platformName} row was not rendered`)
      }

      const logo = platformRow.querySelector('img')
      expect(logo).not.toBeNull()
      expect(logo).toHaveAttribute('src', logoSource)
      expect(logo).toHaveAttribute('alt', '')
      expect(logo).toHaveAttribute('aria-hidden', 'true')
    }
    for (const placeholder of ['WB', 'DY', 'KS', 'RED', 'TT']) {
      expect(screen.queryByText(placeholder, { exact: true })).toBeNull()
    }
    expect(screen.queryByText('待接入')).not.toBeInTheDocument()
    expect(screen.queryByText('暂不可用')).not.toBeInTheDocument()
    expect(screen.getAllByText('尚未检查')).toHaveLength(5)
    expect(screen.getAllByText('待检查')).toHaveLength(5)
    expect(screen.getAllByRole('button', { name: '检查状态' })).toHaveLength(5)
    expect(
      screen
        .getAllByRole('button')
        .filter((button) =>
          /检查状态|重新检查|处理中/.test(button.textContent ?? ''),
        ),
    ).toHaveLength(5)
    expect(screen.queryByText('当前操作指引')).toBeNull()
    expect(
      screen.queryByText('系统只会打开官方页面并检测登录状态。'),
    ).toBeNull()
    expect(
      screen.queryByText(
        '谷歌浏览器出现授权、扫码或验证码时，请由你本人完成。系统不会读取密码，也不会自动绕过安全验证。',
      ),
    ).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('keeps unavailable health state in the platform page without a global status pill', async () => {
    mockedFetchHealth.mockRejectedValueOnce(new Error('无法连接本机后端服务'))

    renderRoute('/platform-accounts')

    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('应用服务暂时不可用，请重新启动应用。')
    expect(screen.queryByText('服务检测中')).toBeNull()
    expect(screen.queryByText('服务正常')).toBeNull()
    expect(screen.queryByText('服务异常')).toBeNull()
    const attemptButtons = screen.getAllByRole('button', {
      name: '检查状态',
    })
    expect(attemptButtons).toHaveLength(5)
    for (const button of attemptButtons) {
      expect(button).toBeDisabled()
    }
    expect(screen.getByRole('button', { name: '一键检测' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: '重试' })).toBeNull()
    expect(mockedFetchHealth).toHaveBeenCalledTimes(1)
  })

  it('recovers health and platform state together from the page-level retry', async () => {
    const user = userEvent.setup()
    mockedFetchHealth
      .mockRejectedValueOnce(new Error('无法连接本机后端服务'))
      .mockResolvedValueOnce(connectedResponse)
    mockedFetchPlatformConnections
      .mockRejectedValueOnce(
        new PlatformConnectionApiError(
          '无法连接本机后端服务，请确认服务已经启动。',
          'service_unavailable',
        ),
      )
      .mockResolvedValueOnce(catalog())

    renderRoute('/platform-accounts')

    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('无法连接本机后端服务')
    expect(screen.getByRole('button', { name: '一键检测' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '重新读取' }))

    expect(await screen.findByText('微博')).toBeInTheDocument()
    const attemptButtons = screen.getAllByRole('button', {
      name: '检查状态',
    })
    await waitFor(() => {
      for (const button of attemptButtons) {
        expect(button).toBeEnabled()
      }
      expect(screen.getByRole('button', { name: '一键检测' })).toBeEnabled()
    })
    expect(mockedFetchHealth).toHaveBeenCalledTimes(2)
    expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(2)
  })

  it.each([
    [
      'checking',
      'starting_browser',
      '检查中',
      '处理中…',
      '正在启动应用专用的谷歌浏览器，请稍候。',
    ],
    [
      'action_required',
      'complete_login',
      '需要操作',
      '处理中…',
      '请在应用打开的专用谷歌浏览器中登录微博。',
    ],
    ['connected', 'none', '已登录', '重新检查', null],
    [
      'disconnected',
      'retry',
      '未登录',
      '重新检查',
      '请在应用打开的专用谷歌浏览器中登录微博，然后重新检查。',
    ],
    [
      'failed',
      'retry',
      '检查失败',
      '重新检查',
      '检查未能完成，请重新检查；应用会在需要时启动专用的谷歌浏览器。',
    ],
    [
      'failed',
      'retry_browser',
      '检查失败',
      '重新检查',
      '专用谷歌浏览器暂时不可用，请重新检查；应用会在需要时自动启动。',
    ],
  ] as const)(
    'renders the %s row status with contextual recovery guidance',
    async (status, guidance, label, actionLabel, recoveryMessage) => {
      mockedFetchPlatformConnections.mockResolvedValue(
        catalog({ status, guidance }),
      )

      renderRoute('/platform-accounts')

      expect(await screen.findByText(label)).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: actionLabel }),
      ).toBeInTheDocument()
      const platformRow = screen.getByText('微博').closest('li')
      if (platformRow === null) {
        throw new Error('微博 row was not rendered')
      }
      if (recoveryMessage === null) {
        expect(
          within(platformRow).queryByText(/应用打开的专用谷歌浏览器/),
        ).toBeNull()
      } else {
        expect(screen.getByText(recoveryMessage)).toBeInTheDocument()
      }
      expect(screen.queryByText('当前操作指引')).toBeNull()
    },
  )

  it('checks enabled platforms in catalog order without overlapping attempts', async () => {
    const user = userEvent.setup()
    let latestCatalog = catalog()
    mockedFetchPlatformConnections.mockImplementation(async () => latestCatalog)
    const pendingAttempts: Array<{
      platform: PlatformConnection['platform']
      resolve: (value: {
        attempt_id: string
        platform: PlatformConnection
      }) => void
    }> = []
    mockedStartAttempt.mockImplementation(
      (platform) =>
        new Promise((resolve) => {
          pendingAttempts.push({ platform, resolve })
        }),
    )

    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', {
      name: '一键检测',
    })
    await waitFor(() => expect(batchButton).toBeEnabled())
    await user.click(batchButton)

    const expectedPlatforms = ['wb', 'dy', 'ks', 'xhs', 'toutiao'] as const
    const terminalStatuses = [
      'failed',
      'disconnected',
      'connected',
      'connected',
      'connected',
    ] as const

    for (const [index, platform] of expectedPlatforms.entries()) {
      await waitFor(() =>
        expect(mockedStartAttempt).toHaveBeenCalledTimes(index + 1),
      )
      expect(mockedStartAttempt.mock.calls[index]?.[0]).toBe(platform)
      expect(pendingAttempts[index]?.platform).toBe(platform)
      expect(screen.getByRole('status')).toHaveTextContent(
        `正在检测${latestCatalog.platforms[index]?.display_name} · ${index + 1}/5`,
      )
      for (const rowButton of screen.getAllByRole('button', {
        name: '检查状态',
      })) {
        expect(rowButton).toBeDisabled()
      }

      const terminal = connection({
        platform,
        display_name: latestCatalog.platforms[index]?.display_name ?? platform,
        status: terminalStatuses[index],
        guidance: terminalStatuses[index] === 'connected' ? 'none' : 'retry',
      })
      latestCatalog = {
        platforms: latestCatalog.platforms.map((item) =>
          item.platform === platform ? terminal : item,
        ),
      }
      pendingAttempts[index]?.resolve({
        attempt_id: attemptId,
        platform: terminal,
      })
    }

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '一键检测' })).toBeEnabled(),
    )
    expect(mockedStartAttempt.mock.calls.map(([platform]) => platform)).toEqual(
      expectedPlatforms,
    )
    expect(
      screen.getByText(
        '检查未能完成，请重新检查；应用会在需要时启动专用的谷歌浏览器。',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        '请在应用打开的专用谷歌浏览器中登录抖音，然后重新检查。',
      ),
    ).toBeInTheDocument()
  })

  it('waits for polling to reach a terminal result before starting the next platform', async () => {
    const user = userEvent.setup()
    const pendingCatalogPolls: Array<
      (value: PlatformConnectionsResponse) => void
    > = []
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(catalog())
      .mockImplementation(
        () =>
          new Promise((resolve) => {
            pendingCatalogPolls.push(resolve)
          }),
      )
    mockedStartAttempt.mockImplementation((platform) => {
      if (platform === 'wb') {
        return Promise.resolve({
          attempt_id: attemptId,
          platform: connection({
            platform: 'wb',
            display_name: '微博',
            status: 'checking',
            active_attempt_id: attemptId,
          }),
        })
      }
      return new Promise(() => undefined)
    })

    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', {
      name: '一键检测',
    })
    await waitFor(() => expect(batchButton).toBeEnabled())
    await user.click(batchButton)

    await waitFor(() => expect(mockedStartAttempt).toHaveBeenCalledTimes(1))
    expect(mockedStartAttempt.mock.calls[0]?.[0]).toBe('wb')
    expect(screen.getByRole('status')).toHaveTextContent('正在检测微博 · 1/5')
    await waitFor(() =>
      expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(2),
    )
    expect(mockedStartAttempt).toHaveBeenCalledTimes(1)

    pendingCatalogPolls[0]?.(
      catalog({
        status: 'action_required',
        guidance: 'complete_login',
        active_attempt_id: attemptId,
      }),
    )

    expect(await screen.findByText('需要操作')).toBeInTheDocument()
    expect(mockedStartAttempt).toHaveBeenCalledTimes(1)
    await waitFor(
      () => expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(3),
      { timeout: 2200 },
    )

    pendingCatalogPolls[1]?.(
      catalog({
        status: 'connected',
        last_checked_at: '2026-08-25T08:00:00Z',
      }),
    )

    await waitFor(() => expect(mockedStartAttempt).toHaveBeenCalledTimes(2))
    expect(mockedStartAttempt.mock.calls[1]?.[0]).toBe('dy')
    expect(screen.getByRole('status')).toHaveTextContent('正在检测抖音 · 2/5')
  })

  it('excludes unavailable platforms from a batch detection run', async () => {
    const user = userEvent.setup()
    const availableCatalog = catalog(
      {},
      {},
      {},
      {},
      { availability: 'coming_soon', status: 'coming_soon' },
    )
    mockedFetchPlatformConnections.mockResolvedValue(availableCatalog)
    mockedStartAttempt.mockImplementation(async (platform) => ({
      attempt_id: attemptId,
      platform: connection({
        platform,
        display_name:
          availableCatalog.platforms.find(
            (connection) => connection.platform === platform,
          )?.display_name ?? platform,
        status: 'connected',
      }),
    }))

    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', {
      name: '一键检测',
    })
    await waitFor(() => expect(batchButton).toBeEnabled())
    await user.click(batchButton)

    await waitFor(() => expect(mockedStartAttempt).toHaveBeenCalledTimes(4))
    expect(mockedStartAttempt.mock.calls.map(([platform]) => platform)).toEqual(
      ['wb', 'dy', 'ks', 'toutiao'],
    )
    expect(mockedStartAttempt).not.toHaveBeenCalledWith(
      'xhs',
      expect.any(AbortSignal),
    )
  })

  it('ends a batch safely when an attempt cannot start', async () => {
    const user = userEvent.setup()
    mockedStartAttempt.mockRejectedValue(
      new PlatformConnectionApiError(
        '无法连接本机后端服务，请确认服务已经启动。',
        'service_unavailable',
      ),
    )

    renderRoute('/platform-accounts')
    const batchButton = await screen.findByRole('button', {
      name: '一键检测',
    })
    await waitFor(() => expect(batchButton).toBeEnabled())
    await user.click(batchButton)

    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('无法连接本机后端服务，请确认服务已经启动。')
    expect(screen.getByRole('button', { name: '一键检测' })).toBeEnabled()
    expect(screen.queryByText(/谷歌浏览器中登录/)).toBeNull()
    expect(mockedStartAttempt).toHaveBeenCalledTimes(1)
  })

  it('disables batch detection when the enabled catalog is empty', async () => {
    mockedFetchPlatformConnections.mockResolvedValue({ platforms: [] })

    renderRoute('/platform-accounts')

    expect(
      await screen.findByRole('button', { name: '一键检测' }),
    ).toBeDisabled()
    expect(mockedStartAttempt).not.toHaveBeenCalled()
  })

  it('prevents duplicate starts while an attempt request is pending', async () => {
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
    const [button] = await screen.findAllByRole('button', {
      name: '检查状态',
    })

    await user.click(button)
    expect(button).toBeDisabled()
    await user.click(button)
    expect(mockedStartAttempt).toHaveBeenCalledTimes(1)

    resolveAttempt?.({
      attempt_id: attemptId,
      platform: connection({
        platform: 'wb',
        display_name: '微博',
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })
    await waitFor(() => expect(button).toBeEnabled())
  })

  it('shows a safe conflict and keeps the existing operation untouched', async () => {
    const user = userEvent.setup()
    mockedStartAttempt.mockRejectedValue(
      new PlatformConnectionApiError(
        '已有平台连接任务正在运行，请完成后再试。',
        'connection_attempt_active',
        409,
      ),
    )

    renderRoute('/platform-accounts')
    const [weiboButton] = await screen.findAllByRole('button', {
      name: '检查状态',
    })
    await user.click(weiboButton)

    expect(
      await within(getConnectionPanel()).findByRole('alert'),
    ).toHaveTextContent('已有平台连接任务正在运行，请完成后再试。')
    expect(mockedStartAttempt).toHaveBeenCalledTimes(1)
  })

  it('starts Kuaishou and reflects action required in its row', async () => {
    const user = userEvent.setup()
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(catalog())
      .mockResolvedValue(
        catalog(
          {},
          {
            status: 'action_required',
            guidance: 'complete_login',
            active_attempt_id: attemptId,
          },
        ),
      )
    mockedStartAttempt.mockResolvedValue({
      attempt_id: attemptId,
      platform: connection({
        platform: 'ks',
        display_name: '快手',
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })

    renderRoute('/platform-accounts')
    const kuaishouName = await screen.findByText('快手')
    const kuaishouRow = kuaishouName.closest('li')
    if (kuaishouRow === null) {
      throw new Error('Kuaishou row was not rendered')
    }

    await user.click(
      within(kuaishouRow).getByRole('button', { name: '检查状态' }),
    )

    expect(mockedStartAttempt).toHaveBeenCalledWith(
      'ks',
      expect.any(AbortSignal),
    )
    expect(await screen.findByText('需要操作')).toBeInTheDocument()
  })

  it('starts Douyin and reflects action required in its row', async () => {
    const user = userEvent.setup()
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(catalog())
      .mockResolvedValue(
        catalog(
          {},
          {},
          {
            status: 'action_required',
            guidance: 'complete_login',
            active_attempt_id: attemptId,
          },
        ),
      )
    mockedStartAttempt.mockResolvedValue({
      attempt_id: attemptId,
      platform: connection({
        platform: 'dy',
        display_name: '抖音',
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })

    renderRoute('/platform-accounts')
    const douyinName = await screen.findByText('抖音')
    const douyinRow = douyinName.closest('li')
    if (douyinRow === null) {
      throw new Error('Douyin row was not rendered')
    }

    expect(screen.getAllByRole('button', { name: '检查状态' })).toHaveLength(5)
    await user.click(
      within(douyinRow).getByRole('button', { name: '检查状态' }),
    )

    expect(mockedStartAttempt).toHaveBeenCalledWith(
      'dy',
      expect.any(AbortSignal),
    )
    expect(await screen.findByText('需要操作')).toBeInTheDocument()
  })

  it('starts Toutiao and reflects action required in its row', async () => {
    const user = userEvent.setup()
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(catalog())
      .mockResolvedValue(
        catalog(
          {},
          {},
          {},
          {
            status: 'action_required',
            guidance: 'complete_login',
            active_attempt_id: attemptId,
          },
        ),
      )
    mockedStartAttempt.mockResolvedValue({
      attempt_id: attemptId,
      platform: connection({
        platform: 'toutiao',
        display_name: '今日头条',
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })

    renderRoute('/platform-accounts')
    const toutiaoName = await screen.findByText('今日头条')
    const toutiaoRow = toutiaoName.closest('li')
    if (toutiaoRow === null) {
      throw new Error('Toutiao row was not rendered')
    }

    await user.click(
      within(toutiaoRow).getByRole('button', { name: '检查状态' }),
    )

    expect(mockedStartAttempt).toHaveBeenCalledWith(
      'toutiao',
      expect.any(AbortSignal),
    )
    expect(await screen.findByText('需要操作')).toBeInTheDocument()
  })

  it('starts enabled Xiaohongshu and reflects action required in its row', async () => {
    const user = userEvent.setup()
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(catalog())
      .mockResolvedValue(
        catalog(
          {},
          {},
          {},
          {},
          {
            status: 'action_required',
            guidance: 'complete_login',
            active_attempt_id: attemptId,
          },
        ),
      )
    mockedStartAttempt.mockResolvedValue({
      attempt_id: attemptId,
      platform: connection({
        platform: 'xhs',
        display_name: '小红书',
        status: 'checking',
        active_attempt_id: attemptId,
      }),
    })

    renderRoute('/platform-accounts')
    const xhsName = await screen.findByText('小红书')
    const xhsRow = xhsName.closest('li')
    if (xhsRow === null) {
      throw new Error('Xiaohongshu row was not rendered')
    }

    expect(screen.getAllByRole('button', { name: '检查状态' })).toHaveLength(5)
    await user.click(within(xhsRow).getByRole('button', { name: '检查状态' }))

    expect(mockedStartAttempt).toHaveBeenCalledWith(
      'xhs',
      expect.any(AbortSignal),
    )
    expect(await screen.findByText('需要操作')).toBeInTheDocument()
  })

  it('polls an enabled Xiaohongshu attempt to its online result', async () => {
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(
        catalog(
          {},
          {},
          {},
          {},
          {
            status: 'checking',
            active_attempt_id: attemptId,
          },
        ),
      )
      .mockResolvedValue(
        catalog(
          {},
          {},
          {},
          {},
          {
            status: 'connected',
            last_checked_at: '2026-08-24T08:00:00Z',
          },
        ),
      )

    renderRoute('/platform-accounts')

    expect(await screen.findByText('检查中')).toBeInTheDocument()
    expect(
      await screen.findByText('已登录', {}, { timeout: 2200 }),
    ).toBeInTheDocument()
    expect(await screen.findByText(/上次检查/)).toBeInTheDocument()
    await waitFor(() =>
      expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(2),
    )
  })

  it('polls an active Toutiao connection until the online result is connected', async () => {
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(
        catalog(
          {},
          {},
          {},
          {
            status: 'checking',
            active_attempt_id: attemptId,
          },
        ),
      )
      .mockResolvedValue(
        catalog(
          {},
          {},
          {},
          {
            status: 'connected',
            last_checked_at: '2026-08-24T08:00:00Z',
          },
        ),
      )

    renderRoute('/platform-accounts')

    expect(await screen.findByText('检查中')).toBeInTheDocument()
    expect(
      await screen.findByText('已登录', {}, { timeout: 2200 }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(2),
    )
  })

  it('polls an active Douyin connection until the online result is connected', async () => {
    mockedFetchPlatformConnections
      .mockResolvedValueOnce(
        catalog(
          {},
          {},
          {
            status: 'checking',
            active_attempt_id: attemptId,
          },
        ),
      )
      .mockResolvedValue(
        catalog(
          {},
          {},
          {
            status: 'connected',
            last_checked_at: '2026-08-24T08:00:00Z',
          },
        ),
      )

    renderRoute('/platform-accounts')

    expect(await screen.findByText('检查中')).toBeInTheDocument()
    expect(
      await screen.findByText('已登录', {}, { timeout: 2200 }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(2),
    )
  })
})
