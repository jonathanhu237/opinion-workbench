import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  CircleDashed,
  Clock3,
  FileSearch,
  LoaderCircle,
  PauseCircle,
  RefreshCw,
  RotateCcw,
  StopCircle,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  cacheSavedAutomationRun,
  useAutomationRun,
  firstFailedStage,
  isAutomationRunRetryable,
} from '@/hooks/use-automation-workflows'
import { useSearchBatch } from '@/hooks/use-search-batches'
import {
  automationErrorMessage,
  cancelAutomationRun,
  formatAutomationDate,
  isAutomationRunActive,
  newAutomationRequestId,
  retryAutomationRun,
  type AutomationRun,
  type AutomationStage,
} from '@/lib/api/automation-workflows'
import type { SearchBatchDetail } from '@/lib/api/search-batches'
import { searchPlatformPresenters } from '@/routes/search-run-presenters'

const stageLabels: Record<AutomationStage['name'], string> = {
  collection: '采集',
  initial_analysis: '初步分析',
  topic_report: '相关性判断与报告',
}

const stageDescriptions: Record<AutomationStage['name'], string> = {
  collection: '按本次任务设置、平台和每个搜索词上限获取内容。',
  initial_analysis: '先理解正文、图片、视频等可用内容。',
  topic_report: '按本次任务的分析目标判断相关性，并生成报告。',
}

const stageStatusLabels: Record<AutomationStage['status'], string> = {
  queued: '等待中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
  configuration_blocked: '配置有问题',
}

const runStatusLabels: Record<AutomationRun['status'], string> = {
  queued: '等待执行',
  collecting: '采集中',
  analysing: '初步分析中',
  reporting: '生成报告中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
  configuration_blocked: 'AI 设置不可用',
}

type ActionKind = 'cancel' | 'retry'
type Action = { kind: ActionKind; requestId: string } | null

function parseId(value: string | undefined) {
  if (!value || !/^[1-9]\d*$/u.test(value)) return null
  const id = Number(value)
  return Number.isSafeInteger(id) ? id : null
}

function StageIcon({ stage }: { stage: AutomationStage }) {
  if (stage.status === 'completed')
    return <CheckCircle2 className="size-5 text-live" aria-hidden />
  if (stage.status === 'running')
    return (
      <LoaderCircle
        className="size-5 animate-spin text-primary motion-reduce:animate-none"
        aria-hidden
      />
    )
  if (stage.status === 'failed' || stage.status === 'configuration_blocked')
    return <AlertCircle className="size-5 text-destructive" aria-hidden />
  if (stage.status === 'cancelled')
    return <XCircle className="size-5 text-muted-foreground" aria-hidden />
  if (stage.status === 'interrupted')
    return <PauseCircle className="size-5 text-warning" aria-hidden />
  return <CircleDashed className="size-5 text-muted-foreground" aria-hidden />
}

function stageLink(stage: AutomationStage) {
  if (stage.child_id === null) return null
  if (stage.name === 'collection')
    return `/collection-batches/${stage.child_id}`
  if (stage.name === 'initial_analysis') return `/results?job=${stage.child_id}`
  return `/results?report=${stage.child_id}`
}

function stageLinkLabel(stage: AutomationStage) {
  if (stage.name === 'collection') return '查看采集批次'
  if (stage.name === 'initial_analysis') return '查看初步分析'
  return '查看报告'
}

const legacyGenericFailureMessages = new Set([
  '自动任务阶段执行失败，请重试。',
  '自动任务阶段执行失败，请从失败阶段重试。',
  '自动任务阶段未完成。',
  '自动任务阶段未完成，请从失败阶段重试。',
])

const failureTitles: Record<string, string> = {
  collection_browser_unavailable: '采集浏览器未就绪',
  collection_browser_busy: '采集浏览器正忙',
  collection_storage_unavailable: '采集数据暂时不可用',
  collection_start_failed: '采集未启动',
  collection_failed: '采集未完成',
  initial_analysis_failed: '初步分析未完成',
  topic_report_failed: '报告未生成',
}

