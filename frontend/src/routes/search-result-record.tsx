import { ExternalLink } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import type { SearchResult } from '@/lib/api/search-runs'
import { cn } from '@/lib/utils'
import { formatLocalDate } from '@/routes/search-run-presenters'

export function SearchResultRecord({
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
