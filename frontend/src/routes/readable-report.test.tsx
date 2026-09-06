import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { fetchReportSections } from '@/lib/api/topic-reports'
import {
  reportFixture,
  reportSectionFixture,
} from '@/lib/api/topic-reports.fixtures'
import { ReadableReport, reportReadingContent } from './readable-report'

vi.mock('@/lib/api/topic-reports', async (original) => ({
  ...(await original<typeof import('@/lib/api/topic-reports')>()),
  fetchReportSections: vi.fn(),
}))

function renderReport(report = reportFixture()) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ReadableReport report={report} />
    </QueryClientProvider>,
  )
}

describe('report reading view', () => {
  it('renders saved text and original URLs without technical report controls', async () => {
    const section = reportSectionFixture()
    vi.mocked(fetchReportSections).mockResolvedValue({
      sections: [section],
      total: 1,
      limit: 100,
      offset: 0,
    })
    renderReport()
    expect(
      await screen.findByRole('article', { name: '报告正文' }),
    ).toBeVisible()
    expect(screen.getByText(section.document!.items[0].text)).toBeVisible()
    expect(screen.getByRole('region', { name: '材料筛选说明' })).toBeVisible()
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(8)
    expect(links[0]).toHaveAttribute(
      'href',
      section.sources[0].source.content_url,
    )
    expect(links[0]).toHaveAttribute('target', '_blank')
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(
      screen.queryByText(/本报告使用的提示词与模型/),
    ).not.toBeInTheDocument()
  })

  it('resolves and deduplicates nested overview citations without repeating child text', () => {
    const leaf = reportSectionFixture()
    const middle = reportSectionFixture({
      id: 502,
      kind: 'overview',
      document: null,
      overview_document: {
        overview: '中间摘要',
        items: [{ text: '中间正文', section_ids: [501], source_ids: [11, 12] }],
      },
      sources: [],
    })
    const root = reportSectionFixture({
      id: 503,
      kind: 'overview',
      document: null,
      overview_document: {
        overview: '最终摘要',
        items: [{ text: '最终正文', section_ids: [502], source_ids: [12] }],
      },
      sources: [],
    })
    const content = reportReadingContent(503, [root, leaf, middle])
    expect(content.overview).toBe('最终摘要')
    expect(content.paragraphs).toHaveLength(1)
    expect(content.paragraphs[0].text).toBe('最终正文')
    expect(content.paragraphs[0].sources).toEqual([leaf.sources[1].source])
  })

  it('renders one original entry for repeated paragraphs and keeps every same-text post accessible', async () => {
    const section = reportSectionFixture()
    const text =
      '居民反映龙田街道老坑社区路口车辆堵塞，已经多次投诉仍未解决，担忧消防车与救护车无法进入。希望有关部门核实处理，并明确负责部门。上述情况属于来源陈述，现场道路性质和执法过程尚未独立核实。'
    section.sources = section.sources.slice(0, 3).map((source) => ({
      ...source,
      source: { ...source.source, snippet: text },
    }))
    section.document = {
      overview: '摘要',
      items: [
        { text: '一条道路投诉的文字内容。', source_ids: [11, 12, 13] },
        { text: '同一投诉的图片观察。', source_ids: [11, 12] },
      ],
    }
    vi.mocked(fetchReportSections).mockResolvedValue({
      sections: [section],
      total: 1,
      limit: 100,
      offset: 0,
    })
    renderReport()
    await screen.findByRole('article', { name: '报告正文' })
    expect(screen.getAllByRole('link', { name: /^查看原文/ })).toHaveLength(1)
    expect(
      screen.getByRole('link', { name: /^查看同文发布 1/ }),
    ).not.toBeVisible()
    expect(screen.getByText('同一投诉的图片观察。')).toBeVisible()
    await userEvent.click(screen.getByText('另有 2 条同文发布'))
    expect(screen.getAllByRole('link')).toHaveLength(3)
    expect(
      screen.getAllByRole('link').map((link) => link.getAttribute('href')),
    ).toEqual(section.sources.map((source) => source.source.content_url))
  })

  it('rejects missing sources and cyclic references', () => {
    expect(() =>
      reportReadingContent(501, [reportSectionFixture({ sources: [] })]),
    ).toThrow('Missing report source')
    expect(() =>
      reportReadingContent(501, [
        reportSectionFixture({
          kind: 'overview',
          document: null,
          overview_document: {
            overview: '摘要',
            items: [{ text: '正文', section_ids: [501] }],
          },
        }),
      ]),
    ).toThrow('Incomplete report references')
  })

  it('does not invent paragraph citations for a legacy overview', () => {
    const leaf = reportSectionFixture()
    const root = reportSectionFixture({
      id: 502,
      kind: 'overview',
      document: null,
      overview_document: {
        overview: '旧摘要',
        items: [{ text: '旧正文', section_ids: [501] }],
      },
      sources: [],
    })
    expect(
      reportReadingContent(502, [root, leaf]).paragraphs[0].sources,
    ).toEqual([])
  })

  it('keeps separate paragraph sources even when both cite the same chapter', () => {
    const leaf = reportSectionFixture()
    const root = reportSectionFixture({
      id: 502,
      kind: 'overview',
      document: null,
      overview_document: {
        overview: '摘要',
        items: [
          { text: '堵路', section_ids: [501], source_ids: [11] },
          { text: '电费', section_ids: [501], source_ids: [12] },
        ],
      },
      sources: [],
    })
    expect(
      reportReadingContent(502, [root, leaf]).paragraphs.map((p) =>
        p.sources.map((s) => s.result_id),
      ),
    ).toEqual([[11], [12]])
    root.overview_document!.items[1].source_ids = [999]
    expect(() => reportReadingContent(502, [root, leaf])).toThrow(
      'Missing report source',
    )
  })

  it('shows a recoverable error when loading fails', async () => {
    vi.mocked(fetchReportSections).mockRejectedValue(new Error('offline'))
    renderReport()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '暂时无法完整读取报告正文',
    )
    expect(screen.getByRole('button', { name: '重试读取报告' })).toBeVisible()
  })

  it('does not spin forever for a completed report without a root', () => {
    renderReport(reportFixture({ root_section_id: null }))
    expect(screen.getByRole('alert')).toHaveTextContent('报告正文缺失')
  })
})
