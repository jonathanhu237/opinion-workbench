import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { AI_SETTINGS_QUERY_KEY, fetchAISettings } from '@/lib/api/ai-settings'
import {
  AnalysisApiError,
  analysisErrorMessage,
} from '@/lib/api/analysis-shared'
import { fetchAnalysisJobItems } from '@/lib/api/content-analyses'
import {
  fetchReportGeneration,
  controlReportGeneration,
  fetchReportGenerations,
  GENERATIONS_QUERY_KEY,
  isActiveGeneration,
  type ReportGeneration,
} from '@/lib/api/report-generations'
import { ReportCoverage, ReportDetails } from '@/routes/results-report-details'
import {
  fetchTopicReport,
  fetchTopicReports,
  reportErrorMessage,
  retryTopicReport,
  isActiveReport,
  TOPIC_REPORTS_QUERY_KEY,
  type ReportRun,
} from '@/lib/api/topic-reports'
import { readId, readOffset } from '@/lib/api/results'
import {
  formatEvidenceDate,
  resultStateLabels,
  ResultsPagination,
} from '@/routes/results-presenters'

const labels = {
  summarising: '正在总结内容',
  paused_for_manual_action: '已暂停，等待人工处理',
  reporting: '正在生成报告',
  completed: '报告已完成',
  empty: '没有可生成报告的内容',
  failed: '报告生成失败',
  configuration_blocked: '模型配置需要处理',
  cancelled: '已取消',
  interrupted: '任务已中断',
}

function legacyReportLabel(report: ReportRun) {
  const kind =
    report.trigger === 'automatic'
      ? '自动报告'
      : report.trigger === 'retry'
        ? '报告重试'
        : '历史报告'
  return `报告 #${report.id} · ${kind} · ${reportStatusLabel(report.status)} · ${formatEvidenceDate(report.created_at)}`
}

function reportStatusLabel(status: ReportRun['status']) {
  return {
    queued: '等待生成',
    judging: '正在判断相关性',
    composing: '正在生成报告',
    completed: '已完成',
    empty: '无相关材料',
    failed: '生成失败',
    cancelled: '已取消',
    interrupted: '已中断',
    configuration_blocked: '配置阻塞',
  }[status]
}

export function LegacyReportRecord({ reportId }: { reportId: number }) {
  const [params, setParams] = useSearchParams()
  const sourceOffset = readOffset(params.get('report_sources_offset'))
  const sectionOffset = readOffset(params.get('report_sections_offset'))
  const sectionId = readId(params.get('report_section'))
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
  const report = useQuery({
    queryKey: [...TOPIC_REPORTS_QUERY_KEY, 'detail', reportId],
    queryFn: ({ signal }) => fetchTopicReport(reportId, signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveReport(query.state.data.status)
        ? 1000
        : false,
  })
  return (
    <Card aria-labelledby="legacy-report-record-heading">
      <CardHeader>
        <h2 id="legacy-report-record-heading" className="font-display text-xl">
          历史报告 #{reportId}
        </h2>
      </CardHeader>
      <CardContent className="space-y-5">
        {report.isPending && <p role="status">正在读取报告…</p>}
        {report.isError && (
          <p role="alert" className="text-sm text-destructive">
            {reportErrorMessage(report.error)}
          </p>
        )}
        {report.data && (
          <>
            <p className="text-sm text-muted-foreground">
              历史记录 ·{' '}
              {report.data.selection.kind === 'explicit'
                ? `选材 ${report.data.selection.result_ids.length} 条`
                : '按历史规则选材'}
            </p>
            <ReportCoverage report={report.data} />
            <ReportDetails
              report={report.data}
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
          </>
        )}
      </CardContent>
    </Card>
  )
}

function ManualRecovery({ value }: { value: ReportGeneration }) {
  const queryClient = useQueryClient()
  const control = useMutation({
    mutationFn: (action: 'manual-page' | 'continue') =>
      controlReportGeneration(value.id, value.control_revision, action),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY }),
  })
  return (
    <div className="rounded-lg border p-3 text-sm" role="status">
      <p>
        {value.pause_reason === 'login_required'
          ? '微博需要重新登录。'
          : value.pause_reason === 'platform_blocked_or_rate_limited'
            ? '微博提示限流，请等待并在专用浏览器确认状态。'
            : '微博需要完成安全验证。'}
        已保存的结果不会丢失，其他依赖浏览器的任务也会等待；已有正文的报告仍可处理。
      </p>
      <p className="mt-2">
        打开窗口、刷新页面或登录成功都不会自动继续；确认处理完成后，请点击“继续生成报告”。
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={control.isPending}
          onClick={() => control.mutate('manual-page')}
        >
          打开微博专用窗口
        </Button>
        <Button
          disabled={control.isPending}
          onClick={() => control.mutate('continue')}
        >
          继续生成报告
        </Button>
      </div>
      {control.isError && (
        <p className="mt-2" role="alert">
          {analysisErrorMessage(control.error)}
        </p>
      )}
    </div>
  )
}

