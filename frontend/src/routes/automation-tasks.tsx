import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  CircleDashed,
  Clock3,
  LoaderCircle,
  PauseCircle,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  TimerReset,
  Trash2,
  XCircle,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

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
  useAutomationOccurrences,
  useAutomationRuns,
  useAutomationTask,
  useAutomationTasks,
  automationTaskDetailKey,
  cacheDeletedAutomationTask,
  cacheSavedAutomationRun,
  cacheSavedAutomationTask,
} from '@/hooks/use-automation-workflows'
import {
  AUTOMATION_TASKS_QUERY_KEY,
  automationErrorMessage,
  automationScheduleLabel,
  automationTaskUpdatePayload,
  deleteAutomationTask,
  formatAutomationDate,
  isAutomationRunActive,
  isAutomationTaskActive,
  newAutomationRequestId,
  runAutomationTaskNow,
  replaceAutomationTask,
  type AutomationOccurrence,
  type AutomationRun,
  type AutomationStage,
  type AutomationTask,
} from '@/lib/api/automation-workflows'
import { AutomationTaskEditor } from '@/routes/automation-task-editor'
import { searchPlatformPresenters } from '@/routes/search-run-presenters'

type ActionState =
  | { kind: 'run'; task: AutomationTask; requestId: string }
  | { kind: 'delete'; task: AutomationTask }
  | { kind: 'toggle'; task: AutomationTask }
  | null

const taskStatusLabels: Record<AutomationRun['status'], string> = {
  queued: '等待执行',
  collecting: '采集中',
  analysing: '初步分析中',
  reporting: '生成报告中',
  completed: '最近一轮已完成',
  failed: '最近一轮失败',
  cancelled: '最近一轮已取消',
  interrupted: '最近一轮被中断',
  configuration_blocked: 'AI 设置不可用',
}

const stageLabels: Record<AutomationStage['name'], string> = {
  collection: '采集',
  initial_analysis: '初步分析',
  topic_report: '相关性判断与报告',
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

const occurrenceStatusLabels: Record<AutomationOccurrence['status'], string> = {
  claimed: '已安排',
  admitted: '已启动',
  skipped: '本轮跳过',
  missed: '错过执行',
  interrupted: '调度中断',
}

function parseId(value: string | undefined | null) {
  if (value === undefined || value === null || !/^[1-9]\d*$/u.test(value))
    return null
  const id = Number(value)
  return Number.isSafeInteger(id) ? id : null
}

function outcomeLabel(run: AutomationRun | null) {
  if (run === null) return '尚未运行'
  if (run.outcome === 'no_new_sources') return '本轮没有新内容'
  if (run.outcome === 'cancelled') return '本轮已取消'
  if (run.outcome === 'completed') return '本轮已完成'
  return taskStatusLabels[run.status]
}

function statusVariant(run: AutomationRun | null) {
  if (run === null) return 'outline' as const
  if (run.status === 'completed') return 'secondary' as const
  if (isAutomationRunActive(run)) return 'default' as const
  if (run.status === 'cancelled') return 'outline' as const
  return 'destructive' as const
}

function StageIcon({ stage }: { stage: AutomationStage }) {
  if (stage.status === 'completed')
    return <CheckCircle2 className="size-4 text-live" aria-hidden />
  if (stage.status === 'running')
    return (
      <LoaderCircle
        className="size-4 animate-spin text-primary motion-reduce:animate-none"
        aria-hidden
      />
    )
  if (stage.status === 'failed' || stage.status === 'configuration_blocked')
    return <AlertCircle className="size-4 text-destructive" aria-hidden />
  if (stage.status === 'cancelled')
    return <XCircle className="size-4 text-muted-foreground" aria-hidden />
  if (stage.status === 'interrupted')
    return <PauseCircle className="size-4 text-warning" aria-hidden />
  return <CircleDashed className="size-4 text-muted-foreground" aria-hidden />
}

function platformLabel(task: AutomationTask) {
  return task.platforms
    .map((platform) => searchPlatformPresenters[platform].label)
    .join('、')
}

function promptSourceLabel(
  prompt: AutomationTask['initial_prompt'] | AutomationTask['report_prompt'],
) {
  if (prompt?.mode === 'custom' || prompt?.mode === 'legacy')
    return '本任务自定义'
  return '系统默认模板'
}

function LatestRun({ task }: { task: AutomationTask }) {
  const run = task.latest_run
  if (run === null) {
    return <p className="text-sm text-muted-foreground">还没有运行记录</p>
  }
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <Badge variant={statusVariant(run)}>{outcomeLabel(run)}</Badge>
      <Link
        className={buttonVariants({
          variant: 'link',
          size: 'sm',
          className: 'h-auto min-h-8 px-0',
        })}
        to={`/automation-runs/${run.id}`}
      >
        查看最近运行
        <ArrowRight aria-hidden />
      </Link>
    </div>
  )
}

