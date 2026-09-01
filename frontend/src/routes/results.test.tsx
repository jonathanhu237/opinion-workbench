import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { appRoutes } from '@/app/router'
import {
  analysisAttemptFixture,
  analysisJobFixture,
  analysisProvider,
  analysisSettingsFixture,
  analysisTimestamp,
  resultFixture,
} from '@/lib/api/analysis-fixtures'
import { AI_SETTINGS_QUERY_KEY, fetchAISettings } from '@/lib/api/ai-settings'
import {
  ANALYSIS_SETTINGS_QUERY_KEY,
  fetchAnalysisSettings,
  saveAnalysisAutomation,
} from '@/lib/api/analysis-settings'
import { AnalysisApiError } from '@/lib/api/analysis-shared'
import {
  cancelAnalysisJob,
  fetchAnalysisAttempt,
  fetchAnalysisJob,
  fetchAnalysisJobItems,
  fetchAnalysisJobs,
  fetchResultAnalyses,
  startContentAnalysis,
  type AnalysisJob,
} from '@/lib/api/content-analyses'
import {
  fetchResult,
  fetchResultLegacyAnalyses,
  fetchResultOrigins,
  fetchResults,
} from '@/lib/api/results'
import { openSearchRunResult } from '@/lib/api/search-runs'
import { Results } from '@/routes/results'
import {
  createTopicReport,
  fetchReportSection,
  fetchReportSections,
  fetchReportSources,
  fetchTopicReport,
  fetchTopicReports,
  retryTopicReport,
} from '@/lib/api/topic-reports'
import {
  reportFixture,
  reportSectionFixture,
  reportSourceFixture,
} from '@/lib/api/topic-reports.fixtures'

vi.mock('@/lib/api/topic-reports', async (original) => ({
  ...(await original<typeof import('@/lib/api/topic-reports')>()),
  fetchTopicReports: vi
    .fn()
    .mockResolvedValue({ reports: [], next_before_id: null }),
  fetchTopicReport: vi.fn(),
  fetchReportSources: vi.fn(),
  fetchReportSections: vi.fn(),
  fetchReportSection: vi.fn(),
  createTopicReport: vi.fn(),
  retryTopicReport: vi.fn(),
}))

vi.mock('@/lib/api/analysis-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/analysis-settings')>()),
  fetchAnalysisSettings: vi.fn(),
  saveAnalysisAutomation: vi.fn(),
}))
vi.mock('@/lib/api/content-analyses', async (original) => ({
  ...(await original<typeof import('@/lib/api/content-analyses')>()),
  startContentAnalysis: vi.fn(),
  fetchAnalysisJobs: vi.fn(),
  fetchAnalysisJob: vi.fn(),
  fetchAnalysisJobItems: vi.fn(),
  fetchAnalysisAttempt: vi.fn(),
  fetchResultAnalyses: vi.fn(),
  cancelAnalysisJob: vi.fn(),
}))
vi.mock('@/lib/api/results', async (original) => ({
  ...(await original<typeof import('@/lib/api/results')>()),
  fetchResults: vi.fn(),
  fetchResult: vi.fn(),
  fetchResultOrigins: vi.fn(),
  fetchResultLegacyAnalyses: vi.fn(),
}))
vi.mock('@/lib/api/ai-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/ai-settings')>()),
  fetchAISettings: vi.fn(),
}))
vi.mock('@/lib/api/search-runs', async (original) => ({
  ...(await original<typeof import('@/lib/api/search-runs')>()),
  openSearchRunResult: vi.fn(),
}))
vi.mock('@/lib/api/health', async (original) => ({
  ...(await original<typeof import('@/lib/api/health')>()),
  fetchHealth: vi
    .fn()
    .mockResolvedValue({ status: 'ok', service: 'longtian-api' }),
}))

