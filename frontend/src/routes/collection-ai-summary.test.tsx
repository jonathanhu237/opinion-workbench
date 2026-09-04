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

const run: SearchRunDetail = {
  id: 70,
  monitoring_rule_id: 1,
  platform: 'wb',
  rule_name: '测试规则',
  term_count: 1,
  terms: ['测试街道 投诉'],
  max_results_per_term: 10,
  status: 'completed_with_results',
  failure_reason: null,
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
  platform: 'wb',
  platform_content_id: '5012345678901234',
  content_type: 'post',
  title: '原始搜索结果',
  snippet: '无需 AI 也能查看这条内容',
  creator_hash: '',
  publisher_name: '',
  published_at_text: '昨天',
  content_url: 'https://m.weibo.cn/detail/5012345678901234',
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
  })

  it('leaves original results usable and never generates on page entry or remount', async () => {
    const first = renderRun()
    expect(await screen.findByText('原始搜索结果')).toBeVisible()
    expect(await screen.findByText('还没有生成汇总。')).toBeVisible()
    expect(screen.getByRole('link', { name: '打开原文' })).toHaveAttribute(
      'href',
      result.content_url,
    )
    expect(screen.queryByRole('button', { name: '生成汇总' })).toBeNull()
    expect(screen.getByRole('link', { name: '前往生成报告' })).toHaveAttribute(
      'href',
      '/reports/new',
    )
    expect(mockedStart).not.toHaveBeenCalled()
    first.unmount()
    renderRun()
    await screen.findByText('还没有生成汇总。')
    expect(mockedStart).not.toHaveBeenCalled()
    expect(mockedCancel).not.toHaveBeenCalled()
  })

  it('preserves a full legacy run and result filters without offering new combined generation', async () => {
    mockedRun.mockResolvedValue({
      ...run,
      total_count: 67,
      new_count: 7,
      repeated_count: 60,
    })
    loadVersion(summaryFixture(), [itemFixture()])
    const { router } = renderRun('/collection-runs/70?kind=new&offset=50')
    await waitFor(() =>
      expect(router.state.location.search).toContain('summary=4'),
    )
    expect(router.state.location.search).toContain('kind=new')
    expect(router.state.location.search).toContain('offset=50')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('button', { name: '生成汇总' })).toBeNull()
    expect(mockedStart).not.toHaveBeenCalled()
    expect(mockedSettings).not.toHaveBeenCalled()
  })

  it('retries a failed legacy history read only, never an ambiguous generation', async () => {
    mockedHistory.mockRejectedValueOnce(
      new AISummaryApiError('service_unavailable'),
    )
    const user = userEvent.setup()
    renderRun()
    await user.click(
      await screen.findByRole('button', { name: '重新加载汇总' }),
    )
    expect(await screen.findByText('还没有生成汇总。')).toBeVisible()
    expect(mockedHistory).toHaveBeenCalledTimes(2)
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('does not rewrite saved legacy text after the shared configuration changes', async () => {
    loadVersion(
      summaryFixture({
        document: {
          overview: '冻结的旧版正文',
          items: [{ text: '保存的历史段落', source_ids: [11] }],
        },
      }),
      [itemFixture()],
    )
    const { client } = renderRun()
    expect(await screen.findByText('冻结的旧版正文')).toBeVisible()
    await act(async () => {
      client.setQueryData(AI_SETTINGS_QUERY_KEY, {
        ...savedSettings,
        revision: 4,
        model: 'new-model',
      })
    })
    expect(screen.queryByText(/new-model/)).toBeNull()
    expect(screen.getByText('冻结的旧版正文')).toBeVisible()
    expect(mockedStart).not.toHaveBeenCalled()
    expect(mockedSettings).not.toHaveBeenCalled()
  })

  it.each([
    ['active', { ...run, status: 'running' as const, finished_at: null }],
    ['empty', { ...run, new_count: 0, total_count: 0 }],
    ['too many', { ...run, new_count: 101, total_count: 101 }],
  ])('does not offer paid work for %s sources', async (_label, source) => {
    mockedRun.mockResolvedValue(source)
    renderRun()
    expect(
      await screen.findByRole('link', { name: '前往生成报告' }),
    ).toHaveAttribute('href', '/reports/new')
    expect(screen.queryByRole('button', { name: '生成汇总' })).toBeNull()
    expect(mockedStart).not.toHaveBeenCalled()
    expect(screen.getByText('原始搜索结果')).toBeVisible()
  })

  it('keeps legacy history and source access independent of current model configuration', async () => {
    mockedSettings.mockResolvedValue({
      base_url: null,
      model: null,
      has_api_key: false,
      revision: 0,
    })
    renderRun()
    expect(
      await screen.findByRole('link', { name: '前往生成报告' }),
    ).toHaveAttribute('href', '/reports/new')
    expect(screen.queryByRole('button', { name: '生成汇总' })).toBeNull()
    expect(mockedSettings).not.toHaveBeenCalled()
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
      screen.getByRole('link', { name: '原文 1 · 微博：测试街道道路情况' }),
    ).toHaveAttribute('href', itemFixture().source.content_url)
    expect(router.state.location.search).toContain('summary=4')
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it.each([
    {
      platform: 'wb',
      platformName: '微博',
      contentId: '5012345678901234',
      contentType: 'post',
      url: 'https://m.weibo.cn/detail/5012345678901234',
    },
  ] as const)(
    'attaches a compact underlined $platform citation to its report paragraph with the stored URL',
    async ({ platform, platformName, contentId, contentType, url }) => {
      mockedRun.mockResolvedValue({ ...run, platform })
      const item = itemFixture({
        source: {
          ...itemFixture().source,
          platform,
          platform_content_id: contentId,
          content_type: contentType,
          content_url: url,
        },
      })
      const summary = summaryFixture({ platform })
      loadVersion(summary, [item])
      const user = userEvent.setup()
      renderRun('/collection-runs/70?summary=4')
      const citation = await screen.findByRole('link', {
        name: `原文 1 · ${platformName}：${item.source.title}`,
      })
      expect(citation).toBeVisible()
      expect(citation).toHaveTextContent(`原文 1 · ${platformName}`)
      expect(citation).not.toHaveTextContent(item.source.title)
      expect(citation).toHaveAttribute('title', item.source.title)
      expect(citation).toHaveAttribute('href', url)
      expect(citation).toHaveAttribute('target', '_blank')
      expect(citation).toHaveAttribute('rel', 'noopener noreferrer')
      expect(citation).toHaveClass('underline')
      expect(citation.closest('p')).toHaveTextContent(
        '视频中可见路面积水，未能确认拍摄日期。',
      )
      expect(citation.closest('details')).toBeNull()
      screen.getByRole('combobox', { name: '汇总版本' }).focus()
      await user.tab()
      expect(citation).toHaveFocus()
      expect(mockedStart).not.toHaveBeenCalled()
      expect(mockedCancel).not.toHaveBeenCalled()
    },
  )

  it('keeps distinct frozen source numbers and keyboard order for multiple and repeated paragraph references', async () => {
    const first = itemFixture()
    const second = itemFixture({
      id: 22,
      position: 1,
      source: {
        ...first.source,
        result_id: 12,
        platform_content_id: '5012345678901235',
        content_url: 'https://m.weibo.cn/detail/5012345678901235',
        title: '测试街道另一处道路情况',
      },
    })
    const summary = summaryFixture({
      counts: { ...summaryFixture().counts, total: 2, relevant: 2 },
      document: {
        overview: '两条内容的测试汇总。',
        items: [
          { text: '两条内容均提及道路情况。', source_ids: [12, 11] },
          { text: '第一条内容尚未确认拍摄日期。', source_ids: [11] },
        ],
      },
    })
    loadVersion(summary, [first, second])
    const user = userEvent.setup()
    renderRun('/collection-runs/70?summary=4')
    const secondCitation = await screen.findByRole('link', {
      name: `原文 2 · 微博：${second.source.title}`,
    })
    const firstCitations = screen.getAllByRole('link', {
      name: `原文 1 · 微博：${first.source.title}`,
    })
    expect(firstCitations).toHaveLength(2)
    expect(secondCitation.closest('p')).toBe(firstCitations[0].closest('p'))
    expect(secondCitation.closest('p')).toHaveTextContent(
      '两条内容均提及道路情况。',
    )
    expect(firstCitations[1].closest('p')).toHaveTextContent(
      '第一条内容尚未确认拍摄日期。',
    )
    expect(firstCitations[1].closest('p')).not.toBe(
      firstCitations[0].closest('p'),
    )
    expect(secondCitation).toHaveAttribute('href', second.source.content_url)
    for (const citation of firstCitations) {
      expect(citation).toHaveAttribute('href', first.source.content_url)
    }
    screen.getByRole('combobox', { name: '汇总版本' }).focus()
    await user.tab()
    expect(secondCitation).toHaveFocus()
    await user.tab()
    expect(firstCitations[0]).toHaveFocus()
    await user.tab()
    expect(firstCitations[1]).toHaveFocus()
    expect(mockedStart).not.toHaveBeenCalled()
  })

  it('keeps analysis record links unchanged when the content analyses are expanded', async () => {
    loadVersion(summaryFixture(), [itemFixture()])
    const user = userEvent.setup()
    renderRun('/collection-runs/70?summary=4')
    await user.click(await screen.findByText('内容分析 · 1 条'))
    const article = screen
      .getByRole('heading', { name: itemFixture().source.title })
      .closest('article')
    expect(article).not.toBeNull()
    if (!article) throw new Error('Missing analysis article')
    const link = within(article).getByRole('link', { name: '打开原文' })
    expect(link).toHaveAttribute('href', itemFixture().source.content_url)
    expect(link).toHaveAttribute('rel', 'noreferrer')
    expect(link).not.toHaveAttribute('aria-label')
    expect(link).not.toHaveAttribute('title')
    expect(link).not.toHaveClass('underline')
    expect(
      within(article).getByText('内容反映监控范围内的公共问题。'),
    ).toBeVisible()
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
    await user.click(await screen.findByRole('option', { name: /汇总 #5/ }))
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
    expect(screen.getByText('使用已有分析')).toBeVisible()
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

  it('keeps inline Weibo citations keyboard-operable and uses the stored URL', async () => {
    const first = itemFixture({
      source: {
        ...itemFixture().source,
        platform: 'wb',
        platform_content_id: '5012345678901234',
        content_url: 'https://m.weibo.cn/detail/5012345678901234',
      },
    })
    const second = itemFixture({
      id: 22,
      position: 1,
      source: {
        ...first.source,
        result_id: 12,
        platform_content_id: '5012345678901235',
        content_url: 'https://m.weibo.cn/detail/5012345678901235',
        title: '另一条微博来源',
      },
    })
    loadVersion(
      summaryFixture({
        platform: 'wb',
        counts: { ...summaryFixture().counts, total: 2, relevant: 2 },
        document: {
          overview: '测试微博来源汇总。',
          items: [{ text: '两条来源待核实。', source_ids: [11, 12] }],
        },
      }),
      [first, second],
    )
    const user = userEvent.setup()
    const { container } = renderRun('/collection-runs/70?summary=4')
    const firstCitation = await screen.findByRole('link', {
      name: `原文 1 · 微博：${first.source.title}`,
    })
    const secondCitation = screen.getByRole('link', {
      name: `原文 2 · 微博：${second.source.title}`,
    })
    expect(firstCitation).toHaveClass('underline')
    expect(firstCitation).toHaveAttribute('title', first.source.title)
    expect(firstCitation.closest('p')).toHaveTextContent('两条来源待核实。')
    expect(firstCitation.closest('p')).toBe(secondCitation.closest('p'))
    expect(firstCitation).toHaveAttribute('href', first.source.content_url)
    expect(secondCitation).toHaveAttribute('href', second.source.content_url)
    screen.getByRole('combobox', { name: '汇总版本' }).focus()
    await user.tab()
    expect(firstCitation).toHaveFocus()
    expect(container.querySelector('a[href*="weibo.cn"]')).not.toBeNull()
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
      await screen.findByRole('link', { name: '原文 12 · 微博：内容 12' }),
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
      '汇总和原文记录不一致',
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