function failurePresentation(
  failure: { code: string; message: string },
  stage: AutomationStage | null,
) {
  if (
    stage &&
    failure.code === 'stage_failed' &&
    legacyGenericFailureMessages.has(failure.message)
  ) {
    if (stage.name === 'collection' && stage.child_id === null) {
      return {
        title: '采集未启动',
        message:
          '采集任务没有成功启动，旧记录未保留具体原因。请先到“平台账号”检查应用专用的谷歌浏览器与平台连接，然后再从采集阶段重试。',
      }
    }
    if (stage.name === 'collection') {
      return {
        title: '采集未完成',
        message:
          '采集任务已经创建，但没有成功完成。请查看采集批次中的平台状态，处理后再从采集阶段重试。',
      }
    }
    if (stage.name === 'initial_analysis') {
      return {
        title: '初步分析未完成',
        message:
          '本次初步分析没有完成。请检查 AI 配置和已保存的分析结果，然后再从初步分析阶段重试。',
      }
    }
    return {
      title: '报告未生成',
      message:
        '本次相关性判断与报告没有完成。请检查 AI 配置和已保存的报告记录，然后再从报告阶段重试。',
    }
  }
  return {
    title:
      failureTitles[failure.code] ??
      (stage ? `${stageLabels[stage.name]}未完成` : '本次运行未完成'),
    message: failure.message,
  }
}

function stageCounts(
  stage: AutomationStage,
  collectionBatch?: SearchBatchDetail,
) {
  if (
    stage.name === 'collection' &&
    stage.child_id === collectionBatch?.id &&
    collectionBatch.status === 'paused_for_manual_action'
  ) {
    const completed = collectionBatch.items.filter(
      (item) => item.status === 'completed',
    ).length
    return `已完成 ${completed} 个平台 · 待处理 ${collectionBatch.platform_count - completed} 个平台 · 共 ${collectionBatch.platform_count} 个平台`
  }
  if (
    stage.input_count === 0 &&
    stage.success_count === 0 &&
    stage.failure_count === 0
  )
    return null
  return `成功 ${stage.success_count} 条 · 未成功 ${stage.failure_count} 条 · 共 ${stage.input_count} 条`
}

function stageUsage(stage: AutomationStage) {
  return `模型调用：${stage.usage_attempted} 次 · Token：${stage.usage_tokens === null ? '未知' : stage.usage_tokens}`
}

function runOutcome(run: AutomationRun) {
  if (run.outcome === 'no_new_sources') return '本轮没有新内容'
  if (run.outcome === 'completed') return '本轮已完成'
  if (run.outcome === 'cancelled') return '本轮已取消'
  return runStatusLabels[run.status]
}

