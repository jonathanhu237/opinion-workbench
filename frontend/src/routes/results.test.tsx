import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  analysisProvider,
  analysisSettingsFixture,
  analysisJobFixture,
  resultFixture,
} from '@/lib/api/analysis-fixtures'
import { fetchAISettings } from '@/lib/api/ai-settings'
import { fetchAnalysisSettings } from '@/lib/api/analysis-settings'
import {
  fetchResultAnalyses,
  fetchAnalysisAttempt,
  fetchAnalysisJob,
  fetchAnalysisJobItems,
  fetchAnalysisJobs,
} from '@/lib/api/content-analyses'
import {
  fetchResult,
  fetchResultLegacyAnalyses,
  fetchResultOrigins,
  fetchResults,
} from '@/lib/api/results'
import {
  createReportGeneration,
  fetchGenerationEligibility,
  fetchReportGenerations,
  previewReportSelection,
} from '@/lib/api/report-generations'
import { fetchTopicReports } from '@/lib/api/topic-reports'
import { reportFixture } from '@/lib/api/topic-reports.fixtures'
import { Results } from '@/routes/results'

vi.mock('@/lib/api/ai-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/ai-settings')>()),
  fetchAISettings: vi.fn(),
}))
vi.mock('@/lib/api/analysis-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/analysis-settings')>()),
  fetchAnalysisSettings: vi.fn(),
}))
vi.mock('@/lib/api/content-analyses', async (original) => ({
  ...(await original<typeof import('@/lib/api/content-analyses')>()),
  fetchResultAnalyses: vi.fn(),
  fetchAnalysisAttempt: vi.fn(),
  fetchAnalysisJob: vi.fn(),
  fetchAnalysisJobItems: vi.fn(),
  fetchAnalysisJobs: vi.fn(),
}))
vi.mock('@/lib/api/results', async (original) => ({
  ...(await original<typeof import('@/lib/api/results')>()),
  fetchResults: vi.fn(),
  fetchResult: vi.fn(),
  fetchResultOrigins: vi.fn(),
  fetchResultLegacyAnalyses: vi.fn(),
}))
vi.mock('@/lib/api/report-generations', async (original) => ({
  ...(await original<typeof import('@/lib/api/report-generations')>()),
  createReportGeneration: vi.fn(),
  fetchGenerationEligibility: vi.fn(),
  fetchReportGenerations: vi.fn(),
  previewReportSelection: vi.fn(),
}))
vi.mock('@/lib/api/topic-reports', async (original) => ({
  ...(await original<typeof import('@/lib/api/topic-reports')>()),
  fetchTopicReports: vi.fn(),
}))

