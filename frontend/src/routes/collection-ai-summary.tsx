import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { ExternalLink, LoaderCircle, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  AI_SETTINGS_QUERY_KEY,
  fetchAISettings,
  type AISettings,
} from '@/lib/api/ai-settings'
import {
  AI_SUMMARIES_QUERY_KEY,
  AISummaryApiError,
  cancelAISummary,
  fetchAISummaries,
  fetchAISummary,
  fetchAISummaryItems,
  isActiveAISummary,
  startAISummary,
  validateAISummarySources,
  type AISummaryItem,
  type AISummaryRequest,
  type AISummarySource,
  type AISummaryUsage,
} from '@/lib/api/ai-summaries'
import { isActiveSearchRun, type SearchRunDetail } from '@/lib/api/search-runs'
import { cn } from '@/lib/utils'
import { CollectionSummaryConfirmation } from '@/routes/collection-summary-confirmation'
import {
  formatLocalDate,
  searchPlatformPresenters,
} from '@/routes/search-run-presenters'

const ANALYSIS_PAGE_SIZE = 10
const summaryLabels = {
  queued: '等待开始',
  running: '正在生成',
  completed: '已完成',
  failed: '生成失败',
  cancelled: '已取消',
  interrupted: '已中断',
} as const
const decisionLabels = {
  relevant: '相关',
  irrelevant: '不相关',
  uncertain: '无法确定',
} as const
const itemLabels = {
  pending: '待分析',
  analysing: '正在分析',
  completed: '已分析',
  input_incomplete: '内容不完整',
  failed: '分析失败',
  cancelled: '已取消',
  interrupted: '已中断',
} as const
const stageLabels = {
  acquisition: '获取内容',
  input: '准备输入',
  analysis: '内容分析',
  composition: '生成汇总',
  execution: '执行任务',
} as const

function readPositiveId(value: string | null) {
  if (value === null || !/^[1-9]\d*$/u.test(value)) return null
  const id = Number(value)
  return Number.isSafeInteger(id) ? id : null
}

function errorMessage(error: unknown) {
  return error instanceof AISummaryApiError
    ? error.message
    : '暂时无法读取汇总，请稍后重试。'
}

function usageMessage(usage: AISummaryUsage) {
  if (usage.attempted_requests === 0) return '本次未调用模型'
  if (usage.total_tokens === null)
    return `本次调用 ${usage.attempted_requests} 次 · Token 用量未知`
  return `本次 ${usage.total_tokens.toLocaleString('zh-CN')} Token${usage.complete ? '' : '（统计不完整）'} · 调用 ${usage.attempted_requests} 次`
}

type SourceControls = {
  openPending: boolean
  activeOpenResultId: number | null | undefined
  openFeedback: { resultId: number; message: string } | null
  onOpen: (resultId: number) => void
}

function SourceLink({
  source,
  disabled,
  citationNumber,
  controls,
}: {
  source: AISummarySource
  disabled: boolean
  citationNumber?: number
  controls: SourceControls
}) {
  const label =
    citationNumber === undefined
      ? '打开原文'
      : `原文 ${citationNumber} · ${searchPlatformPresenters[source.platform].label}`
  const accessibleLabel =
    citationNumber === undefined ? undefined : `${label}：${source.title}`
  const title = citationNumber === undefined ? undefined : source.title
  if (source.platform !== 'xhs')
    return (
      <a
        className={cn(
          buttonVariants({ variant: 'link', size: 'sm' }),
          'h-auto min-h-8 justify-start px-0 text-left [overflow-wrap:anywhere] whitespace-normal',
          citationNumber !== undefined &&
            'ms-2 align-baseline whitespace-nowrap underline',
        )}
        href={source.content_url}
        target="_blank"
        rel={
          citationNumber === undefined ? 'noreferrer' : 'noopener noreferrer'
        }
        aria-label={accessibleLabel}
        title={title}
      >
        {label}
        <ExternalLink className="shrink-0" aria-hidden />
      </a>
    )
  const pending =
    controls.openPending && controls.activeOpenResultId === source.result_id
  return (
    <span
      className={cn(
        'inline-flex flex-col items-start',
        citationNumber !== undefined && 'ms-2 max-w-full align-baseline',
      )}
    >
      <Button
        variant="link"
        size="sm"
        className={cn(
          'h-auto min-h-8 px-0 text-left [overflow-wrap:anywhere] whitespace-normal',
          citationNumber !== undefined && 'whitespace-nowrap underline',
        )}
        disabled={disabled || controls.openPending}
        aria-busy={pending}
        aria-label={accessibleLabel}
        title={title}
        onClick={() => controls.onOpen(source.result_id)}
      >
        {pending ? '正在打开…' : label}
        <ExternalLink className="shrink-0" aria-hidden />
      </Button>
      {controls.openFeedback?.resultId === source.result_id && (
        <span role="status" className="text-sm text-muted-foreground">
          {controls.openFeedback.message}
        </span>
      )}
    </span>
  )
}

