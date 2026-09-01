import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '@/lib/api/search-batches'
import {
  openSearchRunResult,
  type SearchRunStatus,
  type SearchRunSummary,
} from '@/lib/api/search-runs'
import { CollectionBatchDetail } from '@/routes/collection-batch-detail'

vi.mock('@/lib/api/search-batches', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/search-batches')>()),
  fetchSearchBatch: vi.fn(),
  fetchSearchBatchAttempts: vi.fn(),
  fetchSearchBatchResults: vi.fn(),
  continueSearchBatch: vi.fn(),
  skipSearchBatchPlatform: vi.fn(),
  cancelSearchBatch: vi.fn(),
  recoverSearchBatchPlatform: vi.fn(),
  showSearchBatchManualPage: vi.fn(),
}))
vi.mock('@/lib/api/search-runs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/search-runs')>()),
  openSearchRunResult: vi.fn(),
}))

const stamp = '2026-08-27T08:00:00+00:00'
function fixture(
  status: SearchRunStatus = 'login_required',
): api.SearchBatchDetail {
  const run: SearchRunSummary = {
    id: 31,
    monitoring_rule_id: 1,
    platform: 'wb',
    rule_name: '社区规则',
    term_count: 2,
    max_results_per_term: 10,
    status,
    current_term_position: 1,
    new_count: 1,
    repeated_count: 0,
    total_count: 1,
    created_at: stamp,
    started_at: stamp,
    finished_at: stamp,
  }
  return {
    id: 8,
    monitoring_rule_id: 1,
    rule_name: '社区规则',
    term_count: 2,
    platform_count: 1,
    terminal_item_count: 0,
    max_results_per_term: 10,
    status: 'paused_for_manual_action',
    control_revision: 12,
    current_item_position: 0,
    terms: ['龙田街道', '竹坑社区'],
    created_at: stamp,
    started_at: stamp,
    finished_at: null,
    items: [
      {
        position: 0,
        platform: 'wb',
        status: 'paused_for_manual_action',
        attempt_count: 2,
        latest_attempt: { attempt_number: 2, run },
        completed_term_count: 1,
        remaining_term_count: 1,
        next_term_position: 1,
        checkpoint_basis: 'explicit',
        recovery_available: true,
        pause_reason: 'attempt_failed',
        completion_basis: null,
        new_count: 2,
        repeated_count: 1,
        total_count: 3,
        created_at: stamp,
        started_at: stamp,
        finished_at: null,
      },
    ],
  }
}
function ended(source: api.SearchBatchDetail): api.SearchBatchDetail {
  return {
    ...source,
    status: 'completed_with_failures',
    terminal_item_count: 1,
    finished_at: stamp,
    items: source.items.map((item) => ({
      ...item,
      status: 'failed',
      pause_reason: null,
      finished_at: stamp,
    })),
  }
}
function renderBatch(batch = fixture(), url = '/collection-batches/8') {
  vi.mocked(api.fetchSearchBatch).mockResolvedValue(batch)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [
      {
        path: '/collection-batches/:batchId',
        element: <CollectionBatchDetail />,
      },
    ],
    { initialEntries: [url] },
  )
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { client, router }
}
const input = { item_position: 0, expected_run_id: 31, expected_revision: 12 }

