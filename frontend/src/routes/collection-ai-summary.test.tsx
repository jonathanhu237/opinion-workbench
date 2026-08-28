import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AI_SETTINGS_QUERY_KEY, fetchAISettings } from '@/lib/api/ai-settings'
import {
  AISummaryApiError,
  cancelAISummary,
  fetchAISummaries,
  fetchAISummary,
  fetchAISummaryItems,
  startAISummary,
  type AISummaryItem,
  type AISummaryRun,
} from '@/lib/api/ai-summaries'
import {
  itemFixture,
  pendingItemFixture,
  pendingSummaryFixture,
  summaryFixture,
} from '@/lib/api/ai-summaries.fixtures'
import {
  fetchSearchRun,
  fetchSearchRunResults,
  openSearchRunResult,
  type SearchRunDetail,
  type SearchResult,
} from '@/lib/api/search-runs'
import { CollectionRunDetail } from '@/routes/collection-run-detail'

vi.mock('@/lib/api/ai-settings', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/ai-settings')>()),
  fetchAISettings: vi.fn(),
}))
vi.mock('@/lib/api/ai-summaries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/ai-summaries')>()),
  fetchAISummaries: vi.fn(),
  fetchAISummary: vi.fn(),
  fetchAISummaryItems: vi.fn(),
  startAISummary: vi.fn(),
  cancelAISummary: vi.fn(),
}))
vi.mock('@/lib/api/search-runs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/search-runs')>()),
  fetchSearchRun: vi.fn(),
  fetchSearchRunResults: vi.fn(),
  openSearchRunResult: vi.fn(),
}))

const savedSettings = {
  base_url: 'https://api.example.com/v1',
  model: 'test-summary-model',
  has_api_key: true,
  revision: 3,
}
const mockedStart = vi.mocked(startAISummary)
const mockedCancel = vi.mocked(cancelAISummary)
const mockedHistory = vi.mocked(fetchAISummaries)
const mockedDetail = vi.mocked(fetchAISummary)
const mockedItems = vi.mocked(fetchAISummaryItems)
const mockedSettings = vi.mocked(fetchAISettings)
const mockedRun = vi.mocked(fetchSearchRun)
const mockedResults = vi.mocked(fetchSearchRunResults)
const mockedOpen = vi.mocked(openSearchRunResult)

const run: SearchRunDetail = {
  id: 70,
  monitoring_rule_id: 1,
  platform: 'dy',
  rule_name: '测试规则',
  term_count: 1,
  terms: ['测试街道 投诉'],
  max_results_per_term: 10,
  status: 'completed_with_results',
  current_term_position: 0,
  new_count: 1,
  repeated_count: 0,
  total_count: 1,
  created_at: '2026-08-28T08:00:00+00:00',
  started_at: '2026-08-28T08:00:00+00:00',
  finished_at: '2026-08-28T08:00:00+00:00',
}
const result: SearchResult = {
  id: 11,
  platform: 'dy',
  platform_content_id: '7512345678901234567',
  content_type: 'video',
  title: '原始搜索结果',
  snippet: '无需 AI 也能查看这条内容',
  creator_hash: '',
  publisher_name: '',
  published_at_text: '昨天',
  content_url: 'https://www.douyin.com/video/7512345678901234567',
  kind: 'new',
  matched_terms: ['测试街道 投诉'],
  first_seen_at: run.created_at,
  last_seen_at: run.created_at,
  first_observed_at: run.created_at,
  last_observed_at: run.created_at,
}

