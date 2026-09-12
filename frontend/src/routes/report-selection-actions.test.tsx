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
import {
  fetchSummaryPreference,
  saveSummaryPreference,
} from '@/lib/api/summary-preferences'
import { ReportSelectionActions } from '@/routes/report-selection-actions'

vi.mock('@/lib/api/report-generations', async (original) => ({
  ...(await original<typeof import('@/lib/api/report-generations')>()),
  createReportGeneration: vi.fn(),
  fetchGenerationEligibility: vi.fn(),
  previewReportSelection: vi.fn(),
}))

vi.mock('@/lib/api/summary-preferences', () => ({
  fetchSummaryPreference: vi.fn(),
  saveSummaryPreference: vi.fn(),
}))

let preferenceStorage = new Map<string, string>()

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
  vi.mocked(fetchSummaryPreference).mockRejectedValue(
    new Error('legacy preference unavailable'),
  )
  vi.mocked(saveSummaryPreference).mockResolvedValue({ summary_concurrency: 8 })
  sessionStorage.clear()
  preferenceStorage = new Map()
  vi.stubGlobal('localStorage', {
    clear: () => preferenceStorage.clear(),
    getItem: (key: string) => preferenceStorage.get(key) ?? null,
    removeItem: (key: string) => preferenceStorage.delete(key),
    setItem: (key: string, value: string) => preferenceStorage.set(key, value),
  })
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

it('uses the library preview for bulk selection including previous failures', async () => {
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
  await user.click(
    screen.getByRole('button', { name: '选中全部未纳入报告的内容' }),
  )
  await waitFor(() => expect(screen.getByText('已选 3 条')).toBeVisible())
  expect(previewReportSelection).toHaveBeenCalledWith({
    kind: 'library',
  })
  expect(createReportGeneration).not.toHaveBeenCalled()
  expect(onStarted).not.toHaveBeenCalled()
})

it('shows the combined backlog and selected retry count before submission', async () => {
  vi.mocked(previewReportSelection).mockResolvedValue({
    selection: { kind: 'explicit', result_ids: [11, 12] },
    counts: {
      total: 2,
      pending: 1,
      already_summarized: 0,
      failed: 1,
      active: 0,
    },
  })
  const user = userEvent.setup()
  show([11, 12])

  expect(
    await screen.findByText(
      (_, element) =>
        element?.textContent?.replace(/\s+/g, ' ').trim() ===
        '未纳入报告共 29 · 其中曾失败 1',
    ),
  ).toBeVisible()
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  const retryLabel = await screen.findByText('失败重试')
  expect(retryLabel.parentElement).toHaveTextContent('失败重试1')
})

it('blocks submission until the selected preview can confirm retry counts', async () => {
  vi.mocked(previewReportSelection)
    .mockRejectedValueOnce(new AnalysisApiError('service_unavailable'))
    .mockResolvedValueOnce({
      selection: { kind: 'explicit', result_ids: [11, 12] },
      counts: {
        total: 2,
        pending: 1,
        already_summarized: 0,
        failed: 1,
        active: 0,
      },
    })
  vi.mocked(createReportGeneration).mockResolvedValue({
    id: 1,
    request_id: 'request-1',
  } as never)
  const user = userEvent.setup()
  show([11, 12])

  await user.click(screen.getByRole('button', { name: '生成报告' }))
  expect(
    await screen.findByText(
      '暂时无法确认选材状态，已暂停提交。请重新检查后再确认报告。',
    ),
  ).toBeVisible()
  const confirm = screen.getByRole('button', { name: '确认生成报告' })
  expect(confirm).toBeDisabled()
  expect(createReportGeneration).not.toHaveBeenCalled()

  await user.click(screen.getByRole('button', { name: '重新检查选材' }))
  await waitFor(() => expect(confirm).toBeEnabled())
  await user.click(confirm)
  await waitFor(() => expect(createReportGeneration).toHaveBeenCalledTimes(1))
})

it('defaults to eight and only remembers a concurrency after formal submission', async () => {
  vi.mocked(createReportGeneration).mockResolvedValue({} as never)
  const user = userEvent.setup()
  const first = show([11])
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  const trigger = await screen.findByRole('combobox', {
    name: '单条总结并发数',
  })
  expect(trigger).toHaveTextContent('8')
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name: '4 条同时总结' }))
  await user.click(screen.getByRole('button', { name: '确认生成报告' }))
  await waitFor(() => expect(createReportGeneration).toHaveBeenCalled())
  expect(
    JSON.parse(
      localStorage.getItem(
        'opinion-workbench:report-generation:summary-concurrency:v1',
      )!,
    ),
  ).toBe(4)
  first.unmount()

  show([11])
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  expect(
    await screen.findByRole('combobox', { name: '单条总结并发数' }),
  ).toHaveTextContent('4')
})

it('does not remember a concurrency when report submission fails', async () => {
  vi.mocked(createReportGeneration).mockRejectedValue(
    new AnalysisApiError('service_unavailable'),
  )
  const user = userEvent.setup()
  const first = show([11])
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  const trigger = await screen.findByRole('combobox', {
    name: '单条总结并发数',
  })
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name: '2 条同时总结' }))
  await user.click(screen.getByRole('button', { name: '确认生成报告' }))
  await waitFor(() => expect(createReportGeneration).toHaveBeenCalled())
  expect(
    localStorage.getItem(
      'opinion-workbench:report-generation:summary-concurrency:v1',
    ),
  ).toBeNull()
  first.unmount()
  sessionStorage.clear()

  show([11])
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  expect(
    await screen.findByRole('combobox', { name: '单条总结并发数' }),
  ).toHaveTextContent('8')
})

it('falls back to eight when the saved concurrency preference is corrupt', async () => {
  localStorage.setItem(
    'opinion-workbench:report-generation:summary-concurrency:v1',
    'nope',
  )
  const user = userEvent.setup()
  show([11])
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  expect(
    await screen.findByRole('combobox', { name: '单条总结并发数' }),
  ).toHaveTextContent('8')
})

it('loads portable preference when the browser origin has no local value', async () => {
  vi.mocked(fetchSummaryPreference).mockResolvedValue({
    summary_concurrency: 16,
  })
  const user = userEvent.setup()
  show([11])
  await waitFor(() => expect(fetchSummaryPreference).toHaveBeenCalled())
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  expect(
    await screen.findByRole('combobox', { name: '单条总结并发数' }),
  ).toHaveTextContent('16')
})

it('does not persist a portable preference just by opening the dialog', async () => {
  vi.mocked(fetchSummaryPreference).mockResolvedValue({
    summary_concurrency: 4,
  })
  const user = userEvent.setup()
  show([11])
  await user.click(screen.getByRole('button', { name: '生成报告' }))
  expect(saveSummaryPreference).not.toHaveBeenCalled()
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
