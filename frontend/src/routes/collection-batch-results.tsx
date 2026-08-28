import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchBatchResults } from '@/hooks/use-search-batches'
import {
  SEARCH_BATCHES_QUERY_KEY,
  type SearchBatchItem,
  type SearchBatchResult,
} from '@/lib/api/search-batches'
import {
  openSearchRunResult,
  type SearchResultFilter,
} from '@/lib/api/search-runs'
import { SearchResultRecord } from '@/routes/search-result-record'
import {
  openErrorMessage,
  openOutcomeMessages,
  searchPlatformPresenters,
} from '@/routes/search-run-presenters'

const RESULT_LIMIT = 50

export function CollectionBatchResults({
  batchId,
  item,
  browserBusy,
}: {
  batchId: number
  item: SearchBatchItem
  browserBusy: boolean
}) {
  const [params, setParams] = useSearchParams()
  const rawKind = params.get('kind')
  const kind: SearchResultFilter =
    rawKind === 'new' || rawKind === 'repeated' ? rawKind : 'all'
  const rawOffset = params.get('offset') ?? '0'
  const offset =
    /^\d+$/u.test(rawOffset) && Number.isSafeInteger(Number(rawOffset))
      ? Number(rawOffset)
      : 0
  const active = item.status === 'running'
  const resultsQuery = useSearchBatchResults(
    batchId,
    item.position,
    kind,
    offset,
    active,
  )
  const queryClient = useQueryClient()
  const wasActive = useRef(active)
  useEffect(() => {
    if (wasActive.current && !active) {
      void queryClient.invalidateQueries({
        queryKey: [
          ...SEARCH_BATCHES_QUERY_KEY,
          batchId,
          'items',
          item.position,
          'results',
        ],
      })
    }
    wasActive.current = active
  }, [active, batchId, item.position, queryClient])
  const [feedback, setFeedback] = useState<{
    resultId: number
    message: string
  } | null>(null)
  const openMutation = useMutation({
    mutationFn: (result: SearchBatchResult) =>
      openSearchRunResult(result.source_run_id, result.id),
    retry: false,
    onMutate: () => setFeedback(null),
    onSuccess: (response, result) =>
      setFeedback({
        resultId: result.id,
        message: openOutcomeMessages[response.outcome],
      }),
    onError: (error, result) =>
      setFeedback({ resultId: result.id, message: openErrorMessage(error) }),
  })
  function changePage(nextOffset: number) {
    const next = new URLSearchParams(params)
    next.set('platform', item.platform)
    if (nextOffset) next.set('offset', String(nextOffset))
    else next.delete('offset')
    setParams(next)
  }
  const total = resultsQuery.data?.total ?? 0
  return (
    <section id="batch-results" aria-labelledby="batch-results-title">
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2
            id="batch-results-title"
            className="font-display text-xl font-semibold"
          >
            {searchPlatformPresenters[item.platform].label} · 采集结果
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            合并该平台的全部尝试，重复内容只显示一次。
          </p>
        </div>
        <Tabs
          value={kind}
          onValueChange={(value) => {
            const next = new URLSearchParams(params)
            next.set('platform', item.platform)
            if (value === 'all') next.delete('kind')
            else next.set('kind', value)
            next.delete('offset')
            setParams(next)
          }}
        >
          <TabsList aria-label="筛选平台采集结果" className="h-auto flex-wrap">
            <TabsTrigger value="all">全部 {item.total_count}</TabsTrigger>
            <TabsTrigger value="new">新增 {item.new_count}</TabsTrigger>
            <TabsTrigger value="repeated">
              再次命中 {item.repeated_count}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <Card className="overflow-hidden">
        <CardContent className="divide-y p-0">
          {resultsQuery.isPending ? (
            <div className="space-y-3 p-5" aria-label="正在加载平台结果">
              <Skeleton className="h-32 w-full" />
            </div>
          ) : resultsQuery.isError ? (
            <div className="p-8 text-center" role="alert">
              <p>平台结果暂时无法读取</p>
              <Button
                className="mt-4"
                variant="outline"
                onClick={() => resultsQuery.refetch()}
              >
                重新加载结果
              </Button>
            </div>
          ) : resultsQuery.data.results.length === 0 ? (
            <div className="p-8 text-center">
              <p>当前筛选下没有结果</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {active
                  ? '采集仍在进行，结果会自动更新。'
                  : '可以切换筛选条件查看其他结果。'}
              </p>
            </div>
          ) : (
            resultsQuery.data.results.map((result) => (
              <div key={result.id}>
                <SearchResultRecord
                  result={result}
                  openPending={browserBusy || openMutation.isPending}
                  activeOpenResultId={
                    openMutation.isPending ? openMutation.variables.id : null
                  }
                  openFeedback={
                    browserBusy && result.platform === 'xhs'
                      ? '批次正在使用浏览器，请结束或取消批次后再打开原文。'
                      : feedback?.resultId === result.id
                        ? feedback.message
                        : null
                  }
                  onOpen={() => {
                    if (!browserBusy && !openMutation.isPending)
                      openMutation.mutate(result)
                  }}
                />
                <div className="px-5 pb-3">
                  <Link
                    className={buttonVariants({ variant: 'ghost', size: 'sm' })}
                    to={`/collection-runs/${result.source_run_id}`}
                  >
                    查看来源尝试
                  </Link>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
      {(total > RESULT_LIMIT || offset > 0) && (
        <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
          <Button
            variant="outline"
            disabled={offset === 0 || resultsQuery.isPending}
            onClick={() => changePage(Math.max(0, offset - RESULT_LIMIT))}
          >
            上一页
          </Button>
          <Button
            variant="outline"
            disabled={offset + RESULT_LIMIT >= total || resultsQuery.isPending}
            onClick={() => changePage(offset + RESULT_LIMIT)}
          >
            下一页
          </Button>
        </div>
      )}
    </section>
  )
}
