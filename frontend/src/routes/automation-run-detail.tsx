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
import { searchPlatformPresenters } from '@/routes/search-run-presenters'

const stageLabels: Record<AutomationStage['name'], string> = {
  collection: '采集',
  initial_analysis: '初步分析',
  topic_report: '相关性判断与报告',
}

const stageDescriptions: Record<AutomationStage['name'], string> = {
  collection: '按冻结的规则、平台和每词上限获取候选条目。',
  initial_analysis: '不按任务主题预筛，先理解正文、图片、视频等可用内容。',
  topic_report: '按本任务冻结的分析目标判断相关性，并生成一次报告。',
}

const stageStatusLabels: Record<AutomationStage['status'], string> = {
  queued: '等待中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
  configuration_blocked: '配置阻断',
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
  configuration_blocked: 'AI 配置阻断',
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

function stageCounts(stage: AutomationStage) {
  if (
    stage.input_count === 0 &&
    stage.success_count === 0 &&
    stage.failure_count === 0
  )
    return null
  return `${stage.success_count} 成功 · ${stage.failure_count} 未成功 · 共 ${stage.input_count}`
}

function stageUsage(stage: AutomationStage) {
  return `模型请求：${stage.usage_attempted} 次 · Token：${stage.usage_tokens === null ? '未知' : stage.usage_tokens}`
}

function runOutcome(run: AutomationRun) {
  if (run.outcome === 'no_new_sources') return '本轮无新增舆情'
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
              ? `将从“${failed ? stageLabels[failed.name] : '失败阶段'}”重新开始，并复用之前已经完成的阶段。运行的冻结规则、平台和分析目标不会改变。`
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
        <h2 className="font-display text-xl">本轮冻结意图</h2>
        <p className="text-sm leading-6 text-muted-foreground">
          编辑自动任务不会改变这次运行。重试也沿用同一份规则、平台、采集上限和分析目标。
        </p>
      </CardHeader>
      <CardContent className="grid gap-4 pt-5 text-sm sm:grid-cols-2">
        <div>
          <p className="text-muted-foreground">任务修订</p>
          <p className="mt-1 font-medium">
            {run.snapshot.task_name} · 修订 {run.snapshot.task_revision}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">监控规则</p>
          <p className="mt-1 font-medium">
            {run.snapshot.rule_name} · {run.snapshot.terms.length} 个搜索词
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">平台与上限</p>
          <p className="mt-1 font-medium">
            {platforms} · 每词 {run.snapshot.max_results_per_term} 条
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">AI 配置</p>
          <p className="mt-1 font-medium">
            {run.snapshot.ai_model ?? '未记录模型配置'} · 模板{' '}
            {run.snapshot.initial_template_version} /{' '}
            {run.snapshot.report_template_version}
          </p>
        </div>
        <div className="sm:col-span-2">
          <p className="text-muted-foreground">舆情分析目标</p>
          <p className="mt-1 rounded-lg border bg-muted/25 p-3 leading-6">
            {run.snapshot.analysis_goal}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

export function AutomationRunDetail() {
  const runId = parseId(useParams().runId)
  const queryClient = useQueryClient()
  const runQuery = useAutomationRun(runId)
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
          ? '运行已取消，已保存的领域数据仍然保留。'
          : '已接受重试，将从第一个失败阶段继续。',
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
  const liveMessage = active
    ? `当前正在${run.active_stage ? stageLabels[run.active_stage] : '等待执行'}。页面会自动更新，不会改变焦点。`
    : run.status === 'completed'
      ? runOutcome(run)
      : (run.error?.message ?? runOutcome(run))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          className={buttonVariants({
            variant: 'ghost',
            className: 'min-h-11 px-0',
          })}
          to={`/automation-tasks/${run.task_id}/runs`}
        >
          <ArrowLeft aria-hidden />
          返回运行记录
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
                      run.status === 'completed'
                        ? 'secondary'
                        : active
                          ? 'default'
                          : run.status === 'cancelled'
                            ? 'outline'
                            : 'destructive'
                    }
                  >
                    {runOutcome(run)}
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
                  创建于 {formatAutomationDate(run.created_at)} · 任务修订{' '}
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
            {run.error && (
              <p
                role="alert"
                className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm leading-6 text-destructive"
              >
                {run.error.message}
                {failedStage
                  ? ` 可从“${stageLabels[failedStage.name]}”重试。`
                  : ''}
              </p>
            )}
            {run.outcome === 'no_new_sources' && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm leading-6">
                <p className="font-medium">本轮没有新增舆情材料</p>
                <p className="mt-1 text-muted-foreground">
                  采集阶段完成后没有形成这项任务的新成员，因此没有调用模型，也没有伪装成“没有相关事件”的结论。
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center gap-2">
              <Clock3 className="size-5 text-primary" aria-hidden />
              <h2 className="font-display text-xl">固定工作流时间线</h2>
            </div>
            <p className="text-sm text-muted-foreground">
              阶段顺序固定；每个阶段的尝试、时间和已保存产物都来自运行快照。
            </p>
          </CardHeader>
          <CardContent className="pt-5">
            <ol
              aria-label="固定工作流阶段"
              className="relative space-y-4 before:absolute before:top-5 before:bottom-5 before:left-[0.72rem] before:w-px before:bg-border"
            >
              {run.stages.map((stage, index) => {
                const link = stageLink(stage)
                const counts = stageCounts(stage)
                const previousAttempts = run.attempts.filter(
                  (attempt) =>
                    attempt.name === stage.name &&
                    attempt.attempt_number < stage.attempt_number,
                )
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
                          开始：{formatAutomationDate(stage.started_at)}
                        </span>
                        <span>
                          结束：{formatAutomationDate(stage.finished_at)}
                        </span>
                        {counts && (
                          <span className="sm:col-span-2">覆盖：{counts}</span>
                        )}
                        <span className="sm:col-span-2">
                          {stageUsage(stage)}
                        </span>
                        {stage.child_id !== null && (
                          <span className="sm:col-span-2">
                            已保存产物：{stage.child_kind ?? stage.name} #
                            {stage.child_id}
                          </span>
                        )}
                      </div>
                      {stage.error && (
                        <p
                          role="alert"
                          className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm leading-6 text-destructive"
                        >
                          {stage.error.message}
                        </p>
                      )}
                      {previousAttempts.length > 0 && (
                        <details className="mt-3 rounded-lg border bg-muted/20 p-3 text-sm">
                          <summary className="cursor-pointer font-medium">
                            查看此前 {previousAttempts.length} 次尝试
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
                                    覆盖：{stageCounts(attempt)}
                                  </p>
                                )}
                                {attempt.child_id !== null && (
                                  <p className="mt-1">
                                    已保存产物：
                                    {attempt.child_kind ?? attempt.name} #
                                    {attempt.child_id}
                                  </p>
                                )}
                                {attempt.error && (
                                  <p className="mt-1 text-destructive">
                                    {attempt.error.message}
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
                            打开本轮报告
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