function GenerationDetails({ value }: { value: ReportGeneration }) {
  const queryClient = useQueryClient()
  const provider = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    retry: false,
  })
  const cancel = useMutation({
    mutationFn: () =>
      controlReportGeneration(value.id, value.control_revision, 'cancel'),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY }),
  })
  const retryReport = useMutation({
    mutationFn: () => {
      if (!value.report) throw new Error('missing report')
      if (
        !provider.data?.has_api_key ||
        !provider.data.model ||
        !provider.data.base_url
      )
        throw new AnalysisApiError('ai_configuration_required')
      return retryTopicReport(value.report.id, {
        request_id: crypto.randomUUID(),
        expected_revision: value.report.revision,
        configuration_revision: provider.data.revision,
      })
    },
    retry: false,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY })
      void queryClient.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
    },
  })
  const [itemOffset, setItemOffset] = useState(0)
  const [sourceOffset, setSourceOffset] = useState(0)
  const [sectionOffset, setSectionOffset] = useState(0)
  const [sectionId, setSectionId] = useState<number | null>(null)
  const items = useQuery({
    queryKey: [
      ...GENERATIONS_QUERY_KEY,
      'items',
      value.analysis.id,
      itemOffset,
    ],
    queryFn: ({ signal }) =>
      fetchAnalysisJobItems(value.analysis.id, signal, itemOffset),
    retry: false,
    refetchInterval: isActiveGeneration(value.status) ? 1000 : false,
  })
  const counts = value.analysis.counts
  const failed =
    counts.failed +
    counts.input_incomplete +
    counts.unsupported +
    counts.cancelled +
    counts.interrupted
  const processing = counts.acquiring + counts.analysing
  const canRetryReport =
    value.report?.status === 'failed' ||
    value.report?.status === 'configuration_blocked'
  return (
    <div className="flex flex-col gap-4">
      <h3 className="font-medium" role="status">
        {value.status === 'summarising' &&
        (counts.queued > 0 || counts.acquiring > 0)
          ? '阶段 1/4 · 补全内容'
          : value.status === 'summarising'
            ? '阶段 2/4 · 生成单条总结'
            : value.status === 'reporting'
              ? '阶段 3/4 · 汇总报告'
              : value.status === 'completed' || value.status === 'empty'
                ? '阶段 4/4 · 完成'
                : labels[value.status]}
      </h3>
      <p className="text-sm text-muted-foreground">
        {value.name ?? `报告 #${value.id}`} · 选中 {counts.total}{' '}
        条。关闭或刷新页面不会重新提交。
      </p>
      {isActiveGeneration(value.status) && (
        <div className="flex flex-col items-start gap-2">
          <Button
            variant="outline"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            {cancel.isPending ? '正在停止并保留成果…' : '取消本次报告生成'}
          </Button>
          {cancel.isError && (
            <p role="alert" className="text-sm">
              {analysisErrorMessage(cancel.error)}
            </p>
          )}
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        选材方式：
        {value.selection_policy.kind === 'explicit'
          ? '手动勾选'
          : value.selection_policy.include_failed
            ? '全库待分析条目（含分析失败条目）'
            : '全库待分析条目（不含分析失败条目）'}
        ；以下是启动时的固定集合。
      </p>
      <progress
        aria-label="单条内容处理进度"
        className="h-2 w-full accent-primary"
        max={counts.total}
        value={counts.completed + failed}
      />
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        {[
          ['待处理', counts.queued],
          ['处理中', processing],
          ['本次新总结', counts.completed - counts.reused],
          ['复用总结', counts.reused],
          ['失败或中断', failed],
        ].map(([label, count]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="text-lg font-medium tabular-nums">{count}</dd>
          </div>
        ))}
      </dl>
      {value.status === 'summarising' && (
        <p className="text-sm">
          单条总结结束后，后台会继续生成本份报告，不需要再次点击。
        </p>
      )}
      {value.status === 'interrupted' && (
        <p className="text-sm">
          已完成的总结仍保留；系统不会自动重试可能收费的请求。
          可按下方原选材重新勾选并开始，成功总结会复用。
        </p>
      )}
      {value.status === 'cancelled' && (
        <p className="text-sm">
          本次已停止；已保存的正文和总结保留。需要重试时，可重新选中这些条目，已成功的总结会复用。
        </p>
      )}
      {value.status === 'paused_for_manual_action' && (
        <ManualRecovery value={value} />
      )}
      {value.status === 'configuration_blocked' && (
        <p className="text-sm">
          同一配置下的相关手动任务已停止，不会逐条重复失败请求。
          <Link className="underline underline-offset-4" to="/settings/ai">
            检查模型设置
          </Link>
        </p>
      )}
      <details className="rounded-lg border p-3">
        <summary className="min-h-8 cursor-pointer font-medium">
          本次选材与处理结果
        </summary>
        <div className="mt-3 flex flex-col gap-3">
          {items.isError ? (
            <p role="alert">
              {analysisErrorMessage(items.error)}{' '}
              <Button variant="outline" onClick={() => void items.refetch()}>
                重试读取条目
              </Button>
            </p>
          ) : items.isPending ? (
            <p role="status">正在读取条目…</p>
          ) : (
            <>
              {items.data.items.map((item) => (
                <div key={item.id} className="flex flex-col gap-1 text-sm">
                  <Link
                    className="underline underline-offset-4"
                    to={`/reports/history?generation=${value.id}&result=${item.source.result_id}&attempt=${item.id}`}
                  >
                    {item.source.title || `内容 #${item.source.result_id}`}
                  </Link>
                  <p>
                    {item.reused_from_attempt_id
                      ? '已复用总结'
                      : resultStateLabels[item.status]}
                    {item.error ? `：${item.error.message}` : ''}
                  </p>
                </div>
              ))}
              <ResultsPagination
                label="本次选材"
                offset={itemOffset}
                limit={20}
                total={items.data.total}
                onChange={setItemOffset}
              />
            </>
          )}
        </div>
      </details>
      {value.report && (
        <>
          {canRetryReport && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                disabled={
                  retryReport.isPending ||
                  provider.isPending ||
                  provider.isError ||
                  !provider.data?.has_api_key ||
                  !provider.data.model ||
                  !provider.data.base_url
                }
                onClick={() => retryReport.mutate()}
              >
                {retryReport.isPending ? '正在重试报告…' : '仅重试报告'}
              </Button>
              {provider.isError && (
                <p role="alert" className="text-sm text-destructive">
                  无法读取当前 AI 配置，暂不能重试报告。
                </p>
              )}
              {provider.data &&
                (!provider.data.has_api_key ||
                  !provider.data.model ||
                  !provider.data.base_url) && (
                  <p role="alert" className="text-sm text-destructive">
                    请先保存有效的 AI 配置，再重试报告。
                  </p>
                )}
              {retryReport.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {analysisErrorMessage(retryReport.error)}
                </p>
              )}
            </div>
          )}
          <ReportCoverage report={value.report} />
          <ReportDetails
            report={value.report}
            sourceOffset={sourceOffset}
            sectionOffset={sectionOffset}
            sectionId={sectionId}
            onSourcePage={setSourceOffset}
            onSectionPage={setSectionOffset}
            onSection={setSectionId}
          />
          <p className="text-sm text-muted-foreground">
            报告正文、覆盖情况和来源已在本页展示；无需跳转到另一套报告记录。
          </p>
        </>
      )}
    </div>
  )
}