function PlatformChips({ task }: { task: AutomationTask }) {
  return (
    <div
      className="flex flex-wrap gap-1.5"
      aria-label={`采集平台：${platformLabel(task)}`}
    >
      {task.platforms.map((platform) => {
        const presenter = searchPlatformPresenters[platform]
        return (
          <span
            key={platform}
            className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs"
          >
            <img src={presenter.logoSrc} alt="" className="size-4" />
            {presenter.label}
          </span>
        )
      })}
    </div>
  )
}

function AutomationTaskCard({
  task,
  onEdit,
  onRun,
  onToggle,
  onDelete,
  deletePending,
}: {
  task: AutomationTask
  onEdit: (task: AutomationTask) => void
  onRun: (task: AutomationTask) => void
  onToggle: (task: AutomationTask) => void
  onDelete: (task: AutomationTask) => void
  deletePending: boolean
}) {
  const active = isAutomationTaskActive(task)
  const canEnable = task.rule_state === 'enabled' && task.available
  return (
    <article className="group min-w-0 rounded-xl border bg-card p-4 shadow-[0_16px_38px_-34px_rgba(13,59,58,0.8)] transition-colors hover:border-primary/40 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold tracking-[-0.02em] wrap-anywhere">
              {task.name}
            </h3>
            <Badge variant={task.enabled ? 'secondary' : 'outline'}>
              {task.enabled ? '已启用' : '已停用'}
            </Badge>
            {task.rule_state !== 'enabled' && (
              <Badge variant="destructive">
                {task.rule_state === 'deleted'
                  ? '规则已删除'
                  : task.rule_state === 'disabled'
                    ? '规则已停用'
                    : '规则不可用'}
              </Badge>
            )}
          </div>
          <div className="grid gap-x-6 gap-y-2 text-sm text-muted-foreground sm:grid-cols-2">
            <p>
              <span className="font-medium text-foreground">监控规则：</span>
              {task.rule_name}
            </p>
            <p>
              <span className="font-medium text-foreground">计划：</span>
              {automationScheduleLabel(task.schedule)}
            </p>
            <p>
              <span className="font-medium text-foreground">
                每个搜索词上限：
              </span>
              {task.max_results_per_term} 条
            </p>
            <p>
              <span className="font-medium text-foreground">下一次：</span>
              {task.enabled
                ? formatAutomationDate(
                    task.next_due_at,
                    task.schedule.kind === 'daily'
                      ? task.schedule.timezone
                      : 'Asia/Shanghai',
                  )
                : '停用中'}
            </p>
          </div>
          <PlatformChips task={task} />
          <div className="grid gap-2 rounded-lg border border-primary/15 bg-primary/5 p-3 text-sm leading-6 text-foreground/85 sm:grid-cols-2">
            <p>
              <span className="font-medium text-foreground">内容理解：</span>{' '}
              {promptSourceLabel(task.initial_prompt)}
            </p>
            <p>
              <span className="font-medium text-foreground">
                相关性与报告：
              </span>{' '}
              {promptSourceLabel(task.report_prompt)}
            </p>
          </div>
          <LatestRun task={task} />
        </div>

        <div className="flex shrink-0 flex-wrap gap-2 lg:max-w-52 lg:justify-end">
          <Button
            variant="default"
            className="min-h-11"
            disabled={!task.available || active}
            onClick={() => onRun(task)}
          >
            <Play aria-hidden />
            立即运行
          </Button>
          <Link
            className={buttonVariants({
              variant: 'outline',
              className: 'min-h-11',
            })}
            to={`/automation-tasks/${task.id}/runs`}
          >
            <Clock3 aria-hidden />
            查看运行
          </Link>
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => onEdit(task)}
          >
            <Settings2 aria-hidden />
            编辑
          </Button>
          <Button
            variant="ghost"
            className="min-h-11"
            disabled={!task.enabled && !canEnable}
            onClick={() => onToggle(task)}
          >
            {task.enabled ? (
              <PauseCircle aria-hidden />
            ) : (
              <TimerReset aria-hidden />
            )}
            {task.enabled ? '停用' : '启用'}
          </Button>
          <Button
            variant="destructive"
            className="min-h-11"
            aria-label={`删除“${task.name}”${active ? '（请先取消运行）' : ''}`}
            title={active ? '任务正在运行，请先取消后再删除。' : undefined}
            disabled={active || deletePending}
            onClick={() => onDelete(task)}
          >
            <Trash2 aria-hidden />
            删除
          </Button>
        </div>
      </div>
    </article>
  )
}

