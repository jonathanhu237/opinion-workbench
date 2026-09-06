import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchReportSources, type ReportSource } from '@/lib/api/topic-reports'
import {
  reportFixture,
  reportSourceFixture,
} from '@/lib/api/topic-reports.fixtures'
import { ReportMaterialNote } from './report-material-note'

vi.mock('@/lib/api/topic-reports', async (original) => ({
  ...(await original<typeof import('@/lib/api/topic-reports')>()),
  fetchReportSources: vi.fn(),
}))

function renderNote(sources: ReportSource[]) {
  const report = reportFixture()
  report.coverage = {
    total: sources.length,
    ready: sources.filter((item) => item.state !== 'unavailable').length,
    unavailable: 0,
    pending: 0,
    judging: 0,
    relevant: 0,
    irrelevant: 0,
    uncertain: 0,
    failed: 0,
    cancelled: 0,
    interrupted: 0,
  }
  for (const item of sources) report.coverage[item.state] += 1
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ReportMaterialNote report={report} />
    </QueryClientProvider>,
  )
}

function mockPages(sources: ReportSource[]) {
  vi.mocked(fetchReportSources).mockImplementation(
    async (_id, _signal, offset = 0, limit = 100) => ({
      items: sources.slice(offset, offset + limit),
      total: sources.length,
      offset,
      limit,
    }),
  )
}

function remainingSource(position: number, state: 'irrelevant' | 'uncertain') {
  const item = reportSourceFixture(position, {
    state,
    judgment: {
      decision: state,
      reason:
        state === 'irrelevant'
          ? '材料涉及外地演出，未见龙田相关线索。'
          : '仅提到龙田执法队，尚不能确认具体行政区。',
    },
  })
  item.source.title = state === 'irrelevant' ? '外地演出记录' : '执法队记录'
  return item
}

async function expandNote() {
  await userEvent.click(screen.getByText(/^查看未纳入正文的/))
}

describe('report material note', () => {
  beforeEach(() => vi.mocked(fetchReportSources).mockReset())

  it('shows compact counts and lazily reads saved reasons without treating uncertain as irrelevant', async () => {
    const sources = [
      reportSourceFixture(),
      remainingSource(1, 'irrelevant'),
      remainingSource(2, 'uncertain'),
    ]
    mockPages(sources)
    renderNote(sources)
    expect(
      screen.getByText(
        '本次共 3 条材料，1 条判相关；其余 2 条中，1 条判无关、1 条待确认。',
      ),
    ).toBeVisible()
    expect(
      screen.getByText(/模型判断，仅供复核。待确认不等于无关/),
    ).toBeVisible()
    expect(fetchReportSources).not.toHaveBeenCalled()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await expandNote()
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByText('无关')).toBeVisible()
    expect(within(table).getByText('待确认')).toBeVisible()
    expect(within(table).getByText(sources[1].judgment!.reason)).toBeVisible()
    expect(within(table).getByText(sources[2].judgment!.reason)).toBeVisible()
    expect(
      within(table).getByRole('link', { name: /外地演出记录/ }),
    ).toHaveAttribute('href', sources[1].source.content_url)
    expect(within(table).getAllByRole('link')).toHaveLength(2)
    expect(fetchReportSources).toHaveBeenCalledOnce()
  })

  it('does not offer an empty list or fetch sources when all materials are relevant', () => {
    renderNote([reportSourceFixture()])
    expect(screen.getByText('本次共 1 条材料，均判相关。')).toBeVisible()
    expect(screen.queryByText(/^查看未纳入正文的/)).not.toBeInTheDocument()
    expect(fetchReportSources).not.toHaveBeenCalled()
  })

  it('explains unavailable and interrupted materials without calling them irrelevant', async () => {
    const sources = [
      reportSourceFixture(),
      reportSourceFixture(1, {
        state: 'unavailable',
        judgment: null,
        judgment_node_id: null,
        unavailable_reason: 'not_analysed',
      }),
      reportSourceFixture(2, { state: 'interrupted', judgment: null }),
    ]
    mockPages(sources)
    renderNote(sources)
    expect(screen.getByText(/1 条材料不足、1 条未完成判断/)).toBeVisible()
    await expandNote()
    const table = await screen.findByRole('table')
    expect(within(table).getByText('生成报告时还没有单条总结。')).toBeVisible()
    expect(within(table).getByText('判断已中断')).toBeVisible()
    expect(within(table).queryByText('无关')).not.toBeInTheDocument()
  })

  it('loads every page even when all remaining materials are after the first 100 entries', async () => {
    const sources = [
      ...Array.from({ length: 100 }, (_, i) => reportSourceFixture(i)),
      remainingSource(100, 'uncertain'),
    ]
    mockPages(sources)
    renderNote(sources)
    await expandNote()
    expect(
      await screen.findByRole('link', { name: /执法队记录/ }),
    ).toBeVisible()
    expect(fetchReportSources).toHaveBeenNthCalledWith(
      2,
      31,
      expect.any(AbortSignal),
      100,
      100,
    )
    expect(screen.getAllByRole('link')).toHaveLength(1)
  })

  it('retains the counts and offers a working retry on read failure', async () => {
    const sources = [remainingSource(0, 'irrelevant')]
    vi.mocked(fetchReportSources).mockRejectedValue(new Error('offline'))
    renderNote(sources)
    await expandNote()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '报告正文不受影响',
    )
    expect(screen.getByText(/本次共 1 条材料/)).toBeVisible()
    mockPages(sources)
    await userEvent.click(screen.getByRole('button', { name: '重试读取材料' }))
    expect(await screen.findByRole('table')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('rejects a truncated page instead of showing an incomplete explanation', async () => {
    const sources = [reportSourceFixture(), remainingSource(1, 'irrelevant')]
    vi.mocked(fetchReportSources).mockResolvedValue({
      items: [sources[1]],
      total: 2,
      offset: 0,
      limit: 100,
    })
    renderNote(sources)
    await expandNote()
    expect(await screen.findByRole('alert')).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('rejects duplicate sources across pages', async () => {
    const sources = [
      ...Array.from({ length: 100 }, (_, i) => reportSourceFixture(i)),
      remainingSource(100, 'uncertain'),
    ]
    sources[100].source.result_id = sources[0].source.result_id
    mockPages(sources)
    renderNote(sources)
    await expandNote()
    expect(await screen.findByRole('alert')).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('rejects source states that disagree with the report counts', async () => {
    const sources = [remainingSource(0, 'irrelevant')]
    mockPages([reportSourceFixture()])
    renderNote(sources)
    await expandNote()
    expect(await screen.findByRole('alert')).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
