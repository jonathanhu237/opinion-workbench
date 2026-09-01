import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { AI_SETTINGS_QUERY_KEY, fetchAISettings } from '@/lib/api/ai-settings'
import {
  ANALYSIS_SETTINGS_QUERY_KEY,
  fetchAnalysisSettings,
} from '@/lib/api/analysis-settings'
import {
  analysisErrorMessage,
  isAmbiguousAnalysisError,
} from '@/lib/api/analysis-shared'
import {
  CONTENT_ANALYSES_QUERY_KEY,
  CONTENT_ANALYSIS_JOBS_QUERY_KEY,
  startContentAnalysis,
  type AnalysisSelection,
} from '@/lib/api/content-analyses'
import {
  fetchResults,
  isActiveResult,
  parseResultFilters,
  readId,
  RESULT_PAGE_SIZE,
  RESULTS_QUERY_KEY,
  resultStateSchema,
  shanghaiDateBoundary,
  type SharedResult,
} from '@/lib/api/results'
import { SEARCH_PLATFORM_ORDER } from '@/lib/api/search-runs'
import {
  ResultsConfirmation,
  type AnalysisConfirmation,
} from '@/routes/results-confirmation'
import { ResultEvidence } from '@/routes/results-evidence'
import { ResultsJobs } from '@/routes/results-jobs'
import {
  formatEvidenceDate,
  resultStateLabels,
  ResultsPagination,
  ResultSourceLink,
  useResultSourceControls,
} from '@/routes/results-presenters'
import { ResultsSettings } from '@/routes/results-settings'
import { TOPIC_REPORTS_QUERY_KEY } from '@/lib/api/topic-reports'
import { REPORT_URL_KEYS } from '@/routes/results-reports'
import { searchPlatformPresenters } from '@/routes/search-run-presenters'