function TaskActionDialog({
  action,
  pending,
  onClose,
  onConfirm,
}: {
  action: ActionState
  pending: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  const open = action?.kind === 'run' || action?.kind === 'delete'
  if (!open) return null
  const deleting = action.kind === 'delete'
  return (
    <AlertDialog open onOpenChange={(value) => !value && !pending && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {deleting ? `删除“${action.task.name}”？` : '立即运行自动任务？'}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {deleting
              ? '删除后会停止未来计划并从任务列表移除；已有运行、分析结果和报告会保留。此操作无法恢复。'
              : '这会按顺序采集、分析并生成报告，不会改变下一次计划时间。如果任务已经在运行，本次不会重复启动。'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>返回</AlertDialogCancel>
          <AlertDialogAction
            disabled={pending}
            variant={deleting ? 'destructive' : 'default'}
            onClick={onConfirm}
          >
            {pending
              ? deleting
                ? '正在删除…'
                : '正在提交…'
              : deleting
                ? '确认删除'
                : '确认立即运行'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function TaskListPagination({
  nextBeforeId,
  beforeId,
  onChange,
}: {
  nextBeforeId: number | null
  beforeId: number | null
  onChange: (value: number | null) => void
}) {
  if (nextBeforeId === null && beforeId === null) return null
  return (
    <nav
      aria-label="自动任务分页"
      className="flex flex-wrap gap-2 border-t pt-4"
    >
      <Button
        variant="outline"
        className="min-h-11"
        disabled={beforeId === null}
        onClick={() => onChange(null)}
      >
        最新任务
      </Button>
      <Button
        variant="outline"
        className="min-h-11"
        disabled={nextBeforeId === null}
        onClick={() => onChange(nextBeforeId)}
      >
        更早任务
      </Button>
    </nav>
  )
}

export function AutomationTasks() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const beforeId = parseId(params.get('before'))
  const invalidLink = params.has('before') && beforeId === null
  const list = useAutomationTasks(beforeId ?? undefined)
  const [editor, setEditor] = useState<AutomationTask | null | undefined>(
    undefined,
  )
  const [action, setAction] = useState<ActionState>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [focusRefreshAfterDelete, setFocusRefreshAfterDelete] = useState(false)
  const refreshButtonRef = useRef<HTMLButtonElement>(null)
  const createButtonRef = useRef<HTMLButtonElement>(null)
  const toggleMutation = useMutation({
    mutationFn: (task: AutomationTask) =>
      replaceAutomationTask(
        task.id,
        automationTaskUpdatePayload(task, !task.enabled),
      ),
    retry: false,
    onSuccess: async (saved) => {
      await cacheSavedAutomationTask(client, saved)
      setAction(null)
      setFeedback(
        saved.enabled
          ? '自动任务已启用，将在下一次计划时间运行。'
          : '任务已停用，之后不再按计划运行；正在运行的任务会继续。',
      )
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: AUTOMATION_TASKS_QUERY_KEY })
      setAction(null)
      setFeedback('自动任务状态未更新，请刷新后重试。')
    },
  })
  const runMutation = useMutation({
    mutationFn: (value: { task: AutomationTask; requestId: string }) =>
      runAutomationTaskNow(value.task.id, value.requestId),
    retry: false,
    onSuccess: async (run) => {
      await cacheSavedAutomationRun(client, run)
      setAction(null)
      setFeedback('任务已开始，正在处理。')
      void navigate(`/automation-runs/${run.id}`)
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: AUTOMATION_TASKS_QUERY_KEY })
      setFeedback('任务未能启动，请刷新后重试。')
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (task: AutomationTask) =>
      deleteAutomationTask(task.id, { expectedRevision: task.revision }),
    retry: false,
    onSuccess: async (_result, deletedTask) => {
      await cacheDeletedAutomationTask(client, deletedTask.id)
      setAction(null)
      setFeedback(
        `已删除“${deletedTask.name}”。未来计划已停止，已有运行和报告仍会保留。`,
      )
      setFocusRefreshAfterDelete(true)
    },
    onError: (error) => {
      void client.invalidateQueries({ queryKey: AUTOMATION_TASKS_QUERY_KEY })
      setAction(null)
      setFeedback(`任务未删除。${automationErrorMessage(error)}`)
    },
  })

  function changeBefore(value: number | null) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value === null) next.delete('before')
      else next.set('before', String(value))
      return next
    })
  }

  function closeEditor() {
    setEditor(undefined)
    queueMicrotask(() => createButtonRef.current?.focus())
  }

  useEffect(() => {
    if (!focusRefreshAfterDelete || list.isFetching) return
    setFocusRefreshAfterDelete(false)
    refreshButtonRef.current?.focus()
  }, [focusRefreshAfterDelete, list.isFetching])

  return (
    <div className="space-y-6">
      <section aria-label="自动任务操作" className="space-y-4">
        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-card/90">
            <div className="flex justify-end">
              <div className="flex flex-wrap gap-2">
                <Button
                  ref={refreshButtonRef}
                  variant="outline"
                  className="min-h-11"
                  disabled={
                    list.isFetching ||
                    toggleMutation.isPending ||
                    runMutation.isPending
                  }
                  onClick={() => void list.refetch()}
                >
                  <RefreshCw aria-hidden />
                  刷新任务
                </Button>
                <Button
                  ref={createButtonRef}
                  className="min-h-11"
                  disabled={editor !== undefined}
                  onClick={() => {
                    setFeedback(null)
                    setEditor(null)
                  }}
                >
                  <Plus aria-hidden />
                  新建自动任务
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 pt-5">
            <p
              role="status"
              aria-live="polite"
              className="min-h-6 text-sm text-muted-foreground"
            >
              {feedback ?? '新建任务默认停用，启用后才会按计划运行。'}
            </p>
            {invalidLink && (
              <div role="alert" className="space-y-2 text-sm text-destructive">
                <p>自动任务分页链接无效。</p>
                <Button
                  variant="outline"
                  className="min-h-11"
                  onClick={() => changeBefore(null)}
                >
                  重置任务视图
                </Button>
              </div>
            )}
            {list.isPending ? (
              <div
                role="status"
                aria-label="正在加载自动任务"
                className="space-y-3"
              >
                <Skeleton className="h-48" />
                <Skeleton className="h-48" />
              </div>
            ) : list.isError ? (
              <div
                role="alert"
                className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-5"
              >
                <p className="font-medium">自动任务暂时无法读取</p>
                <p className="text-sm text-muted-foreground">
                  {automationErrorMessage(list.error)}
                </p>
                <Button
                  variant="outline"
                  className="min-h-11"
                  onClick={() => void list.refetch()}
                >
                  <RefreshCw aria-hidden />
                  重新读取
                </Button>
              </div>
            ) : list.data.tasks.length === 0 ? (
              <div className="rounded-xl border border-dashed p-8 text-center sm:p-12">
                <TimerReset
                  className="mx-auto size-8 text-primary"
                  aria-hidden
                />
                <h2 className="mt-4 font-display text-xl font-semibold">
                  还没有自动任务
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                  创建任务后，启用它才会按计划运行。
                </p>
                <Button
                  className="mt-5 min-h-11"
                  onClick={() => setEditor(null)}
                >
                  <Plus aria-hidden />
                  创建第一个自动任务
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {list.data.tasks.map((task) => (
                  <AutomationTaskCard
                    key={task.id}
                    task={task}
                    onEdit={(value) => {
                      setFeedback(null)
                      setEditor(value)
                    }}
                    onRun={(value) => {
                      setFeedback(null)
                      setAction({
                        kind: 'run',
                        task: value,
                        requestId: newAutomationRequestId(),
                      })
                    }}
                    onToggle={(value) => {
                      setFeedback(null)
                      setAction({ kind: 'toggle', task: value })
                      toggleMutation.mutate(value)
                    }}
                    onDelete={(value) => {
                      deleteMutation.reset()
                      setFeedback(null)
                      setAction({ kind: 'delete', task: value })
                    }}
                    deletePending={deleteMutation.isPending}
                  />
                ))}
              </div>
            )}
            {!list.isPending && !list.isError && list.data && (
              <TaskListPagination
                nextBeforeId={list.data.next_before_id}
                beforeId={beforeId}
                onChange={changeBefore}
              />
            )}
          </CardContent>
        </Card>
      </section>

      {editor !== undefined && (
        <AutomationTaskEditor
          task={editor}
          onClose={closeEditor}
          onSaved={(saved, message) => {
            setEditor(undefined)
            setFeedback(message)
            queueMicrotask(() => createButtonRef.current?.focus())
            void client.invalidateQueries({
              queryKey: automationTaskDetailKey(saved.id),
            })
          }}
        />
      )}
      <TaskActionDialog
        action={action}
        pending={
          action?.kind === 'delete'
            ? deleteMutation.isPending
            : runMutation.isPending
        }
        onClose={() => setAction(null)}
        onConfirm={() => {
          if (action?.kind === 'run') runMutation.mutate(action)
          if (action?.kind === 'delete') deleteMutation.mutate(action.task)
        }}
      />
    </div>
  )
}