function RunActionDialog({
  action,
  run,
  pending,
  onClose,
  onConfirm,
}: {
  action: Action
  run: AutomationRun
  pending: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  if (action === null) return null
  const retry = action.kind === 'retry'
  const failed = firstFailedStage(run)
  return (
    <AlertDialog open onOpenChange={(value) => !value && !pending && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {retry ? '从失败阶段重试？' : '取消整次运行？'}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {retry
              ? `将从“${failed ? stageLabels[failed.name] : '失败阶段'}”重新开始，已完成的阶段不会重复。任务设置、平台和两阶段提示词保持不变。`
              : '取消会停止当前阶段并阻止后续阶段启动，已经保存的采集结果、初步分析和报告历史不会删除。'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>返回</AlertDialogCancel>
          <AlertDialogAction
            variant={retry ? 'default' : 'destructive'}
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? '正在提交…' : retry ? '确认重试' : '确认取消运行'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function SnapshotCard({ run }: { run: AutomationRun }) {
  const platforms = run.snapshot.platforms
    .map((platform) => searchPlatformPresenters[platform].label)
    .join('、')
  return (
    <Card>
      <CardHeader className="border-b">
        <h2 className="font-display text-xl">本次任务设置</h2>
        <p className="text-sm leading-6 text-muted-foreground">
          编辑自动任务不会改变本次运行。重试时仍使用原来的规则、平台、采集上限和两阶段提示词。
        </p>
      </CardHeader>
      <CardContent className="grid gap-4 pt-5 text-sm sm:grid-cols-2">
        <div>
          <p className="text-muted-foreground">任务版本</p>
          <p className="mt-1 font-medium">
            {run.snapshot.task_name} · 版本 {run.snapshot.task_revision}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">监控规则</p>
          <p className="mt-1 font-medium">
            {run.snapshot.rule_name} · {run.snapshot.terms.length} 个搜索词
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">平台与采集上限</p>
          <p className="mt-1 font-medium">
            {platforms} · 每个搜索词最多 {run.snapshot.max_results_per_term} 条
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">AI 配置</p>
          <p className="mt-1 font-medium">
            {run.snapshot.ai_model ?? '未记录模型配置'}
          </p>
        </div>
        <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2">
          <div>
            <p className="text-muted-foreground">内容理解提示词</p>
            <p className="mt-1 rounded-lg border bg-muted/25 p-3 leading-6">
              {run.snapshot.initial_prompt?.mode === 'default'
                ? '系统默认模板'
                : (run.snapshot.initial_prompt?.instructions ?? '历史版本')}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">相关性判断与报告提示词</p>
            <p className="mt-1 rounded-lg border bg-muted/25 p-3 leading-6">
              {run.snapshot.report_prompt?.mode === 'default'
                ? '系统默认模板'
                : (run.snapshot.report_prompt?.instructions ??
                  run.snapshot.analysis_goal)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function AutomationRunDetail() {
  const runId = parseId(useParams().runId)
  const queryClient = useQueryClient()
  const runQuery = useAutomationRun(runId)
  const projectedRun = runQuery.data
  const projectedFailedStage = projectedRun
    ? firstFailedStage(projectedRun)
    : null
  const projectedCollection = projectedRun?.stages.find(
    (stage) => stage.name === 'collection',
  )
  const projectedCollectionId = projectedCollection?.child_id ?? null
  const observeCollection =
    projectedRun !== undefined &&
    ((isAutomationRunActive(projectedRun) &&
      projectedRun.active_stage === 'collection') ||
      (isAutomationRunRetryable(projectedRun) &&
        projectedFailedStage?.name === 'collection'))
  const collectionBatchQuery = useSearchBatch(
    observeCollection ? projectedCollectionId : null,
  )
  const [action, setAction] = useState<Action>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: async (value: {
      action: ActionKind
      requestId: string
      run: AutomationRun
    }) => {
      if (value.action === 'cancel') {
        return cancelAutomationRun(value.run.id, {
          requestId: value.requestId,
          expectedRevision: value.run.revision,
        })
      }
      return retryAutomationRun(value.run.id, {
        requestId: value.requestId,
        expectedRevision: value.run.revision,
      })
    },
    retry: false,
    onSuccess: async (saved) => {
      await cacheSavedAutomationRun(queryClient, saved)
      setAction(null)
      setFeedback(
        saved.status === 'cancelled'
          ? '任务已取消，已保存的结果仍然保留。'
          : '已开始重试，将从失败阶段继续。',
      )
    },
    onError: (error) => {
      void runQuery.refetch()
      setFeedback(automationErrorMessage(error))
    },
  })

  if (runId === null) {
    return (
      <section
        role="alert"
        className="space-y-3 rounded-xl border border-destructive/30 bg-card p-6"
      >
        <h1 className="font-display text-2xl font-semibold">运行链接无效</h1>
        <p className="text-sm text-muted-foreground">
          请从自动任务的运行记录重新打开。
        </p>
        <Link
          className={buttonVariants({
            variant: 'outline',
            className: 'min-h-11',
          })}
          to="/automation-tasks"
        >
          返回自动任务
        </Link>
      </section>
    )
  }

  if (runQuery.isPending) {
    return (
      <div role="status" aria-label="正在加载运行详情" className="space-y-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
        <Skeleton className="h-48" />
      </div>
    )
  }
  if (runQuery.isError || runQuery.data === undefined) {
    return (
      <section
        role="alert"
        className="space-y-3 rounded-xl border border-destructive/30 bg-card p-6"
      >
        <h1 className="font-display text-2xl font-semibold">
          运行详情暂时无法读取
        </h1>
        <p className="text-sm text-muted-foreground">
          {automationErrorMessage(runQuery.error)}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => void runQuery.refetch()}
          >
            <RefreshCw aria-hidden />
            重新读取
          </Button>
          <Link
            className={buttonVariants({
              variant: 'ghost',
              className: 'min-h-11',
            })}
            to="/automation-tasks"
          >
            返回自动任务
          </Link>
        </div>
      </section>
    )
  }

  const run = runQuery.data
  const active = isAutomationRunActive(run)
  const retryable = isAutomationRunRetryable(run)
  const failedStage = firstFailedStage(run)
  const pausedCollection =
    collectionBatchQuery.data?.status === 'paused_for_manual_action'
  const runFailure = run.error
    ? failurePresentation(run.error, failedStage)
    : null
  const visibleOutcome = pausedCollection ? '等待处理' : runOutcome(run)
  const liveMessage = pausedCollection
    ? '采集已暂停，等待处理当前平台。'
    : active
      ? `正在${run.active_stage ? stageLabels[run.active_stage] : '等待执行'}。`
      : run.status === 'completed'
        ? runOutcome(run)
        : run.error
          ? ''
          : runOutcome(run)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          className={buttonVariants({
            variant: 'ghost',
            className: 'min-h-11 px-0',
          })}
          to="/automation-tasks"
        >
          <ArrowLeft aria-hidden />
          返回自动任务
        </Link>
        <span className="font-utility text-xs text-muted-foreground">
          运行 #{run.id}
        </span>
      </div>

      <section aria-labelledby="automation-run-title" className="space-y-4">
        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-card/90">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant={
                      pausedCollection
                        ? 'outline'
                        : run.status === 'completed'
                          ? 'secondary'
                          : active
                            ? 'default'
                            : run.status === 'cancelled'
                              ? 'outline'
                              : 'destructive'
                    }
                    className={
                      pausedCollection
                        ? 'border-warning/40 bg-warning/5 text-foreground'
                        : undefined
                    }
                  >
                    {visibleOutcome}
                  </Badge>
                  <Badge variant="outline">
                    {run.trigger === 'manual' ? '立即运行' : '按计划'}
                  </Badge>
                </div>
                <h1
                  id="automation-run-title"
                  className="font-display text-2xl tracking-[-0.04em] sm:text-3xl"
                >
                  {run.snapshot.task_name}
                </h1>
                <p className="text-sm text-muted-foreground">
                  创建于 {formatAutomationDate(run.created_at)} · 任务版本{' '}
                  {run.task_revision}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {active && (
                  <Button
                    variant="destructive"
                    className="min-h-11"
                    onClick={() => {
                      setFeedback(null)
                      setAction({
                        kind: 'cancel',
                        requestId: newAutomationRequestId(),
                      })
                    }}
                    disabled={mutation.isPending}
                  >
                    <StopCircle aria-hidden />
                    取消整次运行
                  </Button>
                )}
                {retryable && (
                  <Button
                    variant="outline"
                    className="min-h-11"
                    onClick={() => {
                      setFeedback(null)
                      setAction({
                        kind: 'retry',
                        requestId: newAutomationRequestId(),
                      })
                    }}
                    disabled={mutation.isPending}
                  >
                    <RotateCcw aria-hidden />
                    从失败阶段重试
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 pt-5">
            <p
              role="status"
              aria-live="polite"
              aria-atomic="true"
              className="min-h-6 text-sm text-muted-foreground"
            >
              {feedback ?? liveMessage}
            </p>
            {pausedCollection && projectedCollectionId !== null && (
              <div className="rounded-xl border border-warning/35 bg-warning/5 p-4 text-sm leading-6">
                <div className="flex gap-3">
                  <PauseCircle
                    className="mt-0.5 size-5 shrink-0 text-warning"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <p className="font-medium">采集已暂停，需要处理</p>
                    <p className="mt-1 text-muted-foreground">
                      已完成平台的采集结果和当前平台的续采位置都已保留。
                      {active
                        ? '请进入采集批次处理当前平台；处理完成后，本次自动任务会自动继续初步分析。'
                        : '这条旧运行已被标记为失败。请先从失败阶段重试，系统会重新接管同一个采集批次；再处理当前平台，完成后会自动继续初步分析。'}
                    </p>
                    <Link
                      className={buttonVariants({
                        variant: 'outline',
                        size: 'sm',
                        className: 'mt-3 min-h-9',
                      })}
                      to={`/collection-batches/${projectedCollectionId}`}
                    >
                      处理采集批次
                      <ArrowUpRight aria-hidden />
                    </Link>
                  </div>
                </div>
              </div>
            )}
            {run.error && runFailure && !pausedCollection && (
              <div
                role="alert"
                className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm leading-6"
              >
                <div className="flex gap-3">
                  <AlertCircle
                    className="mt-0.5 size-5 shrink-0 text-destructive"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <p className="font-medium text-destructive">
                      {runFailure.title}
                    </p>
                    <p className="mt-1 text-muted-foreground">
                      {runFailure.message}
                    </p>
                    {failedStage?.name === 'collection' &&
                      failedStage.child_id === null && (
                        <Link
                          className={buttonVariants({
                            variant: 'link',
                            size: 'sm',
                            className: 'mt-2 h-auto min-h-8 px-0',
                          })}
                          to="/platform-accounts"
                        >
                          检查平台连接
                          <ArrowUpRight aria-hidden />
                        </Link>
                      )}
                  </div>
                </div>
              </div>
            )}
            {run.outcome === 'no_new_sources' && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm leading-6">
                <p className="font-medium">这次没有新的可分析内容</p>
                <p className="mt-1 text-muted-foreground">
                  采集完成后没有发现新的内容，所以没有调用模型，也不会生成“没有相关事件”的结论。
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center gap-2">
              <Clock3 className="size-5 text-primary" aria-hidden />
              <h2 className="font-display text-xl">处理过程</h2>
            </div>
          </CardHeader>
          <CardContent className="pt-5">
            <ol
              aria-label="任务处理阶段"
              className="relative space-y-4 before:absolute before:top-5 before:bottom-5 before:left-[0.72rem] before:w-px before:bg-border"
            >
              {run.stages.map((stage, index) => {
                const link = stageLink(stage)
                const counts = stageCounts(stage, collectionBatchQuery.data)
                const previousAttempts = run.attempts.filter(
                  (attempt) =>
                    attempt.name === stage.name &&
                    attempt.attempt_number < stage.attempt_number,
                )
                const stageFailure = stage.error
                  ? failurePresentation(stage.error, stage)
                  : null
                const stageFailureIsRunSummary =
                  stage.error !== null &&
                  run.error?.code === stage.error.code &&
                  run.error.message === stage.error.message &&
                  failedStage?.name === stage.name
                return (
                  <li
                    key={`${stage.name}-${stage.attempt_number}`}
                    className="relative grid grid-cols-[2rem_minmax(0,1fr)] gap-3"
                  >
                    <span className="z-10 flex size-6 items-center justify-center rounded-full bg-card">
                      {' '}
                      <StageIcon stage={stage} />
                    </span>
                    <div className="min-w-0 rounded-xl border bg-card p-4 shadow-[0_12px_32px_-30px_rgba(13,59,58,0.8)]">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-medium">
                              {index + 1}. {stageLabels[stage.name]}
                            </h3>
                            <Badge
                              variant={
                                stage.status === 'completed'
                                  ? 'secondary'
                                  : stage.status === 'failed' ||
                                      stage.status === 'configuration_blocked'
                                    ? 'destructive'
                                    : 'outline'
                              }
                            >
                              {stageStatusLabels[stage.status]}
                            </Badge>
                            <span className="font-utility text-xs text-muted-foreground">
                              第 {stage.attempt_number} 次尝试
                            </span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-muted-foreground">
                            {stageDescriptions[stage.name]}
                          </p>
                        </div>
                        {link && (
                          <Link
                            className={buttonVariants({
                              variant: 'link',
                              size: 'sm',
                              className: 'h-auto min-h-8 shrink-0 px-0',
                            })}
                            to={link}
                          >
                            {stageLinkLabel(stage)}
                            <ArrowUpRight aria-hidden />
                          </Link>
                        )}
                      </div>
                      <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                        <span>
                          开始时间：{formatAutomationDate(stage.started_at)}
                        </span>
                        <span>
                          结束时间：{formatAutomationDate(stage.finished_at)}
                        </span>
                        {counts && (
                          <span className="sm:col-span-2">
                            处理结果：{counts}
                          </span>
                        )}
                        <span className="sm:col-span-2">
                          {stageUsage(stage)}
                        </span>
                      </div>
                      {stageFailure && !stageFailureIsRunSummary && (
                        <div
                          role="alert"
                          className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm leading-6"
                        >
                          <p className="font-medium text-destructive">
                            {stageFailure.title}
                          </p>
                          <p className="mt-1 text-muted-foreground">
                            {stageFailure.message}
                          </p>
                        </div>
                      )}
                      {previousAttempts.length > 0 && (
                        <details className="mt-3 rounded-lg border bg-muted/20 p-3 text-sm">
                          <summary className="cursor-pointer font-medium">
                            查看之前 {previousAttempts.length} 次记录
                          </summary>
                          <ul className="mt-3 space-y-3">
                            {previousAttempts.map((attempt) => (
                              <li
                                key={`${attempt.name}-${attempt.attempt_number}`}
                                className="rounded-md border bg-card p-3 text-muted-foreground"
                              >
                                <p className="font-medium text-foreground">
                                  第 {attempt.attempt_number} 次 ·{' '}
                                  {stageStatusLabels[attempt.status]}
                                </p>
                                <p className="mt-1">
                                  {formatAutomationDate(attempt.started_at)} →{' '}
                                  {formatAutomationDate(attempt.finished_at)}
                                </p>
                                <p className="mt-1">{stageUsage(attempt)}</p>
                                {stageCounts(attempt) && (
                                  <p className="mt-1">
                                    处理结果：
                                    {stageCounts(
                                      attempt,
                                      collectionBatchQuery.data,
                                    )}
                                  </p>
                                )}
                                {attempt.child_id !== null && (
                                  <p className="mt-1">结果已保存</p>
                                )}
                                {attempt.error && (
                                  <p className="mt-1 text-destructive">
                                    {
                                      failurePresentation(
                                        attempt.error,
                                        attempt,
                                      ).message
                                    }
                                  </p>
                                )}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                      {stage.name === 'topic_report' &&
                        stage.status === 'completed' &&
                        run.topic_report_id !== null && (
                          <Link
                            className={buttonVariants({
                              variant: 'secondary',
                              className: 'mt-3 min-h-11',
                            })}
                            to={`/results?report=${run.topic_report_id}`}
                          >
                            <FileSearch aria-hidden />
                            查看本轮报告
                          </Link>
                        )}
                    </div>
                  </li>
                )
              })}
            </ol>
          </CardContent>
        </Card>
      </section>

      <SnapshotCard run={run} />

      <RunActionDialog
        action={action}
        run={run}
        pending={mutation.isPending}
        onClose={() => setAction(null)}
        onConfirm={() => {
          if (action === null) return
          mutation.mutate({
            action: action.kind,
            requestId: action.requestId,
            run,
          })
        }}
      />
    </div>
  )
}
