import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { beforeEach, expect, it, vi } from 'vitest'

import { ReportGeneration } from '@/routes/results'
import {
  analysisProvider,
  analysisSettingsFixture,
  resultFixture,
} from '@/lib/api/analysis-fixtures'
import { fetchAISettings } from '@/lib/api/ai-settings'
import { fetchAnalysisSettings } from '@/lib/api/analysis-settings'
import { fetchResults } from '@/lib/api/results'
import {
  createReportGeneration,
  fetchGenerationEligibility,
  fetchReportGenerations,
  fetchReportGeneration,
  previewReportSelection,
} from '@/lib/api/report-generations'
import { fetchTopicReports } from '@/lib/api/topic-reports'

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
  fetchReportGenerations: vi.fn(),
  fetchReportGeneration: vi.fn(),
  previewReportSelection: vi.fn(),
}))
vi.mock('@/lib/api/topic-reports', async (original) => ({
  ...(await original<typeof import('@/lib/api/topic-reports')>()),
  fetchTopicReports: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  vi.mocked(fetchAISettings).mockResolvedValue(analysisProvider)
  vi.mocked(fetchAnalysisSettings).mockResolvedValue(analysisSettingsFixture())
  vi.mocked(fetchGenerationEligibility).mockResolvedValue({
    pending: 1,
    failed: 0,
    active: 0,
  })
  vi.mocked(fetchReportGenerations).mockResolvedValue({
    items: [],
    next_before_id: null,
  })
  vi.mocked(fetchReportGeneration).mockResolvedValue(undefined as never)
  vi.mocked(fetchTopicReports).mockResolvedValue({
    reports: [],
    next_before_id: null,
  })
  vi.mocked(fetchResults).mockResolvedValue({
    items: [resultFixture(), resultFixture({ id: 12 })],
    total: 2,
    limit: 20,
    offset: 0,
    eligible_count: 2,
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

function renderPage() {
  const router = createMemoryRouter(
    [{ path: '/reports/new', element: <ReportGeneration /> }],
    { initialEntries: ['/reports/new'] },
  )
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

function renderPageWithHistory() {
  const router = createMemoryRouter(
    [
      { path: '/reports/new', element: <ReportGeneration /> },
      { path: '/reports/history', element: <p>报告记录</p> },
    ],
    { initialEntries: ['/reports/new'] },
  )
  return {
    router,
    ...render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

it('keeps selection separate from report creation and submits the fixed IDs after confirmation', async () => {
  const user = userEvent.setup()
  vi.mocked(createReportGeneration).mockImplementation(
    () => new Promise(() => undefined) as never,
  )
  renderPage()
  const row = await screen.findByRole('checkbox', {
    name: `选择内容：${resultFixture().source.title}`,
  })
  await user.click(row)
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
  await user.click(screen.getByRole('button', { name: '确认生成报告' }))
  await waitFor(() => expect(createReportGeneration).toHaveBeenCalledTimes(1))
  expect(vi.mocked(createReportGeneration).mock.calls[0][0]).toEqual(
    expect.objectContaining({
      name: expect.stringContaining('舆情分析报告'),
      selection: { kind: 'explicit', result_ids: [11] },
    }),
  )
})

it('adds the library snapshot to existing manual selection and does not create a report', async () => {
  const user = userEvent.setup()
  vi.mocked(previewReportSelection).mockResolvedValueOnce({
    selection: { kind: 'explicit', result_ids: [11, 12, 13] },
    counts: {
      total: 3,
      pending: 3,
      already_summarized: 0,
      failed: 0,
      active: 0,
    },
  })
  renderPage()
  await user.click(
    await screen.findByRole('checkbox', {
      name: `选择内容：${resultFixture().source.title}`,
    }),
  )
  await user.click(screen.getByRole('button', { name: '选中全部未分析内容' }))
  await waitFor(() => expect(screen.getByText('已选 3 条')).toBeVisible())
  expect(createReportGeneration).not.toHaveBeenCalled()
})

it('takes the user to report records after a generation is accepted', async () => {
  const user = userEvent.setup()
  vi.mocked(createReportGeneration).mockResolvedValue({ id: 23 } as never)
  const { router } = renderPageWithHistory()
  await user.click(
    await screen.findByRole('checkbox', {
      name: `选择内容：${resultFixture().source.title}`,
    }),
  )
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  await user.click(await screen.findByRole('button', { name: '确认生成报告' }))
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/reports/history')
    expect(router.state.location.search).toBe('?generation=23')
  })
})
