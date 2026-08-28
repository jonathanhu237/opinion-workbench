import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { useEffect, useRef } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { analysisErrorMessage } from '@/lib/api/analysis-shared'
import type { AISettings } from '@/lib/api/ai-settings'
import type { AnalysisSettings } from '@/lib/api/analysis-settings'
import {
  ANALYSIS_PAGE_SIZE,
  CONTENT_ANALYSES_QUERY_KEY,
  CONTENT_ANALYSIS_JOBS_QUERY_KEY,
  cancelAnalysisJob,
  fetchAnalysisJob,
  fetchAnalysisJobItems,
  fetchAnalysisJobs,
  isActiveAnalysisJob,
} from '@/lib/api/content-analyses'
import { readId, readOffset, RESULTS_QUERY_KEY } from '@/lib/api/results'
import { FrozenAnalysisPrompts } from '@/routes/results-evidence'
import {
  analysisJobLabels,
  analysisUsageMessage,
  formatEvidenceDate,
  resultStateLabels,
  ResultsPagination,
} from '@/routes/results-presenters'
import { REPORT_URL_KEYS, ResultsReports } from '@/routes/results-reports'

export function ResultsJobs({
  settings,
  provider,
}: {
  settings?: AnalysisSettings
  provider?: AISettings
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const offset = readOffset(params.get('job_offset'))
  const jobs = useInfiniteQuery({
    queryKey: [...CONTENT_ANALYSIS_JOBS_QUERY_KEY, 'list'],
    queryFn: ({ signal, pageParam }) => fetchAnalysisJobs(signal, pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (page) => page.next_before_id ?? undefined,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.jobs.some((job) => isActiveAnalysisJob(job.status)),
      )
        ? 1000
        : false,
  })
  const history = jobs.data?.pages.flatMap((page) => page.jobs) ?? []
  const selectedId = readId(params.get('job')) ?? history[0]?.id ?? null
  const requestedJob = readId(params.get('job'))
  useEffect(() => {
    if (requestedJob === null) return
    heading.current?.focus({ preventScroll: true })
    heading.current?.scrollIntoView?.({ block: 'start', behavior: 'instant' })
  }, [requestedJob])
  const detail = useQuery({
    queryKey: [...CONTENT_ANALYSIS_JOBS_QUERY_KEY, selectedId],
    queryFn: ({ signal }) => fetchAnalysisJob(selectedId ?? 0, signal),
    enabled: selectedId !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveAnalysisJob(query.state.data.status)
        ? 1000
        : false,
  })
  const job = detail.data
  const previousJob = useRef<{ id: number; active: boolean } | null>(null)
  useEffect(() => {
    if (!job) return
    const active = isActiveAnalysisJob(job.status)
    if (
      previousJob.current?.id === job.id &&
      previousJob.current.active &&
      !active
    ) {
      void client.invalidateQueries({
        queryKey: [...CONTENT_ANALYSIS_JOBS_QUERY_KEY, job.id, 'items'],
      })
      void client.invalidateQueries({ queryKey: RESULTS_QUERY_KEY })
      void client.invalidateQueries({ queryKey: CONTENT_ANALYSES_QUERY_KEY })
    }
    previousJob.current = { id: job.id, active }
  }, [client, job])
  const items = useQuery({
    queryKey: [...CONTENT_ANALYSIS_JOBS_QUERY_KEY, selectedId, 'items', offset],
    queryFn: ({ signal }) =>
      fetchAnalysisJobItems(selectedId ?? 0, signal, offset),
    enabled: selectedId !== null,
    retry: false,
    refetchInterval: job && isActiveAnalysisJob(job.status) ? 1000 : false,
  })
  const cancel = useMutation({
    mutationFn: cancelAnalysisJob,
    retry: false,
    onSuccess: async (settled) => {
      client.setQueryData(
        [...CONTENT_ANALYSIS_JOBS_QUERY_KEY, settled.id],
        settled,
      )
      await Promise.all([
        client.invalidateQueries({ queryKey: CONTENT_ANALYSIS_JOBS_QUERY_KEY }),
        client.invalidateQueries({ queryKey: CONTENT_ANALYSES_QUERY_KEY }),
        client.invalidateQueries({ queryKey: RESULTS_QUERY_KEY }),
      ])
    },
    onError: () => {
      void client.invalidateQueries({
        queryKey: CONTENT_ANALYSIS_JOBS_QUERY_KEY,
      })
    },
  })
  const selectJob = (id: number) => {
    const next = new URLSearchParams(params)
    next.set('job', String(id))
    next.delete('job_offset')
    for (const key of REPORT_URL_KEYS) next.delete(key)
    setParams(next)
  }
  const changeOffset = (value: number) => {
    const next = new URLSearchParams(params)
    next.set('job_offset', String(value))
    setParams(next)
  }
  const settled = job
    ? job.counts.total -
      job.counts.queued -
      job.counts.acquiring -
      job.counts.analysing
    : 0
  return (
    <>
      <Card>
        <CardHeader className="border-b">
          <h2
            ref={heading}
            tabIndex={-1}
            className="font-display text-xl outline-none"
          >
            初步分析任务
          </h2>
          <p className="text-sm leading-6 text-muted-foreground">
            任务成员在提交时固定。成功文本逐条保存，失败项不会因刷新或新采集而重试。
          </p>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          {jobs.isPending && (
            <p role="status" className="text-sm">
              正在读取分析任务…
            </p>
          )}
          {jobs.isError && (
            <div role="alert" className="space-y-2 text-sm">
              <p className="text-destructive">
                {analysisErrorMessage(jobs.error)}
              </p>
              <Button variant="outline" onClick={() => void jobs.refetch()}>
                重试读取任务
              </Button>
            </div>
          )}
          {jobs.data && history.length === 0 && (
            <p className="text-sm text-muted-foreground">
              还没有初步分析任务。查看此页不会调用模型。
            </p>
          )}
          {history.some(
            (item) =>
              item.id !== selectedId && isActiveAnalysisJob(item.status),
          ) && (
            <section
              aria-label="其他进行中的分析任务"
              className="space-y-2 rounded-lg border p-3"
            >
              {history
                .filter(
                  (item) =>
                    item.id !== selectedId && isActiveAnalysisJob(item.status),
                )
                .map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-2 text-sm"
                  >
                    <Button variant="link" onClick={() => selectJob(item.id)}>
                      任务 {item.id} · {analysisJobLabels[item.status]}
                    </Button>
                    <Button
                      variant="outline"
                      className="min-h-11"
                      disabled={cancel.isPending}
                      onClick={() => cancel.mutate(item.id)}
                    >
                      取消任务 {item.id}
                    </Button>
                  </div>
                ))}
            </section>
          )}
          {history.length > 0 && (
            <details>
              <summary className="min-h-11 cursor-pointer text-sm font-medium">
                选择任务与历史版本
              </summary>
              <ul className="mt-2 divide-y">
                {history.map((item) => (
                  <li key={item.id}>
                    <Button
                      variant={item.id === selectedId ? 'secondary' : 'ghost'}
                      className="my-1 min-h-11 w-full justify-start text-left whitespace-normal"
                      aria-pressed={item.id === selectedId}
                      onClick={() => selectJob(item.id)}
                    >
                      任务 {item.id} · {analysisJobLabels[item.status]} ·{' '}
                      {item.counts.total} 条 ·{' '}
                      {formatEvidenceDate(item.created_at)}
                    </Button>
                  </li>
                ))}
              </ul>
              {jobs.hasNextPage && (
                <Button
                  variant="outline"
                  disabled={jobs.isFetchingNextPage}
                  onClick={() => void jobs.fetchNextPage()}
                >
                  {jobs.isFetchingNextPage ? '正在读取…' : '更多历史任务'}
                </Button>
              )}
            </details>
          )}
          {detail.isError && (
            <p role="alert" className="text-sm text-destructive">
              {analysisErrorMessage(detail.error)}
            </p>
          )}
          {cancel.isError && (
            <p role="alert" className="text-sm text-destructive">
              {analysisErrorMessage(cancel.error)}
            </p>
          )}
          {job && (
            <section className="space-y-4" aria-label={`分析任务 ${job.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-medium">
                  任务 {job.id}{' '}
                  <Badge variant="outline">
                    {analysisJobLabels[job.status]}
                  </Badge>
                </h3>
                {isActiveAnalysisJob(job.status) && (
                  <Button
                    variant="outline"
                    className="min-h-11"
                    disabled={cancel.isPending}
                    aria-busy={cancel.isPending && cancel.variables === job.id}
                    onClick={() => cancel.mutate(job.id)}
                  >
                    {cancel.isPending && cancel.variables === job.id
                      ? '正在取消…'
                      : `取消任务 ${job.id}`}
                  </Button>
                )}
              </div>
              <div className="space-y-2" role="status" aria-live="polite">
                <p className="text-sm font-medium">
                  初步分析：已处理 {settled}/{job.counts.total}
                </p>
                <progress
                  className="h-2 w-full accent-primary"
                  max={job.counts.total}
                  value={settled}
                  aria-label="初步分析已处理条数"
                />
                <p className="text-sm text-muted-foreground">
                  已保存 {job.counts.completed} 条 · 未成功{' '}
                  {settled - job.counts.completed} 条 · 待处理{' '}
                  {job.counts.queued} 条
                </p>
              </div>
              {job.queue_reason && (
                <p className="rounded-lg bg-muted p-3 text-sm">
                  {job.queue_reason === 'browser_operation_active'
                    ? '正在等待谷歌浏览器空闲，不会中断现有采集或人工验证。'
                    : '正在等待其他 AI 操作结束；尚未新增模型调用。'}
                </p>
              )}
              {job.status === 'configuration_blocked' && (
                <p className="text-sm text-warning-foreground">
                  已保存的模型配置与本任务不一致。未改用新服务；请在内容详情中明确重试。
                </p>
              )}
              <p className="text-sm text-muted-foreground">
                {analysisUsageMessage(job.usage)}
              </p>
              <p className="text-sm text-muted-foreground">
                {job.completion_event_id !== null
                  ? '本任务已全部处理并保存完成记录；此状态不代表全部分析成功或报告已生成。'
                  : job.status === 'cancelled' || job.status === 'interrupted'
                    ? '已保存的初步分析仍可查看；本任务不会自动生成报告。'
                    : '每条分析独立保存，任务结束后才记录一次完成。取消会停止本任务的自动后续处理。'}
              </p>
              <FrozenAnalysisPrompts job={job} />
              {items.isPending && (
                <p role="status" className="text-sm">
                  正在读取逐条进度…
                </p>
              )}
              {items.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {analysisErrorMessage(items.error)}
                </p>
              )}
              <ul className="divide-y">
                {items.data?.items.map((item) => {
                  const next = new URLSearchParams(params)
                  next.set('result', String(item.source.result_id))
                  next.set('attempt', String(item.id))
                  return (
                    <li key={item.id} className="py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="min-w-0 text-sm font-medium [overflow-wrap:anywhere]">
                          {item.position + 1}. {item.source.title}
                        </p>
                        <Badge variant="outline">
                          {resultStateLabels[item.status]}
                        </Badge>
                      </div>
                      {item.error && (
                        <p className="mt-2 text-sm text-muted-foreground">
                          {item.error.message}
                        </p>
                      )}
                      <Link
                        className={buttonVariants({
                          variant: 'link',
                          size: 'sm',
                        })}
                        to={`?${next}`}
                        preventScrollReset
                      >
                        查看此条与分析版本
                      </Link>
                    </li>
                  )
                })}
              </ul>
              {items.data && (
                <ResultsPagination
                  label="任务内容"
                  offset={offset}
                  limit={ANALYSIS_PAGE_SIZE}
                  total={items.data.total}
                  onChange={changeOffset}
                />
              )}
            </section>
          )}
        </CardContent>
      </Card>
      <ResultsReports job={job} settings={settings} provider={provider} />
    </>
  )
}
