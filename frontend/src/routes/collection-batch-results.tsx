import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight } from 'lucide-react'

import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchBatchResults } from '@/hooks/use-search-batches'
import {
  SEARCH_BATCHES_QUERY_KEY,
  SEARCH_BATCH_RESULTS_PAGE_SIZE,
  type SearchBatchItem,
} from '@/lib/api/search-batches'
import { type SearchResultFilter } from '@/lib/api/search-runs'
import { SearchResultRecord } from '@/routes/search-result-record'
import { searchPlatformPresenters } from '@/routes/search-run-presenters'

export function CollectionBatchResults({
  batchId,
  item,
}: {
  batchId: number
  item: SearchBatchItem
}) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<SearchResultFilter>('all')
  const [offset, setOffset] = useState(0)
  const active = item.status === 'running'
  const resultsQuery = useSearchBatchResults(
    batchId,
    item.position,
    kind,
    offset,
    active,
    open,
  )
  const queryClient = useQueryClient()
  const wasActive = useRef(active)
  const returnFocus = useRef<HTMLElement | null>(null)
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
  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) {
      returnFocus.current = document.activeElement as HTMLElement | null
      setKind('all')
      setOffset(0)
    }
    setOpen(nextOpen)
  }
  function handleOpenChangeComplete(nextOpen: boolean) {
    if (!nextOpen) {
      returnFocus.current?.focus({ preventScroll: true })
      returnFocus.current = null
    }
  }
  const total = resultsQuery.data?.total ?? 0
  const pageCount = Math.max(
    1,
    Math.ceil(total / SEARCH_BATCH_RESULTS_PAGE_SIZE),
  )
  const page = Math.floor(offset / SEARCH_BATCH_RESULTS_PAGE_SIZE) + 1
  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
      onOpenChangeComplete={handleOpenChangeComplete}
    >
      <DialogTrigger
        className={buttonVariants({ variant: 'outline', size: 'sm' })}
      >
        查看结果
        <ArrowRight aria-hidden />
      </DialogTrigger>
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-4xl"
        aria-busy={resultsQuery.isFetching}
      >
        <DialogHeader>
          <DialogTitle>
            {searchPlatformPresenters[item.platform].label} · 采集结果（共{' '}
            {item.total_count} 条）
          </DialogTitle>
          <DialogDescription>同一条内容只显示一次。</DialogDescription>
        </DialogHeader>
        <Tabs
          value={kind}
          onValueChange={(value) => {
            const nextKind: SearchResultFilter =
              value === 'new' || value === 'repeated' ? value : 'all'
            setKind(nextKind)
            setOffset(0)
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
                  <SearchResultRecord result={result} />
                  <div className="px-5 pb-3">
                    <Link
                      className={buttonVariants({
                        variant: 'ghost',
                        size: 'sm',
                      })}
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
        {(total > SEARCH_BATCH_RESULTS_PAGE_SIZE || offset > 0) && (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="mr-auto text-sm text-muted-foreground">
              第 {page} / {pageCount} 页
            </span>
            <Button
              variant="outline"
              className="min-h-11 sm:min-h-8"
              disabled={offset === 0 || resultsQuery.isFetching}
              onClick={() =>
                setOffset(Math.max(0, offset - SEARCH_BATCH_RESULTS_PAGE_SIZE))
              }
            >
              上一页
            </Button>
            <Button
              variant="outline"
              className="min-h-11 sm:min-h-8"
              disabled={
                offset + SEARCH_BATCH_RESULTS_PAGE_SIZE >= total ||
                resultsQuery.isFetching
              }
              onClick={() => setOffset(offset + SEARCH_BATCH_RESULTS_PAGE_SIZE)}
            >
              下一页
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