function RunRow({ run }: { run: AutomationRun }) {
  const failed = run.stages.find((stage) =>
    ['failed', 'interrupted', 'configuration_blocked'].includes(stage.status),
  )
  return (
    <article className="rounded-lg border p-4 transition-colors hover:border-primary/40">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusVariant(run)}>{outcomeLabel(run)}</Badge>
            <Badge variant="outline">
              {run.trigger === 'manual' ? '立即运行' : '按计划'}
            </Badge>
            <span className="font-utility text-xs text-muted-foreground">
              运行 #{run.id}
            </span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>创建于 {formatAutomationDate(run.created_at)}</span>
            <span>版本 {run.task_revision}</span>
            {failed && (
              <span className="text-destructive">
                失败阶段：{stageLabels[failed.name]}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2" aria-label="运行阶段状态">
            {run.stages.map((stage) => (
              <span
                key={`${stage.name}-${stage.attempt_number}`}
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
              >
                <StageIcon stage={stage} />
                {stageLabels[stage.name]} · {stageStatusLabels[stage.status]}
              </span>
            ))}
          </div>
        </div>
        <Link
          className={buttonVariants({
            variant: 'outline',
            className: 'min-h-11 shrink-0',
          })}
          to={`/automation-runs/${run.id}`}
        >
          <ArrowRight aria-hidden />
          查看运行详情
        </Link>
      </div>
    </article>
  )
}

function OccurrenceRow({ occurrence }: { occurrence: AutomationOccurrence }) {
  const reason = occurrence.reason
  return (
    <div className="flex flex-col gap-1 rounded-lg border bg-muted/20 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            occurrence.status === 'skipped' || occurrence.status === 'missed'
              ? 'outline'
              : occurrence.status === 'interrupted'
                ? 'destructive'
                : 'secondary'
          }
        >
          {occurrenceStatusLabels[occurrence.status]}
        </Badge>
        <span>{formatAutomationDate(occurrence.due_at)}</span>
        {occurrence.run_id !== null && (
          <Link
            className="underline underline-offset-4"
            to={`/automation-runs/${occurrence.run_id}`}
          >
            运行 #{occurrence.run_id}
          </Link>
        )}
      </div>
      <span className="text-muted-foreground">
        {reason ? occurrenceReasonLabel(reason) : '按计划执行'}
      </span>
    </div>
  )
}

