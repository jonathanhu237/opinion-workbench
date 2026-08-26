import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink, LoaderCircle, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchRun, useSearchRunResults } from '@/hooks/use-search-runs'
import {
  cancelSearchRun,
  isActiveSearchRun,
  openSearchRunResult,
  SEARCH_RUNS_QUERY_KEY,
  SearchRunApiError,
  type SearchResult,
  type SearchResultFilter,
  type SearchResultOpenOutcome,
} from '@/lib/api/search-runs'
import {
  formatLocalDate,
  searchPlatformPresenters,
  searchRunStatusGuidance,
  searchRunStatusLabel,
} from '@/routes/search-run-presenters'
import { cn } from '@/lib/utils'

const RESULT_LIMIT = 50

function cancelErrorMessage(error: unknown) {
  return error instanceof SearchRunApiError
    ? error.message
    : '取消任务失败，请重新尝试。'
}

const openOutcomeMessages: Record<SearchResultOpenOutcome, string> = {
  opened: '已在谷歌浏览器打开',
  content_not_found: '当前搜索中没有找到这条内容，请重新采集后再试。',
  content_unavailable: '这条内容暂时无法查看，可能已被删除或设为不可见。',
  login_required: '请先在当前谷歌浏览器中登录小红书，然后重试。',
  manual_challenge_required: '请在谷歌浏览器中完成小红书安全验证，然后重试。',
  platform_blocked_or_rate_limited: '小红书暂时限制了访问，请稍后再试。',
  structure_changed: '小红书页面发生变化，暂时无法打开这条内容。',
  browser_unavailable: '无法连接谷歌浏览器，请确认远程调试已开启。',
  internal_error: '打开失败，请稍后重试。',
}

function openErrorMessage(error: unknown) {
  return error instanceof SearchRunApiError
    ? error.message
    : '打开原文时发生未知错误，请稍后重试。'
}