export function ReportGenerations({
  selectedId,
  onSelect,
  onSelectReport,
  autoSelectLatest = true,
}: {
  selectedId: number | null
  onSelect: (id: number | null) => void
  onSelectReport?: (id: number) => void
  autoSelectLatest?: boolean
}) {
  const [beforeId, setBeforeId] = useState<number | undefined>()
  const [params, setParams] = useSearchParams()
  const legacyBeforeId = readId(params.get('reports_before'))
  const history = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, 'list', beforeId],
    queryFn: ({ signal }) => fetchReportGenerations(signal, beforeId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some((value) => isActiveGeneration(value.status))
        ? 1000
        : false,
  })
  const legacyHistory = useQuery({
    queryKey: [...TOPIC_REPORTS_QUERY_KEY, 'records', legacyBeforeId],
    queryFn: ({ signal }) =>
      fetchTopicReports(
        signal,
        legacyBeforeId === null ? {} : { beforeId: legacyBeforeId },
      ),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.reports.some((report) => isActiveReport(report.status))
        ? 1000
        : false,
  })
  function changeLegacyPage(nextBeforeId: number | null) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (nextBeforeId === null) next.delete('reports_before')
      else next.set('reports_before', String(nextBeforeId))
      return next
    })
  }
  useEffect(() => {
    if (!autoSelectLatest || selectedId !== null || !history.data?.items.length)
      return
    const preferred =
      history.data.items.find((value) => isActiveGeneration(value.status)) ??
      history.data.items[0]
    onSelect(preferred.id)
  }, [autoSelectLatest, history.data, onSelect, selectedId])
  const selected = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, selectedId],
    queryFn: ({ signal }) => fetchReportGeneration(selectedId!, signal),
    enabled: selectedId !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveGeneration(query.state.data.status)
        ? 1000
        : false,
  })
  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        {selectedId !== null &&
          (selected.isError ? (
            <p role="alert">
              {analysisErrorMessage(selected.error)}{' '}
              <Button variant="outline" onClick={() => void selected.refetch()}>
                重试读取进度
              </Button>
            </p>
          ) : selected.isPending ? (
            <p role="status">正在读取任务进度…</p>
          ) : (
            <GenerationDetails key={selected.data.id} value={selected.data} />
          ))}
        <details className="rounded-lg border p-3" open={selectedId === null}>
          <summary className="min-h-8 cursor-pointer font-medium">
            报告列表
          </summary>
          <div className="mt-3 flex flex-col items-start gap-2">
            {history.isError ? (
              <p role="alert">
                {analysisErrorMessage(history.error)}{' '}
                <Button
                  variant="outline"
                  onClick={() => void history.refetch()}
                >
                  重试读取任务
                </Button>
              </p>
            ) : history.isPending ? (
              <p role="status">正在读取任务…</p>
            ) : (
              <>
                {history.data.items.length === 0 &&
                  legacyHistory.data?.reports.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      尚未启动报告生成任务。
                    </p>
                  )}
                {history.data.items.map((value) => (
                  <Button
                    key={`generation-${value.id}`}
                    variant="ghost"
                    onClick={() => onSelect(value.id)}
                  >
                    {value.name ?? `报告 #${value.id}`} ·{' '}
                    {value.selection.result_ids.length} 条 ·{' '}
                    {labels[value.status]} ·{' '}
                    {formatEvidenceDate(value.created_at)}
                  </Button>
                ))}
                {legacyHistory.data?.reports
                  .filter(
                    (report) =>
                      !history.data.items.some(
                        (generation) => generation.report?.id === report.id,
                      ),
                  )
                  .map((report) => (
                    <Button
                      key={`legacy-${report.id}`}
                      variant="ghost"
                      onClick={() => onSelectReport?.(report.id)}
                    >
                      {legacyReportLabel(report)}
                    </Button>
                  ))}
              </>
            )}
            {legacyHistory.isError && (
              <p role="status" className="text-sm text-muted-foreground">
                历史报告暂时无法读取；已提交的报告任务仍可查看。
              </p>
            )}
            {legacyHistory.data &&
              (legacyBeforeId !== null ||
                legacyHistory.data.next_before_id !== null) && (
                <nav className="flex flex-wrap gap-2" aria-label="历史报告分页">
                  <Button
                    variant="outline"
                    disabled={
                      legacyBeforeId === null || legacyHistory.isFetching
                    }
                    onClick={() => changeLegacyPage(null)}
                  >
                    最新报告
                  </Button>
                  <Button
                    variant="outline"
                    disabled={
                      legacyHistory.data?.next_before_id === null ||
                      legacyHistory.isFetching
                    }
                    onClick={() =>
                      changeLegacyPage(
                        legacyHistory.data?.next_before_id ?? null,
                      )
                    }
                  >
                    更早报告
                  </Button>
                </nav>
              )}
            {history.data?.next_before_id && (
              <Button
                variant="outline"
                onClick={() => setBeforeId(history.data!.next_before_id!)}
              >
                更早的任务
              </Button>
            )}
            {beforeId && (
              <Button variant="outline" onClick={() => setBeforeId(undefined)}>
                返回最新任务
              </Button>
            )}
            {selectedId !== null && (
              <Button variant="outline" onClick={() => onSelect(null)}>
                收起当前任务
              </Button>
            )}
          </div>
        </details>
      </CardContent>
    </Card>
  )
}