function occurrenceReasonLabel(reason: string) {
  const labels: Record<string, string> = {
    previous_run_active: '上一轮还在运行，本次未启动',
    offline: '服务离线时错过，本次没有运行',
    clock_jump: '系统时间变化，本次没有运行',
    dispatch_interrupted: '任务启动被中断',
    monitoring_rule_not_found: '监控规则已删除',
    monitoring_rule_disabled: '监控规则已停用',
    invalid_monitoring_rule: '监控规则有问题',
    configuration_unavailable: 'AI 设置不可用',
    storage_unavailable: '本机数据暂时无法读取',
  }
  return labels[reason] ?? reason
}

export function AutomationTaskRuns() {
  const params = useParams()
  const taskId = parseId(params.taskId)
  const [searchParams, setSearchParams] = useSearchParams()
  const beforeId = parseId(searchParams.get('before'))
  const task = useAutomationTask(taskId)
  const runs = useAutomationRuns(taskId, beforeId ?? undefined)
  const occurrences = useAutomationOccurrences(taskId, undefined)
  const invalidLink =
    taskId === null || (searchParams.has('before') && beforeId === null)

  if (invalidLink) {
    return (
      <section
        role="alert"
        className="space-y-3 rounded-xl border border-destructive/30 bg-card p-6"
      >
        <h1 className="font-display text-2xl font-semibold">
          自动任务链接无效
        </h1>
        <p className="text-sm text-muted-foreground">
          请从自动任务列表重新打开对应任务。
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

  function changeBefore(value: number | null) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value === null) next.delete('before')
      else next.set('before', String(value))
      return next
    })
  }

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
          ← 返回自动任务
        </Link>
        {task.data && (
          <Link
            className={buttonVariants({
              variant: 'outline',
              className: 'min-h-11',
            })}
            to={`/automation-tasks?task=${task.data.id}`}
          >
            查看任务
          </Link>
        )}
      </div>
      {task.isPending ? (
        <Skeleton className="h-36" />
      ) : task.isError || task.data === undefined ? (
        <div
          role="alert"
          className="space-y-3 rounded-xl border border-destructive/30 bg-card p-6"
        >
          <h1 className="font-display text-2xl font-semibold">
            自动任务暂时无法读取
          </h1>
          <p className="text-sm text-muted-foreground">
            {automationErrorMessage(task.error)}
          </p>
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => void task.refetch()}
          >
            重新读取
          </Button>
        </div>
      ) : (
        <section
          aria-labelledby="automation-task-runs-title"
          className="space-y-4"
        >
          <Card>
            <CardHeader className="border-b">
              <div className="flex flex-wrap items-center gap-2">
                <CalendarClock className="size-5 text-primary" aria-hidden />
                <h1
                  id="automation-task-runs-title"
                  className="font-display text-2xl"
                >
                  {task.data.name} · 运行记录
                </h1>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 pt-5">
              {runs.isPending ? (
                <div
                  role="status"
                  aria-label="正在加载运行记录"
                  className="space-y-3"
                >
                  <Skeleton className="h-32" />
                  <Skeleton className="h-32" />
                </div>
              ) : runs.isError ? (
                <div role="alert" className="space-y-3">
                  <p>
                    运行记录暂时无法读取。{automationErrorMessage(runs.error)}
                  </p>
                  <Button
                    variant="outline"
                    className="min-h-11"
                    onClick={() => void runs.refetch()}
                  >
                    重新读取运行记录
                  </Button>
                </div>
              ) : runs.data.runs.length === 0 ? (
                <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                  还没有运行记录。启用任务或点击“立即运行”后，记录会显示在这里。
                </p>
              ) : (
                <div className="space-y-3">
                  {runs.data.runs.map((run) => (
                    <RunRow key={run.id} run={run} />
                  ))}
                </div>
              )}
              {!runs.isPending && !runs.isError && runs.data && (
                <TaskListPagination
                  nextBeforeId={runs.data.next_before_id}
                  beforeId={beforeId}
                  onChange={changeBefore}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="border-b">
              <h2 className="font-display text-xl">计划记录</h2>
            </CardHeader>
            <CardContent className="space-y-3 pt-5">
              {occurrences.isPending ? (
                <Skeleton className="h-24" />
              ) : occurrences.isError ? (
                <div role="alert" className="space-y-3">
                  <p>计划记录暂时无法读取。</p>
                  <Button
                    variant="outline"
                    className="min-h-11"
                    onClick={() => void occurrences.refetch()}
                  >
                    重新读取计划记录
                  </Button>
                </div>
              ) : occurrences.data.occurrences.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  还没有到期记录。
                </p>
              ) : (
                <div className="space-y-2">
                  {occurrences.data.occurrences
                    .slice(0, 10)
                    .map((occurrence) => (
                      <OccurrenceRow
                        key={occurrence.id}
                        occurrence={occurrence}
                      />
                    ))}
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  )
}
