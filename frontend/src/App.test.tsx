import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { appRoutes } from './app/router'
import {
  fetchHealth,
  HEALTH_SERVICE,
  type HealthResponse,
} from './lib/api/health'
import {
  fetchPlatformConnections,
  PlatformConnectionApiError,
  startPlatformConnectionAttempt,
  type PlatformConnection,
  type PlatformConnectionsResponse,
} from './lib/api/platform-connections'

vi.mock('./lib/api/health', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./lib/api/health')>()

  return {
    ...actual,
    fetchHealth: vi.fn(),
  }
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

const connectedResponse: HealthResponse = {
  status: 'ok',
  service: HEALTH_SERVICE,
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
        availability: 'coming_soon',
        status: 'coming_soon',
      }),
      connection({
        platform: 'toutiao',
        display_name: '今日头条',
        availability: 'coming_soon',
        status: 'coming_soon',
      }),
    ],
  }
}

const mockedFetchHealth = vi.mocked(fetchHealth)
const mockedFetchPlatformConnections = vi.mocked(fetchPlatformConnections)
const mockedStartAttempt = vi.mocked(startPlatformConnectionAttempt)
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

describe('Longtian public opinion application', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1024,
    })
    window.matchMedia = defaultMatchMedia
    mockedFetchHealth.mockReset()
    mockedFetchPlatformConnections.mockReset()
    mockedStartAttempt.mockReset()
    mockedFetchHealth.mockResolvedValue(connectedResponse)
    mockedFetchPlatformConnections.mockResolvedValue(catalog())
  })

  it('renders the truthful workbench through the application providers', async () => {
    mockedFetchPlatformConnections.mockResolvedValue(
      catalog({ status: 'connected' }),
    )

    render(<App />)

    expect(
      screen.getByRole('heading', { name: '工作台', level: 1 }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '系统准备情况' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('服务正常')).toBeInTheDocument()
    const dutyLedger = screen.getByLabelText('值守准备台账')
    expect(within(dutyLedger).getByText('1 / 5')).toBeInTheDocument()
    expect(within(dutyLedger).getByText('尚未配置')).toBeInTheDocument()
    expect(
      screen.getByText(
        '已连接 1 / 3 个可用平台；可以继续检测微博、抖音、快手。',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('尚未建立采集任务')).toBeInTheDocument()
    expect(
      screen.getByText('当前没有采集结果、风险事件或待处理任务可展示。'),
    ).toBeInTheDocument()
  })

  it('navigates between real routes and marks only the current route active', async () => {
    const user = userEvent.setup()
    renderRoute()

    const workbenchLink = screen.getByRole('link', { name: '工作台' })
    expect(workbenchLink).toHaveAttribute('aria-current', 'page')

    await user.click(screen.getByRole('link', { name: '平台账号' }))

    expect(
      await screen.findByRole('heading', { name: '平台账号', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '平台账号' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(workbenchLink).not.toHaveAttribute('aria-current')
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
    mockedFetchPlatformConnections.mockReturnValue(
      new Promise((resolve) => {
        resolveCatalog = resolve
      }),
    )

    renderRoute()

    expect(await screen.findByText('正在读取平台状态')).toBeInTheDocument()
    expect(screen.queryByText('本次后端会话的在线结果')).toBeNull()

    resolveCatalog?.(catalog())

    expect(
      await screen.findByText('本次后端会话的在线结果'),
    ).toBeInTheDocument()
  })

  it('keeps future modules disabled and honestly labeled', () => {
    renderRoute()

    const navigation = screen.getByRole('navigation', { name: '主导航' })
    for (const label of [
      '采集任务',
      '舆情信息',
      '监控关键词',
      '舆情日报',
      '系统设置',
    ]) {
      expect(screen.queryByRole('link', { name: new RegExp(label) })).toBeNull()
      expect(
        within(navigation).getByRole('button', { name: label }),
      ).toBeDisabled()
    }
    expect(within(navigation).getAllByText('规划中')).toHaveLength(5)
  })

  it('opens the shadcn mobile sidebar and closes it after navigation', async () => {
    const user = userEvent.setup()
    window.innerWidth = 375
    renderRoute()

    await waitFor(() =>
      expect(screen.queryByText('四社区 · 本机值守')).not.toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: '切换主导航' }))
    const dialog = await screen.findByRole('dialog', { name: '主导航' })
    expect(within(dialog).getByText('四社区 · 本机值守')).toBeInTheDocument()
    expect(
      within(dialog).getByRole('navigation', { name: '主导航' }),
    ).toBeInTheDocument()

    await user.click(within(dialog).getByRole('link', { name: '平台账号' }))

    expect(
      await screen.findByRole('heading', { name: '平台账号', level: 1 }),
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

    await waitFor(() =>
      expect(screen.queryByText('四社区 · 本机值守')).not.toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: '切换主导航' }))

    expect(
      await screen.findByRole('dialog', { name: '主导航' }),
    ).toBeInTheDocument()
  })

  it('shows five honest platform states with Weibo, Douyin, and Kuaishou actionable', async () => {
    renderRoute('/platform-accounts')

    expect(await screen.findByText('微博')).toBeInTheDocument()
    expect(screen.getByText('抖音')).toBeInTheDocument()
    expect(screen.getByText('快手')).toBeInTheDocument()
    expect(screen.getByText('小红书')).toBeInTheDocument()
    expect(screen.getByText('今日头条')).toBeInTheDocument()
    expect(screen.getAllByText('待接入')).toHaveLength(2)
    expect(screen.getAllByText('暂不可用')).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: '检测连接' })).toHaveLength(3)
    expect(
      screen
        .getAllByRole('button')
        .filter((button) =>
          /检测连接|重新检测|处理中/.test(button.textContent ?? ''),
        ),
    ).toHaveLength(3)
  })

  it('allows an unavailable local service to be retried', async () => {
    const user = userEvent.setup()
    mockedFetchHealth
      .mockRejectedValueOnce(new Error('无法连接本机后端服务'))
      .mockResolvedValueOnce(connectedResponse)

    renderRoute('/platform-accounts')

    expect(await screen.findByText('服务异常')).toBeInTheDocument()
    const attemptButtons = screen.getAllByRole('button', {
      name: '检测连接',
    })
    expect(attemptButtons).toHaveLength(3)
    for (const button of attemptButtons) {
      expect(button).toBeDisabled()
    }

    await user.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('服务正常')).toBeInTheDocument()
    for (const button of attemptButtons) {
      expect(button).toBeEnabled()
    }
    expect(mockedFetchHealth).toHaveBeenCalledTimes(2)
  })

  it('offers an explicit retry when the platform catalog cannot be read', async () => {
    const user = userEvent.setup()
    mockedFetchPlatformConnections
      .mockRejectedValueOnce(
        new PlatformConnectionApiError(
          '无法连接本机后端服务，请确认服务已经启动。',
          'service_unavailable',
        ),
      )
      .mockResolvedValueOnce(catalog())

    renderRoute('/platform-accounts')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '无法连接本机后端服务',
    )
    await user.click(screen.getByRole('button', { name: '重新读取' }))

    expect(await screen.findByText('微博')).toBeInTheDocument()
    expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(2)
  })

  it.each([
    [
      'action_required',
      'complete_login',
      '需要人工操作',
      '请在 Chrome 的微博官方页面完成扫码、短信或安全验证。',
    ],
    [
      'connected',
      'none',
      '已连接',
      '微博账号已通过在线检测，可以继续准备后续采集功能。',
    ],
    [
      'disconnected',
      'retry',
      '未连接',
      '本次检测未完成。确认 Chrome 可用后，可以重新检测。',
    ],
    [
      'failed',
      'retry',
      '检测失败',
      '本次检测未完成。确认 Chrome 可用后，可以重新检测。',
    ],
  ] as const)(
    'renders the %s status and its next action',
    async (status, guidance, label, copy) => {
      mockedFetchPlatformConnections.mockResolvedValue(
        catalog({ status, guidance }),
      )

      renderRoute('/platform-accounts')

      expect(await screen.findByText(label)).toBeInTheDocument()
      expect(screen.getByText(copy)).toBeInTheDocument()
    },
  )

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
      name: '检测连接',
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
      name: '检测连接',
    })
    await user.click(weiboButton)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '已有平台连接任务正在运行，请完成后再试。',
    )
    expect(mockedStartAttempt).toHaveBeenCalledTimes(1)
  })

  it('starts Kuaishou and follows its platform-specific manual guidance', async () => {
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
      within(kuaishouRow).getByRole('button', { name: '检测连接' }),
    )

    expect(mockedStartAttempt).toHaveBeenCalledWith(
      'ks',
      expect.any(AbortSignal),
    )
    expect(
      await screen.findByText(
        '请在 Chrome 的快手官方页面完成扫码、短信或安全验证。',
      ),
    ).toBeInTheDocument()
  })

  it('starts Douyin and follows its platform-specific manual guidance', async () => {
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

    expect(screen.getAllByRole('button', { name: '检测连接' })).toHaveLength(3)
    await user.click(
      within(douyinRow).getByRole('button', { name: '检测连接' }),
    )

    expect(mockedStartAttempt).toHaveBeenCalledWith(
      'dy',
      expect.any(AbortSignal),
    )
    expect(
      await screen.findByText(
        '请在 Chrome 的抖音官方页面完成扫码、短信或安全验证。',
      ),
    ).toBeInTheDocument()
  })

  it('derives three-platform readiness copy from an enabled Douyin catalog', async () => {
    mockedFetchPlatformConnections.mockResolvedValue(
      catalog(
        { status: 'connected' },
        { status: 'connected' },
        { status: 'connected' },
      ),
    )

    renderRoute('/')

    expect(
      await screen.findByText(
        '微博、抖音、快手在线检测均已通过；其余 2 个平台仍待接入。',
      ),
    ).toBeInTheDocument()
  })

  it('shows guidance for the most recently checked enabled platform', async () => {
    mockedFetchPlatformConnections.mockResolvedValue(
      catalog(
        {
          status: 'connected',
          last_checked_at: '2026-08-24T07:00:00Z',
        },
        {
          status: 'connected',
          last_checked_at: '2026-08-24T08:00:00Z',
        },
      ),
    )

    renderRoute('/platform-accounts')

    expect(
      await screen.findByText(
        '快手账号已通过在线检测，可以继续准备后续采集功能。',
      ),
    ).toBeInTheDocument()
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

    expect(await screen.findByText('检测中')).toBeInTheDocument()
    expect(
      await screen.findByText('已连接', {}, { timeout: 2200 }),
    ).toBeInTheDocument()
    expect(
      await screen.findByText(
        '抖音账号已通过在线检测，可以继续准备后续采集功能。',
      ),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(mockedFetchPlatformConnections).toHaveBeenCalledTimes(2),
    )
  })
})