const start = vi.mocked(startContentAnalysis)
function renderResults(entry = '/results', shell = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    shell ? appRoutes : [{ path: '/results', element: <Results /> }],
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
function completedJob(values: Partial<AnalysisJob> = {}) {
  const job = analysisJobFixture({
    status: 'completed',
    completion_event_id: 3,
    finished_at: analysisTimestamp,
    ...values,
  })
  job.counts = { ...job.counts, total: 10, queued: 0, completed: 8, failed: 2 }
  return job
}
describe('Results and Analysis', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchTopicReports).mockResolvedValue({
      reports: [],
      next_before_id: null,
    })
    vi.mocked(fetchAISettings).mockResolvedValue(analysisProvider)
    vi.mocked(fetchAnalysisSettings).mockResolvedValue(
      analysisSettingsFixture(),
    )
    vi.mocked(fetchResults).mockImplementation(async (filters) => ({
      items: [resultFixture()],
      total: 101,
      limit: 20,
      offset: filters.offset,
      eligible_count: 101,
      active_count: 0,
    }))
    vi.mocked(fetchResult).mockResolvedValue(resultFixture())
    vi.mocked(fetchResultAnalyses).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchResultOrigins).mockResolvedValue({
      items: [
        {
          source_run_id: 70,
          rule_name: '采集时的规则',
          status: 'completed_with_results',
          discovery_kind: 'new',
          matched_terms: ['龙田'],
          first_observed_at: analysisTimestamp,
          last_observed_at: analysisTimestamp,
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchResultLegacyAnalyses).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchAnalysisJobs).mockResolvedValue({
      jobs: [],
      next_before_id: null,
    })
    vi.mocked(fetchAnalysisJob).mockResolvedValue(analysisJobFixture())
    vi.mocked(fetchAnalysisJobItems).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchAnalysisAttempt).mockResolvedValue(analysisAttemptFixture())
    vi.mocked(openSearchRunResult).mockResolvedValue({ outcome: 'opened' })
    start.mockReset().mockImplementation(async (request) => ({
      job: analysisJobFixture({
        request_id: request.request_id,
        force_refresh: request.force_refresh,
      }),
      admitted_count: 101,
      already_active_count: 2,
    }))
    vi.mocked(saveAnalysisAutomation)
      .mockReset()
      .mockResolvedValue(analysisSettingsFixture())
    vi.mocked(cancelAnalysisJob).mockReset()
  })
  it('connects normal stage-one settlement to one automatic report in the real Results route without another mutation', async () => {
    const job = completedJob()
    vi.mocked(fetchAnalysisJobs).mockResolvedValue({
      jobs: [job],
      next_before_id: null,
    })
    vi.mocked(fetchAnalysisJob).mockResolvedValue(job)
    vi.mocked(fetchTopicReports).mockResolvedValue({
      reports: [reportFixture()],
      next_before_id: null,
    })
    vi.mocked(fetchTopicReport).mockResolvedValue(reportFixture())
    vi.mocked(fetchReportSources).mockResolvedValue({
      items: [reportSourceFixture()],
      total: 1,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchReportSections).mockResolvedValue({
      sections: [reportSectionFixture()],
      total: 1,
      limit: 5,
      offset: 0,
    })
    vi.mocked(fetchReportSection).mockResolvedValue(reportSectionFixture())
    renderResults('/results?job=7', true)
    expect(await screen.findByRole('heading', { name: '报告' })).toBeVisible()
    expect(
      await screen.findByRole('region', { name: '文字报告 31' }),
    ).toBeVisible()
    expect(
      screen.getByText('本次内容 10 条 · 可判断 8 条 · 无法判断 2 条'),
    ).toBeVisible()
    expect(
      await screen.findByText(
        '这是保存的文字报告，并不把来源陈述视为已核实事实。',
        { exact: false },
      ),
    ).toBeVisible()
    expect(startContentAnalysis).not.toHaveBeenCalled()
    expect(createTopicReport).not.toHaveBeenCalled()
    expect(retryTopicReport).not.toHaveBeenCalled()
  })
  it('registers a real shell route and reads only on entry, refresh and remount', async () => {
    const user = userEvent.setup()
    const first = renderResults('/results', true)
    expect(
      await screen.findByRole('heading', { name: '结果与分析', level: 1 }),
    ).toBeVisible()
    const nav = screen.getByRole('navigation', { name: '主导航' })
    expect(
      within(nav).getByRole('link', { name: '结果与分析' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(await screen.findByText('合成采集内容 11')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '刷新' }))
    expect(start).not.toHaveBeenCalled()
    expect(saveAnalysisAutomation).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /生成报告/ })).toBeNull()
    first.unmount()
    renderResults()
    await screen.findByText('合成采集内容 11')
    expect(start).not.toHaveBeenCalled()
    expect(openSearchRunResult).not.toHaveBeenCalled()
  })
  it('confirms the entire 101-record library even when viewing a filtered later page', async () => {
    const user = userEvent.setup()
    renderResults(
      '/results?offset=20&platform=dy&from=2026-08-29&to=2026-08-29',
    )
    await user.click(
      await screen.findByRole('button', { name: '一键初步分析' }),
    )
    const dialog = screen.getByRole('dialog', {
      name: '一键初步分析全部未分析内容',
    })
    expect(dialog).toHaveTextContent(
      '当前有 101 条内容还没做初步分析，包括历史内容。',
    )
    expect(dialog).toHaveTextContent('已在其他任务中的内容不会重复处理')
    expect(start).not.toHaveBeenCalled()
    await user.click(
      within(dialog).getByRole('button', { name: '确认初步分析' }),
    )
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1))
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({
        selection: { kind: 'all_never_started' },
        configuration_revision: 3,
        initial_prompt: { mode: 'default' },
        force_refresh: false,
      }),
      expect.anything(),
    )
    expect(await screen.findByText(/已提交 101 条初步分析/)).toBeVisible()
  })
  it('freezes shown prompts/provider and reuses one UUID after an ambiguous response, including closing the dialog', async () => {
    start.mockRejectedValueOnce(new AnalysisApiError('service_unavailable'))
    const user = userEvent.setup()
    const { client } = renderResults()
    await user.click(
      await screen.findByRole('button', { name: '一键初步分析' }),
    )
    await act(async () => {
      client.setQueryData(AI_SETTINGS_QUERY_KEY, {
        ...analysisProvider,
        revision: 4,
        model: 'changed-model',
      })
      const changed = analysisSettingsFixture()
      changed.initial_prompt = {
        ...changed.initial_prompt,
        id: 5,
        instructions: ' changed prompt ',
      }
      client.setQueryData(ANALYSIS_SETTINGS_QUERY_KEY, changed)
    })
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('模型服务')
    expect(dialog).not.toHaveTextContent('changed-model')
    await user.click(
      within(dialog).getByRole('button', { name: '确认初步分析' }),
    )
    await screen.findByText(/上次提交结果不确定/)
    expect(
      within(dialog).getByRole('combobox', { name: '内容理解提示词' }),
    ).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '暂时关闭' }))
    await user.click(screen.getByRole('button', { name: '继续确认上次请求' }))
    await user.click(screen.getByRole('button', { name: '确认上次提交' }))
    await waitFor(() => expect(start).toHaveBeenCalledTimes(2))
    expect(start.mock.calls[0][0]).toEqual(start.mock.calls[1][0])
    expect(start.mock.calls[1][0].configuration_revision).toBe(3)
    expect(start.mock.calls[1][0].initial_prompt).toEqual({ mode: 'default' })
  })
  it('locks duplicate submission while pending and offers explicit reconfirmation after a stale intent', async () => {
    let fail: ((error: Error) => void) | undefined
    start.mockReturnValueOnce(
      new Promise((_, reject) => {
        fail = reject
      }),
    )
    const user = userEvent.setup()
    renderResults()
    await user.click(
      await screen.findByRole('button', { name: '一键初步分析' }),
    )
    await user.click(screen.getByRole('button', { name: '确认初步分析' }))
    expect(screen.getByRole('button', { name: '正在提交…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled()
    await act(async () => {
      fail?.(new AnalysisApiError('analysis_prompt_changed', 409))
    })
    expect(
      await screen.findByRole('button', { name: '刷新后重新确认' }),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: '确认上次提交' })).toBeNull()
    expect(start).toHaveBeenCalledTimes(1)
  })
  it('shows immutable defaults and sends a per-submission custom initial prompt', async () => {
    const user = userEvent.setup()
    renderResults()
    await user.click(await screen.findByText('自动分析设置'))
    expect(screen.getByText('系统提示词（只读）')).toBeVisible()
    await user.click(screen.getByText('内容理解'))
    expect(
      screen.getByText(analysisSettingsFixture().initial_prompt.instructions),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: /保存.*提示词/ })).toBeNull()

    await user.click(screen.getByRole('button', { name: '一键初步分析' }))
    const dialog = screen.getByRole('dialog', {
      name: '一键初步分析全部未分析内容',
    })
    await user.click(
      within(dialog).getByRole('combobox', { name: '内容理解提示词' }),
    )
    await user.click(
      await screen.findByRole('option', { name: '使用本任务自定义指令' }),
    )
    const input = within(dialog).getByRole('textbox', {
      name: '内容理解提示词',
    })
    expect(input).toHaveValue(
      analysisSettingsFixture().initial_prompt.instructions,
    )
    await user.clear(input)
    await user.type(input, '只整理本次来源的地点和时间线索。')
    await user.click(
      within(dialog).getByRole('button', { name: '确认初步分析' }),
    )
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1))
    expect(start.mock.calls[0][0]).toMatchObject({
      initial_prompt: {
        mode: 'custom',
        instructions: '只整理本次来源的地点和时间线索。',
      },
    })
    expect(start.mock.calls[0][0]).not.toHaveProperty('report_prompt')
  })
  it('keeps immutable defaults separate from the automation authorization setting', async () => {
    const user = userEvent.setup()
    const { client } = renderResults()
    await user.click(await screen.findByText('自动分析设置'))
    expect(screen.getByText(/完整流程尚未启用，当前不会自动执行/)).toBeVisible()
    expect(screen.getByText('系统提示词（只读）')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '设置自动分析授权' }))
    await act(async () => {
      client.setQueryData(AI_SETTINGS_QUERY_KEY, {
        ...analysisProvider,
        revision: 4,
        model: 'changed-model',
      })
    })
    const dialog = screen.getByRole('dialog', { name: '确认自动分析授权' })
    expect(dialog).toHaveTextContent('模型服务')
    await user.click(
      within(dialog).getByRole('button', { name: '确认并保存授权' }),
    )
    await waitFor(() =>
      expect(saveAnalysisAutomation).toHaveBeenCalledWith(
        { enabled: true, expected_revision: 1, configuration_revision: 3 },
        expect.anything(),
      ),
    )
    expect(start).not.toHaveBeenCalled()
  })
  it('retries selected-source and evidence reads from Refresh without submitting work', async () => {
    const failure = new AnalysisApiError('analysis_storage_unavailable')
    vi.mocked(fetchResult).mockRejectedValueOnce(failure)
    vi.mocked(fetchResultAnalyses).mockRejectedValueOnce(failure)
    vi.mocked(fetchAnalysisAttempt).mockRejectedValueOnce(failure)
    vi.mocked(fetchResultOrigins).mockRejectedValueOnce(failure)
    vi.mocked(fetchResultLegacyAnalyses).mockRejectedValueOnce(failure)
    const user = userEvent.setup()
    renderResults('/results?result=11&attempt=21')
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(5))
    await user.click(screen.getByRole('button', { name: '刷新' }))
    await waitFor(() => {
      expect(fetchResult).toHaveBeenCalledTimes(2)
      expect(fetchResultAnalyses).toHaveBeenCalledTimes(2)
      expect(fetchAnalysisAttempt).toHaveBeenCalledTimes(2)
      expect(fetchResultOrigins).toHaveBeenCalledTimes(2)
      expect(fetchResultLegacyAnalyses).toHaveBeenCalledTimes(2)
    })
    expect(await screen.findAllByText('内容理解')).not.toHaveLength(0)
    expect(screen.queryAllByRole('alert')).toHaveLength(0)
    expect(start).not.toHaveBeenCalled()
    expect(saveAnalysisAutomation).not.toHaveBeenCalled()
    expect(openSearchRunResult).not.toHaveBeenCalled()
  })
  it.each([
    ['failed', '重试此条初步分析', 'retry', false],
    ['legacy_completed', '重新获取并分析此条', 'reanalysis', true],
  ] as const)(
    'keeps %s outside bulk and offers its separate explicit action',
    async (state, label, kind, force) => {
      vi.mocked(fetchResult).mockResolvedValue(
        resultFixture({
          analysis_state: state,
          legacy_count: state === 'legacy_completed' ? 1 : 0,
        }),
      )
      const user = userEvent.setup()
      renderResults('/results?result=11')
      await user.click(await screen.findByRole('button', { name: label }))
      await user.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: '确认初步分析',
        }),
      )
      await waitFor(() => expect(start).toHaveBeenCalledTimes(1))
      expect(start.mock.calls[0][0]).toMatchObject({
        selection: { kind, result_ids: [11] },
        force_refresh: force,
      })
    },
  )
  it('reads saved attributed evidence, uncertainty, original text and actual legacy origin without generating', async () => {
    vi.mocked(fetchResult).mockResolvedValue(
      resultFixture({
        analysis_state: 'completed',
        latest_attempt_id: 21,
        legacy_count: 1,
      }),
    )
    vi.mocked(fetchResultAnalyses).mockResolvedValue({
      items: [analysisAttemptFixture()],
      total: 1,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchResultLegacyAnalyses).mockResolvedValue({
      items: [
        {
          summary_id: 4,
          source_run_id: 91,
          item_id: 30,
          status: 'completed',
          decision: 'uncertain',
          reused_from_item_id: null,
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    })
    const user = userEvent.setup()
    renderResults('/results?result=11')
    expect(
      await screen.findByText('无法确认是否位于深圳龙田，也未核实来源陈述。'),
    ).toBeVisible()
    await user.click(screen.getByText('正文和媒体信息'))
    expect(
      screen.getByText('完整保存的合成正文，未把来源陈述当成事实。'),
    ).toBeVisible()
    await user.click(screen.getByText('旧版分析和报告 · 1 条'))
    expect(
      screen.getByRole('link', { name: '查看旧版报告 4' }),
    ).toHaveAttribute('href', '/collection-runs/91?summary=4')
    expect(start).not.toHaveBeenCalled()
    expect(openSearchRunResult).not.toHaveBeenCalled()
  })
  it('opens XHS only with the chosen stored source run, locks links while pending and shows bounded feedback', async () => {
    const result = resultFixture()
    result.source = {
      ...result.source,
      source_run_id: 91,
      platform: 'xhs',
      platform_content_id: 'a'.repeat(24),
      content_url: `https://www.xiaohongshu.com/explore/${'a'.repeat(24)}`,
    }
    vi.mocked(fetchResults).mockResolvedValue({
      items: [result],
      total: 1,
      limit: 20,
      offset: 0,
      eligible_count: 1,
      active_count: 0,
    })
    let finish: ((value: { outcome: 'opened' }) => void) | undefined
    vi.mocked(openSearchRunResult).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const user = userEvent.setup()
    renderResults()
    const open = await screen.findByRole('button', {
      name: '打开原文：合成采集内容 11',
    })
    await user.click(open)
    expect(openSearchRunResult).toHaveBeenCalledWith(91, 11)
    expect(open).toBeDisabled()
    expect(open).toHaveTextContent('正在打开')
    await act(async () => {
      finish?.({ outcome: 'opened' })
    })
    expect(await screen.findByText('已在谷歌浏览器打开')).toBeVisible()
    expect(screen.queryByRole('link', { name: /打开原文/ })).toBeNull()
  })
  it('shows 8/10 saved plus 2 unsuccessful after settlement and keeps other active cancellation visible while browsing history', async () => {
    const active = analysisJobFixture()
    const older = completedJob({ id: 6 })
    vi.mocked(fetchAnalysisJobs).mockResolvedValue({
      jobs: [active, older],
      next_before_id: null,
    })
    vi.mocked(fetchAnalysisJob).mockResolvedValue(older)
    const cancelled = analysisJobFixture({
      status: 'cancelled',
      finished_at: analysisTimestamp,
    })
    cancelled.counts.queued = 0
    cancelled.counts.cancelled = 101
    vi.mocked(cancelAnalysisJob).mockResolvedValue(cancelled)
    const user = userEvent.setup()
    renderResults('/results?job=6')
    expect(await screen.findByText('初步分析：已处理 10/10')).toBeVisible()
    expect(
      screen.getByText('已完成 8 条 · 未完成 2 条 · 待处理 0 条'),
    ).toBeVisible()
    expect(
      screen.getByText(
        /本任务已完成，每条结果都已保存。手动初步分析不会自动生成报告/,
      ),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: '取消任务 7' }))
    await waitFor(() =>
      expect(cancelAnalysisJob).toHaveBeenCalledWith(7, expect.anything()),
    )
    expect(start).not.toHaveBeenCalled()
  })
  it('retains filters/page in the URL and does not widen invalid first-entry date ranges', async () => {
    const user = userEvent.setup()
    const { router } = renderResults()
    await user.click(
      await screen.findByRole('button', { name: '采集结果下一页' }),
    )
    expect(router.state.location.search).toContain('offset=20')
    await act(async () => {
      await router.navigate('/results?from=2026-08-30&to=2026-08-29')
    })
    expect(
      screen.getByText('首次发现时间范围不正确，请检查日期及先后顺序。'),
    ).toBeVisible()
    expect(
      vi
        .mocked(fetchResults)
        .mock.calls.every(([filters]) => filters.first_seen_from === undefined),
    ).toBe(true)
  })
  it('blocks first/retry actions for legacy-owned queued work even without a new job ID', async () => {
    vi.mocked(fetchResult).mockResolvedValue(
      resultFixture({
        analysis_state: 'queued',
        active_job_id: null,
        legacy_count: 1,
      }),
    )
    renderResults('/results?result=11')
    expect(
      await screen.findByRole('button', { name: '此条正在处理中' }),
    ).toBeDisabled()
    expect(start).not.toHaveBeenCalled()
  })
  it('moves keyboard focus to selected evidence and restores it to its source row on close', async () => {
    const user = userEvent.setup()
    renderResults()
    const button = await screen.findByRole('button', {
      name: '查看内容与分析：合成采集内容 11',
    })
    await user.click(button)
    expect(
      await screen.findByRole('heading', { name: '来源与初步分析' }),
    ).toHaveFocus()
    await user.click(screen.getByRole('button', { name: '关闭详情' }))
    expect(button).toHaveFocus()
  })
  it('refreshes item evidence after final settlement without another paid request', async () => {
    const active = analysisJobFixture({ status: 'running' })
    active.counts.total = 1
    active.counts.queued = 1
    const settled = analysisJobFixture({
      status: 'completed',
      completion_event_id: 3,
      finished_at: analysisTimestamp,
    })
    settled.counts = { ...settled.counts, total: 1, queued: 0, completed: 1 }
    vi.mocked(fetchAnalysisJobs).mockResolvedValue({
      jobs: [active],
      next_before_id: null,
    })
    vi.mocked(fetchAnalysisJob)
      .mockResolvedValueOnce(active)
      .mockResolvedValue(settled)
    const queued = analysisAttemptFixture({
      status: 'queued',
      output: null,
      input: null,
      input_fingerprint: null,
      attempted: false,
      usage: null,
      started_at: null,
      finished_at: null,
    })
    vi.mocked(fetchAnalysisJobItems)
      .mockResolvedValueOnce({
        items: [queued],
        total: 1,
        limit: 20,
        offset: 0,
      })
      .mockResolvedValue({
        items: [analysisAttemptFixture()],
        total: 1,
        limit: 20,
        offset: 0,
      })
    renderResults('/results?job=7')
    expect(await screen.findByText('初步分析：已处理 0/1')).toBeVisible()
    await waitFor(
      () => expect(screen.getByText('初步分析：已处理 1/1')).toBeVisible(),
      { timeout: 2500 },
    )
    expect(await screen.findAllByText('已完成')).toHaveLength(2)
    expect(
      vi.mocked(fetchAnalysisJobItems).mock.calls.length,
    ).toBeGreaterThanOrEqual(2)
    expect(start).not.toHaveBeenCalled()
  })
})
