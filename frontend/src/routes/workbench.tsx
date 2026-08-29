import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CircleDashed,
  Clock3,
  FileSearch,
  FileText,
  RefreshCw,
  ScanSearch,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { Link } from 'react-router'

import { useAppShell } from '@/app/shell'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { usePlatformConnections } from '@/hooks/use-platform-connections'
import { useWorkbench } from '@/hooks/use-workbench'
import type {
  PlatformConnection,
  PlatformConnectionStatus,
} from '@/lib/api/platform-connections'
import type {
  WorkbenchAnalysisActivity,
  WorkbenchAttention,
  WorkbenchCollectionActivity,
  WorkbenchReportActivity,
  WorkbenchSnapshot,
} from '@/lib/api/workbench'
import { cn } from '@/lib/utils'

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const platformLabels = {
  toutiao: '今日头条',
  wb: '微博',
  ks: '快手',
  dy: '抖音',
  xhs: '小红书',
} as const

function formatTimestamp(value: string) {
  return dateFormatter.format(new Date(value))
}

function attentionLink(item: WorkbenchAttention) {
  switch (item.kind) {
    case 'collection_schedule':
      return `/collection-runs?schedule=${item.resource_id}`
    case 'collection_batch':
      return `/collection-batches/${item.resource_id}`
    case 'initial_analysis':
      return `/results?job=${item.resource_id}`
    case 'report':
      return `/results?report=${item.resource_id}`
  }
}

function attentionTitle(item: WorkbenchAttention) {
  switch (item.kind) {
    case 'collection_schedule':
      return '定时采集未按计划进入批次'
    case 'collection_batch':
      return item.status === 'paused_for_manual_action'
        ? '采集批次需要在原页面继续'
        : '最近一次采集未完整结束'
    case 'initial_analysis':
      return item.status === 'unsuccessful_members'
        ? '最近一次初步分析有未成功内容'
        : '初步分析未正常结束'
    case 'report':
      return '最近一次报告生成未正常结束'
  }
}

function reasonCopy(item: WorkbenchAttention) {
  const copies: Partial<
    Record<NonNullable<WorkbenchAttention['reason']>, string>
  > = {
    browser_operation_active: '浏览器正在执行其他操作，本次计划未启动。',
    browser_unavailable: '本机浏览器暂不可用。',
    monitoring_rule_not_found: '关联的监控规则已不存在。',
    monitoring_rule_disabled: '关联的监控规则当前已停用。',
    invalid_monitoring_rule: '关联监控规则的内容不符合当前要求。',
    too_many_search_terms: '监控规则展开后的检索词过多。',
    schedule_changed: '计划版本已变化，本次执行未继续。',
    storage_unavailable: '本机数据暂时无法读取。',
    dispatch_interrupted: '计划派发过程被中断。',
    offline: '应用离线期间错过了计划时间。',
    clock_jump: '系统时间变化导致计划时间被跨过。',
    attempt_failed: '当前平台采集尝试未成功。',
    process_interrupted: '应用进程中断后保留在暂停状态。',
    internal_error: '本次任务因内部错误结束。',
    configuration_blocked: '当前 AI 配置无法继续处理。',
    interrupted: '任务在完成前被中断。',
    unsuccessful_members: '部分内容未成功完成，成功内容仍已保存。',
  }
  if (item.reason && copies[item.reason]) return copies[item.reason]
  if (item.status === 'failed') return '本次任务没有生成新的可读报告。'
  return '请进入对应页面查看已保存的状态与原因。'
}

function platformAttentionCopy(status: PlatformConnectionStatus) {
  switch (status) {
    case 'action_required':
      return '需要在当前浏览器中完成登录或验证。'
    case 'disconnected':
      return '当前未登录，后续采集前需要重新连接。'
    case 'failed':
      return '最近一次登录状态检查未通过。'
    default:
      return ''
  }
}

