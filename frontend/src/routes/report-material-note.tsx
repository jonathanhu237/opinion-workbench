import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  fetchReportSources,
  TOPIC_REPORTS_QUERY_KEY,
  type ReportRun,
  type ReportSource,
} from '@/lib/api/topic-reports'
import {
  searchPlatformPresenters,
  searchRunStatusLabel,
} from '@/routes/search-run-presenters'

const stateLabels: Record<ReportSource['state'], string> = {
  relevant: '相关',
  irrelevant: '无关',
  uncertain: '待确认',
  unavailable: '材料不足',
  pending: '尚未判断',
  judging: '尚未完成判断',
  failed: '判断失败',
  cancelled: '判断已取消',
  interrupted: '判断已中断',
}

const unavailableReasons: Record<
  NonNullable<ReportSource['unavailable_reason']>,
  string
> = {
  not_analysed: '生成报告时还没有单条总结。',
  legacy_only: '生成报告时只有旧版总结，无法用于本次判断。',
  in_progress: '生成报告时单条总结尚未完成。',
  input_incomplete: '单条总结的原始材料不完整。',
  unsupported: '单条总结的原始材料格式不受支持。',
  failed: '单条总结生成失败。',
  cancelled: '单条总结已取消。',
  interrupted: '单条总结已中断。',
  stale_evidence: '没有与本次材料匹配的可用总结。',
}

function materialSummary(coverage: ReportRun['coverage']) {
  const remaining = coverage.total - coverage.relevant
  if (remaining === 0) return `本次共 ${coverage.total} 条材料，均判相关。`
  const incomplete =
    coverage.pending +
    coverage.judging +
    coverage.failed +
    coverage.cancelled +
    coverage.interrupted
  const other = [
    coverage.irrelevant > 0 && `${coverage.irrelevant} 条判无关`,
    coverage.uncertain > 0 && `${coverage.uncertain} 条待确认`,
    coverage.unavailable > 0 && `${coverage.unavailable} 条材料不足`,
    incomplete > 0 && `${incomplete} 条未完成判断`,
  ].filter(Boolean)
  return `本次共 ${coverage.total} 条材料，${coverage.relevant} 条判相关；其余 ${remaining} 条中，${other.join('、')}。`
}

function materialReason(item: ReportSource) {
  const reason =
    item.judgment?.reason ??
    item.error?.message ??
    (item.unavailable_reason
      ? unavailableReasons[item.unavailable_reason]
      : '本次未保存可用的判断理由。')
  if (
    item.unavailable_reason === 'input_incomplete' ||
    item.unavailable_reason === 'unsupported'
  ) {
    return `${reason} 无法通过文字判断是否和舆情有关。`
  }
  return reason
}

async function loadRemainingMaterials(report: ReportRun, signal: AbortSignal) {
  const sources: ReportSource[] = []
  for (let offset = 0; offset < report.coverage.total; offset += 100) {
    const page = await fetchReportSources(report.id, signal, offset, 100)
    if (
      page.total !== report.coverage.total ||
      page.total > 10000 ||
      page.items.length !== Math.min(100, page.total - offset)
    )
      throw new Error('Incomplete report materials')
    sources.push(...page.items)
  }
  if (
    new Set(sources.map((item) => item.source.result_id)).size !==
    sources.length
  )
    throw new Error('Duplicate report materials')
  for (const state of Object.keys(stateLabels) as ReportSource['state'][]) {
    if (
      sources.filter((item) => item.state === state).length !==
      report.coverage[state]
    )
      throw new Error('Inconsistent report material counts')
  }
  return sources.filter((item) => item.state !== 'relevant')
}

