import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import douyinLogo from '@/assets/platforms/douyin.svg'
import kuaishouLogo from '@/assets/platforms/kuaishou.svg'
import weiboLogo from '@/assets/platforms/weibo.svg'
import xiaohongshuLogo from '@/assets/platforms/xiaohongshu.svg'
import {
  fetchMonitoringRules,
  type MonitoringRule,
} from '@/lib/api/monitoring-rules'
import {
  cancelSearchRun,
  fetchSearchRun,
  fetchSearchRunResults,
  fetchSearchRuns,
  openSearchRunResult,
  SEARCH_RUNS_QUERY_KEY,
  SearchRunApiError,
  startSearchRun,
  type SearchResult,
  type SearchRunDetail,
} from '@/lib/api/search-runs'
import { CollectionRunDetail } from '@/routes/collection-run-detail'
import { CollectionRuns } from '@/routes/collection-runs'

vi.mock('@/lib/api/monitoring-rules', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/api/monitoring-rules')>()
  return { ...actual, fetchMonitoringRules: vi.fn() }
})

vi.mock('@/lib/api/search-runs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/search-runs')>()
  return {
    ...actual,
    fetchSearchRuns: vi.fn(),
    fetchSearchRun: vi.fn(),
    fetchSearchRunResults: vi.fn(),
    startSearchRun: vi.fn(),
    cancelSearchRun: vi.fn(),
    openSearchRunResult: vi.fn(),
  }
})

const rule: MonitoringRule = {
  id: 1,
  name: '龙田街道及四个社区',
  terms: ['龙田街道', '竹坑社区'],
  enabled: true,
}

function run(values: Partial<SearchRunDetail> = {}): SearchRunDetail {
  return {
    id: 7,
    monitoring_rule_id: 1,
    platform: 'toutiao',
    rule_name: rule.name,
    term_count: 2,
    terms: rule.terms,
    max_results_per_term: 10,
    status: 'completed_with_results',
    current_term_position: 1,
    new_count: 1,
    repeated_count: 1,
    total_count: 2,
    created_at: '2026-08-26T08:00:00+00:00',
    started_at: '2026-08-26T08:00:01+00:00',
    finished_at: '2026-08-26T08:00:05+00:00',
    ...values,
  }
}

function result(values: Partial<SearchResult> = {}): SearchResult {
  return {
    id: 11,
    platform: 'toutiao',
    platform_content_id: '100',
    content_type: 'article',
    title: '龙田街道公开信息',
    snippet: '来自公开搜索页面',
    creator_hash: '0123456789abcdef',
    publisher_name: '本***察',
    published_at_text: '刚刚',
    content_url: 'https://www.toutiao.com/article/100/',
    kind: 'new',
    matched_terms: ['龙田街道'],
    first_seen_at: '2026-08-26T08:00:02+00:00',
    last_seen_at: '2026-08-26T08:00:02+00:00',
    first_observed_at: '2026-08-26T08:00:02+00:00',
    last_observed_at: '2026-08-26T08:00:02+00:00',
    ...values,
  }
}

const mockedFetchRules = vi.mocked(fetchMonitoringRules)
const mockedFetchRuns = vi.mocked(fetchSearchRuns)
const mockedFetchRun = vi.mocked(fetchSearchRun)
const mockedFetchResults = vi.mocked(fetchSearchRunResults)
const mockedStartRun = vi.mocked(startSearchRun)
const mockedCancelRun = vi.mocked(cancelSearchRun)
const mockedOpenResult = vi.mocked(openSearchRunResult)

function renderRoute(initialEntry = '/collection-runs') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [
      { path: '/collection-runs', element: <CollectionRuns /> },
      { path: '/collection-runs/:runId', element: <CollectionRunDetail /> },
      { path: '/platform-accounts', element: <p>平台账号占位</p> },
    ],
    { initialEntries: [initialEntry] },
  )

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }

  return {
    router,
    queryClient,
    ...render(<RouterProvider router={router} />, { wrapper: Wrapper }),
  }
}