function renderRun(entry = '/collection-runs/70') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [{ path: '/collection-runs/:runId', element: <CollectionRunDetail /> }],
    { initialEntries: [entry] },
  )
  return {
    client,
    router,
    ...render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

function loadVersion(summary: AISummaryRun, items: AISummaryItem[]) {
  mockedHistory.mockResolvedValue({
    summaries: [summary],
    next_before_id: null,
  })
  mockedDetail.mockResolvedValue(summary)
  mockedItems.mockResolvedValue({
    items,
    total: items.length,
    limit: 100,
    offset: 0,
  })
}

describe('manual collection summaries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedSettings.mockResolvedValue(savedSettings)
    mockedHistory.mockResolvedValue({ summaries: [], next_before_id: null })
    mockedDetail.mockResolvedValue(summaryFixture())
    mockedItems.mockResolvedValue({
      items: [itemFixture()],
      total: 1,
      limit: 100,
      offset: 0,
    })
    mockedStart.mockReset()
    mockedCancel.mockReset()
    mockedRun.mockResolvedValue(run)
    mockedResults.mockResolvedValue({
      results: [result],
      total: 1,
      limit: 50,
      offset: 0,
    })
    mockedOpen.mockResolvedValue({ outcome: 'opened' })
  })

  it('leaves original results usable and never generates on page entry or remount', async () => {
    const first = renderRun()
    expect(await screen.findByText('原始搜索结果')).toBeVisible()
    expect(await screen.findByText('还没有生成汇总。')).toBeVisible()
    expect(screen.getByRole('link', { name: '打开原文' })).toHaveAttribute(
      'href',
      result.content_url,
    )
    expect(screen.getByRole('button', { name: '生成汇总' })).toHaveAttribute(
      'data-slot',
      'button',
    )
    expect(mockedStart).not.toHaveBeenCalled()
    first.unmount()
    renderRun()
    await screen.findByText('还没有生成汇总。')
    expect(mockedStart).not.toHaveBeenCalled()
    expect(mockedCancel).not.toHaveBeenCalled()
  })

  it('confirms the full run and frozen configuration, blocks double clicks and preserves result filters', async () => {
    mockedRun.mockResolvedValue({
      ...run,
      total_count: 67,
      new_count: 7,
      repeated_count: 60,
    })
    let finish: ((value: AISummaryRun) => void) | undefined
    mockedStart.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const user = userEvent.setup()
    const { client, router } = renderRun(
      '/collection-runs/70?kind=new&offset=50',
    )
    await user.click(await screen.findByRole('button', { name: '生成汇总' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAccessibleDescription(/全部 67 条/)
    expect(within(dialog).getByText(savedSettings.base_url)).toBeVisible()
    await act(async () => {
      client.setQueryData(AI_SETTINGS_QUERY_KEY, {
        ...savedSettings,
        model: 'changed-model',
        base_url: 'https://changed.example/v1',
        revision: 4,
      })
    })
    expect(within(dialog).queryByText('https://changed.example/v1')).toBeNull()
    await user.click(within(dialog).getByRole('checkbox'))
    await user.dblClick(
      within(dialog).getByRole('button', { name: '开始生成' }),
    )
    expect(mockedStart).toHaveBeenCalledOnce()
    const request = mockedStart.mock.calls[0][1]
    expect(request).toEqual({
      request_id: expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      ),
      force_refresh: true,
      configuration_revision: 3,
    })
    expect(
      within(dialog).getByRole('button', { name: '正在提交…' }),
    ).toBeDisabled()
    const queued = {
      ...pendingSummaryFixture(),
      request_id: request.request_id,
      force_refresh: true,
    }
    loadVersion(queued, [pendingItemFixture()])
    await act(async () => finish?.(queued))
    await waitFor(() =>
      expect(router.state.location.search).toContain('summary=4'),
    )
    expect(router.state.location.search).toContain('kind=new')
    expect(router.state.location.search).toContain('offset=50')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('retries an ambiguous submission with the same UUID and no automatic retry', async () => {
    mockedStart.mockRejectedValue(new AISummaryApiError('service_unavailable'))
    const user = userEvent.setup()
    renderRun()
    await user.click(await screen.findByRole('button', { name: '生成汇总' }))
    await user.click(screen.getByRole('button', { name: '开始生成' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('同一请求')
    expect(mockedStart).toHaveBeenCalledOnce()
    expect(screen.getByRole('checkbox')).toHaveAttribute(
      'aria-disabled',
      'true',
    )
    await user.click(screen.getByRole('button', { name: '开始生成' }))
    await waitFor(() => expect(mockedStart).toHaveBeenCalledTimes(2))
    expect(mockedStart.mock.calls[0]).toEqual(mockedStart.mock.calls[1])
  })

  it('requires a new explicit confirmation when the saved configuration changes', async () => {
    mockedStart.mockRejectedValue(
      new AISummaryApiError('ai_configuration_changed', 409),
    )
    const user = userEvent.setup()
    renderRun()
    await user.click(await screen.findByRole('button', { name: '生成汇总' }))
    await user.click(screen.getByRole('button', { name: '开始生成' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '请关闭弹窗后重新确认',
    )
    expect(screen.getByRole('button', { name: '开始生成' })).toBeDisabled()
    mockedSettings.mockResolvedValue({
      ...savedSettings,
      revision: 4,
      model: 'new-model',
    })
    await user.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() => expect(mockedSettings).toHaveBeenCalledTimes(2))
    await user.click(screen.getByRole('button', { name: '生成汇总' }))
    expect(await screen.findByText('new-model')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '开始生成' }))
    await waitFor(() => expect(mockedStart).toHaveBeenCalledTimes(2))
    expect(mockedStart.mock.calls[1][1].configuration_revision).toBe(4)
    expect(mockedStart.mock.calls[0][1].request_id).not.toBe(
      mockedStart.mock.calls[1][1].request_id,
    )
  })

  it.each([
    [
      'active',
      { ...run, status: 'running' as const, finished_at: null },
      '采集结束后可生成汇总。',
    ],
    ['empty', { ...run, new_count: 0, total_count: 0 }, '本次采集暂无内容。'],
    [
      'too many',
      { ...run, new_count: 101, total_count: 101 },
      '一次最多汇总 100 条内容',
    ],
  ])(
    'does not offer paid work for %s sources',
    async (_label, source, message) => {
      mockedRun.mockResolvedValue(source)
      renderRun()
      await screen.findByText(message, { exact: false })
      expect(screen.getByRole('button', { name: '生成汇总' })).toBeDisabled()
      expect(mockedStart).not.toHaveBeenCalled()
      expect(screen.getByText('原始搜索结果')).toBeVisible()
    },
  )

  it('points missing configuration to settings while preserving source access', async () => {
    mockedSettings.mockResolvedValue({
      base_url: null,
      model: null,
      has_api_key: false,
      revision: 0,
    })
    renderRun()
    expect(
      await screen.findByRole('link', { name: '前往 AI 配置' }),
    ).toHaveAttribute('href', '/ai-settings')
    expect(screen.getByRole('button', { name: '生成汇总' })).toBeDisabled()
    expect(screen.getByRole('link', { name: '打开原文' })).toHaveAttribute(
      'href',
      result.content_url,
    )
  })

  it('retains a saved version in the URL and renders escaped prose plus owned links', async () => {
    const summary = summaryFixture({
      document: {
        overview: '<script>not executable</script>',
        items: [{ text: '[ignore](https://evil.example)', source_ids: [11] }],
      },
    })
    loadVersion(summary, [itemFixture()])
    const { router, container } = renderRun()
    expect(
      await screen.findByText('<script>not executable</script>'),
    ).toBeVisible()
    expect(screen.getByText('[ignore](https://evil.example)')).toBeVisible()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('a[href="https://evil.example"]')).toBeNull()
    expect(
      screen.getByRole('link', { name: /原文：测试街道道路情况/ }),
    ).toHaveAttribute('href', itemFixture().source.content_url)
    expect(router.state.location.search).toContain('summary=4')
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('reads old versions without switching them to a newer history entry', async () => {
    const latest = summaryFixture({ id: 5, model: 'new-model' })
    mockedHistory.mockResolvedValue({
      summaries: [latest, summaryFixture()],
      next_before_id: null,
    })
    mockedDetail.mockImplementation(async (id) =>
      id === 4 ? summaryFixture() : latest,
    )
    const user = userEvent.setup()
    const { router } = renderRun('/collection-runs/70?summary=4&kind=repeated')
    await screen.findByText('发布者反映一处道路积水，实际情况尚待核实。')
    expect(router.state.location.search).toContain('summary=4')
    expect(mockedDetail.mock.calls.every(([id]) => id === 4)).toBe(true)
    await user.click(screen.getByRole('combobox', { name: '汇总版本' }))
    await user.click(screen.getByRole('option', { name: /汇总 #5/ }))
    await waitFor(() =>
      expect(router.state.location.search).toContain('summary=5'),
    )
    expect(router.state.location.search).toContain('kind=repeated')
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('polls only active work and cancels once while retaining completed analysis', async () => {
    loadVersion(pendingSummaryFixture(), [pendingItemFixture()])
    const user = userEvent.setup()
    renderRun('/collection-runs/70?summary=4')
    expect(await screen.findByText(/已处理 0 \/ 1 条/)).toBeVisible()
    await waitFor(
      () => expect(mockedDetail.mock.calls.length).toBeGreaterThan(1),
      { timeout: 2200 },
    )
    let finish: ((value: AISummaryRun) => void) | undefined
    mockedCancel.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    await user.dblClick(screen.getByRole('button', { name: '取消生成' }))
    expect(mockedCancel).toHaveBeenCalledExactlyOnceWith(4)
    const cancelled = summaryFixture({ status: 'cancelled', document: null })
    loadVersion(cancelled, [itemFixture()])
    await act(async () => finish?.(cancelled))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '取消生成' })).toBeNull(),
    )
    await screen.findByText('内容分析 · 1 条')
    const calls = mockedDetail.mock.calls.length
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1200))
    })
    expect(mockedDetail).toHaveBeenCalledTimes(calls)
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('shows incomplete input, valid uncertain analysis, preserved failures and partial token counts separately', async () => {
    const base = summaryFixture()
    const items = [
      itemFixture({ reused_from_item_id: 1, attempted: false, usage: null }),
      itemFixture({
        id: 22,
        position: 1,
        source: {
          ...itemFixture().source,
          result_id: 12,
          title: '无法确认地点的内容',
        },
        decision: 'uncertain',
        reason: '无法确认具体地点。',
      }),
      itemFixture({
        id: 23,
        position: 2,
        source: {
          ...itemFixture().source,
          result_id: 13,
          title: '媒体未能获取',
        },
        status: 'input_incomplete',
        decision: null,
        reason: null,
        evidence_summary: null,
        attempted: false,
        usage: null,
        input_status: 'partial',
        input_issues: ['media_missing'],
        error: {
          stage: 'acquisition',
          code: 'input_incomplete',
          message: '正文或媒体不完整，本条未调用模型。',
        },
      }),
    ]
    loadVersion(
      summaryFixture({
        status: 'failed',
        document: null,
        counts: {
          ...base.counts,
          total: 3,
          uncertain: 1,
          input_incomplete: 1,
          reused: 1,
        },
        usage: { ...base.usage, accounted_requests: 1, complete: false },
        error: {
          stage: 'composition',
          code: 'invalid_json',
          message: '模型返回的内容不是有效的 JSON。',
        },
      }),
      items,
    )
    const user = userEvent.setup()
    renderRun('/collection-runs/70?summary=4')
    expect(await screen.findByText(/统计不完整/)).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('生成汇总')
    expect(screen.getByRole('alert')).toHaveTextContent(
      '已完成的内容分析仍可查看',
    )
    await user.click(await screen.findByText('内容分析 · 3 条'))
    expect(screen.getByText('无法确认具体地点。')).toBeVisible()
    expect(screen.getByText('复用已有分析')).toBeVisible()
    expect(screen.getByText(/本条未调用模型/)).toBeVisible()
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it.each(['cancelled', 'interrupted'] as const)(
    'does not repeat retained-analysis guidance for %s',
    async (status) => {
      loadVersion(
        summaryFixture({
          status,
          document: null,
          error: {
            stage: 'execution',
            code: status,
            message:
              status === 'cancelled'
                ? '已取消，已完成的内容分析仍然保留。'
                : '上次分析已中断，已完成的内容分析仍然保留。',
          },
        }),
        [itemFixture()],
      )
      renderRun('/collection-runs/70?summary=4')
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent('已完成的内容分析仍然保留。')
      expect(alert).not.toHaveTextContent('已完成的内容分析仍可查看。')
      expect(await screen.findByText('内容分析 · 1 条')).toBeInTheDocument()
      expect(mockedStart).not.toHaveBeenCalled()
    },
  )

  it('opens Xiaohongshu citations with the existing stored-result action', async () => {
    mockedRun.mockResolvedValue({ ...run, platform: 'xhs' })
    const item = itemFixture({
      source: {
        ...itemFixture().source,
        platform: 'xhs',
        platform_content_id: '0123456789abcdef01234567',
        content_url:
          'https://www.xiaohongshu.com/explore/0123456789abcdef01234567',
      },
    })
    loadVersion(summaryFixture({ platform: 'xhs' }), [item])
    const user = userEvent.setup()
    const { container } = renderRun('/collection-runs/70?summary=4')
    await user.click(
      await screen.findByRole('button', { name: /原文：测试街道道路情况/ }),
    )
    expect(mockedOpen).toHaveBeenCalledExactlyOnceWith(70, 11)
    expect(container.querySelector('a[href*="xiaohongshu.com"]')).toBeNull()
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('resolves citations beyond the visible analysis page and preserves pagination in the URL', async () => {
    const items = Array.from({ length: 12 }, (_, position) =>
      itemFixture({
        id: 21 + position,
        position,
        source: {
          ...itemFixture().source,
          result_id: 11 + position,
          title: `内容 ${position + 1}`,
        },
      }),
    )
    const base = summaryFixture()
    loadVersion(
      summaryFixture({
        counts: { ...base.counts, total: 12, relevant: 12 },
        document: {
          overview: '跨页汇总',
          items: [{ text: '引用最后一条', source_ids: [22] }],
        },
      }),
      items,
    )
    const user = userEvent.setup()
    const { router } = renderRun('/collection-runs/70?summary=4')
    expect(
      await screen.findByRole('link', { name: /原文：内容 12/ }),
    ).toBeVisible()
    await user.click(screen.getByText('内容分析 · 12 条'))
    expect(screen.getByRole('heading', { name: '内容 1' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '内容 12' })).toBeNull()
    await user.click(screen.getByRole('button', { name: '下一页分析' }))
    expect(screen.getByRole('heading', { name: '内容 12' })).toBeVisible()
    expect(router.state.location.search).toContain('analysis_offset=10')
  })

  it('refuses foreign summaries or unresolved citations without hiding raw results', async () => {
    mockedHistory.mockResolvedValue({
      summaries: [summaryFixture()],
      next_before_id: null,
    })
    mockedDetail.mockResolvedValue(summaryFixture({ source_run_id: 999 }))
    renderRun('/collection-runs/70?summary=4')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '汇总接口返回的数据',
    )
    expect(screen.getByText('原始搜索结果')).toBeVisible()
    expect(
      screen.queryByText('发布者反映一处道路积水，实际情况尚待核实。'),
    ).toBeNull()
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('does not render a report with invented citations or automatically retry it', async () => {
    loadVersion(
      summaryFixture({
        document: {
          overview: '未验证的汇总不应展示',
          items: [{ text: '未验证的段落', source_ids: [999] }],
        },
      }),
      [itemFixture()],
    )
    renderRun('/collection-runs/70?summary=4')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '汇总与原文记录不一致',
    )
    expect(screen.queryByText('未验证的汇总不应展示')).toBeNull()
    expect(screen.queryByText('未验证的段落')).toBeNull()
    expect(screen.getByText('原始搜索结果')).toBeVisible()
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('labels missing token accounting as unknown and never calls reuse free', async () => {
    const base = summaryFixture()
    loadVersion(
      summaryFixture({
        counts: { ...base.counts, reused: 1 },
        usage: {
          attempted_requests: 1,
          accounted_requests: 0,
          complete: false,
          prompt_tokens: null,
          completion_tokens: null,
          total_tokens: null,
        },
      }),
      [itemFixture({ reused_from_item_id: 1, attempted: false, usage: null })],
    )
    renderRun('/collection-runs/70?summary=4')
    expect(
      await screen.findByText(/本次调用 1 次 · Token 用量未知/),
    ).toBeVisible()
    expect(screen.queryByText(/本次未调用模型/)).toBeNull()
    expect(screen.queryByText(/本次 0 Token/)).toBeNull()
  })
})
