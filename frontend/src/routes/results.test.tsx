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
  saveAnalysisPrompt,
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
  saveAnalysisPrompt: vi.fn(),
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
    vi.mocked(saveAnalysisPrompt)
      .mockReset()
      .mockResolvedValue(analysisSettingsFixture())
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
      screen.getByText('冻结范围 10 条 · 可分析初步证据 8 条 · 未覆盖 2 条'),
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
    expect(dialog).toHaveTextContent('当前全库有 101 条')
    expect(dialog).toHaveTextContent('不受筛选或分页影响')
    expect(start).not.toHaveBeenCalled()
    await user.click(
      within(dialog).getByRole('button', { name: '确认初步分析' }),
    )
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1))
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({
        selection: { kind: 'all_never_started' },
        configuration_revision: 3,
        initial_prompt_version_id: 1,
        report_prompt_version_id: 2,
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
    expect(dialog).toHaveTextContent('配置版本 3')
    expect(dialog).not.toHaveTextContent('changed-model')
    await user.click(
      within(dialog).getByRole('button', { name: '确认初步分析' }),
    )
    await screen.findByText(/上次提交结果尚不确定/)
    await user.click(screen.getByRole('button', { name: '暂时关闭' }))
    await user.click(screen.getByRole('button', { name: '继续确认上次请求' }))
    await user.click(screen.getByRole('button', { name: '确认上次提交' }))
    await waitFor(() => expect(start).toHaveBeenCalledTimes(2))
    expect(start.mock.calls[0][0]).toEqual(start.mock.calls[1][0])
    expect(start.mock.calls[1][0].configuration_revision).toBe(3)
    expect(start.mock.calls[1][0].initial_prompt_version_id).toBe(1)
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
  it('saves each prompt independently, validates Unicode/blank content and leaves history untouched', async () => {
    const user = userEvent.setup()
    renderResults()
    await user.click(await screen.findByText('提示词与自动分析设置'))
    const initial = screen.getByLabelText('初步分析提示词')
    const report = screen.getByLabelText('报告提示词')
    const reportValue = analysisSettingsFixture().report_prompt.instructions
    await user.clear(initial)
    await user.type(initial, '  新的初步理解指令  ')
    await user.click(screen.getByRole('button', { name: '保存初步分析提示词' }))
    await waitFor(() =>
      expect(saveAnalysisPrompt).toHaveBeenCalledWith('initial', {
        expected_version_id: 1,
        instructions: '  新的初步理解指令  ',
      }),
    )
    expect(report).toHaveValue(reportValue)
    await user.clear(report)
    await user.type(report, '   ')
    await user.click(screen.getByRole('button', { name: '保存报告提示词' }))
    expect(
      await screen.findByText('提示词须为 1 至 8000 字的有效非空文本。'),
    ).toBeVisible()
    expect(report).toHaveFocus()
    expect(start).not.toHaveBeenCalled()
    expect(saveAnalysisPrompt).toHaveBeenCalledTimes(1)
  })
  it.each(['initial', 'report'] as const)(
    'keeps both saved prompts when the earlier %s response arrives last',
    async (firstStage) => {
      const firstSnapshot = analysisSettingsFixture()
      const firstKey =
        firstStage === 'initial' ? 'initial_prompt' : 'report_prompt'
      const secondKey =
        firstStage === 'initial' ? 'report_prompt' : 'initial_prompt'
      firstSnapshot[firstKey] = {
        ...firstSnapshot[firstKey],
        id: 3,
        instructions: '先保存的指令',
      }
      const latestSnapshot = {
        ...firstSnapshot,
        [secondKey]: {
          ...firstSnapshot[secondKey],
          id: 4,
          instructions: '后保存的指令',
        },
      }
      let finishFirst: ((settings: typeof firstSnapshot) => void) | undefined
      vi.mocked(saveAnalysisPrompt).mockImplementation((stage) =>
        stage === firstStage
          ? new Promise((resolve) => {
              finishFirst = resolve
            })
          : Promise.resolve(latestSnapshot),
      )
      const user = userEvent.setup()
      const { client } = renderResults()
      await user.click(await screen.findByText('提示词与自动分析设置'))
      const firstTitle =
        firstStage === 'initial' ? '初步分析提示词' : '报告提示词'
      const secondTitle =
        firstStage === 'initial' ? '报告提示词' : '初步分析提示词'
      const firstInput = screen.getByLabelText(firstTitle)
      const secondInput = screen.getByLabelText(secondTitle)
      await user.clear(firstInput)
      await user.type(firstInput, firstSnapshot[firstKey].instructions)
      await user.click(
        screen.getByRole('button', { name: `保存${firstTitle}` }),
      )
      await waitFor(() => expect(firstInput).toBeDisabled())
      await user.clear(secondInput)
      await user.type(secondInput, latestSnapshot[secondKey].instructions)
      await user.click(
        screen.getByRole('button', { name: `保存${secondTitle}` }),
      )
      await screen.findByText(`${secondTitle}已保存；仅用于之后提交的任务。`)
      await act(async () => finishFirst?.(firstSnapshot))
      await screen.findByText(`${firstTitle}已保存；仅用于之后提交的任务。`)
      expect(firstInput).toHaveValue(firstSnapshot[firstKey].instructions)
      expect(secondInput).toHaveValue(latestSnapshot[secondKey].instructions)
      expect(client.getQueryData(ANALYSIS_SETTINGS_QUERY_KEY)).toEqual(
        latestSnapshot,
      )
      await user.click(screen.getByRole('button', { name: '一键初步分析' }))
      const dialog = screen.getByRole('dialog')
      expect(dialog).toHaveTextContent(
        '初步分析提示词 · 版本 ' + latestSnapshot.initial_prompt.id,
      )
      expect(dialog).toHaveTextContent(
        '报告提示词 · 版本 ' + latestSnapshot.report_prompt.id,
      )
      expect(start).not.toHaveBeenCalled()
    },
  )
  it('does not erase newer automation authorization with an earlier prompt-save response', async () => {
    const promptSaved = analysisSettingsFixture()
    promptSaved.initial_prompt = {
      ...promptSaved.initial_prompt,
      id: 3,
      instructions: '独立保存的初步理解指令',
    }
    const authorized = {
      ...promptSaved,
      automation: {
        ...promptSaved.automation,
        enabled: true,
        revision: 2,
        approved_configuration_revision: 3,
      },
    }
    let finishPrompt: ((settings: typeof promptSaved) => void) | undefined
    vi.mocked(saveAnalysisPrompt).mockReturnValueOnce(
      new Promise((resolve) => {
        finishPrompt = resolve
      }),
    )
    vi.mocked(saveAnalysisAutomation).mockResolvedValueOnce(authorized)
    const user = userEvent.setup()
    const { client } = renderResults()
    await user.click(await screen.findByText('提示词与自动分析设置'))
    const initial = screen.getByLabelText('初步分析提示词')
    await user.clear(initial)
    await user.type(initial, promptSaved.initial_prompt.instructions)
    await user.click(screen.getByRole('button', { name: '保存初步分析提示词' }))
    await waitFor(() => expect(initial).toBeDisabled())
    await user.click(screen.getByRole('button', { name: '设置自动分析授权' }))
    await user.click(screen.getByRole('button', { name: '确认并保存授权' }))
    await screen.findByRole('button', { name: '停用自动分析' })
    await act(async () => finishPrompt?.(promptSaved))
    await screen.findByText('初步分析提示词已保存；仅用于之后提交的任务。')
    expect(screen.getByRole('button', { name: '停用自动分析' })).toBeEnabled()
    expect(client.getQueryData(ANALYSIS_SETTINGS_QUERY_KEY)).toEqual(authorized)
    expect(start).not.toHaveBeenCalled()
  })
  it.each(['before', 'during'] as const)(
    'keeps saved prompt state when a settings GET started %s the save returns late',
    async (readTiming) => {
      const saved = analysisSettingsFixture()
      saved.initial_prompt = {
        ...saved.initial_prompt,
        id: 3,
        instructions: '已提交保存的新指令',
      }
      let finishSave: ((settings: typeof saved) => void) | undefined
      let finishRead: ((settings: typeof saved) => void) | undefined
      vi.mocked(saveAnalysisPrompt).mockReturnValueOnce(
        new Promise((resolve) => {
          finishSave = resolve
        }),
      )
      const user = userEvent.setup()
      const { client } = renderResults()
      await user.click(await screen.findByText('提示词与自动分析设置'))
      const initial = screen.getByLabelText('初步分析提示词')
      await user.clear(initial)
      await user.type(initial, saved.initial_prompt.instructions)
      vi.mocked(fetchAnalysisSettings).mockReturnValueOnce(
        new Promise((resolve) => {
          finishRead = resolve
        }),
      )
      if (readTiming === 'before')
        await user.click(screen.getByRole('button', { name: '刷新' }))
      await user.click(
        screen.getByRole('button', { name: '保存初步分析提示词' }),
      )
      await waitFor(() => expect(initial).toBeDisabled())
      if (readTiming === 'during')
        await user.click(screen.getByRole('button', { name: '刷新' }))
      await waitFor(() =>
        expect(fetchAnalysisSettings).toHaveBeenCalledTimes(2),
      )
      await act(async () => finishSave?.(saved))
      await screen.findByText('初步分析提示词已保存；仅用于之后提交的任务。')
      await act(async () => finishRead?.(analysisSettingsFixture()))
      expect(initial).toHaveValue(saved.initial_prompt.instructions)
      expect(client.getQueryData(ANALYSIS_SETTINGS_QUERY_KEY)).toEqual(saved)
      expect(start).not.toHaveBeenCalled()
    },
  )
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
    expect(await screen.findByText('内容理解')).toBeVisible()
    expect(screen.queryAllByRole('alert')).toHaveLength(0)
    expect(start).not.toHaveBeenCalled()
    expect(saveAnalysisPrompt).not.toHaveBeenCalled()
    expect(saveAnalysisAutomation).not.toHaveBeenCalled()
    expect(openSearchRunResult).not.toHaveBeenCalled()
  })
  it('recovers from a prompt version conflict without discarding the draft or automatically overwriting', async () => {
    const user = userEvent.setup()
    const { client } = renderResults()
    await user.click(await screen.findByText('提示词与自动分析设置'))
    const initial = screen.getByLabelText('初步分析提示词')
    await user.clear(initial)
    await user.type(initial, '保留我的草稿')
    await act(async () => {
      const changed = analysisSettingsFixture()
      changed.initial_prompt = {
        ...changed.initial_prompt,
        id: 9,
        instructions: '其他编辑者的新文本',
      }
      client.setQueryData(ANALYSIS_SETTINGS_QUERY_KEY, changed)
    })
    expect(initial).toHaveValue('保留我的草稿')
    await user.click(
      await screen.findByRole('button', { name: '保留草稿并采用最新版本' }),
    )
    expect(saveAnalysisPrompt).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '保存初步分析提示词' }))
    await waitFor(() =>
      expect(saveAnalysisPrompt).toHaveBeenCalledWith('initial', {
        expected_version_id: 9,
        instructions: '保留我的草稿',
      }),
    )
  })
  it('separates saved automation authorization from disabled rollout and freezes the approved revision', async () => {
    const user = userEvent.setup()
    const { client } = renderResults()
    await user.click(await screen.findByText('提示词与自动分析设置'))
    expect(screen.getByText(/完整流程尚未启用，当前不会自动执行/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: '设置自动分析授权' }))
    await act(async () => {
      client.setQueryData(AI_SETTINGS_QUERY_KEY, {
        ...analysisProvider,
        revision: 4,
        model: 'changed-model',
      })
    })
    const dialog = screen.getByRole('dialog', { name: '确认自动分析授权' })
    expect(dialog).toHaveTextContent('配置版本 3')
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
    await user.click(screen.getByText('已保存的正文与输入覆盖'))
    expect(
      screen.getByText('完整保存的合成正文，未把来源陈述当成事实。'),
    ).toBeVisible()
    await user.click(screen.getByText('旧版分析与报告 · 1 条'))
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
      screen.getByText('已保存 8 条 · 未成功 2 条 · 待处理 0 条'),
    ).toBeVisible()
    expect(screen.getByText(/本任务已全部处理并保存完成记录/)).toBeVisible()
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
      screen.getByText('首次入库时间范围不正确，请检查日期及先后顺序。'),
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
    expect(await screen.findByText('已保存初步分析')).toBeVisible()
    expect(fetchAnalysisJobItems).toHaveBeenCalledTimes(2)
    expect(start).not.toHaveBeenCalled()
  })
})
