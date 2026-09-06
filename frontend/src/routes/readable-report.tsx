import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { groupReadingParagraphs } from '@/lib/report-source-groups'
import {
  fetchReportSections,
  TOPIC_REPORTS_QUERY_KEY,
  type ReportRun,
  type ReportSection,
} from '@/lib/api/topic-reports'
import { ReportMaterialNote } from '@/routes/report-material-note'

type Source = ReportSection['sources'][number]['source']

export function reportReadingContent(
  rootId: number,
  sections: ReportSection[],
) {
  const byId = new Map(sections.map((section) => [section.id, section]))
  const root = byId.get(rootId)
  const seen = new Set<number>()
  const cache = new Map<number, Source[]>()
  const selectSources = (ids: number[], sources: Source[]) =>
    ids.map((id) => {
      const source = sources.find((entry) => entry.result_id === id)
      if (!source) throw new Error('Missing report source')
      return source
    })
  const sourcesFor = (id: number): Source[] => {
    const saved = cache.get(id)
    if (saved) return saved
    const section = byId.get(id)
    if (
      !section ||
      section.status !== 'completed' ||
      seen.has(id) ||
      seen.size >= 64
    )
      throw new Error('Incomplete report references')
    seen.add(id)
    const sources = section.document
      ? section.document.items.flatMap((item) =>
          item.source_ids.map((sourceId) => {
            const source = section.sources.find(
              (entry) => entry.source.result_id === sourceId,
            )
            if (!source) throw new Error('Missing report source')
            return source.source
          }),
        )
      : section.overview_document?.items.flatMap((item) =>
          item.source_ids
            ? selectSources(
                item.source_ids,
                item.section_ids.flatMap(sourcesFor),
              )
            : item.section_ids.flatMap(sourcesFor),
        )
    if (!sources) throw new Error('Missing report content')
    const unique = [
      ...new Map(sources.map((source) => [source.result_id, source])).values(),
    ]
    seen.delete(id)
    cache.set(id, unique)
    return unique
  }
  if (!root) throw new Error('Missing report root')
  const allSources = sourcesFor(rootId)
  const paragraphs = root.document
    ? root.document.items.map((item) => ({
        text: item.text,
        sources: item.source_ids.map((id) =>
          allSources.find((source) => source.result_id === id)!,
        ),
      }))
    : root.overview_document!.items.map((item) => ({
        text: item.text,
        sources: item.source_ids
          ? selectSources(item.source_ids, item.section_ids.flatMap(sourcesFor))
          : [],
      }))
  return {
    overview: (root.document ?? root.overview_document)!.overview,
    paragraphs,
  }
}

async function loadReadingContent(report: ReportRun, signal: AbortSignal) {
  const sections: ReportSection[] = []
  for (let offset = 0; ; offset += 100) {
    const page = await fetchReportSections(
      report.id,
      signal,
      offset,
      undefined,
      100,
    )
    if (
      page.total > 10000 ||
      page.sections.some((section) => section.report_id !== report.id)
    )
      throw new Error('Invalid report sections')
    sections.push(...page.sections)
    if (sections.length >= page.total) break
    if (page.sections.length !== 100)
      throw new Error('Incomplete report sections')
  }
  if (new Set(sections.map((section) => section.id)).size !== sections.length)
    throw new Error('Duplicate report sections')
  return reportReadingContent(report.root_section_id!, sections)
}

export function ReadableReport({ report }: { report: ReportRun }) {
  const content = useQuery({
    queryKey: [
      ...TOPIC_REPORTS_QUERY_KEY,
      'reading',
      report.id,
      report.revision,
    ],
    queryFn: ({ signal }) => loadReadingContent(report, signal),
    enabled: report.status === 'completed' && report.root_section_id !== null,
    retry: false,
  })
  if (report.status !== 'completed')
    return <p role="status">报告尚未生成完成，请返回报告列表查看进度。</p>
  if (report.root_section_id === null)
    return <p role="alert">报告正文缺失，请返回报告列表检查。</p>
  if (content.isPending) return <p role="status">正在读取报告正文…</p>
  if (content.isError)
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <p>暂时无法完整读取报告正文及原文链接，请重试。</p>
        <Button variant="outline" onClick={() => void content.refetch()}>
          重试读取报告
        </Button>
      </div>
    )
  return (
    <article
      aria-label="报告正文"
      className="flex flex-col gap-8 text-base leading-8 wrap-anywhere"
    >
      <section className="flex flex-col gap-3">
        <h3 className="text-lg font-semibold">摘要</h3>
        <p className="whitespace-pre-wrap">{content.data.overview}</p>
      </section>
      <section className="flex flex-col gap-6">
        <h3 className="text-lg font-semibold">分析</h3>
        {groupReadingParagraphs(content.data.paragraphs).map(
          ({ texts, groups }, index) => {
            return (
              <div key={index} className="flex flex-col gap-2">
                {texts.map((text, position) => (
                  <p key={position} className="whitespace-pre-wrap">
                    {text}
                  </p>
                ))}
                <div className="flex flex-wrap gap-x-5 gap-y-1">
                  {groups.map(({ source, count, sources }, position) => (
                    <div
                      key={source.result_id}
                      className="inline-flex flex-wrap items-start gap-2"
                    >
                      <a
                        key={source.result_id}
                        href={source.content_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={source.title}
                        aria-label={`查看原文：${source.title}（新标签页）`}
                        className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4 hover:decoration-2 focus-visible:outline-2 focus-visible:outline-offset-4"
                      >
                        {groups.length === 1
                          ? '查看原文'
                          : `原文 ${position + 1}`}
                      </a>
                      {count > 1 && (
                        <details className="text-sm text-muted-foreground">
                          <summary className="flex min-h-11 cursor-pointer items-center rounded-sm underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4">
                            另有 {count - 1} 条同文发布
                          </summary>
                          <ul className="flex flex-col gap-1">
                            {sources.slice(1).map((other, i) => (
                              <li key={other.content_url}>
                                <a
                                  href={other.content_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex min-h-11 items-center underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4"
                                  aria-label={`查看同文发布 ${i + 1}：${other.title}（新标签页）`}
                                >
                                  {other.published_at_text ||
                                    `同文发布 ${i + 1}`}
                                </a>
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          },
        )}
      </section>
      <ReportMaterialNote key={report.id} report={report} />
    </article>
  )
}
