import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

import {
  analysisProvider,
  analysisSettingsFixture,
} from '@/lib/api/analysis-fixtures'
import { AnalysisApiError } from '@/lib/api/analysis-shared'
import {
  createReportGeneration,
  fetchGenerationEligibility,
  previewReportSelection,
} from '@/lib/api/report-generations'
import { ReportSelectionActions } from '@/routes/report-selection-actions'

vi.mock('@/lib/api/report-generations', async (original) => ({
  ...(await original<typeof import('@/lib/api/report-generations')>()),
  createReportGeneration: vi.fn(),
  fetchGenerationEligibility: vi.fn(),
  previewReportSelection: vi.fn(),
}))

function show(ids: number[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ReportSelectionActions
        selectedIds={ids}
        provider={analysisProvider}
        settings={analysisSettingsFixture()}
        onStarted={vi.fn()}
      />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  vi.mocked(fetchGenerationEligibility).mockResolvedValue({
    pending: 28,
    failed: 1,
    active: 0,
  })
  vi.mocked(previewReportSelection).mockImplementation(async (input) => ({
    selection:
      input.kind === 'library'
        ? { kind: 'explicit', result_ids: [1, 2] }
        : { kind: 'explicit', result_ids: input.result_ids },
    counts: {
      total: input.kind === 'library' ? 2 : input.result_ids.length,
      pending: input.kind === 'library' ? 2 : input.result_ids.length,
      already_summarized: 0,
      failed: 0,
      active: 0,
    },
  }))
})

it('replays the same fixed intent after an ambiguous submission and remount', async () => {
  vi.mocked(createReportGeneration).mockRejectedValue(
    new AnalysisApiError('service_unavailable'),
  )
  const user = userEvent.setup()
  const first = show([11, 12])
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  await user.click(await screen.findByRole('button', { name: '确认生成报告' }))
  await waitFor(() => expect(createReportGeneration).toHaveBeenCalledTimes(1))
  const intent = vi.mocked(createReportGeneration).mock.calls[0][0]
  expect(intent.selection).toEqual({ kind: 'explicit', result_ids: [11, 12] })
  first.unmount()

  show([99])
  expect(await screen.findByText('已选 2 条')).toBeVisible()
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  await user.click(await screen.findByRole('button', { name: '确认生成报告' }))
  await waitFor(() => expect(createReportGeneration).toHaveBeenCalledTimes(2))
  expect(vi.mocked(createReportGeneration).mock.calls[1][0]).toEqual(intent)
})

it('uses the library preview for bulk selection and makes failure inclusion explicit', async () => {
  const user = userEvent.setup()
  const onStarted = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <ReportSelectionActions
        selectedIds={[99]}
        provider={analysisProvider}
        settings={analysisSettingsFixture()}
        onStarted={onStarted}
      />
    </QueryClientProvider>,
  )
  await user.click(screen.getByText('更多选材'))
  await user.click(screen.getByRole('button', { name: '同时加入分析失败内容' }))
  await waitFor(() => expect(screen.getByText('已选 3 条')).toBeVisible())
  expect(previewReportSelection).toHaveBeenCalledWith({
    kind: 'library',
    include_failed: true,
  })
  expect(createReportGeneration).not.toHaveBeenCalled()
  expect(onStarted).not.toHaveBeenCalled()
})

it('keeps the report action beside selection instead of fixing it to the viewport', () => {
  const { container } = show([])
  const toolbar = container.querySelector(
    '[data-slot="report-selection-toolbar"]',
  )
  expect(toolbar).not.toBeNull()
  expect(toolbar).not.toHaveClass('fixed')
  expect(toolbar).not.toHaveClass('inset-x-4')
  expect(toolbar).toContainElement(
    screen.getByRole('button', { name: '生成报告' }),
  )
})
