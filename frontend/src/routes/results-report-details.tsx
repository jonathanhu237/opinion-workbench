import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  fetchReportSection,
  fetchReportSections,
  fetchReportSources,
  isActiveReport,
  REPORT_PAGE_SIZE,
  REPORT_SECTION_PAGE_SIZE,
  reportErrorMessage,
  TOPIC_REPORTS_QUERY_KEY,
  type ReportRun,
  type ReportSection,
  type ReportSource,
} from '@/lib/api/topic-reports'
import {
  analysisUsageMessage,
  formatEvidenceDate,
  ResultsPagination,
  ResultSourceLink,
  useResultSourceControls,
  type ResultSourceControls,
} from '@/routes/results-presenters'

export const reportStatusLabels: Record<ReportRun['status'], string> = {
  queued: '等待生成',
  judging: '正在判断相关性',
  composing: '正在生成报告',
  completed: '已生成',
  empty: '没有相关材料',
  failed: '生成失败',
  cancelled: '报告已取消',
  interrupted: '报告已中断',
  configuration_blocked: '模型设置不可用',
}
const sourceLabels: Record<ReportSource['state'], string> = {
  unavailable: '没有可用的初步分析',
  pending: '待判断',
  judging: '正在判断',
  relevant: '相关',
  irrelevant: '不相关',
  uncertain: '相关性不确定',
  failed: '相关性判断失败',
  cancelled: '相关性判断已取消',
  interrupted: '相关性判断已中断',
}
const unavailableLabels: Record<
  NonNullable<ReportSource['unavailable_reason']>,
  string
> = {
  not_analysed: '当时还没有初步分析',
  legacy_only: '当时只有旧版分析',
  in_progress: '当时仍在分析',
  input_incomplete: '初步分析输入不完整',
  unsupported: '初步分析输入不支持',
  failed: '初步分析失败',
  cancelled: '初步分析已取消',
  interrupted: '初步分析已中断',
  stale_evidence: '没有可用的匹配分析结果',
}
const evidenceLevelLabels = {
  search_preview: '搜索摘要',
  detail_text: '详情文字',
  validated_media: '已确认媒体',
  full_source: '完整内容',
} as const
const sectionLabels: Record<ReportSection['status'], string> = {
  queued: '等待生成',
  running: '正在生成',
  completed: '已生成',
  failed: '生成失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

function ReadError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div role="alert" className="space-y-2 text-sm">
      <p className="text-destructive">{reportErrorMessage(error)}</p>
      <Button variant="outline" onClick={retry}>
        重试读取报告
      </Button>
    </div>
  )
}
export function ReportCoverage({ report }: { report: ReportRun }) {
  const { coverage, nodes, usage } = report
  const judged = coverage.ready - coverage.pending - coverage.judging
  return (
    <div className="space-y-3">
      <div role="status" aria-live="polite" className="space-y-2">
        <p className="font-medium">报告：{reportStatusLabels[report.status]}</p>
        <p className="text-sm">
          本次内容 {coverage.total} 条 · 可判断 {coverage.ready} 条 · 无法判断{' '}
          {coverage.unavailable} 条
        </p>
        <p className="text-sm text-muted-foreground">
          相关性判断：已处理 {judged}/{coverage.ready} 条；相关{' '}
          {coverage.relevant} · 不相关 {coverage.irrelevant} · 不确定{' '}
          {coverage.uncertain} · 技术失败 {coverage.failed} · 取消{' '}
          {coverage.cancelled} · 中断 {coverage.interrupted}
        </p>
        {coverage.ready > 0 && (
          <progress
            aria-label="报告相关性判断已处理条数"
            value={judged}
            max={coverage.ready}
            className="h-2 w-full accent-primary"
          />
        )}
        <p className="text-sm text-muted-foreground">
          报告内容：已生成 {nodes.composition.completed}/
          {nodes.composition.total} 个章节。
        </p>
      </div>
      {report.empty_reason && (
        <p className="rounded-lg bg-muted p-3 text-sm leading-6">
          {report.empty_reason === 'no_ready_sources'
            ? '本次没有可用的初步分析，因此没有调用模型。原始内容和失败原因仍保留。'
            : '相关性判断没有找到足够相关的内容，因此没有生成报告。不相关和不确定的内容仍保留。'}
        </p>
      )}
      {report.queue_reason && (
        <p className="text-sm text-muted-foreground">
          正在等待其他 AI 操作结束。
        </p>
      )}
      {report.status === 'configuration_blocked' && (
        <p className="text-sm text-warning-foreground">
          当前模型设置不可用，系统没有切换其他服务。请检查设置后重试。
        </p>
      )}
      {report.recovery_reason && (
        <p className="text-sm text-warning-foreground">
          报告因服务重启中断。系统不会自动重复可能收费的请求，请手动重试。
        </p>
      )}
      {report.error && (
        <p role="alert" className="text-sm text-destructive">
          {report.error.message} 已完成的分析和章节仍保留。
        </p>
      )}
      <details className="rounded-lg border p-3">
        <summary className="min-h-8 cursor-pointer text-sm font-medium">
          本次报告用量
        </summary>
        <dl className="mt-2 space-y-2 text-sm">
          <div>
            <dt>相关性判断</dt>
            <dd className="text-muted-foreground">
              {analysisUsageMessage(usage.judgment)}
            </dd>
          </div>
          <div>
            <dt>报告生成</dt>
            <dd className="text-muted-foreground">
              {analysisUsageMessage(usage.composition)}
            </dd>
          </div>
          <div>
            <dt>本报告合计</dt>
            <dd className="text-muted-foreground">
              {analysisUsageMessage(usage.total)}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-sm text-muted-foreground">
          {nodes.judgments.reused} 条相关性判断、{nodes.composition.reused}{' '}
          个报告章节沿用了已有结果；历史用量不计入本次。初步分析用量单独显示，未知用量不会按
          0 计算。
        </p>
      </details>
      <details className="rounded-lg border p-3">
        <summary className="min-h-8 cursor-pointer text-sm font-medium">
          本报告使用的提示词与模型
        </summary>
        <p className="mt-2 text-sm">
          {report.prompt.origin === 'override'
            ? '本次专用提示词（未更改默认）'
            : `默认报告提示词 · 版本 ${report.prompt.version_id}`}
        </p>
        <p className="mt-2 text-sm leading-6 wrap-anywhere whitespace-pre-wrap">
          {report.prompt.instructions}
        </p>
        <p className="mt-3 text-xs wrap-anywhere text-muted-foreground">
          {report.model} · {report.base_url}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          每条初步分析使用的提示词可在下方查看。之后修改的提示词或来源不会改变这份报告。
        </p>
      </details>
    </div>
  )
}

