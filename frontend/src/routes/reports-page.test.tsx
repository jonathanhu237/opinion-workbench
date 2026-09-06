import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  analysisProvider,
  analysisJobFixture,
  analysisSettingsFixture,
  resultFixture,
} from '@/lib/api/analysis-fixtures'
import { fetchAISettings } from '@/lib/api/ai-settings'
import { fetchAnalysisSettings } from '@/lib/api/analysis-settings'
import {
  createReportGeneration,
  fetchGenerationEligibility,
  fetchReportRecordByReport,
  fetchReportGenerations,
  fetchReportRecords,
  fetchReportGeneration,
  previewReportSelection,
} from '@/lib/api/report-generations'
import {
  fetchResults,
  fetchResult,
  fetchResultOrigins,
  fetchResultLegacyAnalyses,
} from '@/lib/api/results'
import { ReportHub } from '@/routes/reports-page'
import {
  fetchAnalysisJobItems,
  fetchResultAnalyses,
} from '@/lib/api/content-analyses'

vi.mock('@/lib/api/content-analyses', async (original) => ({
  ...(await original<typeof import('@/lib/api/content-analyses')>()),
  fetchAnalysisJobItems: vi.fn(),
  fetchResultAnalyses: vi.fn(),
}))

vi.mock('@/lib/api/ai-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/ai-settings')>()),
  fetchAISettings: vi.fn(),
}))
vi.mock('@/lib/api/analysis-settings', async (original) => ({
  ...(await original<typeof import('@/lib/api/analysis-settings')>()),
  fetchAnalysisSettings: vi.fn(),
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
  fetchReportRecordByReport: vi.fn(),
  fetchReportGenerations: vi.fn(),
  fetchReportRecords: vi.fn(),
  fetchReportGeneration: vi.fn(),
  previewReportSelection: vi.fn(),
}))