function AnalysisRecord({
  item,
  active,
  controls,
}: {
  item: AISummaryItem
  active: boolean
  controls: SourceControls
}) {
  return (
    <article className="space-y-2 py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={item.decision === 'relevant' ? 'secondary' : 'outline'}>
          {item.decision
            ? decisionLabels[item.decision]
            : itemLabels[item.status]}
        </Badge>
        {item.reused_from_item_id !== null && (
          <span className="text-xs text-muted-foreground">使用已有分析</span>
        )}
        <span className="text-xs text-muted-foreground">
          {item.source.published_at_text || '平台未显示发布时间'}
        </span>
      </div>
      <h3 className="text-sm leading-6 font-medium [overflow-wrap:anywhere]">
        {item.source.title}
      </h3>
      {item.reason && (
        <p className="text-sm leading-6 [overflow-wrap:anywhere]">
          {item.reason}
        </p>
      )}
      {item.evidence_summary && (
        <p className="text-sm leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap text-muted-foreground">
          {item.evidence_summary}
        </p>
      )}
      {item.error && (
        <p className="text-sm leading-6 text-muted-foreground">
          {stageLabels[item.error.stage]}：{item.error.message}
        </p>
      )}
      <SourceLink source={item.source} disabled={active} controls={controls} />
    </article>
  )
}

