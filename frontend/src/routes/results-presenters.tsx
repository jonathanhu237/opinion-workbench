import { ExternalLink } from 'lucide-react'

import { Button, buttonVariants } from '@/components/ui/button'
import type { AISummarySource } from '@/lib/api/ai-summaries'
import type { AnalysisJob, AnalysisUsage } from '@/lib/api/content-analyses'
import type { ResultState } from '@/lib/api/results'
import { cn } from '@/lib/utils'
import { searchPlatformPresenters } from '@/routes/search-run-presenters'

export const resultStateLabels: Record<ResultState, string> = {
  never_started: '待分析',
  pending_new: '新内容待分析',
  queued: '等待开始',
  acquiring: '正在获取内容',
  analysing: '正在初步分析',
  completed: '已完成',
  input_incomplete: '内容不完整',
  unsupported: '输入暂不支持',
  failed: '分析失败',
  cancelled: '已取消',
  interrupted: '已中断',
  legacy_completed: '旧版分析',
  legacy_attempted: '旧版未完成',
}
export const analysisJobLabels: Record<AnalysisJob['status'], string> = {
  queued: '等待开始',
  running: '正在初步分析',
  completed: '已完成',
  cancelled: '已取消',
  interrupted: '已中断',
  configuration_blocked: '模型设置不一致',
}
export function analysisUsageMessage(usage: AnalysisUsage) {
  if (usage.attempted_requests === 0) return '本任务未调用模型'
  return `调用 ${usage.attempted_requests} 次 · 计入用量 ${usage.accounted_requests} 次 · ${usage.total_tokens === null ? 'Token 用量未知' : `${usage.total_tokens.toLocaleString('zh-CN')} Token${usage.complete ? '' : '（统计不完整）'}`}`
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
export function ResultSourceLink({
  source,
  citationNumber,
}: {
  source: AISummarySource
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