describe('collection runs routes', () => {
  beforeEach(() => {
    mockedFetchRules.mockReset()
    mockedFetchRuns.mockReset()
    mockedFetchRun.mockReset()
    mockedFetchResults.mockReset()
    mockedStartRun.mockReset()
    mockedCancelRun.mockReset()
    mockedOpenResult.mockReset()
    mockedFetchRules.mockResolvedValue({ rules: [rule] })
    mockedFetchRuns.mockResolvedValue({
      runs: [run()],
      next_before_id: null,
    })
    mockedFetchRun.mockResolvedValue(run())
    mockedFetchResults.mockResolvedValue({
      results: [result(), result({ id: 12, kind: 'repeated' })],
      total: 2,
      limit: 50,
      offset: 0,
    })
    mockedStartRun.mockResolvedValue(
      run({
        id: 8,
        status: 'queued',
        current_term_position: null,
        new_count: 0,
        repeated_count: 0,
        total_count: 0,
        started_at: null,
        finished_at: null,
      }),
    )
    mockedCancelRun.mockResolvedValue(run({ status: 'cancelled' }))
    mockedOpenResult.mockResolvedValue({ outcome: 'opened' })
  })

  it('starts a Toutiao run from an enabled rule and deep-links to it', async () => {
    const user = userEvent.setup()
    const { router } = renderRoute()
    await screen.findByText(rule.name)

    const ruleSelect = screen.getByRole('combobox', { name: '监控规则' })
    await user.click(ruleSelect)
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    expect(ruleSelect).toHaveTextContent('龙田街道及四个社区（2 个词）')
    expect(ruleSelect).not.toHaveTextContent(/^1$/u)
    await user.clear(screen.getByLabelText('每词最多采集'))
    await user.type(screen.getByLabelText('每词最多采集'), '7')
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    await waitFor(() =>
      expect(mockedStartRun).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platform: 'toutiao',
        max_results_per_term: 7,
      }),
    )
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/collection-runs/8'),
    )
  })

  it('switches to Weibo with the Shadcn platform selector', async () => {
    const user = userEvent.setup()
    mockedStartRun.mockResolvedValue(
      run({ id: 9, platform: 'wb', status: 'queued' }),
    )
    renderRoute()
    await screen.findByText(rule.name)

    const ruleSelect = screen.getByRole('combobox', { name: '监控规则' })
    await user.click(ruleSelect)
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    const platformSelect = screen.getByRole('combobox', { name: '采集平台' })
    expect(platformSelect).toHaveTextContent('今日头条')
    platformSelect.focus()
    await user.keyboard('{Enter}')
    const platformOptions = await screen.findAllByRole('option')
    expect(platformOptions.map((option) => option.textContent)).toEqual([
      '今日头条',
      '微博',
      '快手',
      '抖音',
      '小红书',
    ])
    await user.keyboard('{ArrowDown}{Enter}')
    expect(platformSelect).toHaveTextContent('微博')
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    await waitFor(() =>
      expect(mockedStartRun).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platform: 'wb',
        max_results_per_term: 10,
      }),
    )
  })

  it('switches to Kuaishou with the existing Shadcn platform selector', async () => {
    const user = userEvent.setup()
    mockedStartRun.mockResolvedValue(
      run({ id: 10, platform: 'ks', status: 'queued' }),
    )
    renderRoute()
    await screen.findByText(rule.name)

    await user.click(screen.getByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    await user.click(screen.getByRole('combobox', { name: '采集平台' }))
    await user.click(await screen.findByRole('option', { name: '快手' }))
    expect(
      screen.getByRole('combobox', { name: '采集平台' }),
    ).toHaveTextContent('快手')
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    await waitFor(() =>
      expect(mockedStartRun).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platform: 'ks',
        max_results_per_term: 10,
      }),
    )
  })

  it('switches to Douyin with the existing Shadcn platform selector', async () => {
    const user = userEvent.setup()
    mockedStartRun.mockResolvedValue(
      run({ id: 11, platform: 'dy', status: 'queued' }),
    )
    renderRoute()
    await screen.findByText(rule.name)

    await user.click(screen.getByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    await user.click(screen.getByRole('combobox', { name: '采集平台' }))
    await user.click(await screen.findByRole('option', { name: '抖音' }))
    expect(
      screen.getByRole('combobox', { name: '采集平台' }),
    ).toHaveTextContent('抖音')
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    await waitFor(() =>
      expect(mockedStartRun).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platform: 'dy',
        max_results_per_term: 10,
      }),
    )
  })

  it('switches to Xiaohongshu with the existing Shadcn platform selector', async () => {
    const user = userEvent.setup()
    mockedStartRun.mockResolvedValue(
      run({ id: 12, platform: 'xhs', status: 'queued' }),
    )
    renderRoute()
    await screen.findByText(rule.name)

    await user.click(screen.getByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    await user.click(screen.getByRole('combobox', { name: '采集平台' }))
    await user.click(await screen.findByRole('option', { name: '小红书' }))
    expect(
      screen.getByRole('combobox', { name: '采集平台' }),
    ).toHaveTextContent('小红书')
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    await waitFor(() =>
      expect(mockedStartRun).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platform: 'xhs',
        max_results_per_term: 10,
      }),
    )
  })

  it('rejects more than twenty terms before creating a task', async () => {
    const user = userEvent.setup()
    const oversized = {
      ...rule,
      id: 2,
      name: '过大的规则',
      terms: Array.from({ length: 21 }, (_, index) => `搜索词${index + 1}`),
    }
    mockedFetchRules.mockResolvedValue({ rules: [oversized] })
    renderRoute()

    await user.click(await screen.findByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /过大的规则/u }))
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    expect(
      await screen.findByText('这条规则超过 20 个搜索词，请拆分后再采集。'),
    ).toBeVisible()
    expect(screen.getByRole('combobox', { name: '监控规则' })).toHaveFocus()
    expect(mockedStartRun).not.toHaveBeenCalled()
  })

  it('shows active progress, prevents another start, and cancels explicitly', async () => {
    const user = userEvent.setup()
    mockedFetchRuns.mockResolvedValue({
      runs: [
        run({
          status: 'running',
          current_term_position: 0,
          new_count: 0,
          repeated_count: 0,
          total_count: 0,
          finished_at: null,
        }),
      ],
      next_before_id: null,
    })
    renderRoute()

    expect(await screen.findByText(`正在采集“${rule.name}”`)).toBeVisible()
    expect(screen.getByText('第 1 / 2 个搜索词')).toBeVisible()
    expect(screen.getByRole('button', { name: '开始采集' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '取消任务' }))
    await waitFor(() => expect(mockedCancelRun).toHaveBeenCalledWith(7))
  })

  it('loads older task history through the opaque cursor', async () => {
    const user = userEvent.setup()
    mockedFetchRuns.mockImplementation(async (_signal, options = {}) => {
      if (options.beforeId === 6) {
        return {
          runs: [run({ id: 6, rule_name: '更早的采集任务' })],
          next_before_id: null,
        }
      }
      return { runs: [run()], next_before_id: 6 }
    })
    renderRoute()

    await user.click(
      await screen.findByRole('button', { name: '加载更多任务' }),
    )

    expect(await screen.findByText('更早的采集任务')).toBeVisible()
    expect(mockedFetchRuns).toHaveBeenCalledWith(expect.any(AbortSignal), {
      beforeId: 6,
    })
    expect(screen.queryByRole('button', { name: '加载更多任务' })).toBeNull()
  })

  it('shows bounded guidance when cancellation fails', async () => {
    const user = userEvent.setup()
    mockedFetchRuns.mockResolvedValue({
      runs: [run({ status: 'running', finished_at: null })],
      next_before_id: null,
    })
    mockedCancelRun.mockRejectedValue(
      new SearchRunApiError(
        '该采集任务已经结束，无法取消。',
        'search_run_not_active',
        409,
      ),
    )
    renderRoute()

    await user.click(await screen.findByRole('button', { name: '取消任务' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '该采集任务已经结束，无法取消。',
    )
  })

  it('keeps bounded API conflict guidance beside the start form', async () => {
    const user = userEvent.setup()
    mockedStartRun.mockRejectedValue(
      new SearchRunApiError(
        '谷歌浏览器正在执行其他操作，请稍后重试。',
        'browser_operation_active',
        409,
      ),
    )
    renderRoute()

    await user.click(await screen.findByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '谷歌浏览器正在执行其他操作，请稍后重试。',
    )
  })

  it('renders deep-linked new/repeated evidence with safe original links', async () => {
    mockedFetchResults.mockResolvedValue({
      results: [
        result({
          id: 12,
          kind: 'repeated',
          title: '历史内容再次出现',
          matched_terms: ['龙田街道', '竹坑社区'],
        }),
      ],
      total: 51,
      limit: 50,
      offset: 50,
    })
    const { router } = renderRoute('/collection-runs/7?kind=repeated&offset=50')

    expect(await screen.findByText('历史内容再次出现')).toBeVisible()
    expect(screen.getByText('历史内容再次命中')).toBeVisible()
    expect(screen.getAllByText('龙田街道')).toHaveLength(2)
    expect(screen.getAllByText('竹坑社区')).toHaveLength(2)
    const original = screen.getByRole('link', { name: '打开原文' })
    expect(original).toHaveAttribute(
      'href',
      'https://www.toutiao.com/article/100/',
    )
    expect(original).toHaveAttribute('target', '_blank')
    expect(original).toHaveAttribute('rel', 'noreferrer')
    expect(mockedFetchResults).toHaveBeenCalledWith(
      7,
      'repeated',
      expect.any(AbortSignal),
      { offset: 50 },
    )

    await userEvent.click(screen.getByRole('button', { name: '上一页' }))
    await waitFor(() =>
      expect(router.state.location.search).toBe('?kind=repeated'),
    )
  })

  it('renders the Weibo identity in history and detail views', async () => {
    mockedFetchRuns.mockResolvedValue({
      runs: [run({ platform: 'wb' })],
      next_before_id: null,
    })
    const list = renderRoute()

    const historyPlatform = await screen.findByText(/微博 · 2 个搜索词/u)
    expect(historyPlatform.parentElement?.querySelector('img')).toHaveAttribute(
      'src',
      weiboLogo,
    )
    list.unmount()

    mockedFetchRun.mockResolvedValue(run({ platform: 'wb' }))
    mockedFetchResults.mockResolvedValue({
      results: [
        result({
          platform: 'wb',
          platform_content_id: '5012345678901234',
          content_url: 'https://m.weibo.cn/detail/5012345678901234',
        }),
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    renderRoute('/collection-runs/7')

    const detailPlatform = await screen.findByText('微博 · 规则快照')
    expect(detailPlatform.querySelector('img')).toHaveAttribute(
      'src',
      weiboLogo,
    )
    expect(screen.getByRole('link', { name: '打开原文' })).toHaveAttribute(
      'href',
      'https://m.weibo.cn/detail/5012345678901234',
    )
  })

  it('renders the Kuaishou identity in history and detail views', async () => {
    mockedFetchRuns.mockResolvedValue({
      runs: [run({ platform: 'ks' })],
      next_before_id: null,
    })
    const list = renderRoute()

    const historyPlatform = await screen.findByText(/快手 · 2 个搜索词/u)
    expect(historyPlatform.parentElement?.querySelector('img')).toHaveAttribute(
      'src',
      kuaishouLogo,
    )
    list.unmount()

    mockedFetchRun.mockResolvedValue(run({ platform: 'ks' }))
    mockedFetchResults.mockResolvedValue({
      results: [
        result({
          platform: 'ks',
          platform_content_id: '3xabc123',
          content_type: 'video',
          content_url: 'https://www.kuaishou.com/short-video/3xabc123',
        }),
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    renderRoute('/collection-runs/7')

    const detailPlatform = await screen.findByText('快手 · 规则快照')
    expect(detailPlatform.querySelector('img')).toHaveAttribute(
      'src',
      kuaishouLogo,
    )
    expect(screen.getByRole('link', { name: '打开原文' })).toHaveAttribute(
      'href',
      'https://www.kuaishou.com/short-video/3xabc123',
    )
  })

  it('renders the Douyin identity in history and detail views', async () => {
    mockedFetchRuns.mockResolvedValue({
      runs: [run({ platform: 'dy' })],
      next_before_id: null,
    })
    const list = renderRoute()

    const historyPlatform = await screen.findByText(/抖音 · 2 个搜索词/u)
    expect(historyPlatform.parentElement?.querySelector('img')).toHaveAttribute(
      'src',
      douyinLogo,
    )
    list.unmount()

    mockedFetchRun.mockResolvedValue(run({ platform: 'dy' }))
    mockedFetchResults.mockResolvedValue({
      results: [
        result({
          platform: 'dy',
          platform_content_id: '7512345678901234567',
          content_type: 'video',
          content_url: 'https://www.douyin.com/video/7512345678901234567',
        }),
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    renderRoute('/collection-runs/7')

    const detailPlatform = await screen.findByText('抖音 · 规则快照')
    expect(detailPlatform.querySelector('img')).toHaveAttribute(
      'src',
      douyinLogo,
    )
    expect(screen.getByRole('link', { name: '打开原文' })).toHaveAttribute(
      'href',
      'https://www.douyin.com/video/7512345678901234567',
    )
  })

  it('renders the Xiaohongshu identity and opens through the product action', async () => {
    mockedFetchRuns.mockResolvedValue({
      runs: [run({ platform: 'xhs' })],
      next_before_id: null,
    })
    const list = renderRoute()

    const historyPlatform = await screen.findByText(/小红书 · 2 个搜索词/u)
    expect(historyPlatform.parentElement?.querySelector('img')).toHaveAttribute(
      'src',
      xiaohongshuLogo,
    )
    list.unmount()

    mockedFetchRun.mockResolvedValue(run({ platform: 'xhs' }))
    mockedFetchResults.mockResolvedValue({
      results: [
        result({
          platform: 'xhs',
          platform_content_id: '0123456789abcdef01234567',
          content_type: 'image',
          snippet: '小红书公开信息',
          published_at_text: '',
          content_url:
            'https://www.xiaohongshu.com/explore/0123456789abcdef01234567',
        }),
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    renderRoute('/collection-runs/7')

    const detailPlatform = await screen.findByText('小红书 · 规则快照')
    expect(detailPlatform.querySelector('img')).toHaveAttribute(
      'src',
      xiaohongshuLogo,
    )
    expect(screen.queryByRole('link', { name: '打开原文' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '打开原文' }))
    await waitFor(() => expect(mockedOpenResult).toHaveBeenCalledWith(7, 11))
    expect(await screen.findByText('已在谷歌浏览器打开')).toBeVisible()
  })

  it('owns one XHS open mutation and disables every XHS button while pending', async () => {
    mockedFetchRun.mockResolvedValue(run({ platform: 'xhs' }))
    mockedFetchResults.mockResolvedValue({
      results: [
        result({
          id: 11,
          platform: 'xhs',
          platform_content_id: '0123456789abcdef01234567',
          content_url:
            'https://www.xiaohongshu.com/explore/0123456789abcdef01234567',
        }),
        result({
          id: 12,
          platform: 'xhs',
          platform_content_id: 'abcdef0123456789abcdef01',
          content_url:
            'https://www.xiaohongshu.com/explore/abcdef0123456789abcdef01',
        }),
      ],
      total: 2,
      limit: 50,
      offset: 0,
    })
    let resolveOpen: ((value: { outcome: 'opened' }) => void) | undefined
    mockedOpenResult.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveOpen = resolve
        }),
    )
    renderRoute('/collection-runs/7')
    const user = userEvent.setup()
    const buttons = await screen.findAllByRole('button', {
      name: '打开原文',
    })

    await user.click(buttons[0])

    const activeButton = screen.getByRole('button', { name: '正在打开…' })
    expect(activeButton).toBeDisabled()
    expect(activeButton).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: '打开原文' })).toBeDisabled()
    expect(mockedOpenResult).toHaveBeenCalledTimes(1)
    resolveOpen?.({ outcome: 'opened' })
    expect(await screen.findByText('已在谷歌浏览器打开')).toBeVisible()
  })

  it('shows actionable XHS outcomes and preserves technical API errors', async () => {
    mockedFetchRun.mockResolvedValue(run({ platform: 'xhs' }))
    mockedFetchResults.mockResolvedValue({
      results: [
        result({
          platform: 'xhs',
          platform_content_id: '0123456789abcdef01234567',
          content_url:
            'https://www.xiaohongshu.com/explore/0123456789abcdef01234567',
        }),
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    mockedOpenResult
      .mockResolvedValueOnce({ outcome: 'login_required' })
      .mockRejectedValueOnce(
        new SearchRunApiError(
          '无法连接本机后端服务，请确认服务已经启动。',
          'service_unavailable',
        ),
      )
    renderRoute('/collection-runs/7')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: '打开原文' }))
    expect(
      await screen.findByText('请先在当前谷歌浏览器中登录小红书，然后重试。'),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: '打开原文' }))
    expect(
      await screen.findByText('无法连接本机后端服务，请确认服务已经启动。'),
    ).toBeVisible()
  })

  it('performs one final result refresh when an active task finishes', async () => {
    mockedFetchRun.mockResolvedValue(
      run({
        status: 'running',
        current_term_position: 0,
        new_count: 0,
        repeated_count: 0,
        total_count: 0,
        finished_at: null,
      }),
    )
    const { queryClient } = renderRoute('/collection-runs/7')
    await screen.findByText('第 1 / 2 个搜索词')
    await waitFor(() => expect(mockedFetchResults).toHaveBeenCalled())
    mockedFetchResults.mockClear()

    act(() => {
      queryClient.setQueryData([...SEARCH_RUNS_QUERY_KEY, 7], run())
    })

    await waitFor(() => expect(mockedFetchResults).toHaveBeenCalledTimes(1))
  })

  it('turns login-required into an honest platform-account action', async () => {
    mockedFetchRun.mockResolvedValue(
      run({
        status: 'login_required',
        new_count: 0,
        repeated_count: 0,
        total_count: 0,
      }),
    )
    mockedFetchResults.mockResolvedValue({
      results: [],
      total: 0,
      limit: 50,
      offset: 0,
    })
    renderRoute('/collection-runs/7')

    expect(
      await screen.findByText(
        '请先到“平台账号”检查今日头条登录状态，再重新采集。',
      ),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: '前往平台账号' })).toHaveAttribute(
      'href',
      '/platform-accounts',
    )
    expect(screen.queryByText(/自动登录|绕过/u)).toBeNull()
  })

  it('uses the selected platform name in active and login guidance', async () => {
    mockedFetchRun.mockResolvedValue(
      run({
        platform: 'wb',
        status: 'login_required',
        new_count: 0,
        repeated_count: 0,
        total_count: 0,
      }),
    )
    mockedFetchResults.mockResolvedValue({
      results: [],
      total: 0,
      limit: 50,
      offset: 0,
    })
    renderRoute('/collection-runs/7')

    expect(
      await screen.findByText('请先到“平台账号”检查微博登录状态，再重新采集。'),
    ).toBeVisible()
  })

  it('rejects invalid deep links without issuing any API request', () => {
    renderRoute('/collection-runs/not-a-number')

    expect(screen.getByRole('alert')).toHaveTextContent('采集任务地址不正确')
    expect(mockedFetchRun).not.toHaveBeenCalled()
    expect(mockedFetchResults).not.toHaveBeenCalled()
  })
})
