import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { analysisErrorMessage } from '@/lib/api/analysis-shared'
import { mediaIssueLabels } from '@/lib/media-presenters'
import { OriginalMediaCache } from '@/routes/original-media-cache'
import {
  ANALYSIS_PAGE_SIZE,
  CONTENT_ANALYSES_QUERY_KEY,
  CONTENT_ANALYSIS_JOBS_QUERY_KEY,
  fetchAnalysisAttempt,
  fetchAnalysisJob,
  fetchResultAnalyses,
  isActiveAnalysisAttempt,
  type AnalysisAttempt,
  type AnalysisJob,
} from '@/lib/api/content-analyses'
import {
  fetchResult,
  fetchResultLegacyAnalyses,
  fetchResultOrigins,
  isActiveResult,
  readId,
  readOffset,
  RESULTS_QUERY_KEY,
  type SharedResult,
} from '@/lib/api/results'
import {
  resultStateLabels,
  ResultSourceLink,
  ResultsPagination,
  formatEvidenceDate,
} from '@/routes/results-presenters'
import {
  searchPlatformPresenters,
  searchRunStatusLabel,
} from '@/routes/search-run-presenters'

export function FrozenAnalysisPrompts({ job }: { job: AnalysisJob }) {
  const sourceLabel = (prompt: AnalysisJob['initial_prompt']) => {
    if (prompt.mode === 'legacy')
      return `历史共享提示词 · 版本 ${prompt.version_id ?? prompt.id}`
    if (prompt.mode === 'custom')
      return `本次自定义提示词 · 版本 ${prompt.version_id ?? prompt.id}`
    return `系统默认模板 · 版本 ${prompt.version_id ?? prompt.id}`
  }
  return (
    <details className="rounded-lg border p-3">
      <summary className="min-h-8 cursor-pointer text-sm font-medium">
        本任务使用的提示词与模型
      </summary>
      <p className="mt-3 text-sm [overflow-wrap:anywhere]">
        {job.model} · {job.base_url}
      </p>
      {[job.initial_prompt, job.report_prompt].map((prompt) => (
        <section key={prompt.stage} className="mt-4">
          <h4 className="text-sm font-medium">
            {prompt.stage === 'initial' ? '内容理解' : '报告生成'}提示词
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">
            {sourceLabel(prompt)}
          </p>
          <p className="mt-2 text-sm leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap">
            {prompt.instructions}
          </p>
        </section>
      ))}
    </details>
  )
}