describe('manual batch recovery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.fetchSearchBatchAttempts).mockResolvedValue({ attempts: [] })
    vi.mocked(api.fetchSearchBatchResults).mockResolvedValue({
      results: [],
      total: 0,
      limit: 50,
      offset: 0,
    })
    vi.mocked(api.continueSearchBatch).mockResolvedValue(fixture())
    vi.mocked(api.skipSearchBatchPlatform).mockResolvedValue(ended(fixture()))
    vi.mocked(api.cancelSearchBatch).mockResolvedValue({
      ...ended(fixture()),
      status: 'cancelled',
    })
    vi.mocked(api.recoverSearchBatchPlatform).mockResolvedValue(fixture())
    vi.mocked(api.showSearchBatchManualPage).mockResolvedValue({
      outcome: 'opened_existing',
    })
    vi.mocked(openSearchRunResult).mockResolvedValue({ outcome: 'opened' })
  })

  it.each([
    ['login_required', '请打开平台，在当前谷歌浏览器中登录后继续采集。'],
    ['manual_challenge_required', '平台要求安全验证。'],
    ['platform_blocked_or_rate_limited', '平台暂时限制了访问。'],
    ['structure_changed', '平台页面发生变化'],
    ['timed_out', '采集等待超时。'],
    ['browser_unavailable', '无法连接谷歌浏览器。'],
    ['internal_error', '本次采集未能完成。'],
  ] as const)(
    'explains %s without inventing a login or captcha state',
    async (status, message) => {
      renderBatch(fixture(status))
      expect(
        await screen.findByRole('heading', { name: '采集已暂停 · 微博' }),
      ).toBeVisible()
      expect(screen.getByText(new RegExp(message, 'u'))).toBeVisible()
      expect(screen.getByText(/已确认完成 1 \/ 2 个搜索词/u)).toHaveTextContent(
        '继续时将从“竹坑社区”开始',
      )
      for (const name of ['打开平台', '继续采集', '跳过此平台', '取消采集'])
        expect(screen.getByRole('button', { name })).toBeEnabled()
    },
  )

  it('keeps keyboard activation, wrapping actions, and announced manual feedback', async () => {
    const user = userEvent.setup()
    renderBatch()
    const open = await screen.findByRole('button', { name: '打开平台' })
    expect(open.parentElement).toHaveClass('flex-wrap')
    await user.tab()
    await user.tab()
    expect(open).toHaveFocus()
    await user.keyboard('{Enter}')
    await waitFor(() =>
      expect(api.showSearchBatchManualPage).toHaveBeenCalledExactlyOnceWith(
        8,
        input,
      ),
    )
    const message = await screen.findByText(/已在谷歌浏览器中打开平台页面/u)
    expect(message).toHaveAttribute('role', 'status')
    expect(message.parentElement).toHaveAttribute('aria-live', 'polite')
    expect(message).not.toHaveTextContent('登录成功')
  })

  it.each([
    'opened_homepage',
    'browser_unavailable',
    'navigation_failed',
    'internal_error',
    'cancelled',
  ] as const)(
    'shows truthful manual outcome %s without starting collection',
    async (outcome) => {
      const user = userEvent.setup()
      vi.mocked(api.showSearchBatchManualPage).mockResolvedValue({ outcome })
      renderBatch()
      await user.click(await screen.findByRole('button', { name: '打开平台' }))
      await waitFor(() =>
        expect(api.showSearchBatchManualPage).toHaveBeenCalledOnce(),
      )
      await waitFor(() =>
        expect(screen.getByRole('button', { name: '打开平台' })).toBeEnabled(),
      )
      expect(api.continueSearchBatch).not.toHaveBeenCalled()
      expect(screen.queryByText('登录成功')).toBeNull()
      if (outcome === 'opened_homepage')
        expect(screen.getByText(/原页面已不可用/u)).toBeVisible()
      if (outcome === 'navigation_failed')
        expect(screen.getByRole('alert')).toHaveTextContent('平台页面未能打开')
    },
  )

  it('locks continue and skip while opening but allows cancellation and ignores the late opening response', async () => {
    const user = userEvent.setup()
    let finishOpen!: (response: { outcome: api.ManualPageOutcome }) => void
    vi.mocked(api.showSearchBatchManualPage).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishOpen = resolve
        }),
    )
    renderBatch()
    await user.click(await screen.findByRole('button', { name: '打开平台' }))
    expect(screen.getByRole('button', { name: '正在打开…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '继续采集' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '跳过此平台' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '取消采集' }))
    await waitFor(() =>
      expect(api.cancelSearchBatch).toHaveBeenCalledExactlyOnceWith(8, {
        expected_revision: 12,
      }),
    )
    expect(
      await screen.findByText('已取消采集，已有结果仍然保留。'),
    ).toBeVisible()
    await act(async () => finishOpen({ outcome: 'opened_existing' }))
    expect(screen.queryByText(/已在谷歌浏览器中打开平台页面/u)).toBeNull()
    expect(screen.getByText('已取消采集，已有结果仍然保留。')).toBeVisible()
  })

  it('refetches stale controls without automatically replaying the failed mutation', async () => {
    const user = userEvent.setup()
    vi.mocked(api.continueSearchBatch).mockRejectedValue(
      new api.SearchBatchApiError(
        '采集任务状态已变化，请刷新后重试。',
        'search_batch_state_changed',
        409,
      ),
    )
    renderBatch()
    await user.click(await screen.findByRole('button', { name: '继续采集' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '采集任务状态已变化',
    )
    await waitFor(() => expect(api.fetchSearchBatch).toHaveBeenCalledTimes(2))
    expect(api.continueSearchBatch).toHaveBeenCalledExactlyOnceWith(8, input)
  })

  it('disables only continuation when checkpoint evidence is corrupt', async () => {
    const user = userEvent.setup()
    const batch = fixture()
    Object.assign(batch.items[0], {
      recovery_available: false,
      checkpoint_basis: 'unknown',
      completed_term_count: 0,
      remaining_term_count: 2,
      next_term_position: null,
    })
    renderBatch(batch)
    const continued = await screen.findByRole('button', { name: '继续采集' })
    expect(continued).toBeDisabled()
    expect(continued).toHaveAttribute(
      'aria-describedby',
      'recovery-unavailable',
    )
    expect(screen.queryByText(/继续时将从/u)).toBeNull()
    await user.click(screen.getByRole('button', { name: '跳过此平台' }))
    await waitFor(() =>
      expect(api.skipSearchBatchPlatform).toHaveBeenCalledExactlyOnceWith(
        8,
        input,
      ),
    )
  })

  it('allows pre-attempt interruption recovery with a null expected run id', async () => {
    const user = userEvent.setup()
    const batch = fixture()
    Object.assign(batch.items[0], {
      attempt_count: 0,
      latest_attempt: null,
      pause_reason: 'process_interrupted',
      completed_term_count: 0,
      remaining_term_count: 2,
      next_term_position: 0,
      checkpoint_basis: 'unknown',
    })
    renderBatch(batch)
    expect(await screen.findByText(/服务中断/u)).toBeVisible()
    await user.click(screen.getByRole('button', { name: '继续采集' }))
    await waitFor(() =>
      expect(api.continueSearchBatch).toHaveBeenCalledExactlyOnceWith(8, {
        ...input,
        expected_run_id: null,
      }),
    )
  })

  it.each(['structure_changed', 'cancelled'] as const)(
    'offers recovery for an older failed item with a %s attempt without confusing checkpoint trust with eligibility',
    async (status) => {
      const user = userEvent.setup()
      const batch = ended(fixture(status))
      batch.items[0].recovery_available = false
      renderBatch(batch)
      await user.click(
        await screen.findByRole('button', { name: '继续处理平台' }),
      )
      await waitFor(() =>
        expect(api.recoverSearchBatchPlatform).toHaveBeenCalledExactlyOnceWith(
          8,
          0,
          { expected_run_id: 31, expected_revision: 12 },
        ),
      )
      expect(
        screen.getByText('已准备好继续处理此平台，请检查页面后继续采集。'),
      ).toBeVisible()
    },
  )

  it('shows confirmed-terms completion while keeping the last failed attempt truthful', async () => {
    const batch = ended(fixture('internal_error'))
    batch.status = 'completed'
    Object.assign(batch.items[0], {
      status: 'completed',
      completion_basis: 'confirmed_terms',
      completed_term_count: 2,
      remaining_term_count: 0,
      next_term_position: null,
    })
    renderBatch(batch)
    expect(await screen.findByText(/所有搜索词均已确认完成/u)).toBeVisible()
    expect(screen.getByText('最近一次尝试：采集失败')).toBeVisible()
    expect(screen.getByRole('link', { name: '本次尝试' })).toHaveAttribute(
      'href',
      '/collection-runs/31',
    )
    expect(screen.queryByRole('button', { name: '继续处理平台' })).toBeNull()
    expect(screen.getByText(/已结束 1 \/ 1 个平台/u)).toBeVisible()
  })

  it('selects aggregate results by URL, resets paging with filters, and opens XHS through source_run_id', async () => {
    const user = userEvent.setup()
    const batch = ended(fixture())
    const item = batch.items[0]
    item.platform = 'xhs'
    if (item.latest_attempt) item.latest_attempt.run.platform = 'xhs'
    const result: api.SearchBatchResult = {
      id: 4,
      source_run_id: 20,
      platform: 'xhs',
      platform_content_id: '64f123456789abcdef012345',
      content_type: 'note',
      title: '合并后的内容',
      snippet: '',
      creator_hash: '',
      publisher_name: '',
      content_url:
        'https://www.xiaohongshu.com/explore/64f123456789abcdef012345',
      kind: 'new',
      matched_terms: ['龙田街道', '竹坑社区'],
      published_at_text: '今天',
      first_seen_at: stamp,
      last_seen_at: stamp,
      first_observed_at: stamp,
      last_observed_at: stamp,
    }
    vi.mocked(api.fetchSearchBatchResults).mockResolvedValue({
      results: [result],
      total: 51,
      offset: 50,
      limit: 50,
    })
    const { router } = renderBatch(
      batch,
      '/collection-batches/8?platform=xhs&kind=new&offset=50',
    )
    expect(await screen.findByText('合并后的内容')).toBeVisible()
    expect(api.fetchSearchBatchResults).toHaveBeenCalledWith(
      8,
      0,
      'new',
      50,
      expect.any(AbortSignal),
    )
    expect(screen.getByRole('link', { name: '查看来源尝试' })).toHaveAttribute(
      'href',
      '/collection-runs/20',
    )
    expect(screen.getByRole('link', { name: '本次尝试' })).toHaveAttribute(
      'href',
      '/collection-runs/31',
    )
    await user.click(screen.getByRole('button', { name: '打开原文' }))
    await waitFor(() =>
      expect(openSearchRunResult).toHaveBeenCalledExactlyOnceWith(20, 4),
    )
    await user.click(screen.getByRole('tab', { name: '再次命中 1' }))
    expect(router.state.location.search).toBe('?platform=xhs&kind=repeated')
    await waitFor(() =>
      expect(api.fetchSearchBatchResults).toHaveBeenLastCalledWith(
        8,
        0,
        'repeated',
        0,
        expect.any(AbortSignal),
      ),
    )
    const card = screen.getByText('合并后的内容').closest('article')
    expect(card).not.toBeNull()
    expect(within(card!).getByText('龙田街道')).toBeVisible()
    expect(within(card!).getByText('竹坑社区')).toBeVisible()
  })

  it('keeps aggregate XHS opening disabled while the paused batch owns the browser', async () => {
    const batch = fixture()
    batch.items[0].platform = 'xhs'
    vi.mocked(api.fetchSearchBatchResults).mockResolvedValue({
      results: [
        {
          id: 4,
          source_run_id: 20,
          platform: 'xhs',
          platform_content_id: 'abc',
          content_type: 'note',
          title: '已采集内容',
          snippet: '',
          creator_hash: '',
          publisher_name: '',
          content_url: 'https://www.xiaohongshu.com/explore/abc',
          kind: 'new',
          matched_terms: ['龙田街道'],
          published_at_text: '',
          first_seen_at: stamp,
          last_seen_at: stamp,
          first_observed_at: stamp,
          last_observed_at: stamp,
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    renderBatch(batch, '/collection-batches/8?platform=xhs')
    expect(
      await screen.findByRole('button', { name: '打开原文' }),
    ).toBeDisabled()
    expect(screen.getByText(/采集正在使用浏览器/u)).toBeVisible()
    expect(openSearchRunResult).not.toHaveBeenCalled()
  })
})