function AttentionList({
  persistent,
  platforms,
}: {
  persistent: WorkbenchAttention[]
  platforms: PlatformConnection[]
}) {
  if (persistent.length === 0 && platforms.length === 0) return null

  return (
    <section
      aria-labelledby="workbench-attention-heading"
      className="space-y-3"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="size-4 text-warning" aria-hidden />
        <h2
          id="workbench-attention-heading"
          className="font-display text-lg font-semibold"
        >
          需要查看
        </h2>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {platforms.map((platform) => (
          <Card
            key={platform.platform}
            size="sm"
            className="border-l-3 border-l-warning"
          >
            <CardContent className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">平台连接需要查看</p>
                  <Badge variant="outline">{platform.display_name}</Badge>
                </div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {platformAttentionCopy(platform.status)}
                </p>
                <p className="mt-1 font-utility text-[10px] tracking-[0.06em] text-muted-foreground">
                  {platform.last_checked_at
                    ? `最后检查 ${formatTimestamp(platform.last_checked_at)}`
                    : '尚无检查时间'}
                </p>
              </div>
              <Link
                to="/platform-accounts"
                className={cn(
                  buttonVariants({ variant: 'outline' }),
                  'min-h-9',
                )}
              >
                查看平台账号
                <ArrowUpRight aria-hidden />
              </Link>
            </CardContent>
          </Card>
        ))}
        {persistent.map((item) => (
          <Card
            key={`${item.kind}-${item.resource_id}`}
            size="sm"
            className={cn(
              'border-l-3',
              item.severity === 'error'
                ? 'border-l-destructive'
                : 'border-l-warning',
            )}
          >
            <CardContent className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{attentionTitle(item)}</p>
                  <Badge variant="outline">{item.owner}</Badge>
                </div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {reasonCopy(item)}
                  {item.unsuccessful_count !== null
                    ? ` 共 ${item.unsuccessful_count} 项。`
                    : ''}
                </p>
                <p className="mt-1 font-utility text-[10px] tracking-[0.06em] text-muted-foreground">
                  {formatTimestamp(item.occurred_at)}
                </p>
              </div>
              <Link
                to={attentionLink(item)}
                className={cn(
                  buttonVariants({ variant: 'outline' }),
                  'min-h-9',
                )}
              >
                查看详情
                <ArrowUpRight aria-hidden />
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}

function ReportPanel({
  loading,
  readError,
  report,
  onRetry,
}: {
  loading: boolean
  readError: boolean
  report: WorkbenchSnapshot['latest_report']
  onRetry: () => void
}) {
  return (
    <Card className="min-h-[25rem]">
      <CardHeader className="border-b">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-utility text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
              Latest readable report
            </p>
            <CardTitle className="mt-1 font-display text-xl">
              最新舆情报告
            </CardTitle>
          </div>
          <FileText className="size-5 text-primary" aria-hidden />
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col pt-1">
        {loading ? (
          <div role="status" className="space-y-4 py-3">
            <span className="sr-only">正在读取最新舆情报告…</span>
            <Skeleton className="h-5 w-36" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-[92%]" />
            <Skeleton className="h-4 w-[78%]" />
          </div>
        ) : readError ? (
          <div
            role="alert"
            className="flex flex-1 flex-col justify-center py-8"
          >
            <p className="font-medium text-destructive">最新报告暂时无法读取</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              当前没有可安全保留的工作台快照。刷新只会重新读取状态，不会生成报告。
            </p>
            <Button
              type="button"
              variant="outline"
              className="mt-4 self-start"
              onClick={onRetry}
            >
              重新读取
            </Button>
          </div>
        ) : report === null ? (
          <div className="flex flex-1 flex-col justify-center py-8">
            <p className="font-display text-xl">还没有可阅读的舆情报告</p>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              采集内容完成初步分析后，系统会把最新一份可读报告汇总到这里。原始采集结果仍在“结果与分析”中查看。
            </p>
            <Link
              to="/results"
              className={cn(
                buttonVariants({ variant: 'outline' }),
                'mt-5 w-fit',
              )}
            >
              查看结果与分析
              <ArrowUpRight aria-hidden />
            </Link>
          </div>
        ) : report.status === 'empty' ? (
          <div className="flex flex-1 flex-col py-3">
            <Badge variant="secondary" className="mb-4">
              已完成 · 暂无可汇总内容
            </Badge>
            <p className="font-display text-xl leading-8">
              {report.empty_reason === 'no_ready_sources'
                ? '本次范围内没有已准备好的来源文本。'
                : '本次已完成判断，没有来源进入报告正文。'}
            </p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              这是一次如实完成的报告结果，不代表任务失败，也不会补造摘要。
            </p>
            <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t pt-5">
              <p className="text-xs text-muted-foreground">
                完成于 {formatTimestamp(report.finished_at)} · 覆盖{' '}
                {report.coverage.total} 条来源
              </p>
              <Link
                to={`/results?report=${report.id}`}
                className={buttonVariants({ variant: 'outline' })}
              >
                查看完整报告记录
                <ArrowUpRight aria-hidden />
              </Link>
            </div>
          </div>
        ) : (
          <article className="flex flex-1 flex-col py-3">
            <Badge variant="secondary" className="mb-4">
              已完成 · 可阅读
            </Badge>
            <p className="font-display text-lg leading-8 text-foreground sm:text-xl">
              {report.overview}
            </p>
            <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t pt-5">
              <p className="text-xs leading-5 text-muted-foreground">
                完成于 {formatTimestamp(report.finished_at)} · 覆盖{' '}
                {report.coverage.total} 条来源，其中 {report.coverage.relevant}{' '}
                条进入报告判断
              </p>
              <Link
                to={`/results?report=${report.id}`}
                className={buttonVariants({ variant: 'outline' })}
              >
                阅读完整报告
                <ArrowUpRight aria-hidden />
              </Link>
            </div>
          </article>
        )}
      </CardContent>
    </Card>
  )
}

type StageProps = {
  label: string
  status: string
  detail: string
  active: boolean
  href?: string
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  progress?: { value: number; total: number }
}

function ActivityStage({
  label,
  status,
  detail,
  active,
  href,
  icon: Icon,
  progress,
}: StageProps) {
  const content = (
    <>
      <span
        className={cn(
          'relative z-10 flex size-9 shrink-0 items-center justify-center rounded-full border bg-card',
          active ? 'border-primary text-primary' : 'text-muted-foreground',
        )}
      >
        <Icon className="size-4" aria-hidden />
        {active && (
          <span
            className="absolute inset-0 -z-10 animate-pulse rounded-full bg-primary/10 motion-reduce:animate-none"
            aria-hidden
          />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium">{label}</span>
          <span className="text-xs text-muted-foreground">{status}</span>
        </span>
        <span className="mt-1 block text-xs leading-5 text-muted-foreground">
          {detail}
        </span>
        {progress && progress.total > 0 && (
          <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-secondary">
            <span
              role="progressbar"
              aria-label={`${label}进度`}
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-valuenow={progress.value}
              className="block h-full rounded-full bg-primary transition-[width] motion-reduce:transition-none"
              style={{
                width: `${Math.min(100, (progress.value / progress.total) * 100)}%`,
              }}
            />
          </span>
        )}
      </span>
      {href && <ArrowUpRight className="size-4 shrink-0" aria-hidden />}
    </>
  )

  const classes =
    'relative flex min-w-0 items-start gap-3 py-3 text-left after:absolute after:top-12 after:bottom-[-0.75rem] after:left-[1.08rem] after:w-px after:bg-border last:after:hidden'
  return href ? (
    <Link
      to={href}
      className={cn(
        classes,
        'rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
      )}
    >
      {content}
    </Link>
  ) : (
    <div className={classes}>{content}</div>
  )
}

function collectionStage(
  activity: WorkbenchCollectionActivity | null,
): StageProps {
  return {
    label: '采集',
    status: activity
      ? activity.status === 'paused_for_manual_action'
        ? '已暂停'
        : activity.status === 'queued'
          ? '排队中'
          : '进行中'
      : '空闲',
    detail: activity
      ? `${activity.rule_name}${activity.current_platform ? ` · ${platformLabels[activity.current_platform]}` : ''} · ${activity.completed_item_count}/${activity.item_count} 个平台`
      : '当前没有进行中的采集批次',
    active: activity !== null && activity.status !== 'paused_for_manual_action',
    href: activity ? `/collection-batches/${activity.id}` : undefined,
    icon: ScanSearch,
    progress: activity
      ? {
          value: activity.completed_item_count,
          total: activity.item_count,
        }
      : undefined,
  }
}

function analysisStage(activity: WorkbenchAnalysisActivity | null): StageProps {
  return {
    label: '初步分析',
    status: activity
      ? activity.status === 'queued'
        ? '排队中'
        : '进行中'
      : '空闲',
    detail: activity
      ? `已完成 ${activity.completed_count}/${activity.total_count} 条${activity.unsuccessful_count ? ` · ${activity.unsuccessful_count} 条未成功` : ''}`
      : '当前没有进行中的初步分析',
    active: activity !== null,
    href: activity ? `/results?job=${activity.id}` : undefined,
    icon: FileSearch,
    progress: activity
      ? {
          value: activity.completed_count + activity.unsuccessful_count,
          total: activity.total_count,
        }
      : undefined,
  }
}

function reportStage(activity: WorkbenchReportActivity | null): StageProps {
  const statuses = { queued: '排队中', judging: '判断中', composing: '成文中' }
  return {
    label: '报告',
    status: activity ? statuses[activity.status] : '空闲',
    detail: activity
      ? activity.status === 'composing'
        ? '来源判断已完成，正在组织可读报告'
        : `已判断 ${activity.completed_count}/${activity.total_count} 条`
      : '当前没有进行中的报告任务',
    active: activity !== null,
    href: activity ? `/results?report=${activity.id}` : undefined,
    icon: FileText,
    progress: activity
      ? { value: activity.completed_count, total: activity.total_count }
      : undefined,
  }
}

function ActivityRail({
  snapshot,
  loading,
  platformQuery,
}: {
  snapshot: WorkbenchSnapshot | undefined
  loading: boolean
  platformQuery: ReturnType<typeof usePlatformConnections>
}) {
  const enabledPlatforms =
    platformQuery.data?.platforms.filter(
      (platform) => platform.availability === 'enabled',
    ) ?? []
  const connected = enabledPlatforms.filter(
    (platform) => platform.status === 'connected',
  ).length
  const unknown = enabledPlatforms.filter(
    (platform) => platform.status === 'not_checked',
  ).length
  const checking = enabledPlatforms.filter(
    (platform) => platform.status === 'checking',
  ).length
  const attention = enabledPlatforms.filter((platform) =>
    ['action_required', 'disconnected', 'failed'].includes(platform.status),
  ).length
  const platformText = platformQuery.isPending
    ? '正在读取平台状态'
    : platformQuery.isError && platformQuery.data === undefined
      ? '平台状态暂不可用'
      : enabledPlatforms.length === 0
        ? '暂无已接入平台'
        : attention > 0
          ? `${connected}/${enabledPlatforms.length} 已连接 · ${attention} 个需要查看`
          : unknown > 0
            ? `${connected}/${enabledPlatforms.length} 已连接 · ${unknown} 个尚未检查`
            : checking > 0
              ? `${connected}/${enabledPlatforms.length} 已连接 · ${checking} 个检查中`
              : `${connected}/${enabledPlatforms.length} 已连接`

  return (
    <Card>
      <CardHeader className="border-b">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="font-display text-lg">当前运行</CardTitle>
          <Activity className="size-5 text-primary" aria-hidden />
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div role="status" className="space-y-4 py-4">
            <span className="sr-only">正在读取当前运行状态…</span>
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : snapshot ? (
          <div aria-label="采集、初步分析和报告运行状态">
            <ActivityStage {...collectionStage(snapshot.activity.collection)} />
            <ActivityStage
              {...analysisStage(snapshot.activity.initial_analysis)}
            />
            <ActivityStage {...reportStage(snapshot.activity.report)} />
          </div>
        ) : (
          <p className="py-4 text-sm text-muted-foreground">
            运行状态暂不可用。
          </p>
        )}

        <div className="mt-2 space-y-4 border-t pt-5">
          <section aria-labelledby="next-collection-heading">
            <div className="flex items-center gap-2">
              <Clock3 className="size-4 text-primary" aria-hidden />
              <h3 id="next-collection-heading" className="font-medium">
                下一次定时采集
              </h3>
            </div>
            {snapshot?.next_collection ? (
              <div className="mt-2 flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm">
                    {snapshot.next_collection.rule_name}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatTimestamp(snapshot.next_collection.due_at)} · 每{' '}
                    {snapshot.next_collection.interval_minutes} 分钟
                  </p>
                </div>
                <Link
                  to={`/collection-runs?schedule=${snapshot.next_collection.id}`}
                  aria-label="查看下一次定时采集"
                  className={cn(
                    buttonVariants({ variant: 'ghost', size: 'icon-sm' }),
                    'shrink-0',
                  )}
                >
                  <ArrowUpRight aria-hidden />
                </Link>
              </div>
            ) : snapshot ? (
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                暂无可执行的定时采集计划。
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">暂不可用</p>
            )}
          </section>

          <section
            aria-labelledby="platform-readiness-heading"
            className="border-t pt-4"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <CircleDashed className="size-4 text-primary" aria-hidden />
                <h3 id="platform-readiness-heading" className="font-medium">
                  平台准备情况
                </h3>
              </div>
              <Link
                to="/platform-accounts"
                className="text-xs text-primary underline-offset-4 hover:underline"
              >
                查看账号
              </Link>
            </div>
            <p
              role={
                platformQuery.isError && platformQuery.data === undefined
                  ? 'alert'
                  : undefined
              }
              className="mt-2 text-sm leading-6 text-muted-foreground"
            >
              {platformText}
            </p>
          </section>
        </div>
      </CardContent>
    </Card>
  )
}

export function Workbench() {
  const { healthState, retryHealth } = useAppShell()
  const workbenchQuery = useWorkbench()
  const platformQuery = usePlatformConnections(30_000)
  const snapshot = workbenchQuery.data
  const platformAttention =
    platformQuery.data?.platforms.filter(
      (platform) =>
        platform.availability === 'enabled' &&
        ['action_required', 'disconnected', 'failed'].includes(platform.status),
    ) ?? []
  const enabledPlatforms =
    platformQuery.data?.platforms.filter(
      (platform) => platform.availability === 'enabled',
    ) ?? []
  const unknownPlatforms = enabledPlatforms.filter(
    (platform) =>
      platform.status === 'not_checked' || platform.status === 'checking',
  ).length
  const issueCount =
    (snapshot?.attention.length ?? 0) + platformAttention.length
  const persistentUnavailable = workbenchQuery.isError && snapshot === undefined
  const platformUnavailable =
    platformQuery.isError && platformQuery.data === undefined
  const loading = workbenchQuery.isPending && snapshot === undefined
  const stale =
    (workbenchQuery.isError && snapshot !== undefined) ||
    (platformQuery.isError && platformQuery.data !== undefined)
  const fullyKnown =
    snapshot !== undefined &&
    platformQuery.data !== undefined &&
    !stale &&
    !persistentUnavailable &&
    !platformUnavailable &&
    healthState.status === 'connected' &&
    enabledPlatforms.length > 0 &&
    unknownPlatforms === 0
  const duty =
    issueCount > 0
      ? {
          title: `当前有 ${issueCount} 项需要查看`,
          detail: '问题会在同一归属出现更新的健康状态后自动从这里消失。',
          icon: AlertTriangle,
          tone: 'warning',
        }
      : fullyKnown
        ? {
            title: '当前运行正常',
            detail: '已读取持久任务、定时计划、最新报告与平台连接状态。',
            icon: CheckCircle2,
            tone: 'normal',
          }
        : {
            title: loading ? '正在汇总值守状态' : '当前状态尚未完全确认',
            detail: stale
              ? '最近一次更新失败，下面保留的是上次成功读取的内容。'
              : '仍有状态正在读取、尚未检查或暂不可用。',
            icon: CircleDashed,
            tone: 'unknown',
          }
  const DutyIcon = duty.icon

  const refresh = () => {
    if (healthState.status === 'unavailable') retryHealth()
    void workbenchQuery.refetch()
    void platformQuery.refetch()
  }

  return (
    <div className="space-y-6">
      <section
        aria-labelledby="duty-state-heading"
        className={cn(
          'overflow-hidden rounded-xl border bg-card shadow-[0_18px_45px_-40px_rgba(13,59,58,0.75)]',
          duty.tone === 'warning'
            ? 'border-warning/35'
            : duty.tone === 'normal'
              ? 'border-live/25'
              : 'border-border',
        )}
      >
        <div className="grid gap-4 p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center sm:p-5">
          <span
            className={cn(
              'flex size-11 items-center justify-center rounded-full',
              duty.tone === 'warning'
                ? 'bg-warning/10 text-warning'
                : duty.tone === 'normal'
                  ? 'bg-live/10 text-live'
                  : 'bg-secondary text-muted-foreground',
            )}
          >
            <DutyIcon className="size-5" aria-hidden />
          </span>
          <div role="status" className="min-w-0">
            <p className="font-utility text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
              Duty signal
            </p>
            <h2
              id="duty-state-heading"
              className="mt-1 font-display text-xl font-semibold sm:text-2xl"
            >
              {duty.title}
            </h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {duty.detail}
            </p>
            {snapshot && (
              <p className="mt-1 font-utility text-[10px] tracking-[0.06em] text-muted-foreground">
                状态时间 {formatTimestamp(snapshot.observed_at)}
              </p>
            )}
          </div>
          <Button
            type="button"
            variant="outline"
            className="min-h-10 sm:self-center"
            disabled={workbenchQuery.isFetching || platformQuery.isFetching}
            onClick={refresh}
          >
            <RefreshCw
              className={cn(
                (workbenchQuery.isFetching || platformQuery.isFetching) &&
                  'animate-spin motion-reduce:animate-none',
              )}
              aria-hidden
            />
            刷新状态
          </Button>
        </div>
      </section>

      {stale && (
        <p
          role="alert"
          className="rounded-lg border border-warning/30 bg-warning/8 px-4 py-3 text-sm text-warning-foreground"
        >
          状态更新失败；当前继续显示上次成功读取的内容，请留意上方状态时间。
        </p>
      )}

      <AttentionList
        persistent={snapshot?.attention ?? []}
        platforms={platformAttention}
      />

      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1.65fr)_minmax(20rem,0.75fr)] lg:items-start">
        <ReportPanel
          loading={loading}
          readError={persistentUnavailable}
          report={snapshot?.latest_report ?? null}
          onRetry={() => void workbenchQuery.refetch()}
        />
        <ActivityRail
          snapshot={snapshot}
          loading={loading}
          platformQuery={platformQuery}
        />
      </div>
    </div>
  )
}