function SectionContent({
  section,
  draft,
  controls,
  onSection,
}: {
  section: ReportSection
  draft: boolean
  controls: ResultSourceControls
  onSection: (id: number) => void
}) {
  const document = section.document ?? section.overview_document
  return (
    <article
      className="min-w-0 space-y-3 rounded-lg border p-4"
      aria-label={`报告章节 ${section.id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="font-medium">
          {section.kind === 'leaf'
            ? `详细章节 ${section.position + 1}`
            : `总览 · 层级 ${section.level}`}{' '}
          · #{section.id}
        </h4>
        <Badge variant="outline">{sectionLabels[section.status]}</Badge>
        {draft && <Badge variant="outline">部分草稿</Badge>}
      </div>
      <p className="text-xs text-muted-foreground">
        引用 {section.source_count} 条相关来源
        {section.reused_from_node_id !== null
          ? ' · 沿用已有章节，不重复计入用量'
          : ''}
      </p>
      {document && (
        <p className="max-w-prose text-sm leading-7 wrap-anywhere whitespace-pre-wrap">
          {document.overview}
        </p>
      )}
      {section.document?.items.map((paragraph, index) => (
        <p
          key={index}
          className="max-w-prose text-sm leading-7 wrap-anywhere whitespace-pre-wrap"
        >
          {paragraph.text}
          {paragraph.source_ids.map((id) => {
            const citation = section.sources.find(
              (item) => item.source.result_id === id,
            )
            return citation ? (
              <span key={id} className="ml-2 inline">
                <ResultSourceLink
                  source={citation.source}
                  controls={controls}
                  citationNumber={citation.position + 1}
                />
              </span>
            ) : null
          })}
        </p>
      ))}
      {section.overview_document?.items.map((paragraph, index) => (
        <div key={index} className="space-y-1">
          <p className="max-w-prose text-sm leading-7 wrap-anywhere whitespace-pre-wrap">
            {paragraph.text}
          </p>
          <div className="flex flex-wrap gap-2">
            {paragraph.section_ids.map((id) => (
              <Button
                key={id}
                variant="link"
                className="min-h-8 px-0 underline"
                onClick={() => onSection(id)}
              >
                查看引用章节 #{id}
              </Button>
            ))}
          </div>
        </div>
      ))}
      {section.children.length > 0 && (
        <details>
          <summary className="min-h-8 cursor-pointer text-sm font-medium">
            全部下级章节（保留详细证据）
          </summary>
          <ul className="mt-2 space-y-2">
            {section.children.map((child) => (
              <li key={child.id}>
                <Button
                  variant="link"
                  className="h-auto min-h-8 px-0 text-left wrap-anywhere whitespace-normal"
                  onClick={() => onSection(child.id)}
                >
                  章节 #{child.id} · {child.source_count} 条来源 ·{' '}
                  {child.overview}
                </Button>
              </li>
            ))}
          </ul>
        </details>
      )}
      {section.error && (
        <p role="alert" className="text-sm text-destructive">
          {section.error.message}
        </p>
      )}
      {!document && (
        <p className="text-sm text-muted-foreground">
          本章节暂时没有可显示的文字；相关来源仍保留。
        </p>
      )}
    </article>
  )
}
export function ReportDetails({
  report,
  sourceOffset,
  sectionOffset,
  sectionId,
  onSourcePage,
  onSectionPage,
  onSection,
}: {
  report: ReportRun
  sourceOffset: number
  sectionOffset: number
  sectionId: number | null
  onSourcePage: (offset: number) => void
  onSectionPage: (offset: number) => void
  onSection: (id: number | null) => void
}) {
  const active = isActiveReport(report.status)
  const controls = useResultSourceControls()
  const sources = useQuery({
    queryKey: [...TOPIC_REPORTS_QUERY_KEY, 'sources', report.id, sourceOffset],
    queryFn: ({ signal }) =>
      fetchReportSources(report.id, signal, sourceOffset),
    retry: false,
    refetchInterval: active ? 1000 : false,
  })
  const leaves = useQuery({
    queryKey: [
      ...TOPIC_REPORTS_QUERY_KEY,
      'sections',
      report.id,
      'leaf',
      sectionOffset,
    ],
    queryFn: ({ signal }) =>
      fetchReportSections(report.id, signal, sectionOffset, 'leaf'),
    retry: false,
    refetchInterval: active ? 1000 : false,
  })
  const viewedSectionId = sectionId ?? report.root_section_id
  const selectedSection = useQuery({
    queryKey: [
      ...TOPIC_REPORTS_QUERY_KEY,
      'section',
      report.id,
      viewedSectionId,
    ],
    queryFn: ({ signal }) =>
      fetchReportSection(report.id, viewedSectionId ?? 0, signal),
    enabled: viewedSectionId !== null,
    retry: false,
    refetchInterval: active ? 1000 : false,
  })
  const draft = report.status !== 'completed'
  return (
    <div className="space-y-5">
      {draft && report.nodes.composition.completed > 0 && (
        <p className="text-sm text-warning-foreground">
          以下是已保存的部分草稿，不是完整成功报告；初步文本与引用继续可查。
        </p>
      )}
      {viewedSectionId !== null && (
        <section aria-label="所选报告章节" className="space-y-3">
          {sectionId !== null && (
            <Button variant="outline" onClick={() => onSection(null)}>
              返回报告总览
            </Button>
          )}
          {selectedSection.isPending ? (
            <p role="status">正在读取报告章节…</p>
          ) : selectedSection.isError ? (
            <ReadError
              error={selectedSection.error}
              retry={() => void selectedSection.refetch()}
            />
          ) : sectionId !== null || selectedSection.data.kind === 'overview' ? (
            <SectionContent
              section={selectedSection.data}
              draft={draft}
              controls={controls}
              onSection={onSection}
            />
          ) : null}
        </section>
      )}
      <section aria-labelledby="report-leaves-heading" className="space-y-3">
        <h4 id="report-leaves-heading" className="font-medium">
          全部详细章节
        </h4>
        {leaves.isPending ? (
          <p role="status">正在读取详细章节…</p>
        ) : leaves.isError ? (
          <ReadError error={leaves.error} retry={() => void leaves.refetch()} />
        ) : (
          <>
            {leaves.data.sections.length === 0 && (
              <p className="text-sm text-muted-foreground">
                暂时没有详细章节。
              </p>
            )}
            {leaves.data.sections.map((section) => (
              <SectionContent
                key={section.id}
                section={section}
                draft={draft}
                controls={controls}
                onSection={onSection}
              />
            ))}
            <ResultsPagination
              label="报告详细章节"
              offset={sectionOffset}
              limit={REPORT_SECTION_PAGE_SIZE}
              total={leaves.data.total}
              onChange={onSectionPage}
            />
          </>
        )}
      </section>
      <details className="rounded-lg border p-3" open>
        <summary className="min-h-8 cursor-pointer font-medium">
          报告来源与相关性
        </summary>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          这是首次发现时间范围和当时的证据，不是事件发生日期。没有可用分析的内容不会自动重做；重试会继续使用本次报告的内容。
        </p>
        {sources.isPending ? (
          <p role="status">正在读取报告来源…</p>
        ) : sources.isError ? (
          <ReadError
            error={sources.error}
            retry={() => void sources.refetch()}
          />
        ) : (
          <>
            <ul className="divide-y">
              {sources.data.items.map((item) => (
                <li
                  key={item.source.result_id}
                  className="min-w-0 space-y-2 py-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <h5 className="text-sm font-medium wrap-anywhere">
                      原文 {item.position + 1} · {item.source.title}
                    </h5>
                    <Badge variant="outline">{sourceLabels[item.state]}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    首次发现 {formatEvidenceDate(item.first_seen_at)} ·
                    原文发布时间 {item.source.published_at_text || '未知'}
                  </p>
                  {item.evidence_coverage && (
                    <p className="text-xs text-muted-foreground">
                      内容：{evidenceLevelLabels[item.evidence_coverage.level]}{' '}
                      · 文字
                      {item.evidence_coverage.text_complete ? '完整' : '部分'} ·
                      图片 {item.evidence_coverage.image.ready}/
                      {item.evidence_coverage.image.expected} · 视频{' '}
                      {item.evidence_coverage.video.ready}/
                      {item.evidence_coverage.video.expected}
                      {item.evidence_coverage.image.unknown +
                        item.evidence_coverage.video.unknown +
                        item.evidence_coverage.audio.unknown >
                      0
                        ? ' · 部分媒体尚未确认'
                        : ''}
                    </p>
                  )}
                  {item.judgment && (
                    <p className="text-sm leading-6 wrap-anywhere whitespace-pre-wrap">
                      {item.judgment.reason}
                    </p>
                  )}
                  {item.unavailable_reason && (
                    <p className="text-sm text-muted-foreground">
                      {unavailableLabels[item.unavailable_reason]}
                      ；因此没有判断为相关或不相关。
                    </p>
                  )}
                  {item.error && (
                    <p className="text-sm text-destructive">
                      {item.error.message}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-3">
                    <ResultSourceLink
                      source={item.source}
                      controls={controls}
                    />
                    <Link
                      className={buttonVariants({
                        variant: 'link',
                        className: 'min-h-11',
                      })}
                      to={`/results?result=${item.source.result_id}${item.initial_attempt_id === null ? '' : `&attempt=${item.initial_attempt_id}`}&report=${report.id}`}
                      preventScrollReset
                    >
                      {item.initial_attempt_id === null
                        ? '查看内容和历史'
                        : '查看本次初步分析'}
                    </Link>
                    <Link
                      className={buttonVariants({
                        variant: 'link',
                        className: 'min-h-11',
                      })}
                      to={`/collection-runs/${item.source.source_run_id}`}
                    >
                      查看采集记录 #{item.source.source_run_id}
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
            <ResultsPagination
              label="报告来源"
              offset={sourceOffset}
              limit={REPORT_PAGE_SIZE}
              total={sources.data.total}
              onChange={onSourcePage}
            />
          </>
        )}
      </details>
    </div>
  )
}
