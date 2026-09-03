import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { useTopicReport, useTopicReports } from '@/hooks/use-topic-reports'
import type { AISettings } from '@/lib/api/ai-settings'
import type { AnalysisSettings } from '@/lib/api/analysis-settings'
import {
  isActiveAnalysisJob,
  type AnalysisJob,
} from '@/lib/api/content-analyses'
import { readId, readOffset } from '@/lib/api/results'
import {
  isActiveReport,
  reportErrorMessage,
  TOPIC_REPORTS_QUERY_KEY,
  type ReportRun,
} from '@/lib/api/topic-reports'
import { ReportActions } from '@/routes/results-report-actions'
import {
  ReportCoverage,
  ReportDetails,
  reportStatusLabels,
} from '@/routes/results-report-details'
import { formatEvidenceDate } from '@/routes/results-presenters'

export const REPORT_URL_KEYS = [
  'report',
  'report_section',
  'report_sources_offset',
  'report_sections_offset',
  'reports_before',
] as const

export function ResultsReports({
  job,
  settings,
  provider,
}: {
  job?: AnalysisJob
  settings?: AnalysisSettings
  provider?: AISettings
}) {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const heading = useRef<HTMLHeadingElement>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const beforeId = readId(params.get('reports_before'))
  const history = useTopicReports(beforeId === null ? {} : { beforeId })
  const automatic = useTopicReports(
    job ? { initialJobId: job.id } : {},
    job?.status === 'completed',
    job?.status === 'completed',
  )
  const selectedId =
    readId(params.get('report')) ??
    automatic.data?.reports[0]?.id ??
    (job ? null : (history.data?.reports[0]?.id ?? null))
  const selected = useTopicReport(selectedId)
  const report = selected.data
  const sourceOffset = readOffset(params.get('report_sources_offset'))
  const sectionOffset = readOffset(params.get('report_sections_offset'))
  const sectionId = readId(params.get('report_section'))
  const invalidLink = REPORT_URL_KEYS.some(
    (key) =>
      params.has(key) &&
      (key.endsWith('_offset')
        ? !/^(?:0|[1-9]\d*)$/u.test(params.get(key) ?? '') ||
          !Number.isSafeInteger(Number(params.get(key)))
        : readId(params.get(key)) === null),
  )
  const requestedReport = readId(params.get('report'))
  useEffect(() => {
    if (requestedReport !== null)
      heading.current?.focus({ preventScroll: true })
  }, [requestedReport])
  const previousReport = useRef<{ id: number; active: boolean } | null>(null)
  useEffect(() => {
    if (!report) return
    const active = isActiveReport(report.status)
    if (
      previousReport.current?.id === report.id &&
      previousReport.current.active &&
      !active
    ) {
      void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
    }
    previousReport.current = { id: report.id, active }
  }, [client, report])
  function change(values: Record<string, number | null>) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(values)) {
        if (value === null || value === 0) next.delete(key)
        else next.set(key, String(value))
      }
      return next
    })
  }
  function select(id: number | null) {
    change({
      report: id,
      report_section: null,
      report_sources_offset: null,
      report_sections_offset: null,
    })
  }
  function saved(value: ReportRun) {
    select(value.id)
    setFeedback(
      value.status === 'cancelled'
        ? '报告已取消，初步文本和已有章节仍保留。'
        : '报告请求已提交，只使用本次已有的文字，不会重新采集或分析。',
    )
  }
  return (
    <Card aria-labelledby="results-report-heading">
      <CardHeader className="border-b">
        <h2
          id="results-report-heading"
          ref={heading}
          tabIndex={-1}
          className="font-display text-xl"
        >
          报告
        </h2>
        <p className="text-sm leading-6 text-muted-foreground">
          这里保留历史报告和独立重试版本。新的手动分析请在内容库选材；下方按时间范围生成仅用于已有文字结果。
        </p>
      </CardHeader>
      <CardContent className="space-y-5 pt-5">
        {feedback && (
          <p role="status" className="text-sm">
            {feedback}
          </p>
        )}
        {job && (
          <section
            className="space-y-2 rounded-lg bg-secondary/45 p-3"
            aria-label={`任务 ${job.id} 的报告`}
          >
            <p className="text-sm font-medium">初步分析任务 #{job.id} 的报告</p>
            {isActiveAnalysisJob(job.status) ? (
              <p role="status" className="text-sm">
                初步分析仍在进行；本次手动任务不会自动提交报告。
              </p>
            ) : job.status !== 'completed' ? (
              <p className="text-sm">
                本任务未正常完成；已保存的初步文本仍可查看。
              </p>
            ) : automatic.isError ? (
              <div role="alert" className="space-y-2">
                <p className="text-sm text-destructive">
                  {reportErrorMessage(automatic.error)}
                </p>
                <Button
                  variant="outline"
                  onClick={() => void automatic.refetch()}
                >
                  重试读取报告
                </Button>
              </div>
            ) : automatic.isPending ? (
              <p role="status" className="text-sm">
                正在读取本任务的报告…
              </p>
            ) : automatic.data?.reports.length === 0 ? (
              <p className="text-sm">
                此历史单条处理任务没有关联报告，可以在内容库重新选材。
              </p>
            ) : (
              <div className="space-y-2">
                <p className="text-sm">
                  已完成 {job.counts.completed}/{job.counts.total}{' '}
                  条初步分析；失败内容保留原因，不会自动重试。
                </p>
                <Button
                  variant="link"
                  className="h-auto min-h-8 px-0 underline"
                  onClick={() => select(automatic.data.reports[0].id)}
                >
                  查看本任务报告 #{automatic.data.reports[0].id}
                  {automatic.data.reports[0].trigger === 'retry'
                    ? '（最新重试版本）'
                    : ''}
                </Button>
              </div>
            )}
          </section>
        )}
        <ReportActions
          report={report}
          provider={provider}
          settings={settings}
          onSaved={saved}
        />
        <p className="text-xs text-muted-foreground">
          按时间范围或改提示词生成报告，都需要单独提交；不会重新采集或初步分析。
        </p>
        {invalidLink && (
          <div role="alert" className="space-y-2">
            <p className="text-sm text-destructive">
              报告链接中的编号或分页位置无效。
            </p>
            <Button
              variant="outline"
              onClick={() =>
                change(
                  Object.fromEntries(REPORT_URL_KEYS.map((key) => [key, null])),
                )
              }
            >
              重置报告视图
            </Button>
          </div>
        )}
        <details className="rounded-lg border p-3">
          <summary className="min-h-8 cursor-pointer font-medium">
            报告历史与独立版本
          </summary>
          {history.isPending ? (
            <p role="status">正在读取报告历史…</p>
          ) : history.isError ? (
            <div role="alert" className="space-y-2">
              <p className="text-sm text-destructive">
                {reportErrorMessage(history.error)}
              </p>
              <Button variant="outline" onClick={() => void history.refetch()}>
                重试读取报告历史
              </Button>
            </div>
          ) : (
            <>
              {history.data.reports.length === 0 && (
                <p className="mt-3 text-sm text-muted-foreground">
                  还没有文字报告。
                </p>
              )}
              <ul className="mt-2 divide-y">
                {history.data.reports.map((item) => (
                  <li key={item.id}>
                    <Button
                      className="my-1 h-auto min-h-11 w-full justify-start text-left wrap-anywhere whitespace-normal"
                      variant={item.id === selectedId ? 'secondary' : 'ghost'}
                      aria-pressed={item.id === selectedId}
                      onClick={() => select(item.id)}
                    >
                      报告 #{item.id} · {reportStatusLabels[item.status]} ·{' '}
                      {item.trigger === 'automatic'
                        ? '任务自动报告'
                        : item.trigger === 'retry'
                          ? `源自报告 #${item.parent_report_id}`
                          : '首次发现时间范围'}{' '}
                      · {formatEvidenceDate(item.created_at)}
                    </Button>
                  </li>
                ))}
              </ul>
              {(beforeId !== null || history.data.next_before_id !== null) && (
                <nav
                  className="mt-3 flex flex-wrap gap-2"
                  aria-label="报告历史分页"
                >
                  <Button
                    variant="outline"
                    disabled={beforeId === null || history.isFetching}
                    onClick={() => change({ reports_before: null })}
                  >
                    最新报告
                  </Button>
                  <Button
                    variant="outline"
                    disabled={
                      history.data.next_before_id === null || history.isFetching
                    }
                    onClick={() =>
                      change({ reports_before: history.data.next_before_id })
                    }
                  >
                    更早报告
                  </Button>
                </nav>
              )}
            </>
          )}
        </details>
        {history.data?.reports.some(
          (item) => item.id !== selectedId && isActiveReport(item.status),
        ) && (
          <div
            className="flex flex-wrap gap-2"
            aria-label="其他正在处理的文字报告"
          >
            {history.data.reports
              .filter(
                (item) => item.id !== selectedId && isActiveReport(item.status),
              )
              .map((item) => (
                <Button
                  key={item.id}
                  variant="outline"
                  onClick={() => select(item.id)}
                >
                  查看并取消报告 #{item.id} · {reportStatusLabels[item.status]}
                </Button>
              ))}
          </div>
        )}
        {selectedId !== null && selected.isPending && (
          <p role="status">正在读取文字报告…</p>
        )}
        {selected.isError && (
          <div role="alert" className="space-y-2">
            <p className="text-sm text-destructive">
              {reportErrorMessage(selected.error)}
            </p>
            <Button variant="outline" onClick={() => void selected.refetch()}>
              重试读取所选报告
            </Button>
          </div>
        )}
        {report && (
          <section className="space-y-5" aria-label={`文字报告 ${report.id}`}>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-display text-xl">文字报告 #{report.id}</h3>
              <Badge variant="outline">
                {reportStatusLabels[report.status]}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {report.selection.kind === 'initial_job'
                ? `来自初步分析任务 #${report.selection.job_id}`
                : report.selection.kind === 'workflow_run'
                  ? `来自自动任务 #${report.selection.run_id}，使用当时的任务目标`
                  : report.selection.kind === 'explicit'
                    ? `手动选材：${report.selection.result_ids.length} 条；未选中的历史总结不会加入`
                    : `首次发现时间：${formatEvidenceDate(report.selection.first_seen_from)}（含）至 ${formatEvidenceDate(report.selection.first_seen_to)}（不含），北京时间`}
              {report.parent_report_id !== null
                ? ` · 基于报告 #${report.parent_report_id} 的新版本`
                : ''}
            </p>
            {report.initial_job_id !== null &&
              report.initial_job_id !== job?.id && (
                <Link
                  to={`?job=${report.initial_job_id}&report=${report.id}`}
                  className={buttonVariants({
                    variant: 'link',
                    className: 'min-h-11 px-0',
                  })}
                >
                  查看本报告的初步分析任务
                </Link>
              )}
            <ReportCoverage report={report} />
            <ReportDetails
              report={report}
              sourceOffset={sourceOffset}
              sectionOffset={sectionOffset}
              sectionId={sectionId}
              onSourcePage={(offset) =>
                change({ report_sources_offset: offset })
              }
              onSectionPage={(offset) =>
                change({ report_sections_offset: offset })
              }
              onSection={(id) => change({ report_section: id })}
            />
          </section>
        )}
        {!job && selectedId === null && history.isSuccess && (
          <p className="text-sm text-muted-foreground">
            自动任务的报告会显示在这里。也可以按时间范围，用已有分析结果生成报告；不会自动重做初步分析。
          </p>
        )}
      </CardContent>
    </Card>
  )
}