export function CollectionAISummary({
  run,
  historyOnly = false,
  ...controls
}: { run: SearchRunDetail; historyOnly?: boolean } & SourceControls) {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [confirmation, setConfirmation] = useState<{
    settings: AISettings
    sourceCount: number
  } | null>(null)
  const intent = useRef<AISummaryRequest | null>(null)
  const submitLock = useRef(false)
  const cancelLock = useRef(false)
  const historyKey = [...AI_SUMMARIES_QUERY_KEY, 'history', run.id]
  const settingsQuery = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    enabled: !historyOnly,
    retry: false,
  })
  const historyQuery = useInfiniteQuery({
    queryKey: historyKey,
    queryFn: ({ signal, pageParam }) =>
      fetchAISummaries(run.id, signal, pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (page) => page.next_before_id ?? undefined,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.summaries.some((summary) => isActiveAISummary(summary.status)),
      )
        ? 1000
        : false,
  })
  const history =
    historyQuery.data?.pages.flatMap((page) => page.summaries) ?? []
  const requestedId = params.get('summary')
  const selectedId = readPositiveId(requestedId)
  const invalidSelection = requestedId !== null && selectedId === null
  const detailQuery = useQuery({
    queryKey: [...AI_SUMMARIES_QUERY_KEY, 'detail', selectedId, run.id],
    queryFn: async ({ signal }) => {
      const data = await fetchAISummary(selectedId ?? 0, signal)
      if (data.source_run_id !== run.id || data.platform !== run.platform)
        throw new AISummaryApiError('invalid_response', 200)
      return data
    },
    enabled: selectedId !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveAISummary(query.state.data.status)
        ? 1000
        : false,
  })
  const selected = detailQuery.data
  const active = selected !== undefined && isActiveAISummary(selected.status)
  const itemsQuery = useQuery({
    queryKey: [...AI_SUMMARIES_QUERY_KEY, 'items', selectedId],
    queryFn: ({ signal }) => fetchAISummaryItems(selectedId ?? 0, signal),
    enabled: selectedId !== null && selected !== undefined,
    retry: false,
    refetchInterval: active ? 1000 : false,
  })

  const latestId = history.at(0)?.id
  useEffect(() => {
    if (requestedId !== null || latestId === undefined) return
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.set('summary', String(latestId))
        return next
      },
      { replace: true },
    )
  }, [latestId, requestedId, setParams])

  // Terminal reads refresh only stored state; no generation is ever started by an effect.
  useEffect(() => {
    if (!selected || isActiveAISummary(selected.status)) return
    void queryClient.invalidateQueries({
      queryKey: [...AI_SUMMARIES_QUERY_KEY, 'history', run.id],
    })
    void queryClient.invalidateQueries({
      queryKey: [...AI_SUMMARIES_QUERY_KEY, 'items', selected.id],
    })
  }, [queryClient, run.id, selected?.id, selected?.status])

  const chooseSummary = (id: number) => {
    setParams((current) => {
      const next = new URLSearchParams(current)
      next.set('summary', String(id))
      next.delete('analysis_offset')
      return next
    })
  }

  const startMutation = useMutation({
    mutationFn: (request: AISummaryRequest) => startAISummary(run.id, request),
    retry: false,
    onSuccess: (data) => {
      queryClient.setQueryData(
        [...AI_SUMMARIES_QUERY_KEY, 'detail', data.id, run.id],
        data,
      )
      void queryClient.invalidateQueries({ queryKey: historyKey })
      setConfirmation(null)
      intent.current = null
      chooseSummary(data.id)
    },
    onSettled: () => {
      submitLock.current = false
    },
  })
  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelAISummary(id),
    retry: false,
    onSuccess: (data) => {
      queryClient.setQueryData(
        [...AI_SUMMARIES_QUERY_KEY, 'detail', data.id, run.id],
        data,
      )
      void queryClient.invalidateQueries({ queryKey: historyKey })
      void queryClient.invalidateQueries({
        queryKey: [...AI_SUMMARIES_QUERY_KEY, 'items', data.id],
      })
    },
    onSettled: () => {
      cancelLock.current = false
    },
  })

  const settings = settingsQuery.data
  const activeVersion = history.find((entry) => isActiveAISummary(entry.status))
  const admissionMessage = isActiveSearchRun(run.status)
    ? '采集结束后可生成汇总。'
    : run.total_count === 0
      ? '本次采集暂无内容。'
      : run.total_count > 100
        ? '一次最多汇总 100 条内容，请缩小采集范围。'
        : settingsQuery.isError
          ? 'AI 配置暂时无法读取。'
          : settingsQuery.isPending
            ? '正在读取 AI 配置…'
            : !settings?.has_api_key
              ? '请先保存 AI 配置。'
              : activeVersion || active
                ? '已有汇总正在生成。'
                : null
  const canStart =
    admissionMessage === null &&
    historyQuery.isSuccess &&
    !startMutation.isPending
  const startError = startMutation.isError
    ? startMutation.error instanceof AISummaryApiError &&
      startMutation.error.code === 'ai_configuration_changed'
      ? 'AI 配置已更改，请关闭弹窗后重新确认模型服务地址。'
      : startMutation.error instanceof AISummaryApiError &&
          (startMutation.error.code === 'service_unavailable' ||
            startMutation.error.code === 'invalid_response')
        ? '提交结果尚未确认。再次提交将使用同一请求，不会重复创建汇总。'
        : errorMessage(startMutation.error)
    : null
  const staleConfirmation =
    startMutation.error instanceof AISummaryApiError &&
    startMutation.error.code === 'ai_configuration_changed'

  const options = history.map((entry) => ({
    value: String(entry.id),
    label: `汇总 #${entry.id} · ${formatLocalDate(entry.created_at)}`,
  }))
  if (
    selected &&
    !options.some((option) => option.value === String(selected.id))
  )
    options.unshift({
      value: String(selected.id),
      label: `汇总 #${selected.id} · ${formatLocalDate(selected.created_at)}`,
    })
  const items = itemsQuery.data?.items ?? []
  const sourcesValid =
    selected !== undefined &&
    itemsQuery.data !== undefined &&
    validateAISummarySources(selected, items)
  const offsetValue = Number(params.get('analysis_offset') ?? 0)
  const offset =
    Number.isSafeInteger(offsetValue) &&
    offsetValue >= 0 &&
    offsetValue < items.length
      ? Math.floor(offsetValue / ANALYSIS_PAGE_SIZE) * ANALYSIS_PAGE_SIZE
      : 0
  const changeAnalysisPage = (nextOffset: number) =>
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (nextOffset === 0) next.delete('analysis_offset')
      else next.set('analysis_offset', String(nextOffset))
      return next
    })

  return (
    <section aria-labelledby="ai-summary-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id="ai-summary-title"
          className="font-display text-xl font-semibold"
        >
          AI 汇总（旧版）
        </h2>
        {historyOnly ? (
          <Link
            to="/reports/new"
            className={buttonVariants({ className: 'min-h-11 sm:min-h-8' })}
          >
            前往生成报告
          </Link>
        ) : (
          <Button
            className="min-h-11 sm:min-h-8"
            disabled={!canStart}
            onClick={() => {
              if (!settings || !canStart) return
              startMutation.reset()
              intent.current = null
              setConfirmation({ settings, sourceCount: run.total_count })
            }}
          >
            生成汇总
          </Button>
        )}
      </div>
      <p className="text-sm leading-6 text-muted-foreground">
        旧版分析只针对本次采集，历史报告继续保留。
        <Link to="/reports/new" className="ml-1 underline underline-offset-4">
          前往生成报告查看选材与报告
        </Link>
      </p>
      {historyOnly && (
        <p className="text-sm text-muted-foreground">
          这里只显示旧版汇总和引用。新的选材与报告请前往生成报告；正在进行的旧版任务仍可取消。
        </p>
      )}
      {!historyOnly && admissionMessage && (
        <p className="text-sm text-muted-foreground">
          {admissionMessage}
          {!settingsQuery.isPending && !settings?.has_api_key && (
            <Link
              to="/settings/ai"
              className="ml-2 underline underline-offset-4"
            >
              前往 AI 配置
            </Link>
          )}
          {settingsQuery.isError && (
            <Button
              size="sm"
              variant="link"
              onClick={() => settingsQuery.refetch()}
            >
              重新读取
            </Button>
          )}
          {activeVersion && selectedId !== activeVersion.id && (
            <Button
              variant="link"
              size="sm"
              onClick={() => chooseSummary(activeVersion.id)}
            >
              查看正在生成的汇总
            </Button>
          )}
        </p>
      )}
      {historyQuery.isError ? (
        <p className="text-sm" role="alert">
          汇总记录暂时无法读取。
          <Button
            variant="link"
            size="sm"
            onClick={() => historyQuery.refetch()}
          >
            重新加载汇总
          </Button>
        </p>
      ) : historyQuery.isPending ? (
        <Skeleton className="h-10 w-full" aria-label="正在加载汇总记录" />
      ) : history.length === 0 && selectedId === null && !invalidSelection ? (
        <p className="text-sm text-muted-foreground">还没有生成汇总。</p>
      ) : null}

      {options.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Select
            items={options}
            value={selectedId === null ? null : String(selectedId)}
            onValueChange={(value) => {
              if (value !== null) chooseSummary(Number(value))
            }}
          >
            <SelectTrigger
              aria-label="汇总版本"
              className="max-w-full min-w-48"
            >
              <SelectValue placeholder="选择汇总版本" />
            </SelectTrigger>
            <SelectContent>
              {options.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {historyQuery.hasNextPage && (
            <Button
              size="sm"
              variant="ghost"
              disabled={historyQuery.isFetchingNextPage}
              onClick={() => historyQuery.fetchNextPage()}
            >
              {historyQuery.isFetchingNextPage ? '正在加载…' : '加载较早汇总'}
            </Button>
          )}
        </div>
      )}

      {invalidSelection || detailQuery.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {invalidSelection
            ? '汇总地址不正确，请选择一个汇总版本。'
            : errorMessage(detailQuery.error)}
          {!invalidSelection && (
            <Button
              size="sm"
              variant="link"
              onClick={() => detailQuery.refetch()}
            >
              重新读取汇总
            </Button>
          )}
        </p>
      ) : selectedId !== null && detailQuery.isPending ? (
        <Skeleton className="h-28 w-full" aria-label="正在读取汇总" />
      ) : (
        selected && (
          <Card>
            <CardContent className="space-y-4 p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div
                  className="flex flex-wrap items-center gap-2"
                  role="status"
                >
                  <Badge variant="outline">
                    {active && (
                      <LoaderCircle
                        className="animate-spin motion-reduce:animate-none"
                        aria-hidden
                      />
                    )}
                    {summaryLabels[selected.status]}
                  </Badge>
                  {active && (
                    <span className="text-sm">
                      {selected.phase === 'summarising'
                        ? '正在生成文字汇总…'
                        : `正在分析内容 · 已处理 ${selected.counts.total - selected.counts.pending - selected.counts.analysing} / ${selected.counts.total} 条`}
                    </span>
                  )}
                </div>
                {active && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={cancelMutation.isPending}
                    onClick={() => {
                      if (cancelLock.current) return
                      cancelLock.current = true
                      cancelMutation.mutate(selected.id)
                    }}
                  >
                    <Square aria-hidden />
                    {cancelMutation.isPending ? '正在取消…' : '取消生成'}
                  </Button>
                )}
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                本次范围 {selected.counts.total} 条 · 相关{' '}
                {selected.counts.relevant} · 不相关 {selected.counts.irrelevant}{' '}
                · 无法确定 {selected.counts.uncertain} · 内容不完整{' '}
                {selected.counts.input_incomplete} · 失败{' '}
                {selected.counts.failed}
                {selected.counts.cancelled > 0 &&
                  ` · 已取消 ${selected.counts.cancelled}`}
                {selected.counts.interrupted > 0 &&
                  ` · 已中断 ${selected.counts.interrupted}`}
                {selected.counts.reused > 0 &&
                  ` · 使用已有分析 ${selected.counts.reused}`}
              </p>
              {selected.source_run_status !== 'completed_with_results' && (
                <p className="text-sm text-muted-foreground">
                  原采集任务未完整结束，本汇总仅包含当时已获取的内容。
                </p>
              )}
              {selected.error && (
                <p className="text-sm text-destructive" role="alert">
                  {stageLabels[selected.error.stage]}：{selected.error.message}{' '}
                  {selected.error.code !== 'cancelled' &&
                    selected.error.code !== 'interrupted' &&
                    '已完成的内容分析仍可查看。'}
                </p>
              )}
              {cancelMutation.isError && (
                <p className="text-sm text-destructive" role="alert">
                  {errorMessage(cancelMutation.error)}
                </p>
              )}
              {itemsQuery.isError ? (
                <p className="text-sm" role="alert">
                  内容分析暂时无法读取。
                  <Button
                    size="sm"
                    variant="link"
                    onClick={() => itemsQuery.refetch()}
                  >
                    重新读取分析
                  </Button>
                </p>
              ) : itemsQuery.isPending ? (
                <Skeleton
                  className="h-12 w-full"
                  aria-label="正在读取内容分析"
                />
              ) : !sourcesValid ? (
                <p className="text-sm text-destructive" role="alert">
                  汇总和原文记录不一致，暂时无法显示引用。
                  <Button
                    variant="link"
                    size="sm"
                    onClick={() => {
                      void detailQuery.refetch()
                      void itemsQuery.refetch()
                    }}
                  >
                    重新读取分析
                  </Button>
                </p>
              ) : (
                <>
                  {selected.document && (
                    <div className="space-y-4 border-t pt-4">
                      <p className="text-sm leading-7 [overflow-wrap:anywhere] whitespace-pre-wrap">
                        {selected.document.overview}
                      </p>
                      {selected.document.items.map((paragraph, index) => (
                        <p
                          key={index}
                          className="text-sm leading-7 [overflow-wrap:anywhere] whitespace-pre-wrap"
                        >
                          {paragraph.text}
                          {paragraph.source_ids.map((id) => {
                            const item = items.find(
                              (entry) => entry.source.result_id === id,
                            )
                            return item ? (
                              <SourceLink
                                key={id}
                                source={item.source}
                                disabled={active}
                                controls={controls}
                                citationNumber={item.position + 1}
                              />
                            ) : null
                          })}
                        </p>
                      ))}
                    </div>
                  )}
                  <details className="border-t pt-3">
                    <summary className="cursor-pointer rounded-sm text-sm font-medium outline-offset-4">
                      内容分析 · {items.length} 条
                    </summary>
                    <div className="mt-4 divide-y">
                      {items
                        .slice(offset, offset + ANALYSIS_PAGE_SIZE)
                        .map((item) => (
                          <AnalysisRecord
                            key={item.id}
                            item={item}
                            active={active}
                            controls={controls}
                          />
                        ))}
                    </div>
                    {items.length > ANALYSIS_PAGE_SIZE && (
                      <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
                        <span className="text-xs text-muted-foreground">
                          {offset + 1}–
                          {Math.min(offset + ANALYSIS_PAGE_SIZE, items.length)}{' '}
                          / {items.length}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={offset === 0}
                          onClick={() =>
                            changeAnalysisPage(offset - ANALYSIS_PAGE_SIZE)
                          }
                        >
                          上一页分析
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={offset + ANALYSIS_PAGE_SIZE >= items.length}
                          onClick={() =>
                            changeAnalysisPage(offset + ANALYSIS_PAGE_SIZE)
                          }
                        >
                          下一页分析
                        </Button>
                      </div>
                    )}
                  </details>
                </>
              )}
              <p className="border-t pt-3 text-xs leading-5 [overflow-wrap:anywhere] text-muted-foreground">
                {usageMessage(selected.usage)} · {selected.model} ·{' '}
                {formatLocalDate(selected.created_at)}
              </p>
            </CardContent>
          </Card>
        )
      )}

      {!historyOnly && confirmation && (
        <CollectionSummaryConfirmation
          sourceCount={confirmation.sourceCount}
          settings={confirmation.settings}
          pending={startMutation.isPending}
          locked={intent.current !== null}
          blocked={staleConfirmation}
          error={startError}
          onClose={() => {
            if (submitLock.current) return
            setConfirmation(null)
            intent.current = null
            startMutation.reset()
            void queryClient.invalidateQueries({
              queryKey: AI_SETTINGS_QUERY_KEY,
            })
            void queryClient.invalidateQueries({ queryKey: historyKey })
          }}
          onConfirm={(forceRefresh) => {
            if (submitLock.current || staleConfirmation) return
            const request = intent.current ?? {
              request_id: crypto.randomUUID(),
              force_refresh: forceRefresh,
              configuration_revision: confirmation.settings.revision,
            }
            intent.current = request
            submitLock.current = true
            startMutation.mutate(request)
          }}
        />
      )}
    </section>
  )
}