export function SavedAnalysisEvidence({
  attempt,
}: {
  attempt: AnalysisAttempt
}) {
  const output = attempt.output
  return (
    <article className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Badge variant={output ? 'secondary' : 'outline'}>
            {resultStateLabels[attempt.status]}
          </Badge>
          <h3 className="mt-2 text-base font-medium [overflow-wrap:anywhere]">
            {attempt.source.title}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            第 {attempt.id} 次分析 · 首次发现{' '}
            {formatEvidenceDate(attempt.first_seen_at)}
          </p>
        </div>
        <ResultSourceLink source={attempt.source} />
      </div>
      {attempt.error && (
        <p role="status" className="rounded-lg bg-muted p-3 text-sm leading-6">
          {attempt.error.message} 此状态不代表内容与主题无关。
        </p>
      )}
      {output ? (
        <div className="space-y-4 text-sm leading-7 [overflow-wrap:anywhere]">
          <p className="text-xs text-muted-foreground">
            以下为模型对原始内容的理解，保留来源说法和不确定性，不是已经核实的事实。
          </p>
          <section>
            <h4 className="font-medium">内容理解</h4>
            <p className="mt-1 whitespace-pre-wrap">{output.summary}</p>
          </section>
          <section>
            <h4 className="font-medium">地点线索</h4>
            {output.location_clues.length > 0 ? (
              <ul className="mt-1 space-y-2">
                {output.location_clues.map((clue, index) => (
                  <li key={index} className="border-l-2 border-primary/30 pl-3">
                    <span className="mr-2 text-xs text-muted-foreground">
                      {
                        {
                          text: '文字',
                          image: '图片',
                          video: '视频',
                          audio: '音频',
                        }[clue.modality]
                      }
                    </span>
                    <span className="whitespace-pre-wrap">{clue.excerpt}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-muted-foreground">
                没有足以保存的明确地点线索。
              </p>
            )}
          </section>
          <section>
            <h4 className="font-medium">时间背景</h4>
            <p className="mt-1 whitespace-pre-wrap">{output.time_context}</p>
          </section>
          <section>
            <h4 className="font-medium">媒体观察</h4>
            {output.media_observations.length ? (
              <ul className="mt-1 list-inside list-disc space-y-1">
                {output.media_observations.map((text, index) => (
                  <li key={index} className="whitespace-pre-wrap">
                    {text}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-muted-foreground">没有额外媒体观察。</p>
            )}
          </section>
          <section className="rounded-lg bg-secondary/60 p-3">
            <h4 className="font-medium">仍不确定的内容</h4>
            <p className="mt-1 whitespace-pre-wrap">{output.uncertainties}</p>
          </section>
        </div>
      ) : (
        !attempt.error && (
          <p className="text-sm text-muted-foreground">
            尚无成功保存的单条总结；已有原始采集结果不受影响。
          </p>
        )
      )}
      <p className="text-xs text-muted-foreground">
        {attempt.reused_from_attempt_id !== null
          ? `沿用第 ${attempt.reused_from_attempt_id} 次分析；本次未重复计入用量。`
          : attempt.attempted
            ? attempt.usage
              ? `本次 ${attempt.usage.total_tokens.toLocaleString('zh-CN')} Token`
              : '本次已尝试调用模型，Token 用量未知。'
            : '本次尚未调用模型。'}
      </p>
      {attempt.input && (
        <details className="rounded-lg border p-3">
          <summary className="min-h-8 cursor-pointer text-sm font-medium">
            正文和媒体信息
          </summary>
          <dl className="my-3 grid gap-2 text-sm sm:grid-cols-2">
            {attempt.input.coverage && (
              <div>
                <dt className="text-muted-foreground">内容来源</dt>
                <dd>
                  {
                    {
                      search_preview: '搜索摘要',
                      detail_text: '详情文字',
                      validated_media: '已确认媒体',
                      full_source: '完整内容',
                    }[attempt.input.coverage.level]
                  }
                </dd>
              </div>
            )}
            <div>
              <dt className="text-muted-foreground">正文完整度</dt>
              <dd>
                {
                  { complete: '完整', partial: '部分', unavailable: '没有' }[
                    attempt.input.text.coverage
                  ]
                }
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">媒体清单</dt>
              <dd>
                {attempt.input.media_inventory_complete
                  ? '已确认范围'
                  : '仍有未确认媒体'}{' '}
                · {attempt.input.assets.length} 项
              </dd>
            </div>
          </dl>
          {attempt.input.coverage && (
            <p className="text-sm text-muted-foreground">
              文字来自：
              {attempt.input.coverage.text_origin === 'search_preview'
                ? '搜索结果标题/摘要'
                : '详情页'}
              {' · '}图片已获取 {attempt.input.coverage.image.ready}/
              {attempt.input.coverage.image.expected}，视频已获取{' '}
              {attempt.input.coverage.video.ready}/
              {attempt.input.coverage.video.expected}，音频已确认{' '}
              {attempt.input.coverage.audio.ready}/
              {attempt.input.coverage.audio.expected}
              {attempt.input.coverage.image.unknown +
                attempt.input.coverage.video.unknown +
                attempt.input.coverage.audio.unknown >
              0
                ? '；还有媒体未确认'
                : ''}
            </p>
          )}
          <p className="text-sm font-medium [overflow-wrap:anywhere] whitespace-pre-wrap">
            {attempt.input.text.title}
          </p>
          <p className="mt-2 text-sm leading-7 [overflow-wrap:anywhere] whitespace-pre-wrap">
            {attempt.input.text.body || '未保存正文。'}
          </p>
          {attempt.input.issues.length > 0 && (
            <p className="mt-3 text-sm text-warning-foreground">
              这条内容有 {attempt.input.issues.length}{' '}
              处信息不完整，不能当作完整内容理解。
            </p>
          )}
          {attempt.input.assets.length > 0 && (
            <ul className="mt-3 divide-y text-sm">
              {attempt.input.assets.map((asset) => (
                <li key={asset.position} className="py-2">
                  {asset.position + 1}.{' '}
                  {asset.kind === 'image' ? '图片' : '视频'} ·{' '}
                  {
                    {
                      ready: '已获取',
                      unavailable: '不可用',
                      unsupported: '暂不支持',
                      failed: '获取失败',
                    }[asset.status]
                  }{' '}
                  · 信息完整度
                  {
                    { complete: '完整', partial: '部分', unknown: '未知' }[
                      asset.coverage
                    ]
                  }
                  {asset.kind === 'video' &&
                    ` · 音轨${{ present: '存在', absent: '缺失', unknown: '未知', not_applicable: '不适用' }[asset.audio_track]}`}
                  {asset.issue_code &&
                    ` · ${mediaIssueLabels[asset.issue_code]}`}
                </li>
              ))}
            </ul>
          )}
          {attempt.input.assets.some((asset) => asset.kind === 'video') && (
            <p className="mt-2 text-xs text-muted-foreground">
              当前视频范围：单帖最多 1 段、30 秒，MP4（H.264 画面及 AAC 音轨），
              最高约 1080p；图片和视频合计不超过 6 MiB。超出范围会保留缺失原因，
              不以封面代替视频，不自动转码或抽帧。
            </p>
          )}
          {attempt.attempted && !attempt.reused_from_attempt_id && (
            <p className="mt-3 text-xs text-muted-foreground">
              本次提交模型：
              {
                attempt.input.assets.filter(
                  (asset) => asset.kind === 'image' && asset.status === 'ready',
                ).length
              }{' '}
              张图片，
              {
                attempt.input.assets.filter(
                  (asset) => asset.kind === 'video' && asset.status === 'ready',
                ).length
              }{' '}
              段视频。
              已提交的媒体未在本机抽样或缩小；这不表示模型已完整识别所有细节。
            </p>
          )}
          {attempt.input.assets.length > 0 && (
            <OriginalMediaCache key={attempt.id} attemptId={attempt.id} />
          )}
        </details>
      )}
    </article>
  )
}

export function ResultEvidence({
  resultId,
  onSelect,
  selected,
  onClose,
  asSheet = false,
  selectionEnabled = true,
  closeLabel = '关闭详情',
}: {
  resultId: number
  onSelect: (result: SharedResult) => void
  selected: boolean
  onClose: () => void
  asSheet?: boolean
  selectionEnabled?: boolean
  closeLabel?: string
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [params, setParams] = useSearchParams()
  const offset = readOffset(params.get('attempt_offset'))
  const originOffset = readOffset(params.get('origin_offset'))
  const legacyOffset = readOffset(params.get('legacy_offset'))
  const requestedAttempt = readId(params.get('attempt'))
  useEffect(() => {
    const timer = window.setTimeout(() => {
      heading.current?.focus({ preventScroll: true })
      heading.current?.scrollIntoView?.({ block: 'start', behavior: 'instant' })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [resultId, requestedAttempt])
  const change = (key: string, value: number | null) => {
    const next = new URLSearchParams(params)
    if (value === null || value === 0) next.delete(key)
    else next.set(key, String(value))
    setParams(next)
  }
  const resultQuery = useQuery({
    queryKey: [...RESULTS_QUERY_KEY, resultId],
    queryFn: ({ signal }) => fetchResult(resultId, signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveResult(query.state.data) ? 1000 : false,
  })
  const active = resultQuery.data ? isActiveResult(resultQuery.data) : false
  const history = useQuery({
    queryKey: [...CONTENT_ANALYSES_QUERY_KEY, 'result', resultId, offset],
    queryFn: ({ signal }) => fetchResultAnalyses(resultId, signal, offset),
    retry: false,
    refetchInterval: active ? 1000 : false,
  })
  const wasActive = useRef(false)
  useEffect(() => {
    if (wasActive.current && !active) void history.refetch()
    wasActive.current = active
  }, [active, history.refetch])
  const origins = useQuery({
    queryKey: [...RESULTS_QUERY_KEY, resultId, 'origins', originOffset],
    queryFn: ({ signal }) => fetchResultOrigins(resultId, signal, originOffset),
    retry: false,
  })
  const legacy = useQuery({
    queryKey: [...RESULTS_QUERY_KEY, resultId, 'legacy', legacyOffset],
    queryFn: ({ signal }) =>
      fetchResultLegacyAnalyses(resultId, signal, legacyOffset),
    retry: false,
  })
  const attemptQuery = useQuery({
    queryKey: [...CONTENT_ANALYSES_QUERY_KEY, requestedAttempt],
    queryFn: ({ signal }) =>
      fetchAnalysisAttempt(requestedAttempt ?? 0, signal),
    enabled: requestedAttempt !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveAnalysisAttempt(query.state.data.status)
        ? 1000
        : false,
  })
  const attempt =
    requestedAttempt === null ? history.data?.items[0] : attemptQuery.data
  const validAttempt =
    attempt?.source.result_id === resultId ? attempt : undefined
  const jobQuery = useQuery({
    queryKey: [...CONTENT_ANALYSIS_JOBS_QUERY_KEY, validAttempt?.job_id],
    queryFn: ({ signal }) =>
      fetchAnalysisJob(validAttempt?.job_id ?? 0, signal),
    enabled: validAttempt !== undefined,
    retry: false,
  })
  const result = resultQuery.data
  const panel = (
    <Card id="result-evidence">
      <CardHeader className="border-b">
        <div className="flex items-start justify-between gap-3">
          <h2
            ref={heading}
            tabIndex={-1}
            className="font-display text-xl outline-none"
          >
            来源与单条总结
          </h2>
          <Button variant="ghost" className="min-h-11" onClick={onClose}>
            {closeLabel}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pt-5">
        {resultQuery.isPending && <p role="status">正在读取内容…</p>}
        {resultQuery.isError && (
          <p role="alert" className="text-sm text-destructive">
            {analysisErrorMessage(resultQuery.error)}
          </p>
        )}
        {result && (
          <section className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">
                {searchPlatformPresenters[result.source.platform].label}
              </Badge>
              <Badge variant="outline">
                {resultStateLabels[result.analysis_state]}
              </Badge>
            </div>
            <h3 className="text-base font-semibold [overflow-wrap:anywhere]">
              {result.source.title}
            </h3>
            <p className="text-sm leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap">
              {result.source.snippet}
            </p>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">
                  首次发现时间 · 北京时间
                </dt>
                <dd className="mt-1">
                  {formatEvidenceDate(result.first_seen_at)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">原文显示的发布时间</dt>
                <dd className="mt-1">
                  {result.source.published_at_text || '未知'}
                  （平台显示时间可能与首次发现时间不同）
                </dd>
              </div>
            </dl>
            <div className="flex flex-wrap gap-3">
              <ResultSourceLink source={result.source} />
              {selectionEnabled && (
                <Button
                  variant="outline"
                  className="min-h-11"
                  disabled={selected || active}
                  onClick={() => onSelect(result)}
                >
                  {active
                    ? '此条正在处理中'
                    : selected
                      ? '已选入本次报告'
                      : '选入本次报告'}
                </Button>
              )}
            </div>
            {result.legacy_count > 0 && (
              <p className="text-sm text-muted-foreground">
                旧版结果只适用于当时的监控范围，不能替代现在的分析。历史版本仍可查看。
              </p>
            )}
          </section>
        )}
        <section aria-label="单条总结记录" className="space-y-3 border-t pt-4">
          <h3 className="font-medium">总结记录</h3>
          {history.isPending && (
            <p role="status" className="text-sm">
              正在读取总结记录…
            </p>
          )}
          {history.isError && (
            <p role="alert" className="text-sm text-destructive">
              {analysisErrorMessage(history.error)}
            </p>
          )}
          {history.data?.total === 0 && (
            <p className="text-sm text-muted-foreground">还没有单条总结。</p>
          )}
          <div className="flex flex-wrap gap-2">
            {history.data?.items.map((item) => (
              <Button
                key={item.id}
                variant={validAttempt?.id === item.id ? 'secondary' : 'outline'}
                className="min-h-11"
                aria-pressed={validAttempt?.id === item.id}
                onClick={() => change('attempt', item.id)}
              >
                第 {item.id} 次 · {resultStateLabels[item.status]}
              </Button>
            ))}
          </div>
          {history.data && history.data.total > ANALYSIS_PAGE_SIZE && (
            <ResultsPagination
              label="总结记录"
              offset={offset}
              limit={ANALYSIS_PAGE_SIZE}
              total={history.data.total}
              onChange={(value) => {
                const next = new URLSearchParams(params)
                next.delete('attempt')
                next.set('attempt_offset', String(value))
                setParams(next)
              }}
            />
          )}
          {attemptQuery.isError && (
            <p role="alert" className="text-sm text-destructive">
              {analysisErrorMessage(attemptQuery.error)}
            </p>
          )}
          {attempt && !validAttempt && (
            <p role="alert" className="text-sm text-destructive">
              这条分析不属于当前内容，无法显示。
            </p>
          )}
          {validAttempt && <SavedAnalysisEvidence attempt={validAttempt} />}
          {jobQuery.isError && (
            <p role="alert" className="text-sm text-destructive">
              无法读取本次分析使用的提示词。
              {analysisErrorMessage(jobQuery.error)}
            </p>
          )}
          {jobQuery.data && <FrozenAnalysisPrompts job={jobQuery.data} />}
        </section>
        <details className="rounded-lg border p-3">
          <summary className="min-h-8 cursor-pointer font-medium">
            发现来源 · {result?.origin_count ?? '…'} 次
          </summary>
          {origins.isError && (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {analysisErrorMessage(origins.error)}
            </p>
          )}
          <ul className="divide-y">
            {origins.data?.items.map((origin) => (
              <li key={origin.source_run_id} className="py-3 text-sm">
                <Link
                  className="font-medium underline underline-offset-4"
                  to={`/collection-runs/${origin.source_run_id}`}
                >
                  {origin.rule_name} · 采集 {origin.source_run_id}
                </Link>
                <p className="mt-1 text-muted-foreground">
                  {searchRunStatusLabel(origin.status)} ·{' '}
                  {origin.discovery_kind === 'new' ? '首次发现' : '再次命中'} ·{' '}
                  {formatEvidenceDate(origin.first_observed_at)}
                </p>
                <p className="mt-1 [overflow-wrap:anywhere]">
                  命中词：{origin.matched_terms.join('、')}
                </p>
              </li>
            ))}
          </ul>
          {origins.data && origins.data.total > ANALYSIS_PAGE_SIZE && (
            <ResultsPagination
              label="采集来源"
              offset={originOffset}
              limit={ANALYSIS_PAGE_SIZE}
              total={origins.data.total}
              onChange={(value) => change('origin_offset', value)}
            />
          )}
        </details>
        <details className="rounded-lg border p-3">
          <summary className="min-h-8 cursor-pointer font-medium">
            旧版分析和报告 · {result?.legacy_count ?? '…'} 条
          </summary>
          {legacy.isError && (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {analysisErrorMessage(legacy.error)}
            </p>
          )}
          {legacy.data?.total === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              没有旧版分析记录。
            </p>
          )}
          <ul className="divide-y">
            {legacy.data?.items.map((item) => (
              <li key={item.item_id} className="py-3 text-sm">
                <Link
                  className={buttonVariants({ variant: 'link' })}
                  to={`/collection-runs/${item.source_run_id}?summary=${item.summary_id}`}
                >
                  查看旧版报告 {item.summary_id}
                </Link>
                <p className="text-muted-foreground">
                  旧版分析 {item.item_id} ·{' '}
                  {item.status === 'completed'
                    ? '已完成相关性判断'
                    : '旧版未完成'}
                  {item.reused_from_item_id !== null
                    ? ` · 沿用旧版 ${item.reused_from_item_id}`
                    : ''}
                </p>
              </li>
            ))}
          </ul>
          {legacy.data && legacy.data.total > ANALYSIS_PAGE_SIZE && (
            <ResultsPagination
              label="旧版分析"
              offset={legacyOffset}
              limit={ANALYSIS_PAGE_SIZE}
              total={legacy.data.total}
              onChange={(value) => change('legacy_offset', value)}
            />
          )}
        </details>
      </CardContent>
    </Card>
  )
  if (!asSheet) return panel
  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-2xl"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>内容详情</SheetTitle>
          <SheetDescription>
            查看正文、媒体、总结、来源和历史处理记录。
          </SheetDescription>
        </SheetHeader>
        {panel}
      </SheetContent>
    </Sheet>
  )
}