function renderResults(entry = '/results') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [{ path: '/results', element: <Results /> }],
    { initialEntries: [entry] },
  )
  return {
    router,
    ...render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

describe('报告生成页面', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    vi.mocked(fetchAISettings).mockResolvedValue(analysisProvider)
    vi.mocked(fetchAnalysisSettings).mockResolvedValue(
      analysisSettingsFixture(),
    )
    vi.mocked(fetchGenerationEligibility).mockResolvedValue({
      pending: 2,
      failed: 1,
      active: 0,
    })
    vi.mocked(fetchReportGenerations).mockResolvedValue({
      items: [],
      next_before_id: null,
    })
    vi.mocked(fetchTopicReports).mockResolvedValue({
      reports: [],
      next_before_id: null,
    })
    vi.mocked(fetchResults).mockImplementation(async ({ offset }) => {
      const first = resultFixture({ id: offset === 0 ? 11 : 31 })
      const second = resultFixture({ id: offset === 0 ? 12 : 32 })
      return {
        items: [first, second],
        total: 40,
        limit: 20,
        offset,
        eligible_count: 2,
        active_count: 0,
      }
    })
    vi.mocked(fetchResult).mockResolvedValue(resultFixture())
    vi.mocked(fetchResultAnalyses).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchResultOrigins).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchResultLegacyAnalyses).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.mocked(fetchAnalysisAttempt).mockResolvedValue(undefined as never)
    vi.mocked(fetchAnalysisJob).mockResolvedValue(undefined as never)
    vi.mocked(fetchAnalysisJobs).mockResolvedValue({
      jobs: [],
      next_before_id: null,
    })
    vi.mocked(fetchAnalysisJobItems).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.mocked(previewReportSelection).mockResolvedValue({
      selection: { kind: 'explicit', result_ids: [11] },
      counts: {
        total: 1,
        pending: 1,
        already_summarized: 0,
        failed: 0,
        active: 0,
      },
    })
  })

  it('shows report composition without an extra page-level introduction', async () => {
    const user = userEvent.setup()
    // Keep the mutation pending so the route does not need a second, unrelated
    // report-detail fixture to verify the submission boundary.
    vi.mocked(createReportGeneration).mockImplementation(
      () => new Promise(() => undefined) as never,
    )
    renderResults()

    expect(screen.queryByText(/选择舆情内容并填写报告信息后/u)).toBeNull()
    expect(screen.queryByRole('tab', { name: '生成报告' })).toBeNull()
    expect(screen.queryByRole('tab', { name: '报告记录' })).toBeNull()
    expect(
      await screen.findByRole('table', { name: '舆情内容表格' }),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: '刷新舆情内容' })).toBeVisible()
    expect(screen.queryByRole('region', { name: '报告操作' })).toBeNull()
    expect(screen.getByText('内容摘要')).toBeVisible()
    expect(screen.queryByText('筛选')).toBeNull()

    await user.click(
      screen.getByRole('checkbox', { name: '选择内容：合成采集内容 11' }),
    )
    expect(screen.getByText('已选 1 条')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '生成报告' }))
    expect(
      await screen.findByRole('dialog', { name: '填写报告信息' }),
    ).toBeVisible()
    expect(createReportGeneration).not.toHaveBeenCalled()
    expect(
      (screen.getByRole('textbox', { name: '报告名称' }) as HTMLInputElement)
        .value,
    ).toContain('舆情分析报告')
    expect(
      screen.getByRole('note', { name: '总结提示词默认模板预览' }),
    ).toHaveTextContent(analysisSettingsFixture().initial_prompt.instructions)

    await user.click(screen.getByRole('button', { name: '确认生成报告' }))
    await waitFor(() => expect(createReportGeneration).toHaveBeenCalledTimes(1))
    expect(vi.mocked(createReportGeneration).mock.calls[0][0]).toEqual(
      expect.objectContaining({
        name: expect.stringContaining('舆情分析报告'),
        selection: { kind: 'explicit', result_ids: [11] },
      }),
    )
  })

  it('turns bulk actions into concrete selection snapshots without creating a report', async () => {
    const user = userEvent.setup()
    vi.mocked(previewReportSelection).mockResolvedValueOnce({
      selection: { kind: 'explicit', result_ids: [11, 12, 13] },
      counts: {
        total: 3,
        pending: 2,
        already_summarized: 0,
        failed: 1,
        active: 0,
      },
    })
    renderResults()
    await user.click(
      await screen.findByRole('button', { name: '选中全部未纳入报告的内容' }),
    )
    await waitFor(() => expect(screen.getByText('已选 3 条')).toBeVisible())
    expect(createReportGeneration).not.toHaveBeenCalled()
    expect(previewReportSelection).toHaveBeenCalledWith({
      kind: 'library',
    })
  })

  it('keeps explicit selections when moving between pages', async () => {
    const user = userEvent.setup()
    const { router } = renderResults()
    await user.click(
      await screen.findByRole('checkbox', {
        name: '选择内容：合成采集内容 11',
      }),
    )
    await user.click(screen.getByRole('button', { name: '舆情内容下一页' }))
    await screen.findByRole('checkbox', { name: '选择内容：合成采集内容 31' })
    await user.click(
      screen.getByRole('checkbox', { name: '选择内容：合成采集内容 31' }),
    )
    expect(screen.getByText('已选 2 条')).toBeVisible()
    expect(router.state.location.search).toContain('offset=20')
    await user.click(screen.getByRole('button', { name: '舆情内容上一页' }))
    expect(
      await screen.findByRole('checkbox', {
        name: '选择内容：合成采集内容 11',
      }),
    ).toBeChecked()
    expect(screen.getByText('已选 2 条')).toBeVisible()
  })

  it('marks active rows as processing and keeps them out of selection', async () => {
    const active = resultFixture({
      analysis_state: 'analysing',
      active_job_id: 7,
    })
    vi.mocked(fetchResults).mockResolvedValue({
      items: [active],
      total: 1,
      limit: 20,
      offset: 0,
      eligible_count: 0,
      active_count: 1,
    })
    renderResults()
    expect(await screen.findByText('处理中')).toBeVisible()
    expect(
      screen.getByRole('checkbox', { name: '选择内容：合成采集内容 11' }),
    ).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('已选 0 条')).toBeVisible()
  })

  it('persists the selection draft for a remount in the same browser session', async () => {
    sessionStorage.setItem(
      'opinion-workbench:report-selection-draft:v1',
      JSON.stringify([11]),
    )
    renderResults()
    expect(
      await screen.findByRole('checkbox', {
        name: '选择内容：合成采集内容 11',
      }),
    ).toBeChecked()
    expect(screen.getByText('已选 1 条')).toBeVisible()
  })

  it('opens item details in a sheet and restores focus to the source row', async () => {
    const user = userEvent.setup()
    renderResults()
    const detail = await screen.findByRole('button', {
      name: '查看内容详情：合成采集内容 11',
    })
    await user.click(detail)
    expect(
      await screen.findByRole('dialog', { name: '内容详情' }),
    ).toBeVisible()
    const heading = await screen.findByRole('heading', {
      name: '来源与单条总结',
    })
    expect(heading).toBeVisible()
    expect(heading).toHaveFocus()
    await user.click(screen.getByRole('button', { name: '关闭详情' }))
    await waitFor(() => expect(detail).toHaveFocus())
  })

  it('shows report records as a separate route without the former analysis panels', async () => {
    renderResults('/results?view=records')
    expect(await screen.findByText('报告列表')).toBeVisible()
    expect(screen.getByRole('button', { name: '刷新报告记录' })).toBeVisible()
    expect(await screen.findByText('尚未启动报告生成任务。')).toBeVisible()
    expect(screen.queryByText('自动分析设置')).toBeNull()
    expect(screen.queryByText('报告筛选')).toBeNull()
  })

  it('disables a second submission while another generation is active', async () => {
    vi.mocked(fetchReportGenerations).mockResolvedValue({
      items: [{ status: 'summarising' } as never],
      next_before_id: null,
    })
    const user = userEvent.setup()
    renderResults()
    await user.click(
      await screen.findByRole('checkbox', {
        name: '选择内容：合成采集内容 11',
      }),
    )
    expect(screen.getByRole('button', { name: '生成报告' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('当前已有报告正在生成')
  })

  it('disables report submission and explains the missing model configuration', async () => {
    vi.mocked(fetchAISettings).mockResolvedValue({
      ...analysisProvider,
      base_url: null,
      model: null,
      has_api_key: false,
      revision: 0,
    })
    const user = userEvent.setup()
    renderResults()
    await user.click(
      await screen.findByRole('checkbox', {
        name: '选择内容：合成采集内容 11',
      }),
    )
    expect(screen.getByRole('button', { name: '生成报告' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent(
      '尚未配置 AI 模型，请先到 AI 设置完成配置后再生成报告',
    )
  })

  it('infers the records view from legacy report query parameters', async () => {
    renderResults('/results?job=7')
    expect(await screen.findByText('报告列表')).toBeVisible()
    expect(screen.queryByRole('tab')).toBeNull()
  })

  it('keeps a legacy analysis job deep link inside report records', async () => {
    const job = analysisJobFixture({ id: 7 })
    vi.mocked(fetchAnalysisJobs).mockResolvedValue({
      jobs: [job],
      next_before_id: null,
    })
    vi.mocked(fetchAnalysisJob).mockResolvedValue(job)
    renderResults('/results?job=7')
    expect(
      await screen.findByRole('region', { name: '分析任务 7' }),
    ).toBeVisible()
    expect(screen.getByText(/历史单条处理任务/u)).toBeVisible()
  })

  it('keeps the legacy report list cursor in the report records route', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchReportGenerations).mockResolvedValue({
      items: [
        {
          id: 9,
          name: '新版任务',
          status: 'completed',
          created_at: '2026-09-04T00:00:00Z',
          selection: { result_ids: [11] },
        } as never,
      ],
      next_before_id: null,
    })
    vi.mocked(fetchTopicReports).mockImplementation(
      async (_signal, options) => ({
        reports: [reportFixture({ id: options?.beforeId ? 14 : 15 })],
        next_before_id: options?.beforeId ? null : 15,
      }),
    )
    const { router } = renderResults('/results?view=records&reports_before=27')
    expect(
      await screen.findByRole('button', { name: /报告 #14/u }),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: /新版任务/u })).toBeVisible()
    expect(screen.queryByText(/阶段 [1-4]\/4/u)).toBeNull()
    expect(router.state.location.search).toBe('?view=records&reports_before=27')
    expect(fetchTopicReports).toHaveBeenCalledWith(expect.anything(), {
      beforeId: 27,
    })
    await user.click(screen.getByRole('button', { name: '最新报告' }))
    await waitFor(() =>
      expect(router.state.location.search).toBe('?view=records'),
    )
    await waitFor(() =>
      expect(fetchTopicReports).toHaveBeenCalledWith(expect.anything(), {}),
    )
  })

  it('resets legacy report detail pagination when selecting another report', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchTopicReports).mockResolvedValue({
      reports: [reportFixture({ id: 15 }), reportFixture({ id: 14 })],
      next_before_id: null,
    })
    const { router } = renderResults(
      '/results?view=records&report=15&report_section=501&report_sources_offset=20',
    )
    expect(
      await screen.findByRole('button', { name: /报告 #14/u }),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: /报告 #14/u }))
    await waitFor(() =>
      expect(router.state.location.search).not.toContain('report_section='),
    )
    expect(router.state.location.search).not.toContain('report_sources_offset=')
  })
})
