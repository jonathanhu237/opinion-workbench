import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelSearchBatch,
  continueSearchBatch,
  fetchSearchBatch,
  fetchSearchBatchAttempts,
  fetchSearchBatches,
  startSearchBatch,
  SearchBatchApiError,
  type SearchBatchDetail,
} from '@/lib/api/search-batches'
import {
  fetchMonitoringRules,
  type MonitoringRule,
} from '@/lib/api/monitoring-rules'
import {
  fetchSearchRun,
  fetchSearchRunResults,
  fetchSearchRuns,
  type SearchRunSummary,
} from '@/lib/api/search-runs'
import { CollectionBatchDetail } from '@/routes/collection-batch-detail'
import { CollectionRunDetail } from '@/routes/collection-run-detail'
import { CollectionRuns } from '@/routes/collection-runs'

vi.mock('@/lib/api/monitoring-rules', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/api/monitoring-rules')>()
  return { ...actual, fetchMonitoringRules: vi.fn() }
})

vi.mock('@/lib/api/ai-settings', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/ai-settings')>()),
  fetchAISettings: vi.fn().mockResolvedValue({
    base_url: null,
    model: null,
    has_api_key: false,
    revision: 0,
  }),
}))

vi.mock('@/lib/api/ai-summaries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/ai-summaries')>()),
  fetchAISummaries: vi
    .fn()
    .mockResolvedValue({ summaries: [], next_before_id: null }),
}))

vi.mock('@/lib/api/search-batches', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/api/search-batches')>()
  return {
    ...actual,
    fetchSearchBatches: vi.fn(),
    fetchSearchBatch: vi.fn(),
    fetchSearchBatchAttempts: vi.fn(),
    fetchSearchBatchResults: vi.fn(),
    showSearchBatchManualPage: vi.fn(),
    skipSearchBatchPlatform: vi.fn(),
    recoverSearchBatchPlatform: vi.fn(),
    startSearchBatch: vi.fn(),
    continueSearchBatch: vi.fn(),
    cancelSearchBatch: vi.fn(),
  }
})

vi.mock('@/lib/api/search-runs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/search-runs')>()
  return {
    ...actual,
    fetchSearchRuns: vi.fn(),
    fetchSearchRun: vi.fn(),
    fetchSearchRunResults: vi.fn(),
  }
})

const rule: MonitoringRule = {
  id: 1,
  name: '龙田街道及四个社区',
  monitoring_objects: ['龙田街道', '竹坑社区'],
  issue_keywords: [],
  terms: ['龙田街道', '竹坑社区'],
  enabled: true,
}

function standaloneRun(
  values: Partial<SearchRunSummary> = {},
): SearchRunSummary {
  return {
    id: 70,
    monitoring_rule_id: 1,
    platform: 'toutiao',
    rule_name: rule.name,
    term_count: 2,
    max_results_per_term: 10,
    status: 'completed_empty',
    current_term_position: 1,
    new_count: 0,
    repeated_count: 0,
    total_count: 0,
    created_at: '2026-08-26T08:00:00+00:00',
    started_at: '2026-08-26T08:00:01+00:00',
    finished_at: '2026-08-26T08:00:05+00:00',
    ...values,
  }
}

const completedProgress = {
  completed_term_count: 2,
  remaining_term_count: 0,
  next_term_position: null,
  checkpoint_basis: 'explicit' as const,
  recovery_available: true,
  pause_reason: null,
  completion_basis: 'attempt_success' as const,
  new_count: 0,
  repeated_count: 0,
  total_count: 0,
}

const pausedProgress = {
  ...completedProgress,
  completed_term_count: 1,
  remaining_term_count: 1,
  next_term_position: 1,
  pause_reason: 'attempt_failed' as const,
  completion_basis: null,
}

function batch(values: Partial<SearchBatchDetail> = {}): SearchBatchDetail {
  const run = standaloneRun({ id: 71, platform: 'toutiao' })
  return {
    id: 9,
    control_revision: 5,
    monitoring_rule_id: 1,
    rule_name: rule.name,
    term_count: 2,
    platform_count: 3,
    terminal_item_count: 3,
    max_results_per_term: 10,
    status: 'completed',
    current_item_position: null,
    terms: rule.terms,
    items: [
      {
        ...completedProgress,
        position: 0,
        platform: 'toutiao',
        status: 'completed',
        attempt_count: 1,
        latest_attempt: { attempt_number: 1, run },
        created_at: run.created_at,
        started_at: run.started_at,
        finished_at: run.finished_at,
      },
      {
        ...completedProgress,
        position: 1,
        platform: 'wb',
        status: 'completed',
        attempt_count: 1,
        latest_attempt: {
          attempt_number: 1,
          run: standaloneRun({ id: 72, platform: 'wb' }),
        },
        created_at: run.created_at,
        started_at: run.started_at,
        finished_at: run.finished_at,
      },
      {
        ...completedProgress,
        position: 2,
        platform: 'ks',
        status: 'completed',
        attempt_count: 1,
        latest_attempt: {
          attempt_number: 1,
          run: standaloneRun({ id: 73, platform: 'ks' }),
        },
        created_at: run.created_at,
        started_at: run.started_at,
        finished_at: run.finished_at,
      },
    ],
    created_at: run.created_at,
    started_at: run.started_at,
    finished_at: run.finished_at,
    ...values,
  }
}

