import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { startAISummary } from '@/lib/api/ai-summaries'
import {
  cancelSearchBatch,
  continueSearchBatch,
  fetchSearchBatch,
  fetchSearchBatches,
  startSearchBatch,
  type SearchBatchDetail,
} from '@/lib/api/search-batches'
import {
  fetchMonitoringRules,
  type MonitoringRule,
} from '@/lib/api/monitoring-rules'
import { fetchPlatformConnections } from '@/lib/api/platform-connections'
import {
  fetchSearchRun,
  fetchSearchRunResults,
  fetchSearchRuns,
  type SearchRunSummary,
} from '@/lib/api/search-runs'
import { CollectionBatchDetail } from '@/routes/collection-batch-detail'
import { CollectionRunDetail } from '@/routes/collection-run-detail'
import { CollectionRuns } from '@/routes/collection-runs'

vi.mock('@/lib/api/platform-connections', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/platform-connections')>()),
  fetchPlatformConnections: vi.fn(),
}))
vi.mock('@/lib/api/monitoring-rules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/monitoring-rules')>()),
  fetchMonitoringRules: vi.fn(),
}))
vi.mock('@/lib/api/ai-summaries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/ai-summaries')>()),
  fetchAISummaries: vi
    .fn()
    .mockResolvedValue({ summaries: [], next_before_id: null }),
  startAISummary: vi.fn(),
}))
vi.mock('@/lib/api/search-batches', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/search-batches')>()),
  fetchSearchBatches: vi.fn(),
  fetchSearchBatch: vi.fn(),
  startSearchBatch: vi.fn(),
  continueSearchBatch: vi.fn(),
  cancelSearchBatch: vi.fn(),
}))
vi.mock('@/lib/api/search-runs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/search-runs')>()),
  fetchSearchRuns: vi.fn(),
  fetchSearchRun: vi.fn(),
  fetchSearchRunResults: vi.fn(),
}))

const stamp = '2026-08-27T08:00:00+00:00'
const rule: MonitoringRule = {
  id: 1,
  name: '社区规则',
  monitoring_objects: ['龙田街道'],
  issue_keywords: [],
  terms: ['龙田街道'],
  enabled: true,
}
const wbCatalog = {
  platforms: [
    {
      platform: 'wb' as const,
      display_name: '微博',
      availability: 'enabled' as const,
      status: 'not_checked' as const,
      guidance: 'none' as const,
      last_checked_at: null,
      active_attempt_id: null,
    },
  ],
}

function run(values: Partial<SearchRunSummary> = {}): SearchRunSummary {
  return {
    id: 31,
    monitoring_rule_id: 1,
    platform: 'wb',
    rule_name: rule.name,
    term_count: 1,
    max_results_per_term: 10,
    status: 'completed_with_results',
    failure_reason: null,
    current_term_position: 0,
    new_count: 1,
    repeated_count: 0,
    total_count: 1,
    created_at: stamp,
    started_at: stamp,
    finished_at: stamp,
    ...values,
  }
}

function batch(values: Partial<SearchBatchDetail> = {}): SearchBatchDetail {
  return {
    id: 8,
    monitoring_rule_id: 1,
    rule_name: rule.name,
    term_count: 1,
    platform_count: 1,
    terminal_item_count: 1,
    max_results_per_term: 10,
    status: 'completed',
    control_revision: 2,
    current_item_position: null,
    terms: rule.terms,
    created_at: stamp,
    started_at: stamp,
    finished_at: stamp,
    items: [
      {
        position: 0,
        platform: 'wb',
        status: 'completed',
        attempt_count: 1,
        latest_attempt: { attempt_number: 1, run: run() },
        completed_term_count: 1,
        remaining_term_count: 0,
        next_term_position: null,
        checkpoint_basis: 'explicit',
        recovery_available: true,
        pause_reason: null,
        completion_basis: 'attempt_success',
        new_count: 1,
        repeated_count: 0,
        total_count: 1,
        created_at: stamp,
        started_at: stamp,
        finished_at: stamp,
      },
    ],
    ...values,
  }
}