export function Results() {
  const resultsHeading = useRef<HTMLHeadingElement>(null)
  const resultButtons = useRef(new Map<number, HTMLButtonElement>())
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const filters = parseResultFilters(params)
  const resultId = readId(params.get('result'))
  const [confirmation, setConfirmation] = useState<AnalysisConfirmation | null>(
    null,
  )
  const [confirmationOpen, setConfirmationOpen] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const controls = useResultSourceControls()
  const invalidInterval = Boolean(
    (params.get('from') && !shanghaiDateBoundary(params.get('from'))) ||
    (params.get('to') && !shanghaiDateBoundary(params.get('to'), true)) ||
    (filters.first_seen_from &&
      filters.first_seen_to &&
      filters.first_seen_from >= filters.first_seen_to),
  )
  const results = useQuery({
    queryKey: [...RESULTS_QUERY_KEY, 'list', filters],
    queryFn: ({ signal }) => fetchResults(filters, signal),
    enabled: !invalidInterval,
    retry: false,
    refetchInterval: (query) => (query.state.data?.active_count ? 1000 : false),
  })
  const settings = useQuery({
    queryKey: ANALYSIS_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAnalysisSettings(signal),
    retry: false,
  })
  const provider = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    retry: false,
  })
  const start = useMutation({
    mutationFn: startContentAnalysis,
    retry: false,
    onSuccess: async (admission) => {
      setConfirmation(null)
      setConfirmationOpen(false)
      setFeedback(
        admission.job
          ? `已提交 ${admission.admitted_count} 条初步分析；另有 ${admission.already_active_count} 条仍由原任务处理。`
          : `没有可新提交的内容；已有 ${admission.already_active_count} 条正在其他任务中处理。`,
      )
      if (admission.job) {
        client.setQueryData(
          [...CONTENT_ANALYSIS_JOBS_QUERY_KEY, admission.job.id],
          admission.job,
        )
        setParams((current) => {
          const next = new URLSearchParams(current)
          next.set('job', String(admission.job?.id))
          next.delete('job_offset')
          for (const key of REPORT_URL_KEYS) next.delete(key)
          return next
        })
      }
      await Promise.all([
        client.invalidateQueries({ queryKey: RESULTS_QUERY_KEY }),
        client.invalidateQueries({ queryKey: CONTENT_ANALYSIS_JOBS_QUERY_KEY }),
        client.invalidateQueries({ queryKey: CONTENT_ANALYSES_QUERY_KEY }),
      ])
    },
  })
  const ambiguous = start.isError && isAmbiguousAnalysisError(start.error)
  const blocked = start.isError && !ambiguous
  const begin = (
    selection: AnalysisSelection,
    label: string,
    count: number,
  ) => {
    if (confirmation) {
      setConfirmationOpen(true)
      return
    }
    if (!settings.data || !provider.data?.has_api_key) return
    start.reset()
    setFeedback(null)
    setConfirmation({
      settings: settings.data,
      provider: { ...provider.data },
      label,
      count,
      request: {
        request_id: crypto.randomUUID(),
        configuration_revision: provider.data.revision,
        initial_prompt_version_id: settings.data.initial_prompt.id,
        report_prompt_version_id: settings.data.report_prompt.id,
        force_refresh: selection.kind === 'reanalysis',
        selection,
      },
    })
    setConfirmationOpen(true)
  }
  const analyseResult = (result: SharedResult) => {
    const kind =
      result.analysis_state === 'never_started' ||
      result.analysis_state === 'pending_new'
        ? 'explicit'
        : result.analysis_state === 'completed' ||
            result.analysis_state === 'legacy_completed'
          ? 'reanalysis'
          : 'retry'
    begin(
      { kind, result_ids: [result.id] },
      kind === 'explicit'
        ? '初步分析此条'
        : kind === 'reanalysis'
          ? '重新获取并分析此条'
          : '重试此条初步分析',
      1,
    )
  }
  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (!value || value === 'all') next.delete(key)
    else next.set(key, value)
    next.delete('offset')
    setParams(next)
  }
  const selectResult = (id: number) => {
    const next = new URLSearchParams(params)
    next.set('result', String(id))
    for (const key of [
      'attempt',
      'attempt_offset',
      'origin_offset',
      'legacy_offset',
    ])
      next.delete(key)
    setParams(next)
  }
  const canStart =
    Boolean(settings.data && provider.data?.has_api_key) && !start.isPending
  const retryRead = () => {
    void client.invalidateQueries({ queryKey: RESULTS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: CONTENT_ANALYSES_QUERY_KEY })
    void settings.refetch()
    void provider.refetch()
    void client.invalidateQueries({ queryKey: CONTENT_ANALYSIS_JOBS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
  }
  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="space-y-4 p-4 sm:p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h2 className="font-display text-2xl">内容与分析</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                这里汇集采集到的原文和分析结果。分析仅供参考，地点线索和来源说法仍需核实。
              </p>
            </div>
            <Button
              variant="outline"
              className="min-h-11 shrink-0"
              onClick={retryRead}
              disabled={
                results.isFetching || settings.isFetching || provider.isFetching
              }
            >
              <RefreshCw aria-hidden />
              刷新
            </Button>
          </div>
          <div className="flex flex-col gap-3 rounded-lg bg-secondary/55 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-medium">
                全库待首次分析：{results.data?.eligible_count ?? '—'} 条
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                包含历史内容；已处理、失败或正在处理的内容不会重复提交。
                {results.data?.active_count
                  ? ` 另有 ${results.data.active_count} 条正在处理。`
                  : ''}
              </p>
            </div>
            <Button
              className="min-h-11 shrink-0"
              disabled={
                !canStart ||
                (!confirmation &&
                  (!results.data || results.data.eligible_count === 0))
              }
              onClick={() =>
                begin(
                  { kind: 'all_never_started' },
                  '一键初步分析全部未分析内容',
                  results.data?.eligible_count ?? 0,
                )
              }
            >
              {confirmation ? '继续确认上次请求' : '一键初步分析'}
            </Button>
          </div>
          {provider.data?.has_api_key && (
            <p className="text-xs leading-5 [overflow-wrap:anywhere] text-muted-foreground">
              已保存模型：{provider.data.model} · {provider.data.base_url}。
              初步分析会发送正文和媒体，并消耗 API
              额度；手动分析不会自动生成报告。
            </p>
          )}
          {provider.data && !provider.data.has_api_key && (
            <Link
              className={buttonVariants({ variant: 'link' })}
              to="/ai-settings"
            >
              先保存 AI 配置，再进行初步分析
            </Link>
          )}
          {(settings.isError || provider.isError) && (
            <p role="alert" className="text-sm text-destructive">
              无法读取已保存的提示词或模型配置，暂不能提交分析。请刷新后重试。
            </p>
          )}
          {feedback && (
            <p role="status" className="text-sm">
              {feedback}
            </p>
          )}
        </CardContent>
      </Card>
      {settings.data && (
        <ResultsSettings settings={settings.data} provider={provider.data} />
      )}
      <Card>
        <CardContent className="space-y-4 p-4 sm:p-5">
          <h2
            ref={resultsHeading}
            tabIndex={-1}
            className="font-display text-xl outline-none"
          >
            全部采集结果
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="result-platform">平台</Label>
              <Select
                value={filters.platform ?? 'all'}
                onValueChange={(value) =>
                  updateFilter('platform', value ?? 'all')
                }
              >
                <SelectTrigger id="result-platform" className="min-h-11 w-full">
                  <SelectValue>
                    {filters.platform
                      ? searchPlatformPresenters[filters.platform].label
                      : '全部平台'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部平台</SelectItem>
                  {SEARCH_PLATFORM_ORDER.map((platform) => (
                    <SelectItem key={platform} value={platform}>
                      {searchPlatformPresenters[platform].label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="result-state">初步分析状态</Label>
              <Select
                value={filters.state ?? 'all'}
                onValueChange={(value) => updateFilter('state', value ?? 'all')}
              >
                <SelectTrigger id="result-state" className="min-h-11 w-full">
                  <SelectValue>
                    {filters.state
                      ? resultStateLabels[filters.state]
                      : '全部状态'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部状态</SelectItem>
                  {resultStateSchema.options.map((state) => (
                    <SelectItem key={state} value={state}>
                      {resultStateLabels[state]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="result-from">首次发现开始日期</Label>
              <Input
                id="result-from"
                className="min-h-11"
                type="date"
                value={params.get('from') ?? ''}
                onChange={(event) => updateFilter('from', event.target.value)}
                aria-describedby="result-date-help"
                aria-invalid={invalidInterval}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="result-to">首次发现结束日期</Label>
              <Input
                id="result-to"
                className="min-h-11"
                type="date"
                value={params.get('to') ?? ''}
                onChange={(event) => updateFilter('to', event.target.value)}
                aria-describedby="result-date-help"
                aria-invalid={invalidInterval}
              />
            </div>
          </div>
          <p id="result-date-help" className="text-xs text-muted-foreground">
            按首次发现时间筛选，结束日期当天也包含在内。
          </p>
          {invalidInterval && (
            <p role="alert" className="text-sm text-destructive">
              首次发现时间范围不正确，请检查日期及先后顺序。
            </p>
          )}
          {!invalidInterval && results.isPending && (
            <p role="status" className="text-sm">
              正在读取采集结果…
            </p>
          )}
          {results.isError && (
            <p role="alert" className="text-sm text-destructive">
              {analysisErrorMessage(results.error)}
            </p>
          )}
          {!invalidInterval && results.data?.items.length === 0 && (
            <p className="py-6 text-sm text-muted-foreground">
              当前范围没有结果。请调整筛选条件，或先去采集内容。
            </p>
          )}
          {!invalidInterval && (
            <div className="divide-y">
              {results.data?.items.map((result) => (
                <article key={result.id} className="py-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">
                          {
                            searchPlatformPresenters[result.source.platform]
                              .label
                          }
                        </Badge>
                        <Badge
                          variant={
                            result.analysis_state === 'completed'
                              ? 'secondary'
                              : 'outline'
                          }
                        >
                          {resultStateLabels[result.analysis_state]}
                        </Badge>
                      </div>
                      <h3 className="text-base font-semibold [overflow-wrap:anywhere]">
                        {result.source.title}
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        首次发现 {formatEvidenceDate(result.first_seen_at)} ·{' '}
                        被采集 {result.origin_count} 次
                      </p>
                      <p className="text-sm text-muted-foreground">
                        原文发布时间：
                        {result.source.published_at_text || '未知'}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <Button
                        ref={(element) => {
                          if (element)
                            resultButtons.current.set(result.id, element)
                          else resultButtons.current.delete(result.id)
                        }}
                        variant={
                          result.id === resultId ? 'secondary' : 'outline'
                        }
                        className="min-h-11"
                        onClick={() => selectResult(result.id)}
                        aria-label={`查看内容与分析：${result.source.title}`}
                      >
                        查看内容与分析
                      </Button>
                      <ResultSourceLink
                        source={result.source}
                        controls={controls}
                        disabled={isActiveResult(result)}
                      />
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
          {!invalidInterval && results.data && (
            <ResultsPagination
              label="采集结果"
              offset={filters.offset}
              limit={RESULT_PAGE_SIZE}
              total={results.data.total}
              onChange={(value) => {
                const next = new URLSearchParams(params)
                next.set('offset', String(value))
                setParams(next)
              }}
            />
          )}
        </CardContent>
      </Card>
      {resultId !== null && (
        <ResultEvidence
          key={resultId}
          resultId={resultId}
          controls={controls}
          onAnalyse={analyseResult}
          actionPending={!canStart || confirmation !== null}
          onClose={() => {
            const next = new URLSearchParams(params)
            next.delete('result')
            next.delete('attempt')
            setParams(next)
            const target =
              resultButtons.current.get(resultId) ?? resultsHeading.current
            target?.focus()
          }}
        />
      )}
      <ResultsJobs settings={settings.data} provider={provider.data} />
      {confirmation && confirmationOpen && (
        <ResultsConfirmation
          confirmation={confirmation}
          pending={start.isPending}
          ambiguous={ambiguous}
          blocked={blocked}
          error={start.isError ? analysisErrorMessage(start.error) : null}
          onClose={() => {
            setConfirmationOpen(false)
            if (!ambiguous) {
              setConfirmation(null)
              start.reset()
            }
          }}
          onConfirm={() => start.mutate(confirmation.request)}
          onReconfirm={() => {
            setConfirmation(null)
            setConfirmationOpen(false)
            start.reset()
            retryRead()
          }}
        />
      )}
    </div>
  )
}
