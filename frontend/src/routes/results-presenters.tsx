import { useMutation } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { useState } from 'react'

import { Button, buttonVariants } from '@/components/ui/button'
import type { AISummarySource } from '@/lib/api/ai-summaries'
import type { AnalysisJob, AnalysisUsage } from '@/lib/api/content-analyses'
import type { ResultState } from '@/lib/api/results'
import { openSearchRunResult } from '@/lib/api/search-runs'
import { cn } from '@/lib/utils'
import {
  openErrorMessage,
  openOutcomeMessages,
  searchPlatformPresenters,
} from '@/routes/search-run-presenters'

export const resultStateLabels: Record<ResultState, string> = {
  never_started: '尚未初步分析',
  pending_new: '新内容待分析',
  queued: '等待开始',
  acquiring: '获取正文与媒体',
  analysing: '正在初步分析',
  completed: '已保存初步分析',
  input_incomplete: '内容不完整',
  unsupported: '输入暂不支持',
  failed: '分析失败',
  cancelled: '已取消',
  interrupted: '已中断',
  legacy_completed: '仅有旧版分析',
  legacy_attempted: '旧版尝试未完成',
}
export const analysisJobLabels: Record<AnalysisJob['status'], string> = {
  queued: '等待开始',
  running: '正在初步分析',
  completed: '已处理完毕',
  cancelled: '已取消',
  interrupted: '已中断',
  configuration_blocked: '模型配置已变化',
}
export function analysisUsageMessage(usage: AnalysisUsage) {
  if (usage.attempted_requests === 0) return '本任务未调用模型'
  return `已调用 ${usage.attempted_requests} 次 · 已计量 ${usage.accounted_requests} 次 · ${usage.total_tokens === null ? 'Token 用量未知' : `${usage.total_tokens.toLocaleString('zh-CN')} Token${usage.complete ? '' : '（统计不完整）'}`}`
}
export function formatEvidenceDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}
function sourceKey(source: AISummarySource) {
  return `${source.source_run_id}:${source.result_id}`
}
export function useResultSourceControls() {
  const [feedback, setFeedback] = useState<{
    key: string
    message: string
  } | null>(null)
  const mutation = useMutation({
    mutationFn: (source: AISummarySource) =>
      openSearchRunResult(source.source_run_id, source.result_id),
    retry: false,
    onMutate: () => setFeedback(null),
    onSuccess: (data, source) =>
      setFeedback({
        key: sourceKey(source),
        message: openOutcomeMessages[data.outcome],
      }),
    onError: (error, source) =>
      setFeedback({ key: sourceKey(source), message: openErrorMessage(error) }),
  })
  return {
    pending: mutation.isPending,
    activeKey: mutation.variables ? sourceKey(mutation.variables) : null,
    feedback,
    open: mutation.mutate,
  }
}
export type ResultSourceControls = ReturnType<typeof useResultSourceControls>
export function ResultSourceLink({
  source,
  controls,
  disabled = false,
  citationNumber,
}: {
  source: AISummarySource
  controls: ResultSourceControls
  disabled?: boolean
  citationNumber?: number
}) {
  const text =
    citationNumber === undefined
      ? '打开原文'
      : `原文 ${citationNumber} · ${searchPlatformPresenters[source.platform].label}`
  const label = `${text}：${source.title}`
  const variant = citationNumber === undefined ? 'outline' : 'link'
  const style = cn(
    'min-h-11 shrink-0 whitespace-normal [overflow-wrap:anywhere]',
    citationNumber !== undefined &&
      'h-auto min-h-8 px-0 align-baseline underline',
  )
  if (source.platform !== 'xhs')
    return (
      <a
        href={source.content_url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={label}
        title={citationNumber === undefined ? undefined : source.title}
        className={cn(buttonVariants({ variant, size: 'sm' }), style)}
      >
        {text}
        <ExternalLink aria-hidden />
      </a>
    )
  const active = controls.pending && controls.activeKey === sourceKey(source)
  return (
    <span className="inline-flex max-w-full flex-col items-start align-baseline">
      <Button
        variant={variant}
        size="sm"
        className={style}
        disabled={disabled || controls.pending}
        aria-busy={active}
        aria-label={label}
        title={citationNumber === undefined ? undefined : source.title}
        onClick={() => controls.open(source)}
      >
        {active ? '正在打开…' : text}
        <ExternalLink aria-hidden />
      </Button>
      {controls.feedback?.key === sourceKey(source) && (
        <span
          role="status"
          className="mt-2 max-w-72 text-sm text-muted-foreground"
        >
          {controls.feedback.message}
        </span>
      )}
    </span>
  )
}
export function ResultsPagination({
  offset,
  limit,
  total,
  onChange,
  label,
}: {
  offset: number
  limit: number
  total: number
  onChange: (value: number) => void
  label: string
}) {
  return (
    <nav
      aria-label={`${label}分页`}
      className="flex flex-wrap items-center justify-between gap-3 border-t pt-4"
    >
      <p className="text-sm text-muted-foreground">
        {total === 0 || offset >= total
          ? `共 ${total} 条`
          : `${offset + 1}–${Math.min(total, offset + limit)} / ${total} 条`}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          className="min-h-11"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
          aria-label={`${label}上一页`}
        >
          上一页
        </Button>
        <Button
          variant="outline"
          className="min-h-11"
          disabled={total - offset <= limit}
          onClick={() => onChange(offset + limit)}
          aria-label={`${label}下一页`}
        >
          下一页
        </Button>
      </div>
    </nav>
  )
}