export function CollectionGapNote({ report }: { report: ReportRun }) {
  if (report.collection_gaps.length === 0) return null
  return (
    <div className="rounded-lg border border-amber-300/70 bg-amber-50/60 p-3 dark:border-amber-700/70 dark:bg-amber-950/20">
      <p className="font-medium">采集缺口</p>
      <p className="mt-1">
        以下平台采集项没有形成可用结果，本报告只基于已取得并选中的内容：
      </p>
      <ul className="mt-1 list-disc pl-5">
        {report.collection_gaps.map((gap) => {
          const platform = searchPlatformPresenters[gap.platform].label
          const reason = gap.run_status
            ? searchRunStatusLabel(gap.run_status, gap.failure_reason)
            : gap.status === 'skipped'
              ? '已跳过'
              : gap.status === 'cancelled'
                ? '已取消'
                : '采集失败'
          return <li key={`${gap.position}-${gap.platform}`}>{platform}：{reason}</li>
        })}
      </ul>
    </div>
  )
}

export function ReportMaterialNote({ report }: { report: ReportRun }) {
  const [open, setOpen] = useState(false)
  const remaining = report.coverage.total - report.coverage.relevant
  const materials = useQuery({
    queryKey: [
      ...TOPIC_REPORTS_QUERY_KEY,
      'material-note',
      report.id,
      report.revision,
    ],
    queryFn: ({ signal }) => loadRemainingMaterials(report, signal),
    enabled: open && remaining > 0,
    retry: false,
  })

  return (
    <section
      aria-label="材料筛选说明"
      className="flex flex-col gap-2 text-sm leading-7"
    >
      <h3 className="font-semibold">材料筛选说明</h3>
      <CollectionGapNote report={report} />
      <p>{materialSummary(report.coverage)}</p>
      {report.empty_reason === 'text_insufficient' && (
        <p className="rounded-lg bg-muted p-3">
          文字信息不足，无法通过文字判断是否和舆情有关。请打开下方原文链接人工核查。
        </p>
      )}
      <p className="text-muted-foreground">
        以上为生成报告时保存的模型判断，仅供复核。
        {report.coverage.uncertain > 0 && '待确认不等于无关。'}
      </p>
      {remaining > 0 && (
        <details onToggle={(event) => setOpen(event.currentTarget.open)}>
          <summary className="min-h-11 cursor-pointer rounded-sm py-2 text-primary underline underline-offset-4 hover:decoration-2 focus-visible:outline-2 focus-visible:outline-offset-4">
            查看未纳入正文的 {remaining} 条材料及原因
          </summary>
          {open && materials.isPending && (
            <p role="status">正在读取材料及原因…</p>
          )}
          {open && materials.isError && (
            <div className="flex flex-col items-start gap-2">
              <p role="alert">暂时无法完整读取材料及原因，报告正文不受影响。</p>
              <Button
                variant="outline"
                onClick={() => void materials.refetch()}
              >
                重试读取材料
              </Button>
            </div>
          )}
          {open && materials.isSuccess && (
            <Table aria-label="未纳入正文的材料及原因" className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead scope="col" className="w-1/3">
                    材料
                  </TableHead>
                  <TableHead scope="col" className="w-24">
                    模型判断
                  </TableHead>
                  <TableHead scope="col">原因</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {materials.data.map((item) => (
                  <TableRow key={item.source.result_id}>
                    <TableCell className="align-top whitespace-normal">
                      <div className="flex flex-col gap-1">
                        <a
                          href={item.source.content_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`查看原文：${item.source.title}（新标签页）`}
                          className="inline-flex min-h-11 items-center rounded-sm text-primary underline underline-offset-4 hover:decoration-2 focus-visible:outline-2 focus-visible:outline-offset-4"
                        >
                          {item.source.title}
                        </a>
                        {item.source.snippet && (
                          <p className="text-xs leading-5 text-muted-foreground">
                            已有文案：{item.source.snippet}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="align-top whitespace-normal">
                      {stateLabels[item.state]}
                    </TableCell>
                    <TableCell className="align-top whitespace-pre-wrap">
                      {materialReason(item)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </details>
      )}
    </section>
  )
}
