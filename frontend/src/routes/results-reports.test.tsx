import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cacheSavedReport,
  reportDetailKey,
  reportListKey,
} from '@/hooks/use-topic-reports'
import {
  analysisJobFixture,
  analysisProvider,
  analysisSettingsFixture,
  analysisTimestamp,
} from '@/lib/api/analysis-fixtures'
import { fetchAISettings } from '@/lib/api/ai-settings'
import { fetchAnalysisSettings } from '@/lib/api/analysis-settings'
import {
  cancelAnalysisJob,
  startContentAnalysis,
  type AnalysisJob,
} from '@/lib/api/content-analyses'
import { openSearchRunResult } from '@/lib/api/search-runs'
import {
  cancelTopicReport,
  createTopicReport,
  fetchReportSection,
  fetchReportSections,
  fetchReportSources,
  fetchTopicReport,
  fetchTopicReports,
  retryTopicReport,
  TOPIC_REPORTS_QUERY_KEY,
  TopicReportApiError,
  type ReportRun,
} from '@/lib/api/topic-reports'
import {
  reportFixture,
  reportSectionFixture,
  reportSourceFixture,
  reportUsage,
} from '@/lib/api/topic-reports.fixtures'
import { reportRequestFormSchema } from '@/routes/results-report-actions'
import { ResultsReports } from '@/routes/results-reports'

vi.mock('@/lib/api/topic-reports', async (original) => ({
  ...(await original<typeof import('@/lib/api/topic-reports')>()),
  fetchTopicReports: vi.fn(),
  fetchTopicReport: vi.fn(),
  fetchReportSources: vi.fn(),
  fetchReportSections: vi.fn(),
  fetchReportSection: vi.fn(),
  createTopicReport: vi.fn(),
  retryTopicReport: vi.fn(),
  cancelTopicReport: vi.fn(),
}))
vi.mock('@/lib/api/content-analyses', async (original) => ({
  ...(await original<typeof import('@/lib/api/content-analyses')>()),
  startContentAnalysis: vi.fn(),
  cancelAnalysisJob: vi.fn(),
}))
vi.mock('@/lib/api/analysis-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/analysis-settings')>()),
  fetchAnalysisSettings: vi.fn(),
}))
vi.mock('@/lib/api/ai-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/ai-settings')>()),
  fetchAISettings: vi.fn(),
}))
vi.mock('@/lib/api/search-runs', async (original) => ({
  ...(await original<typeof import('@/lib/api/search-runs')>()),
  openSearchRunResult: vi.fn(),
}))

