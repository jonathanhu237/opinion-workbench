import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  fetchResultAnalyses,
  type AnalysisAttempt,
} from '@/lib/api/content-analyses'
import { fetchResult, RESULTS_QUERY_KEY } from '@/lib/api/results'
import { ResultSourceLink } from '@/routes/results-presenters'

// The endpoint is newest-first. Keep paging past failed attempts so they never
// hide an older successful summary. No analysis is started by this reader.
async function fetchReading(resultId: number, signal: AbortSignal) {
  let offset = 0
  let original: AnalysisAttempt | null = null
  for (;;) {
    const page = await fetchResultAnalyses(resultId, signal, offset)
    original ??= page.items.find((item) => item.input !== null) ?? null
    const summary = page.items.find(
      (item) => item.status === 'completed' && item.output !== null,
    )
    if (summary)
      return { original: summary.input ? summary : original, summary }
    offset += page.items.length
    if (page.items.length === 0 || offset >= page.total)
      return { original, summary: null }
  }
}

export function ResultReadingDetail({
  resultId,
  onClose,
}: {
  resultId: number
  onClose: () => void
}) {
  const result = useQuery({
    queryKey: [...RESULTS_QUERY_KEY, 'detail', resultId],
    queryFn: ({ signal }) => fetchResult(resultId, signal),
  })
  const reading = useQuery({
    queryKey: ['result-reading', resultId],
    queryFn: ({ signal }) => fetchReading(resultId, signal),
  })
  const input = reading.data?.original?.input
  const body = input?.text.body?.trim() || result.data?.source.snippet
  const title = input?.text.title?.trim() || result.data?.source.title
  return (
    <div className="flex flex-col gap-6 py-2">
      <div>
        <Button variant="ghost" onClick={onClose}>
          返回选材
        </Button>
      </div>
      <section aria-label="原文" className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">原文</h2>
          {result.data && <ResultSourceLink source={result.data.source} />}
        </div>
        {result.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : result.isError ? (
          <p role="alert">
            原文读取失败。
            <Button variant="link" onClick={() => void result.refetch()}>
              重试
            </Button>
          </p>
        ) : (
          <>
            {result.data.source.content_type !== 'post' &&
              title &&
              title !== body && (
                <h3 className="font-medium [overflow-wrap:anywhere]">
                  {title}
                </h3>
              )}
            <p className="leading-7 [overflow-wrap:anywhere] whitespace-pre-wrap">
              {body || '暂无原文正文，请打开原文查看。'}
            </p>
            {(!input?.text.body?.trim() ||
              input.text.coverage !== 'complete') &&
              body && (
                <p className="text-sm text-muted-foreground">
                  仅保存了部分正文，完整内容请查看原文。
                </p>
              )}
          </>
        )}
      </section>
      <Separator />
      <section aria-label="总结" className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">总结</h2>
        {reading.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : reading.isError ? (
          <p role="alert">
            总结读取失败。
            <Button variant="link" onClick={() => void reading.refetch()}>
              重试
            </Button>
          </p>
        ) : (
          <p className="leading-7 [overflow-wrap:anywhere] whitespace-pre-wrap">
            {reading.data.summary?.output?.summary || '暂无总结'}
          </p>
        )}
      </section>
    </div>
  )
}