const mockedFetchRules = vi.mocked(fetchMonitoringRules)
const mockedFetchBatches = vi.mocked(fetchSearchBatches)
const mockedFetchBatch = vi.mocked(fetchSearchBatch)
const mockedFetchAttempts = vi.mocked(fetchSearchBatchAttempts)
const mockedStartBatch = vi.mocked(startSearchBatch)
const mockedContinueBatch = vi.mocked(continueSearchBatch)
const mockedCancelBatch = vi.mocked(cancelSearchBatch)
const mockedFetchRuns = vi.mocked(fetchSearchRuns)
const mockedFetchRun = vi.mocked(fetchSearchRun)
const mockedFetchRunResults = vi.mocked(fetchSearchRunResults)

function renderRoute(initialEntry = '/collection-runs') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [
      { path: '/collection-runs', element: <CollectionRuns /> },
      {
        path: '/collection-batches/:batchId',
        element: <CollectionBatchDetail />,
      },
      { path: '/collection-runs/:runId', element: <CollectionRunDetail /> },
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

describe('multi-platform collection routes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedFetchRules.mockResolvedValue({ rules: [rule] })
    mockedFetchBatches.mockResolvedValue({ batches: [], next_before_id: null })
    mockedFetchRuns.mockResolvedValue({ runs: [], next_before_id: null })
    mockedFetchBatch.mockResolvedValue(batch())
    mockedFetchAttempts.mockResolvedValue({ attempts: [] })
    mockedFetchRun.mockResolvedValue({
      ...standaloneRun(),
      terms: rule.terms,
    })
    mockedFetchRunResults.mockResolvedValue({
      results: [],
      total: 0,
      limit: 50,
      offset: 0,
    })
    mockedStartBatch.mockResolvedValue(batch({ id: 10, status: 'queued' }))
    mockedContinueBatch.mockResolvedValue(batch({ status: 'running' }))
    mockedCancelBatch.mockResolvedValue(batch({ status: 'cancelled' }))
  })

  it('defaults all five Shadcn checkboxes and starts one batch in catalog order', async () => {
    const user = userEvent.setup()
    const { router } = renderRoute()

    await user.click(await screen.findByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(5)
    for (const checkbox of checkboxes) expect(checkbox).toBeChecked()
    await user.clear(screen.getByLabelText('每词最多采集'))
    await user.type(screen.getByLabelText('每词最多采集'), '7')
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    await waitFor(() =>
      expect(mockedStartBatch).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platforms: ['toutiao', 'wb', 'ks', 'dy', 'xhs'],
        max_results_per_term: 7,
      }),
    )
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/collection-batches/10'),
    )
  })

  it('allows any platform subset and keeps the submitted order canonical', async () => {
    const user = userEvent.setup()
    renderRoute()
    await user.click(await screen.findByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    await user.click(screen.getByRole('checkbox', { name: '微博' }))
    await user.click(screen.getByRole('checkbox', { name: '抖音' }))
    await user.click(screen.getByRole('checkbox', { name: '小红书' }))
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    await waitFor(() =>
      expect(mockedStartBatch).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platforms: ['toutiao', 'ks'],
        max_results_per_term: 10,
      }),
    )
  })

  it.each([
    { objectCount: 2, issueCount: 10, effectiveCount: 20 },
    { objectCount: 3, issueCount: 7, effectiveCount: 21 },
  ])(
    'counts $effectiveCount composed queries for the selector and execution limit',
    async ({ objectCount, issueCount, effectiveCount }) => {
      const user = userEvent.setup()
      const objects = Array.from(
        { length: objectCount },
        (_, index) => `对象${index}`,
      )
      const issues = Array.from(
        { length: issueCount },
        (_, index) => `问题${index}`,
      )
      const composedRule: MonitoringRule = {
        ...rule,
        name: '组合数量边界',
        monitoring_objects: objects,
        issue_keywords: issues,
        terms: objects.flatMap((object) =>
          issues.map((issue) => `${object} ${issue}`),
        ),
      }
      mockedFetchRules.mockResolvedValue({ rules: [composedRule] })
      const { router } = renderRoute()

      await user.click(
        await screen.findByRole('combobox', { name: '监控规则' }),
      )
      await user.click(
        await screen.findByRole('option', {
          name: `组合数量边界（${effectiveCount} 个词）`,
        }),
      )
      expect(mockedStartBatch).not.toHaveBeenCalled()
      await user.click(screen.getByRole('button', { name: '开始采集' }))

      if (effectiveCount === 20) {
        await waitFor(() =>
          expect(mockedStartBatch).toHaveBeenCalledExactlyOnceWith({
            monitoring_rule_id: composedRule.id,
            platforms: ['toutiao', 'wb', 'ks', 'dy', 'xhs'],
            max_results_per_term: 10,
          }),
        )
      } else {
        expect(
          await screen.findByText('这条规则超过 20 个搜索词，请拆分后再采集。'),
        ).toBeVisible()
        expect(mockedStartBatch).not.toHaveBeenCalled()
        expect(router.state.location.pathname).toBe('/collection-runs')
      }
    },
  )

  it('shows a nearby validation error when no platform is selected', async () => {
    const user = userEvent.setup()
    renderRoute()
    await user.click(await screen.findByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /龙田街道/u }))
    for (const checkbox of screen.getAllByRole('checkbox')) {
      await user.click(checkbox)
    }
    await user.click(screen.getByRole('button', { name: '开始采集' }))

    expect(await screen.findByText('请至少选择一个采集平台。')).toBeVisible()
    expect(mockedStartBatch).not.toHaveBeenCalled()
  })

  it('shows batch history without duplicating its child runs', async () => {
    mockedFetchBatches.mockResolvedValue({
      batches: [batch()],
      next_before_id: null,
    })
    renderRoute()

    expect(await screen.findByText('3 / 3')).toBeVisible()
    expect(screen.getByRole('link', { name: /查看/u })).toHaveAttribute(
      'href',
      '/collection-batches/9',
    )
    expect(screen.queryByText('之前的单平台任务')).toBeNull()
  })

  it('keeps new collection controls locked while a batch awaits verification', async () => {
    mockedFetchBatches.mockResolvedValue({
      batches: [
        batch({
          status: 'paused_for_manual_action',
          terminal_item_count: 1,
          current_item_position: 1,
          finished_at: null,
        }),
      ],
      next_before_id: null,
    })
    renderRoute()

    expect(await screen.findByText('采集已暂停，等待人工处理')).toBeVisible()
    expect(screen.getByRole('button', { name: '开始采集' })).toBeDisabled()
    for (const checkbox of screen.getAllByRole('checkbox')) {
      expect(checkbox).toHaveAttribute('aria-disabled', 'true')
      expect(checkbox).toHaveAttribute('tabindex', '-1')
    }
  })

  it('keeps standalone history readable through the old run detail link', async () => {
    mockedFetchRuns.mockResolvedValue({
      runs: [standaloneRun()],
      next_before_id: null,
    })
    renderRoute()

    expect(await screen.findByText('之前的单平台任务')).toBeVisible()
    expect(screen.getByRole('link', { name: /查看/u })).toHaveAttribute(
      'href',
      '/collection-runs/70',
    )
  })

  it('keeps an existing standalone run deep link readable', async () => {
    renderRoute('/collection-runs/70')

    expect(await screen.findByText('今日头条 · 规则快照')).toBeVisible()
    expect(screen.getByText(rule.name)).toBeVisible()
    expect(screen.getByRole('heading', { name: '采集结果' })).toBeVisible()
    expect(mockedFetchRun).toHaveBeenCalledWith(70, expect.any(AbortSignal))
  })

  it('keeps older standalone history reachable through its cursor', async () => {
    const user = userEvent.setup()
    mockedFetchRuns
      .mockResolvedValueOnce({
        runs: [standaloneRun()],
        next_before_id: 70,
      })
      .mockResolvedValueOnce({
        runs: [standaloneRun({ id: 69, rule_name: '更早的单平台任务' })],
        next_before_id: null,
      })
    renderRoute()

    await user.click(
      await screen.findByRole('button', { name: '加载更多单平台任务' }),
    )

    expect(await screen.findByText('更早的单平台任务')).toBeVisible()
    expect(mockedFetchRuns).toHaveBeenLastCalledWith(expect.any(AbortSignal), {
      beforeId: 70,
      scope: 'standalone',
    })
  })

  it('renders the ordered platform rail with truthful counts and detail links', async () => {
    renderRoute('/collection-batches/9')

    expect(
      await screen.findByRole('heading', { name: rule.name }),
    ).toBeVisible()
    const platformHeading = screen.getByRole('heading', { name: '平台进度' })
    const rail = platformHeading.parentElement
    expect(rail).toHaveTextContent('今日头条')
    expect(rail).toHaveTextContent('微博')
    expect(rail).toHaveTextContent('快手')
    expect(screen.getAllByRole('link', { name: /查看结果/u })).toHaveLength(3)
  })

  it('continues a paused platform and exposes immutable attempt history', async () => {
    const user = userEvent.setup()
    const firstAttempt = standaloneRun({
      id: 80,
      platform: 'wb',
      status: 'manual_challenge_required',
    })
    const paused = batch({
      status: 'paused_for_manual_action',
      terminal_item_count: 1,
      current_item_position: 1,
      items: [
        batch().items[0],
        {
          ...pausedProgress,
          position: 1,
          platform: 'wb',
          status: 'paused_for_manual_action',
          attempt_count: 2,
          latest_attempt: { attempt_number: 2, run: firstAttempt },
          created_at: firstAttempt.created_at,
          started_at: firstAttempt.started_at,
          finished_at: firstAttempt.finished_at,
        },
        {
          ...batch().items[2],
          status: 'queued',
          attempt_count: 0,
          latest_attempt: null,
          started_at: null,
          finished_at: null,
        },
      ],
      finished_at: null,
    })
    mockedFetchBatch.mockResolvedValue(paused)
    mockedFetchAttempts.mockResolvedValue({
      attempts: [
        { attempt_number: 2, run: firstAttempt },
        { attempt_number: 1, run: { ...firstAttempt, id: 79 } },
      ],
    })
    renderRoute('/collection-batches/9')

    expect(
      await screen.findByRole('heading', { name: '采集已暂停 · 微博' }),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: '查看 2 次尝试' }))
    expect(
      await screen.findByText((content) => content.includes('第 2 次 ·')),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: '继续采集' }))
    await waitFor(() =>
      expect(mockedContinueBatch).toHaveBeenCalledWith(9, {
        item_position: 1,
        expected_run_id: 80,
        expected_revision: 5,
      }),
    )
    expect(await screen.findByText(/已继续处理/u)).toBeVisible()
  })

  it('clears an earlier continue error when cancellation later succeeds', async () => {
    const user = userEvent.setup()
    const challengeRun = standaloneRun({
      id: 80,
      platform: 'wb',
      status: 'manual_challenge_required',
    })
    mockedFetchBatch.mockResolvedValue(
      batch({
        status: 'paused_for_manual_action',
        terminal_item_count: 1,
        current_item_position: 1,
        items: [
          batch().items[0],
          {
            ...pausedProgress,
            position: 1,
            platform: 'wb',
            status: 'paused_for_manual_action',
            attempt_count: 1,
            latest_attempt: { attempt_number: 1, run: challengeRun },
            created_at: challengeRun.created_at,
            started_at: challengeRun.started_at,
            finished_at: challengeRun.finished_at,
          },
          {
            ...batch().items[2],
            status: 'queued',
            attempt_count: 0,
            latest_attempt: null,
            started_at: null,
            finished_at: null,
          },
        ],
        finished_at: null,
      }),
    )
    mockedContinueBatch.mockRejectedValue(
      new SearchBatchApiError(
        '谷歌浏览器正在执行其他操作，请稍后重试。',
        'browser_operation_active',
        409,
      ),
    )
    renderRoute('/collection-batches/9')

    await user.click(await screen.findByRole('button', { name: '继续采集' }))
    expect(
      await screen.findByText('谷歌浏览器正在执行其他操作，请稍后重试。'),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: '取消批次' }))

    expect(
      await screen.findByText('已取消批次，已有结果仍然保留。'),
    ).toBeVisible()
    expect(
      screen.queryByText('谷歌浏览器正在执行其他操作，请稍后重试。'),
    ).toBeNull()
  })

  it('cancels the remaining batch from the overview', async () => {
    const user = userEvent.setup()
    mockedFetchBatch.mockResolvedValue(
      batch({ status: 'running', terminal_item_count: 1, finished_at: null }),
    )
    renderRoute('/collection-batches/9')

    await user.click(await screen.findByRole('button', { name: '取消批次' }))
    await waitFor(() =>
      expect(mockedCancelBatch).toHaveBeenCalledWith(9, {
        expected_revision: 5,
      }),
    )
    expect(
      await screen.findByText('已取消批次，已有结果仍然保留。'),
    ).toBeVisible()
  })
})