function settledJob() {
  const job = analysisJobFixture({
    status: 'completed',
    completion_event_id: 3,
    finished_at: analysisTimestamp,
  })
  job.counts = { ...job.counts, total: 10, queued: 0, completed: 8, failed: 2 }
  return job
}
function renderReports(
  entry = '/results?job=7',
  job: AnalysisJob | undefined = settledJob(),
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  const router = createMemoryRouter(
    [
      {
        path: '/results',
        element: (
          <ResultsReports
            job={job}
            provider={analysisProvider}
            settings={analysisSettingsFixture()}
          />
        ),
      },
    ],
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
function assertNoMutation() {
  for (const fn of [
    createTopicReport,
    retryTopicReport,
    cancelTopicReport,
    startContentAnalysis,
    cancelAnalysisJob,
    openSearchRunResult,
  ])
    expect(fn).not.toHaveBeenCalled()
}
function useReport(report: ReportRun) {
  vi.mocked(fetchTopicReports).mockResolvedValue({
    reports: [report],
    next_before_id: null,
  })
  vi.mocked(fetchTopicReport).mockResolvedValue(report)
}
describe('automatic second-stage report views', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    useReport(reportFixture())
    vi.mocked(fetchReportSources).mockImplementation(
      async (_id, _signal, offset = 0) => ({
        items: [reportSourceFixture(offset)],
        total: 101,
        limit: 20,
        offset,
      }),
    )
    vi.mocked(fetchReportSections).mockImplementation(
      async (_id, _signal, offset = 0) => ({
        sections: offset === 0 ? [reportSectionFixture()] : [],
        total: 1,
        limit: 5,
        offset,
      }),
    )
    vi.mocked(fetchReportSection).mockResolvedValue(reportSectionFixture())
    vi.mocked(fetchAISettings).mockResolvedValue(analysisProvider)
    vi.mocked(fetchAnalysisSettings).mockResolvedValue(
      analysisSettingsFixture(),
    )
    vi.mocked(openSearchRunResult).mockResolvedValue({ outcome: 'opened' })
  })
  it('automatically shows one report for settled 8/10, preserves coverage and performs only reads on mount/reload/poll', async () => {
    let empty = true
    vi.mocked(fetchTopicReports).mockImplementation(async (_signal, options) =>
      options?.initialJobId && empty
        ? { reports: [], next_before_id: null }
        : { reports: [reportFixture()], next_before_id: null },
    )
    const first = renderReports()
    expect(await screen.findByText(/本任务还没有报告/)).toBeVisible()
    assertNoMutation()
    empty = false
    expect(
      await screen.findByRole(
        'region',
        { name: '文字报告 31' },
        { timeout: 2500 },
      ),
    ).toBeVisible()
    expect(screen.getByText(/已完成 8\/10 条初步分析/)).toBeVisible()
    expect(
      screen.getByText('本次内容 10 条 · 可判断 8 条 · 无法判断 2 条'),
    ).toBeVisible()
    expect(
      await screen.findAllByRole('article', { name: '报告章节 501' }),
    ).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /^生成报告$/ })).toBeNull()
    await act(async () => {
      await first.client.invalidateQueries({
        queryKey: TOPIC_REPORTS_QUERY_KEY,
      })
    })
    assertNoMutation()
    first.unmount()
    renderReports('/results?job=7&report=31')
    expect(
      await screen.findByRole('region', { name: '文字报告 31' }),
    ).toBeVisible()
    assertNoMutation()
  })
  it('waits for normal settlement and does not automatically report cancelled upstream work', async () => {
    const view = renderReports('/results?job=7', analysisJobFixture())
    expect(await screen.findByText(/初步分析仍在进行/)).toBeVisible()
    expect(fetchTopicReports).not.toHaveBeenCalledWith(expect.anything(), {
      initialJobId: 7,
    })
    assertNoMutation()
    view.unmount()
    renderReports(
      '/results?job=7',
      analysisJobFixture({
        status: 'cancelled',
        finished_at: analysisTimestamp,
      }),
    )
    expect(
      await screen.findByText(/本任务未正常完成；已保存的初步文本仍可查看/),
    ).toBeVisible()
    assertNoMutation()
  })
  it.each([
    ['judging', '正在判断相关性'],
    ['composing', '正在生成报告'],
    ['failed', '生成失败'],
    ['cancelled', '报告已取消'],
    ['interrupted', '报告已中断'],
    ['configuration_blocked', '模型设置不可用'],
  ] as const)(
    'presents %s as report state, not a third stage or successful-empty',
    async (status, label) => {
      useReport(
        reportFixture({
          status,
          root_section_id: null,
          finished_at:
            status === 'judging' || status === 'composing'
              ? null
              : analysisTimestamp,
        }),
      )
      renderReports()
      expect(await screen.findByText(`报告：${label}`)).toBeVisible()
      expect(screen.getByRole('heading', { name: '报告' })).toBeVisible()
      expect(screen.queryByText(/第三阶段/)).toBeNull()
      assertNoMutation()
    },
  )
  it.each(['no_ready_sources', 'no_relevant_sources'] as const)(
    'keeps %s honest and retains source reasons without stage-one retry',
    async (empty_reason) => {
      const report = reportFixture({
        status: 'empty',
        root_section_id: null,
        empty_reason,
      })
      useReport(report)
      vi.mocked(fetchReportSources).mockResolvedValue({
        items: [
          reportSourceFixture(0, {
            state: 'unavailable',
            unavailable_reason: 'in_progress',
            initial_status: 'analysing',
            judgment: null,
            judgment_node_id: null,
          }),
        ],
        total: 1,
        limit: 20,
        offset: 0,
      })
      renderReports()
      expect(
        await screen.findByText(
          empty_reason === 'no_ready_sources'
            ? /本次没有可用的初步分析，因此没有调用模型/
            : /相关性判断没有找到足够相关的内容，因此没有生成报告/,
        ),
      ).toBeVisible()
      expect(
        await screen.findByText(/当时仍在分析；因此没有判断为相关或不相关/),
      ).toBeVisible()
      expect(screen.getAllByText(/没有可用的初步分析/)).not.toHaveLength(0)
      expect(
        screen.queryByRole('button', { name: '仅重试文字报告' }),
      ).toBeNull()
      assertNoMutation()
    },
  )
  it('renders frozen prompts and partial/unknown stage-separated usage, without historical reused tokens', async () => {
    const report = reportFixture({
      usage: {
        judgment: reportUsage(8, 0),
        composition: reportUsage(),
        total: reportUsage(8, 0),
      },
    })
    report.nodes.composition.reused = 1
    useReport(report)
    const user = userEvent.setup()
    renderReports()
    await screen.findByRole('region', { name: '文字报告 31' })
    await user.click(screen.getByText('本次报告用量'))
    expect(
      screen.getAllByText('调用 8 次 · 计入用量 0 次 · Token 用量未知'),
    ).toHaveLength(2)
    expect(
      screen.getByText(/1 个报告章节沿用了已有结果；历史用量不计入本次/),
    ).toBeVisible()
    await user.click(screen.getByText('本报告使用的提示词与模型'))
    expect(screen.getByText(report.prompt.instructions)).toBeVisible()
    expect(screen.getByText(/历史共享提示词 · 版本 2/)).toBeVisible()
  })
  it('keeps cross-page citations resolved from bounded frozen section sources and XHS origin proof', async () => {
    const user = userEvent.setup()
    const lateSource = reportSourceFixture(100).source
    lateSource.source_run_id = 88
    lateSource.platform = 'xhs'
    lateSource.platform_content_id = 'a'.repeat(24)
    lateSource.content_url = `https://www.xiaohongshu.com/explore/${'a'.repeat(24)}`
    const late = reportSectionFixture({
      id: 513,
      position: 12,
      source_count: 1,
      sources: [{ position: 100, source: lateSource }],
      document: {
        overview: '最后一个详细章节',
        items: [
          {
            text: '<img src=x onerror=alert(1)> https://llm.example/ 不得执行',
            source_ids: [lateSource.result_id],
          },
        ],
      },
    })
    vi.mocked(fetchReportSections).mockImplementation(
      async (_id, _signal, offset = 0) => ({
        sections: offset === 10 ? [late] : [reportSectionFixture()],
        total: 13,
        limit: 5,
        offset,
      }),
    )
    const { router, container } = renderReports(
      '/results?job=7&report=31&report_sections_offset=10',
    )
    const citation = await screen.findByRole('button', {
      name: `原文 101 · 小红书：${lateSource.title}`,
    })
    expect(screen.queryByRole('link', { name: /llm.example/ })).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(fetchReportSources).toHaveBeenCalledWith(
      31,
      expect.any(AbortSignal),
      0,
    )
    expect(fetchReportSources).not.toHaveBeenCalledWith(
      31,
      expect.anything(),
      100,
    )
    await user.click(citation)
    expect(openSearchRunResult).toHaveBeenCalledWith(88, 111)
    await user.click(screen.getByRole('button', { name: '报告来源下一页' }))
    expect(router.state.location.search).toContain('report_sources_offset=20')
    expect(router.state.location.search).toContain('report_sections_offset=10')
    await waitFor(() =>
      expect(fetchReportSources).toHaveBeenCalledWith(
        31,
        expect.any(AbortSignal),
        20,
      ),
    )
    expect(startContentAnalysis).not.toHaveBeenCalled()
  })
  it('navigates current report child IDs and preserves independent URL page state', async () => {
    const user = userEvent.setup()
    const root = reportSectionFixture({
      id: 700,
      kind: 'overview',
      level: 1,
      sources: [],
      document: null,
      overview_document: {
        overview: '总览文字',
        items: [{ text: '查看全部下级证据', section_ids: [501, 502] }],
      },
      children: [
        {
          id: 501,
          kind: 'leaf',
          position: 0,
          level: 0,
          source_count: 8,
          overview: '甲',
        },
        {
          id: 502,
          kind: 'leaf',
          position: 1,
          level: 0,
          source_count: 8,
          overview: '乙',
        },
      ],
      source_count: 16,
    })
    useReport(reportFixture({ root_section_id: 700 }))
    vi.mocked(fetchReportSection).mockImplementation(async (_id, sectionId) =>
      sectionId === 700 ? root : reportSectionFixture({ id: sectionId }),
    )
    const { router } = renderReports(
      '/results?job=7&report=31&report_sources_offset=20',
    )
    await user.click(
      await screen.findByRole('button', { name: '查看引用章节 #502' }),
    )
    await waitFor(() =>
      expect(fetchReportSection).toHaveBeenCalledWith(
        31,
        502,
        expect.any(AbortSignal),
      ),
    )
    expect(router.state.location.search).toContain('report_section=502')
    expect(router.state.location.search).toContain('report_sources_offset=20')
    await user.click(screen.getByRole('button', { name: '返回报告总览' }))
    expect(router.state.location.search).not.toContain('report_section=')
    assertNoMutation()
  })
  it('paginates report history and clears only report detail pagination when selecting a version', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchTopicReports).mockImplementation(
      async (_signal, options) => ({
        reports: [reportFixture({ id: options?.beforeId ? 30 : 31 })],
        next_before_id: options?.beforeId ? null : 31,
      }),
    )
    vi.mocked(fetchTopicReport).mockImplementation(async (id) =>
      reportFixture({ id }),
    )
    const { router } = renderReports(
      '/results?job=7&platform=dy&report=31&report_sources_offset=20&report_section=501',
    )
    await screen.findByRole('region', { name: '文字报告 31' })
    await user.click(screen.getByText('报告历史与独立版本'))
    await user.click(screen.getByRole('button', { name: '更早报告' }))
    await user.click(
      await screen.findByRole('button', { name: /报告 #30 · 已生成/ }),
    )
    expect(router.state.location.search).toContain('job=7')
    expect(router.state.location.search).toContain('platform=dy')
    expect(router.state.location.search).toContain('report=30')
    expect(router.state.location.search).not.toContain('report_sources_offset')
    expect(router.state.location.search).not.toContain('report_section=')
    expect(screen.getByRole('heading', { name: '报告' })).toHaveFocus()
    assertNoMutation()
  })
  it('cancels only the report with observed revision and fences a late active detail read', async () => {
    const user = userEvent.setup()
    const active = reportFixture({
      status: 'composing',
      root_section_id: null,
      finished_at: null,
      revision: 1,
    })
    const cancelled = reportFixture({
      status: 'cancelled',
      root_section_id: null,
      revision: 2,
    })
    useReport(active)
    vi.mocked(cancelTopicReport).mockResolvedValue(cancelled)
    const { client } = renderReports()
    await user.click(
      await screen.findByRole('button', { name: '取消文字报告 #31' }),
    )
    expect(cancelTopicReport).not.toHaveBeenCalled()
    let resolveRead: (value: ReportRun) => void = () => undefined
    vi.mocked(fetchTopicReport).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRead = resolve
        }),
    )
    await act(async () => {
      void client.invalidateQueries({ queryKey: reportDetailKey(31) })
    })
    await user.click(screen.getByRole('button', { name: '确认取消文字报告' }))
    await waitFor(() =>
      expect(cancelTopicReport).toHaveBeenCalledWith(31, {
        request_id: expect.any(String),
        expected_revision: 1,
      }),
    )
    expect(await screen.findByText('报告：报告已取消')).toBeVisible()
    await act(async () => resolveRead(active))
    expect(client.getQueryData<ReportRun>(reportDetailKey(31))?.revision).toBe(
      2,
    )
    expect(
      screen.queryByRole('button', { name: '取消文字报告 #31' }),
    ).toBeNull()
    expect(cancelAnalysisJob).not.toHaveBeenCalled()
    expect(startContentAnalysis).not.toHaveBeenCalled()
  })
  it('preserves ambiguous retry intent across close and explicit replay despite later revisions', async () => {
    const user = userEvent.setup()
    const failed = reportFixture({
      status: 'failed',
      root_section_id: null,
      revision: 4,
    })
    useReport(failed)
    vi.mocked(retryTopicReport)
      .mockRejectedValueOnce(new TopicReportApiError('service_unavailable'))
      .mockImplementationOnce(async (_id, request) =>
        reportFixture({
          id: 32,
          trigger: 'retry',
          parent_report_id: 31,
          completion_event_id: null,
          request_id: request.request_id,
        }),
      )
    const { client, router } = renderReports()
    await user.click(
      await screen.findByRole('button', { name: '仅重试文字报告' }),
    )
    await user.click(screen.getByRole('button', { name: '确认文字重试' }))
    expect(await screen.findByText(/上次操作结果不确定/)).toBeVisible()
    const original = vi.mocked(retryTopicReport).mock.calls[0]
    expect(original).toEqual([
      31,
      {
        request_id: expect.any(String),
        expected_revision: 4,
        configuration_revision: 3,
      },
    ])
    await user.click(screen.getByRole('button', { name: '暂时关闭' }))
    await act(async () => {
      await cacheSavedReport(client, { ...failed, revision: 5 })
    })
    expect(
      screen.getByRole('button', { name: '仅重试文字报告' }),
    ).toBeDisabled()
    await user.click(
      screen.getByRole('button', { name: '继续确认上次报告请求' }),
    )
    await user.click(screen.getByRole('button', { name: '确认上次报告提交' }))
    expect(vi.mocked(retryTopicReport).mock.calls[1]).toEqual(original)
    await waitFor(() =>
      expect(router.state.location.search).toContain('report=32'),
    )
    expect(startContentAnalysis).not.toHaveBeenCalled()
  })
  it('keeps override text dirty, explicit and separate from shared defaults or stage one', async () => {
    const user = userEvent.setup()
    const { router } = renderReports()
    vi.mocked(retryTopicReport).mockImplementation(async (_id, request) =>
      reportFixture({
        id: 32,
        trigger: 'retry',
        parent_report_id: 31,
        completion_event_id: null,
        request_id: request.request_id,
        prompt: {
          ...reportFixture().prompt,
          mode: 'custom',
          origin: 'custom',
          instructions:
            request.report_prompt?.mode === 'custom'
              ? request.report_prompt.instructions
              : reportFixture().prompt.instructions,
        },
      }),
    )
    await user.click(
      await screen.findByRole('button', { name: '用其他提示词重新生成' }),
    )
    const input = screen.getByRole('textbox', {
      name: '相关性判断与报告提示词',
    })
    await user.clear(input)
    await user.type(input, '  本次只整理道路信息，保留不确定性。')
    await user.click(screen.getByRole('button', { name: '取消' }))
    expect(screen.getByText('有未保存的报告设置，是否放弃？')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '继续编辑报告' }))
    await user.click(
      screen.getByRole('button', { name: '创建专用提示词新版本' }),
    )
    await waitFor(() =>
      expect(retryTopicReport).toHaveBeenCalledWith(31, {
        request_id: expect.any(String),
        expected_revision: 2,
        configuration_revision: 3,
        report_prompt: {
          mode: 'custom',
          instructions: '  本次只整理道路信息，保留不确定性。',
        },
      }),
    )
    await waitFor(() =>
      expect(router.state.location.search).toContain('report=32'),
    )
    expect(startContentAnalysis).not.toHaveBeenCalled()
  })
  it('normalizes inclusive Shanghai dates to a UTC half-open first-entry interval', async () => {
    const user = userEvent.setup()
    vi.mocked(createTopicReport).mockImplementation(async (request) =>
      reportFixture({
        id: 32,
        trigger: 'interval',
        request_id: request.request_id,
        initial_job_id: null,
        completion_event_id: null,
        selection: request.selection,
      }),
    )
    renderReports()
    await user.click(
      screen.getByRole('button', { name: '可选：按首次发现时间报告' }),
    )
    await user.type(screen.getByLabelText('报告首次发现开始日期'), '2026-08-29')
    await user.type(screen.getByLabelText('报告首次发现结束日期'), '2026-08-29')
    expect(createTopicReport).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '提交文字报告' }))
    await waitFor(() =>
      expect(createTopicReport).toHaveBeenCalledWith({
        request_id: expect.any(String),
        configuration_revision: 3,
        report_prompt: { mode: 'default' },
        selection: {
          kind: 'first_seen_interval',
          first_seen_from: '2026-08-28T16:00:00.000Z',
          first_seen_to: '2026-08-29T16:00:00.000Z',
        },
      }),
    )
    expect(startContentAnalysis).not.toHaveBeenCalled()
  })
  it('retains an override draft through known configuration conflict and requires a newly confirmed intent', async () => {
    const user = userEvent.setup()
    vi.mocked(retryTopicReport)
      .mockRejectedValueOnce(
        new TopicReportApiError('ai_configuration_changed', 409),
      )
      .mockImplementationOnce(async (_id, request) =>
        reportFixture({
          id: 32,
          trigger: 'retry',
          request_id: request.request_id,
          parent_report_id: 31,
          completion_event_id: null,
        }),
      )
    vi.mocked(fetchAISettings).mockResolvedValue({
      ...analysisProvider,
      revision: 4,
    })
    renderReports()
    await user.click(
      await screen.findByRole('button', { name: '用其他提示词重新生成' }),
    )
    const input = screen.getByRole('textbox', {
      name: '相关性判断与报告提示词',
    })
    await user.clear(input)
    await user.type(input, '草稿必须保留')
    await user.click(
      screen.getByRole('button', { name: '创建专用提示词新版本' }),
    )
    await user.click(
      await screen.findByRole('button', { name: '保留草稿并重新核对' }),
    )
    await waitFor(() => expect(input).toBeEnabled())
    expect(input).toHaveValue('草稿必须保留')
    expect(retryTopicReport).toHaveBeenCalledTimes(1)
    await user.click(
      screen.getByRole('button', { name: '创建专用提示词新版本' }),
    )
    await waitFor(() => expect(retryTopicReport).toHaveBeenCalledTimes(2))
    const calls = vi.mocked(retryTopicReport).mock.calls
    expect(calls[1][1].request_id).not.toBe(calls[0][1].request_id)
    expect(calls[1][1]).toMatchObject({
      configuration_revision: 4,
      report_prompt: {
        mode: 'custom',
        instructions: '草稿必须保留',
      },
    })
  })
  it('does not let an older detail cache defeat a newer list revision', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const newest = reportFixture({
      revision: 3,
      status: 'cancelled',
      root_section_id: null,
    })
    client.setQueryData([...reportListKey, {}], {
      reports: [newest],
      next_before_id: null,
    })
    client.setQueryData(reportDetailKey(31), reportFixture({ revision: 2 }))
    useReport(reportFixture({ revision: 2 }))
    renderReports('/results?report=31', undefined, client)
    await waitFor(() => expect(fetchTopicReports).toHaveBeenCalled())
    await waitFor(() => expect(client.isFetching()).toBe(0))
    expect(
      client.getQueryData<{ reports: ReportRun[] }>([...reportListKey, {}])
        ?.reports[0].revision,
    ).toBe(3)
    expect(client.getQueryData<ReportRun>(reportDetailKey(31))?.revision).toBe(
      3,
    )
    expect(screen.getByText('报告：报告已取消')).toBeVisible()
    expect(
      screen.queryByRole('button', { name: '取消文字报告 #31' }),
    ).toBeNull()
  })
  it('requires a new observed cancellation intent after a known version conflict', async () => {
    const user = userEvent.setup()
    const active = reportFixture({
      status: 'judging',
      root_section_id: null,
      finished_at: null,
      revision: 1,
    })
    useReport(active)
    vi.mocked(cancelTopicReport)
      .mockRejectedValueOnce(
        new TopicReportApiError('topic_report_changed', 409),
      )
      .mockResolvedValueOnce(
        reportFixture({
          status: 'cancelled',
          root_section_id: null,
          revision: 3,
        }),
      )
    renderReports()
    await user.click(
      await screen.findByRole('button', { name: '取消文字报告 #31' }),
    )
    useReport({ ...active, revision: 2 })
    await user.click(screen.getByRole('button', { name: '确认取消文字报告' }))
    await user.click(
      await screen.findByRole('button', { name: '关闭并刷新报告' }),
    )
    expect(cancelTopicReport).toHaveBeenCalledTimes(1)
    await user.click(
      await screen.findByRole('button', { name: '取消文字报告 #31' }),
    )
    await user.click(screen.getByRole('button', { name: '确认取消文字报告' }))
    await waitFor(() => expect(cancelTopicReport).toHaveBeenCalledTimes(2))
    const calls = vi.mocked(cancelTopicReport).mock.calls
    expect(calls[0][1].expected_revision).toBe(1)
    expect(calls[1][1].expected_revision).toBe(2)
    expect(calls[1][1].request_id).not.toBe(calls[0][1].request_id)
    expect(cancelAnalysisJob).not.toHaveBeenCalled()
  })
  it('locks report submission and dismissal until its explicit request settles', async () => {
    const user = userEvent.setup()
    useReport(reportFixture({ status: 'failed', root_section_id: null }))
    let finish: ((report: ReportRun) => void) | undefined
    vi.mocked(retryTopicReport).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    renderReports()
    await user.click(
      await screen.findByRole('button', { name: '仅重试文字报告' }),
    )
    await user.dblClick(screen.getByRole('button', { name: '确认文字重试' }))
    expect(retryTopicReport).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '正在提交…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '返回' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('dialog')).toBeVisible()
    const request = vi.mocked(retryTopicReport).mock.calls[0][1]
    await act(async () =>
      finish?.(
        reportFixture({
          id: 32,
          trigger: 'retry',
          parent_report_id: 31,
          request_id: request.request_id,
          completion_event_id: null,
        }),
      ),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(startContentAnalysis).not.toHaveBeenCalled()
  })
  it('handles malformed report URL state with read-only reset and bounded defaults', async () => {
    const user = userEvent.setup()
    const { router } = renderReports(
      '/results?job=7&report=-1&report_sources_offset=9007199254740992',
    )
    expect(
      await screen.findByText('报告链接中的编号或分页位置无效。'),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: '重置报告视图' }))
    expect(router.state.location.search).toBe('?job=7')
    assertNoMutation()
  })
})

describe('optional saved-text form validation', () => {
  it('rejects impossible dates and inverted inclusive intervals', () => {
    const base = {
      from: '2026-08-29',
      to: '2026-08-29',
      prompt: { mode: 'default' as const },
    }
    expect(reportRequestFormSchema(true).safeParse(base).success).toBe(true)
    for (const change of [
      { from: '2026-02-30' },
      { to: '2026-08-28' },
      { from: '' },
      { to: '' },
    ])
      expect(
        reportRequestFormSchema(true).safeParse({ ...base, ...change }).success,
      ).toBe(false)
  })
  it('validates exact codepoint-bounded override text only when used', () => {
    const base = {
      from: '',
      to: '',
      prompt: { mode: 'custom' as const, instructions: '😀'.repeat(8000) },
    }
    expect(reportRequestFormSchema(false).safeParse(base).success).toBe(true)
    for (const instructions of [' ', '\u0000', '\ud800', '😀'.repeat(8001)])
      expect(
        reportRequestFormSchema(false).safeParse({
          ...base,
          prompt: { mode: 'custom', instructions },
        }).success,
      ).toBe(false)
  })
})