function parseRunId(value: string | undefined) {
  if (value === undefined || !/^\d+$/u.test(value)) return null
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

function parseFilter(value: string | null): SearchResultFilter {
  return value === 'new' || value === 'repeated' ? value : 'all'
}

function parseOffset(value: string | null) {
  if (value === null || !/^\d+$/u.test(value)) return 0
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0
}

function ResultRecord({
  result,
  openPending,
  activeOpenResultId,
  openFeedback,
  onOpen,
}: {
  result: SearchResult
  openPending: boolean
  activeOpenResultId: number | null
  openFeedback: string | null
  onOpen: (resultId: number) => void
}) {
  const isNew = result.kind === 'new'
  const isActiveOpen = openPending && activeOpenResultId === result.id

  return (
    <article
      className={`border-l-4 px-4 py-5 sm:px-5 ${isNew ? 'border-l-live' : 'border-l-warning'}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <Badge variant={isNew ? 'secondary' : 'outline'}>
            {isNew ? '新增' : '历史内容再次命中'}
          </Badge>
          <h3 className="mt-2 text-base leading-7 font-semibold text-foreground">
            {result.title}
          </h3>
          {result.snippet && (
            <p className="mt-1 line-clamp-3 text-sm leading-6 text-muted-foreground">
              {result.snippet}
            </p>
          )}
        </div>
        {result.platform === 'xhs' ? (
          <div className="shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 w-full sm:min-h-8"
              disabled={openPending}
              aria-busy={isActiveOpen}
              onClick={() => onOpen(result.id)}
            >
              {isActiveOpen ? '正在打开…' : '打开原文'}
              <ExternalLink aria-hidden />
            </Button>
            <p
              className="mt-1 max-w-64 text-sm text-muted-foreground"
              aria-live="polite"
            >
              {openFeedback}
            </p>
          </div>
        ) : (
          <a
            href={result.content_url}
            target="_blank"
            rel="noreferrer"
            className={cn(
              buttonVariants({ variant: 'outline', size: 'sm' }),
              'min-h-11 shrink-0 sm:min-h-8',
            )}
          >
            打开原文
            <ExternalLink aria-hidden />
          </a>
        )}
      </div>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted-foreground">命中搜索词</dt>
          <dd className="mt-1 flex flex-wrap gap-1.5">
            {result.matched_terms.map((term) => (
              <Badge key={term} variant="outline" className="font-normal">
                {term}
              </Badge>
            ))}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">平台显示时间</dt>
          <dd className="mt-1">{result.published_at_text || '未显示'}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">发现时间</dt>
          <dd className="mt-1">
            首次 {formatLocalDate(result.first_seen_at)} · 最近{' '}
            {formatLocalDate(result.last_seen_at)}
          </dd>
        </div>
      </dl>
    </article>
  )
}

export function CollectionRunDetail() {
  const runId = parseRunId(useParams().runId)
  const [searchParams, setSearchParams] = useSearchParams()
  const filter = parseFilter(searchParams.get('kind'))
  const offset = parseOffset(searchParams.get('offset'))
  const queryClient = useQueryClient()
  const runQuery = useSearchRun(runId)
  const active = runQuery.data ? isActiveSearchRun(runQuery.data.status) : false
  const resultsQuery = useSearchRunResults(runId, filter, active, offset)
  const previousRunState = useRef({ runId, active })
  const [openFeedback, setOpenFeedback] = useState<{
    resultId: number
    message: string
  } | null>(null)
  useEffect(() => {
    const previous = previousRunState.current
    previousRunState.current = { runId, active }
    if (
      previous.runId === runId &&
      previous.active &&
      !active &&
      runId !== null
    ) {
      void queryClient.invalidateQueries({
        queryKey: [...SEARCH_RUNS_QUERY_KEY, runId, 'results'],
      })
    }
  }, [active, queryClient, runId])
  const cancelMutation = useMutation({
    mutationFn: () => cancelSearchRun(runId ?? 0),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: SEARCH_RUNS_QUERY_KEY })
    },
  })
  const openMutation = useMutation({
    mutationFn: (resultId: number) => openSearchRunResult(runId ?? 0, resultId),
    onMutate: (resultId) => {
      setOpenFeedback(null)
      return { resultId }
    },
    onSuccess: (response, resultId) => {
      setOpenFeedback({
        resultId,
        message: openOutcomeMessages[response.outcome],
      })
    },
    onError: (error, resultId) => {
      setOpenFeedback({ resultId, message: openErrorMessage(error) })
    },
  })
  const activeOpenResultId = openMutation.isPending
    ? openMutation.variables
    : null

  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams)
    if (nextOffset === 0) next.delete('offset')
    else next.set('offset', String(nextOffset))
    setSearchParams(next)
  }

  if (runId === null) {
    return (
      <Card>
        <CardContent className="p-8 text-center" role="alert">
          <p className="font-medium">采集任务地址不正确</p>
          <Link
            className={cn(buttonVariants({ variant: 'outline' }), 'mt-4')}
            to="/collection-runs"
          >
            返回采集任务
          </Link>
        </CardContent>
      </Card>
    )
  }

  if (runQuery.isPending) {
    return (
      <div className="space-y-4" aria-label="正在加载采集任务">
        <Skeleton className="h-9 w-40" />
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-52 w-full" />
      </div>
    )
  }

  if (runQuery.isError) {
    return (
      <Card>
        <CardContent className="p-8 text-center" role="alert">
          <p className="font-medium">采集任务暂时无法读取</p>
          <div className="mt-4 flex justify-center gap-2">
            <Link
              className={buttonVariants({ variant: 'outline' })}
              to="/collection-runs"
            >
              返回任务列表
            </Link>
            <Button onClick={() => runQuery.refetch()}>重新加载</Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  const run = runQuery.data
  const platform = searchPlatformPresenters[run.platform]
  const guidance = searchRunStatusGuidance(run.status, run.platform)
  const progress =
    run.current_term_position === null
      ? `正在连接${platform.label}…`
      : `第 ${run.current_term_position + 1} / ${run.term_count} 个搜索词`
  const results = resultsQuery.data?.results ?? []
  const resultTotal = resultsQuery.data?.total ?? 0
  const visibleResults = results

  return (
    <div className="space-y-5">
      <Link
        className={cn(
          buttonVariants({ variant: 'ghost' }),
          '-ml-2 min-h-11 sm:min-h-8',
        )}
        to="/collection-runs"
      >
        <ArrowLeft aria-hidden />
        返回任务列表
      </Link>

      <Card>
        <CardHeader className="border-b">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="flex items-center gap-1.5 text-xs tracking-wide text-muted-foreground">
                <img src={platform.logoSrc} alt="" className="size-4" />
                {platform.label} · 规则快照
              </p>
              <CardTitle className="mt-1 font-display text-2xl">
                {run.rule_name}
              </CardTitle>
            </div>
            <Badge variant={active ? 'default' : 'outline'}>
              {active && (
                <LoaderCircle
                  className="animate-spin motion-reduce:animate-none"
                  aria-hidden
                />
              )}
              {searchRunStatusLabel(run.status)}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          {active && (
            <div className="rounded-lg bg-secondary/55 p-4" aria-live="polite">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-medium">{progress}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    已发现 {run.total_count} 条内容
                  </p>
                </div>
                <Button
                  variant="outline"
                  className="min-h-11 sm:min-h-8"
                  disabled={cancelMutation.isPending}
                  onClick={() => cancelMutation.mutate()}
                >
                  <Square className="size-3" aria-hidden />
                  {cancelMutation.isPending ? '正在取消…' : '取消任务'}
                </Button>
              </div>
              {cancelMutation.isError && (
                <p className="mt-3 text-sm text-destructive" role="alert">
                  {cancelErrorMessage(cancelMutation.error)}
                </p>
              )}
            </div>
          )}

          {guidance && (
            <div
              className="rounded-lg border bg-muted/45 p-4 text-sm"
              role="status"
            >
              <p>{guidance}</p>
              {run.status === 'login_required' && (
                <Link
                  className={cn(
                    buttonVariants({ variant: 'outline', size: 'sm' }),
                    'mt-3',
                  )}
                  to="/platform-accounts"
                >
                  前往平台账号
                </Link>
              )}
            </div>
          )}

          <dl className="grid grid-cols-3 gap-3 rounded-lg border p-4 text-center">
            <div>
              <dt className="text-xs text-muted-foreground">新增</dt>
              <dd className="mt-1 text-xl font-semibold">{run.new_count}</dd>
            </div>
            <div className="border-x">
              <dt className="text-xs text-muted-foreground">再次命中</dt>
              <dd className="mt-1 text-xl font-semibold">
                {run.repeated_count}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">合计</dt>
              <dd className="mt-1 text-xl font-semibold">{run.total_count}</dd>
            </div>
          </dl>

          <div>
            <p className="text-xs text-muted-foreground">本次搜索词</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {run.terms.map((term) => (
                <Badge key={term} variant="outline">
                  {term}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <section aria-labelledby="collection-results-title">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2
            id="collection-results-title"
            className="font-display text-xl font-semibold"
          >
            采集结果
          </h2>
          <Tabs
            value={filter}
            onValueChange={(value) => {
              const next = new URLSearchParams(searchParams)
              if (value === 'all') next.delete('kind')
              else next.set('kind', value)
              next.delete('offset')
              setSearchParams(next)
            }}
          >
            <TabsList aria-label="筛选采集结果">
              <TabsTrigger value="all">全部 {run.total_count}</TabsTrigger>
              <TabsTrigger value="new">新增 {run.new_count}</TabsTrigger>
              <TabsTrigger value="repeated">
                再次命中 {run.repeated_count}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <Card className="overflow-hidden">
          <CardContent className="divide-y p-0">
            {resultsQuery.isPending ? (
              <div className="space-y-3 p-5" aria-label="正在加载采集结果">
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : resultsQuery.isError ? (
              <div className="p-8 text-center" role="alert">
                <p className="font-medium">采集结果暂时无法读取</p>
                <Button
                  className="mt-4"
                  variant="outline"
                  onClick={() => resultsQuery.refetch()}
                >
                  重新加载
                </Button>
              </div>
            ) : visibleResults.length === 0 ? (
              <div className="p-8 text-center">
                <p className="font-medium">当前筛选下没有结果</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {active
                    ? '采集仍在进行，结果会自动更新。'
                    : '可以切换筛选条件查看其他结果。'}
                </p>
              </div>
            ) : (
              visibleResults.map((result) => (
                <ResultRecord
                  key={result.id}
                  result={result}
                  openPending={openMutation.isPending}
                  activeOpenResultId={activeOpenResultId}
                  openFeedback={
                    openFeedback?.resultId === result.id
                      ? openFeedback.message
                      : null
                  }
                  onOpen={(resultId) => openMutation.mutate(resultId)}
                />
              ))
            )}
          </CardContent>
        </Card>

        {resultTotal > RESULT_LIMIT && (
          <div className="mt-4 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              disabled={offset === 0}
              onClick={() => changePage(Math.max(0, offset - RESULT_LIMIT))}
            >
              上一页
            </Button>
            <Button
              variant="outline"
              disabled={offset + RESULT_LIMIT >= resultTotal}
              onClick={() => changePage(offset + RESULT_LIMIT)}
            >
              下一页
            </Button>
          </div>
        )}
      </section>
    </div>
  )
}