function renderRoute(initialEntry = '/collection-runs') {
  const client = new QueryClient({
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
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return {
    router,
    client,
    ...render(<RouterProvider router={router} />, { wrapper: Wrapper }),
  }
}

describe('Weibo collection routes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchPlatformConnections).mockResolvedValue(wbCatalog)
    vi.mocked(fetchMonitoringRules).mockResolvedValue({ rules: [rule] })
    vi.mocked(fetchSearchBatches).mockResolvedValue({
      batches: [],
      next_before_id: null,
    })
    vi.mocked(fetchSearchRuns).mockResolvedValue({
      runs: [],
      next_before_id: null,
    })
    vi.mocked(fetchSearchBatch).mockResolvedValue(batch())
    vi.mocked(fetchSearchRun).mockResolvedValue({ ...run(), terms: rule.terms })
    vi.mocked(fetchSearchRunResults).mockResolvedValue({
      results: [],
      total: 0,
      limit: 50,
      offset: 0,
    })
    vi.mocked(startSearchBatch).mockResolvedValue(
      batch({
        status: 'queued',
        terminal_item_count: 0,
        started_at: null,
        finished_at: null,
        items: [
          {
            ...batch().items[0],
            status: 'queued',
            attempt_count: 0,
            latest_attempt: null,
            completed_term_count: 0,
            remaining_term_count: 1,
            next_term_position: 0,
            completion_basis: null,
            new_count: 0,
            repeated_count: 0,
            total_count: 0,
            started_at: null,
            finished_at: null,
          },
        ],
      }),
    )
    vi.mocked(continueSearchBatch).mockResolvedValue(
      batch({ status: 'running', finished_at: null }),
    )
    vi.mocked(cancelSearchBatch).mockResolvedValue(
      batch({ status: 'cancelled' }),
    )
  })

  it('starts a selected platform collection from the monitoring rule', async () => {
    const user = userEvent.setup()
    const { router } = renderRoute()
    const limit = await screen.findByRole('spinbutton', {
      name: '每词最多采集',
    })
    expect(limit).toHaveValue(10)
    await waitFor(() => expect(limit).toBeEnabled())
    await user.clear(limit)
    await user.type(limit, '7')
    await user.click(await screen.findByRole('combobox', { name: '监控规则' }))
    await user.click(await screen.findByRole('option', { name: /社区规则/u }))
    await user.click(screen.getByRole('button', { name: '开始采集' }))
    await waitFor(() =>
      expect(startSearchBatch).toHaveBeenCalledWith({
        monitoring_rule_id: 1,
        platforms: ['wb'],
        max_results_per_term: 7,
      }),
    )
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/collection-batches/8'),
    )
  })

  it('shows a truthful empty state with the platform selector', async () => {
    renderRoute()
    expect(await screen.findByText('采集平台')).toBeVisible()
    expect(screen.getByRole('checkbox', { name: '微博' })).toBeVisible()
    expect(screen.getByRole('checkbox', { name: '抖音' })).toBeVisible()
  })

  it('keeps completed batch and standalone Weibo history readable', async () => {
    vi.mocked(fetchSearchBatches).mockResolvedValue({
      batches: [batch()],
      next_before_id: null,
    })
    vi.mocked(fetchSearchRuns).mockResolvedValue({
      runs: [run()],
      next_before_id: null,
    })
    renderRoute()
    expect(await screen.findByText('1 / 1')).toBeVisible()
    expect(screen.getByText('独立采集任务')).toBeVisible()
    expect(screen.getAllByRole('link', { name: '查看' })).toHaveLength(2)
  })

  it('renders an existing Weibo run detail without legacy platform names', async () => {
    renderRoute('/collection-runs/31')
    expect(await screen.findByText(rule.name)).toBeVisible()
    expect(screen.getByRole('heading', { name: '采集结果' })).toBeVisible()
    expect(screen.queryByText(/今日头条|抖音|快手|小红书/u)).toBeNull()
  })

  it('shows incomplete keyword coverage without presenting it as login failure', async () => {
    const incomplete = run({
      incomplete_terms: [
        {
          position: 0,
          term: '龙田街道',
          reason: 'view_all_unresolved',
          result_count: 1,
        },
      ],
    })
    vi.mocked(fetchSearchRun).mockResolvedValue({
      ...incomplete,
      terms: rule.terms,
    })
    renderRoute('/collection-runs/31')
    expect(
      await screen.findByText(
        /以下搜索词未能完整获取：龙田街道（已保留 1 条）/u,
      ),
    ).toBeVisible()
    expect(screen.queryByText(/请先到“平台账号”/u)).toBeNull()
  })

  it('keeps incomplete keywords visible when a later global failure is primary', async () => {
    const incomplete = run({
      status: 'structure_changed',
      failure_reason: 'page_state_unrecognized',
      incomplete_terms: [
        {
          position: 0,
          term: '龙田街道',
          reason: 'view_all_unresolved',
          result_count: 1,
        },
      ],
    })
    vi.mocked(fetchSearchRun).mockResolvedValue({
      ...incomplete,
      terms: rule.terms,
    })
    renderRoute('/collection-runs/31')
    expect(
      await screen.findByText(/微博页面尚未完整加载，或页面结构暂时无法识别/u),
    ).toBeVisible()
    expect(
      screen.getByText(/以下搜索词未能完整获取：龙田街道（已保留 1 条）/u),
    ).toBeVisible()
  })

  it('renders one-item batch progress and no platform fan-out', async () => {
    renderRoute('/collection-batches/8')
    expect(
      await screen.findByRole('heading', { name: '采集进度' }),
    ).toBeVisible()
    expect(screen.getByText('微博')).toBeVisible()
    expect(screen.getAllByRole('button', { name: /查看结果/u })).toHaveLength(1)
  })

  it('does not start legacy summary generation when opening a collection run', async () => {
    renderRoute('/collection-runs/31')
    await screen.findByRole('heading', { name: '采集结果' })
    expect(startAISummary).not.toHaveBeenCalled()
  })
})