function renderPage() {
  const router = createMemoryRouter(
    [{ path: '/reports', element: <ReportHub /> }],
    { initialEntries: ['/reports'] },
  )
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    router,
    ...render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

const record = {
  record_type: 'generation' as const,
  record_id: 8,
  generation_id: 8,
  report_id: null,
  automation_run_id: null,
  name: '龙田舆情报告',
  trigger: 'manual' as const,
  status: 'summarising' as const,
  created_at: '2026-08-29T08:00:00+00:00',
  selection_count: 2,
  processed_count: 1,
  failed_count: 0,
  active_count: 1,
  parent_report_id: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  vi.mocked(fetchAISettings).mockResolvedValue(analysisProvider)
  vi.mocked(fetchAnalysisSettings).mockResolvedValue(analysisSettingsFixture())
  vi.mocked(fetchGenerationEligibility).mockResolvedValue({
    pending: 1,
    failed: 1,
    active: 0,
  })
  vi.mocked(fetchReportRecordByReport).mockResolvedValue(record)
  vi.mocked(fetchReportGenerations).mockResolvedValue({
    items: [],
    next_before_id: null,
  })
  vi.mocked(fetchReportRecords).mockResolvedValue({
    items: [record],
    next_offset: null,
  })
  vi.mocked(fetchResults).mockResolvedValue({
    items: [resultFixture()],
    total: 1,
    limit: 20,
    offset: 0,
    eligible_count: 1,
    active_count: 0,
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

describe('舆情报告统一页面', () => {
  it('opens details inside the selection dialog and returns with selection intact', async () => {
    vi.mocked(fetchResult).mockResolvedValue(resultFixture())
    const empty = { items: [], total: 0, limit: 20, offset: 0 }
    vi.mocked(fetchResultOrigins).mockResolvedValue(empty)
    vi.mocked(fetchResultLegacyAnalyses).mockResolvedValue(empty)
    vi.mocked(fetchResultAnalyses).mockResolvedValue(empty)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: '生成报告' }))
    const checkbox = await screen.findByRole('checkbox', {
      name: '选择内容：合成采集内容 11',
    })
    await user.click(checkbox)
    await user.click(
      screen.getByRole('button', { name: '查看内容详情：合成采集内容 11' }),
    )
    expect(
      await screen.findByRole('dialog', { name: '内容详情' }),
    ).toBeVisible()
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull()
    await user.click(screen.getByRole('button', { name: '返回选材' }))
    expect(
      await screen.findByRole('dialog', { name: '生成报告' }),
    ).toBeVisible()
    expect(
      screen.getByRole('checkbox', { name: '选择内容：合成采集内容 11' }),
    ).toBeChecked()
    await user.click(
      screen.getByRole('button', { name: '查看内容详情：合成采集内容 11' }),
    )
    await user.keyboard('{Escape}')
    expect(
      await screen.findByRole('dialog', { name: '生成报告' }),
    ).toBeVisible()
    expect(createReportGeneration).not.toHaveBeenCalled()
  })
  it('shows failed historic empty generations as failures without a report action', async () => {
    vi.mocked(fetchReportRecords).mockResolvedValue({
      items: [
        {
          ...record,
          status: 'empty',
          report_id: 2,
          selection_count: 17,
          failed_count: 17,
          active_count: 0,
          processed_count: 17,
        },
      ],
      next_offset: null,
    })
    renderPage()
    expect(await screen.findByText('生成失败')).toBeVisible()
    expect(screen.queryByRole('button', { name: '查看报告' })).toBeNull()
    expect(screen.getByRole('button', { name: '查看处理' })).toBeVisible()
  })

  it('shows analysis failures even when no report was created', async () => {
    const job = analysisJobFixture()
    vi.mocked(fetchReportRecords).mockResolvedValue({
      items: [{ ...record, status: 'failed', active_count: 0 }],
      next_offset: null,
    })
    vi.mocked(fetchReportGeneration).mockResolvedValue({
      id: 8,
      name: record.name,
      status: 'failed',
      created_at: record.created_at,
      pause_reason: null,
      report: null,
      analysis: {
        ...job,
        counts: {
          ...job.counts,
          total: 2,
          queued: 0,
          failed: 1,
          interrupted: 1,
          completed: 0,
        },
      },
    } as never)
    vi.mocked(fetchAnalysisJobItems).mockResolvedValue({
      items: [
        {
          id: 1,
          source: resultFixture().source,
          error: {
            code: 'invalid_schema',
            message: '模型返回的格式不正确',
            validation_issues: ['summary: string_type'],
          },
        },
      ],
      total: 1,
      offset: 0,
      limit: 20,
    } as never)
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '查看处理' }))
    expect(await screen.findByText('模型返回的格式不正确')).toBeVisible()
    expect(screen.getByText('summary: string_type')).toBeVisible()
  })
  it('renders one report table and opens the preparation dialog on demand', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(
      await screen.findByRole('table', { name: '舆情报告列表' }),
    ).toBeVisible()
    expect(screen.getByText('龙田舆情报告')).toBeVisible()
    expect(screen.getByText('已处理 1/2 · 进行中 1')).toBeVisible()
    expect(screen.queryByText('报告记录')).toBeNull()

    await user.click(screen.getByRole('button', { name: '生成报告' }))
    expect(
      await screen.findByRole('dialog', { name: '生成报告' }),
    ).toBeVisible()
    expect(
      await screen.findByRole('table', { name: '报告选材内容表格' }),
    ).toBeVisible()
    expect(fetchReportRecords).toHaveBeenCalledTimes(1)
  })

  it('keeps the three preparation steps separate from final submission', async () => {
    const user = userEvent.setup()
    vi.mocked(createReportGeneration).mockImplementation(
      () => new Promise(() => undefined) as never,
    )
    renderPage()

    await user.click(screen.getByRole('button', { name: '生成报告' }))
    await user.click(
      await screen.findByRole('checkbox', {
        name: '选择内容：合成采集内容 11',
      }),
    )
    await user.click(screen.getByRole('button', { name: '下一步' }))
    expect(screen.getByText('内容分析提示词')).toBeVisible()
    expect(createReportGeneration).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '下一步' }))
    expect(screen.getByText('报告总结提示词')).toBeVisible()
    await waitFor(() => expect(previewReportSelection).toHaveBeenCalled())
    await user.click(screen.getByRole('button', { name: '开始生成' }))
    await waitFor(() => expect(createReportGeneration).toHaveBeenCalledTimes(1))
    expect(vi.mocked(createReportGeneration).mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        name: expect.stringContaining('舆情分析报告'),
        selection: { kind: 'explicit', result_ids: [11] },
      }),
    )
  })
})
