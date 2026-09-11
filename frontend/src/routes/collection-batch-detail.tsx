import { useMutation, useQueryClient } from '@tanstack/react-query'
import { collectionLimitLabel } from '@/lib/collection-limit'
import {
  ArrowLeft,
  Check,
  Circle,
  LoaderCircle,
  Pause,
  Square,
  TriangleAlert,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useSearchBatch,
  useSearchBatchAttempts,
} from '@/hooks/use-search-batches'
import {
  cancelSearchBatch,
  continueSearchBatch,
  skipSearchBatchPlatform,
  showSearchBatchManualPage,
  recoverSearchBatchPlatform,
  SEARCH_BATCHES_QUERY_KEY,
  SearchBatchApiError,
  type SearchBatchDetail,
  type SearchBatchItem,
  type SearchBatchItemStatus,
  type SearchBatchStatus,
  type SearchBatchControl,
} from '@/lib/api/search-batches'
import { SEARCH_RUNS_QUERY_KEY } from '@/lib/api/search-runs'
import {
  formatLocalDate,
  batchPauseGuidance,
  incompleteTermsGuidance,
  manualPageMessages,
  searchBatchItemStatusLabel,
  searchBatchStatusLabel,
  searchPlatformPresenters,
  searchRunDisplayLabel,
  searchRunStatusLabel,
} from '@/routes/search-run-presenters'
import { CollectionBatchResults } from '@/routes/collection-batch-results'

function parseBatchId(value: string | undefined) {
  if (!value || !/^[1-9][0-9]*$/u.test(value)) return null
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) ? parsed : null
}

function batchBadgeVariant(status: SearchBatchStatus) {
  if (status === 'completed') return 'secondary' as const
  if (status === 'queued' || status === 'running') return 'default' as const
  if (status === 'paused_for_manual_action' || status === 'cancelled') {
    return 'outline' as const
  }
  return 'destructive' as const
}

function itemBadgeVariant(status: SearchBatchItemStatus) {
  if (status === 'completed') return 'secondary' as const
  if (status === 'running') return 'default' as const
  if (
    status === 'queued' ||
    status === 'paused_for_manual_action' ||
    status === 'skipped' ||
    status === 'cancelled'
  ) {
    return 'outline' as const
  }
  return 'destructive' as const
}

function StatusMark({ status }: { status: SearchBatchItemStatus }) {
  if (status === 'completed') {
    return <Check className="size-4" aria-hidden />
  }
  if (status === 'running') {
    return (
      <LoaderCircle
        className="size-4 animate-spin motion-reduce:animate-none"
        aria-hidden
      />
    )
  }
  if (status === 'paused_for_manual_action') {
    return <Pause className="size-4" aria-hidden />
  }
  if (status === 'failed') {
    return <TriangleAlert className="size-4" aria-hidden />
  }
  if (status === 'cancelled') {
    return <Square className="size-3" aria-hidden />
  }
  return <Circle className="size-3" aria-hidden />
}

function AttemptHistory({
  batchId,
  item,
}: {
  batchId: number
  item: SearchBatchItem
}) {
  const [open, setOpen] = useState(false)
  const attemptsQuery = useSearchBatchAttempts(
    open ? batchId : null,
    open ? item.position : null,
  )

  if (item.attempt_count <= 1) return null

  return (
    <div className="mt-3 border-t border-border/70 pt-3">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {open ? '收起尝试记录' : `查看 ${item.attempt_count} 次尝试`}
      </Button>
      {open && (
        <div className="mt-2 space-y-2">
          {attemptsQuery.isPending ? (
            <p className="text-sm text-muted-foreground" role="status">
              正在读取尝试记录…
            </p>
          ) : attemptsQuery.isError ? (
            <p className="text-sm text-destructive" role="alert">
              尝试记录暂时无法读取。
            </p>
          ) : (
            attemptsQuery.data?.attempts.map((attempt) => (
              <div
                key={attempt.attempt_number}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/60 px-3 py-2 text-sm"
              >
                <span>
                  第 {attempt.attempt_number} 次 ·{' '}
                  {searchRunStatusLabel(
                    attempt.run.status,
                    attempt.run.failure_reason,
                  )}
                </span>
                <Link
                  className={buttonVariants({ variant: 'ghost', size: 'sm' })}
                  to={`/collection-runs/${attempt.run.id}`}
                >
                  查看任务
                </Link>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function BatchRail({
  batch,
  pending,
  recoveringPosition,
  onRecover,
}: {
  batch: SearchBatchDetail
  pending: boolean
  recoveringPosition: number | null
  onRecover: (item: SearchBatchItem) => void
}) {
  return (
    <ol className="relative space-y-3 before:absolute before:top-7 before:bottom-7 before:left-6 before:w-px before:bg-border sm:before:left-7">
      {batch.items.map((item) => {
        const platform = searchPlatformPresenters[item.platform]
        const run = item.latest_attempt?.run
        const progress =
          run?.status === 'running'
            ? run.current_term_position === null
              ? `正在连接${platform.label}…`
              : `第 ${run.current_term_position + 1} / ${run.term_count} 个搜索词`
            : null
        return (
          <li key={item.platform} className="relative pl-13 sm:pl-16">
            <div
              className={`absolute top-4 left-2.5 z-10 grid size-7 place-items-center rounded-full border bg-background sm:left-3.5 ${
                item.status === 'running'
                  ? 'border-primary text-primary'
                  : item.status === 'failed'
                    ? 'border-destructive text-destructive'
                    : 'border-border text-muted-foreground'
              }`}
            >
              <StatusMark status={item.status} />
            </div>
            <Card>
              <CardContent className="p-4 sm:p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <img src={platform.logoSrc} alt="" className="size-7" />
                      <h3 className="font-medium">{platform.label}</h3>
                      <Badge variant={itemBadgeVariant(item.status)}>
                        {searchBatchItemStatusLabel(item.status)}
                      </Badge>
                      {item.attempt_count > 1 && (
                        <span className="text-xs text-muted-foreground">
                          第 {item.attempt_count} 次尝试
                        </span>
                      )}
                    </div>
                    {progress && (
                      <p className="mt-2 text-sm text-muted-foreground">
                        {progress}
                      </p>
                    )}
                    {run?.access_waiting && (
                      <p
                        className="mt-2 text-sm text-muted-foreground"
                        role="status"
                      >
                        正在等待{platform.label}
                        的访问间隔；合法等待不会被误报为超时，任务会在允许的访问开始时间继续。
                      </p>
                    )}
                    {run?.access_notice && (
                      <p
                        className="mt-2 text-sm text-amber-700 dark:text-amber-300"
                        role="alert"
                      >
                        已记录{platform.label}的访问限制
                        {run.access_notice.status_code
                          ? `（HTTP ${run.access_notice.status_code}）`
                          : ''}
                        。本次任务不会自动绕过限制，请确认平台状态后显式继续。
                        {run.access_notice.manual_challenge_required
                          ? ' 平台还要求完成安全验证。'
                          : ''}
                      </p>
                    )}
                    <p className="mt-2 text-sm text-muted-foreground">
                      {batch.max_total_results != null
                        ? `已采集 ${item.total_count} / ${batch.max_total_results} 条（去重）`
                        : item.recovery_available
                          ? `搜索词进度：${item.completed_term_count} / ${batch.term_count}`
                          : '无法确认从哪里继续'}
                    </p>
                    {run &&
                      item.status !== 'running' &&
                      item.status !== 'queued' && (
                        <p className="mt-2 text-sm text-muted-foreground">
                          最近一次尝试：
                          {searchRunDisplayLabel(run)}
                        </p>
                      )}
                    {item.incomplete_terms?.length ? (
                      <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
                        {incompleteTermsGuidance(item.incomplete_terms)}
                      </p>
                    ) : null}
                    {item.completion_basis === 'confirmed_terms' && (
                      <p className="mt-1 text-sm text-muted-foreground">
                        所有搜索词均已确认完成，无需再次采集。最近一次尝试的失败记录仍保留。
                      </p>
                    )}
                    {
                      <p className="mt-2 text-sm">
                        <span className="font-medium">
                          新增 {item.new_count}
                        </span>
                        <span className="mx-2 text-border">/</span>
                        <span className="text-muted-foreground">
                          再次命中 {item.repeated_count}
                        </span>
                      </p>
                    }
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {batch.status === 'completed_with_failures' &&
                      item.status === 'failed' &&
                      run &&
                      ![
                        'queued',
                        'running',
                        'completed_empty',
                        'completed_with_results',
                        'completed_with_incomplete',
                      ].includes(run.status) && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="min-h-11 sm:min-h-8"
                          disabled={pending}
                          onClick={() => onRecover(item)}
                        >
                          {recoveringPosition === item.position
                            ? '正在准备…'
                            : '继续采集'}
                        </Button>
                      )}
                    {run && (
                      <>
                        <CollectionBatchResults
                          batchId={batch.id}
                          item={item}
                        />
                        <Link
                          className={buttonVariants({
                            variant: 'ghost',
                            size: 'sm',
                          })}
                          to={`/collection-runs/${run.id}`}
                        >
                          本次尝试
                        </Link>
                      </>
                    )}
                  </div>
                </div>
                <AttemptHistory batchId={batch.id} item={item} />
              </CardContent>
            </Card>
          </li>
        )
      })}
    </ol>
  )
}

function errorMessage(error: unknown) {
  return error instanceof SearchBatchApiError
    ? error.message
    : '操作未能完成，请重新尝试。'
}

export function CollectionBatchDetail() {
  const batchId = parseBatchId(useParams().batchId)
  const queryClient = useQueryClient()
  const batchQuery = useSearchBatch(batchId)
  const [feedback, setFeedback] = useState<{
    message: string
    error: boolean
  } | null>(null)
  const feedbackRef = useRef<HTMLDivElement>(null)
  const generation = useRef(0)
  const controlLock = useRef(false)
  const manualLock = useRef(false)
  useEffect(
    () => () => {
      generation.current += 1
    },
    [batchId],
  )
  useEffect(() => {
    if (feedback) feedbackRef.current?.focus()
  }, [feedback])
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: SEARCH_BATCHES_QUERY_KEY }),
      queryClient.invalidateQueries({ queryKey: SEARCH_RUNS_QUERY_KEY }),
    ])
  }
  type ControlAction = {
    kind: 'continue' | 'skip' | 'recover' | 'cancel'
    batchId: number
    input: SearchBatchControl
    generation: number
  }
  const controlMutation = useMutation({
    mutationFn: (action: ControlAction) => {
      if (action.kind === 'continue')
        return continueSearchBatch(action.batchId, action.input)
      if (action.kind === 'skip')
        return skipSearchBatchPlatform(action.batchId, action.input)
      if (action.kind === 'cancel')
        return cancelSearchBatch(action.batchId, {
          expected_revision: action.input.expected_revision,
        })
      return recoverSearchBatchPlatform(
        action.batchId,
        action.input.item_position,
        {
          expected_run_id: action.input.expected_run_id,
          expected_revision: action.input.expected_revision,
        },
      )
    },
    retry: false,
    onSuccess: (response, action) => {
      queryClient.setQueryData<SearchBatchDetail>(
        [...SEARCH_BATCHES_QUERY_KEY, action.batchId],
        (current) =>
          current && current.control_revision > response.control_revision
            ? current
            : response,
      )
      if (action.generation !== generation.current) return
      const messages = {
        continue: '已继续；完成过的搜索词不会重复采集。',
        skip: '已跳过本次采集，已有结果仍然保留。',
        recover: '已准备好继续本次采集，请检查页面后继续采集。',
        cancel: '已取消采集，已有结果仍然保留。',
      }
      setFeedback({ message: messages[action.kind], error: false })
    },
    onError: (error, action) => {
      if (action.generation === generation.current)
        setFeedback({ message: errorMessage(error), error: true })
    },
    onSettled: async () => {
      try {
        await invalidate()
      } finally {
        controlLock.current = false
      }
    },
  })
  const manualMutation = useMutation({
    mutationFn: (action: Omit<ControlAction, 'kind'>) =>
      showSearchBatchManualPage(action.batchId, action.input),
    retry: false,
    onSuccess: (response, action) => {
      if (action.generation === generation.current)
        setFeedback({
          message: manualPageMessages[response.outcome],
          error: !['opened_existing', 'opened_homepage', 'cancelled'].includes(
            response.outcome,
          ),
        })
    },
    onError: (error, action) => {
      if (action.generation === generation.current)
        setFeedback({ message: errorMessage(error), error: true })
    },
    onSettled: async () => {
      try {
        await invalidate()
      } finally {
        manualLock.current = false
      }
    },
  })
  const pending = controlMutation.isPending || manualMutation.isPending
  function act(kind: ControlAction['kind'] | 'open', item?: SearchBatchItem) {
    const current = batchQuery.data
    if (
      !current ||
      controlLock.current ||
      (manualLock.current && kind !== 'cancel')
    )
      return
    const input: SearchBatchControl = {
      item_position: item?.position ?? 0,
      expected_run_id: item?.latest_attempt?.run.id ?? null,
      expected_revision: current.control_revision,
    }
    const action = {
      batchId: current.id,
      input,
      generation: ++generation.current,
    }
    setFeedback(null)
    if (kind === 'open') {
      manualLock.current = true
      manualMutation.mutate(action)
    } else {
      controlLock.current = true
      controlMutation.mutate({ ...action, kind })
    }
  }

  if (batchId === null) {
    return (
      <Card>
        <CardContent className="p-8 text-center" role="alert">
          <p className="font-medium">采集任务编号不正确</p>
          <Link
            className={buttonVariants({ variant: 'outline' })}
            to="/collection-runs"
          >
            返回采集任务
          </Link>
        </CardContent>
      </Card>
    )
  }

  if (batchQuery.isPending) {
    return (
      <div className="space-y-4" aria-label="正在加载采集进度">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (batchQuery.isError || !batchQuery.data) {
    return (
      <Card>
        <CardContent className="p-8 text-center" role="alert">
          <p className="font-medium">采集进度暂时无法读取</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => batchQuery.refetch()}
          >
            重新加载
          </Button>
        </CardContent>
      </Card>
    )
  }

  const batch = batchQuery.data
  const canCancel = ['queued', 'running', 'paused_for_manual_action'].includes(
    batch.status,
  )
  const pausedItem = batch.items.find(
    (item) => item.status === 'paused_for_manual_action',
  )
  const pausedPlatform = pausedItem
    ? searchPlatformPresenters[pausedItem.platform].label
    : null
  const cancelling =
    controlMutation.isPending && controlMutation.variables.kind === 'cancel'
  const continuing =
    controlMutation.isPending && controlMutation.variables.kind === 'continue'
  const skipping =
    controlMutation.isPending && controlMutation.variables.kind === 'skip'

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link
            to="/collection-runs"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-4" aria-hidden />
            返回采集任务
          </Link>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <h2 className="font-display text-2xl font-semibold">
              {batch.rule_name}
            </h2>
            <Badge variant={batchBadgeVariant(batch.status)}>
              {searchBatchStatusLabel(batch.status)}
            </Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            已结束 {batch.terminal_item_count} / {batch.platform_count} 个采集项
            · {batch.term_count} 个搜索词 · 创建于{' '}
            {formatLocalDate(batch.created_at)}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {collectionLimitLabel(batch)}
          </p>
        </div>
        {canCancel && batch.status !== 'paused_for_manual_action' && (
          <Button
            type="button"
            variant="outline"
            disabled={controlMutation.isPending}
            onClick={() => act('cancel')}
          >
            <Square className="size-3" aria-hidden />
            {cancelling ? '正在取消…' : '取消采集'}
          </Button>
        )}
      </div>

      {batch.status === 'paused_for_manual_action' &&
        pausedPlatform &&
        pausedItem && (
          <Card className="border-primary/35">
            <CardHeader>
              <h3 className="text-lg font-medium">
                采集已暂停 · {pausedPlatform}
              </h3>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {batchPauseGuidance(pausedItem)}
              </p>
              <p className="text-sm">
                {batch.max_total_results != null ? (
                  `已保留 ${pausedItem.total_count} 条。继续后仍按平台实际顺序轮流检索，重复命中不占新名额，整批合计最多 ${batch.max_total_results} 条。`
                ) : (
                  <>
                    已确认完成 {pausedItem.completed_term_count} /{' '}
                    {batch.term_count} 个搜索词，剩余{' '}
                    {pausedItem.remaining_term_count} 个。
                    {pausedItem.next_term_position !== null && (
                      <>
                        {' '}
                        继续时将从“{batch.terms[pausedItem.next_term_position]}
                        ”开始。
                      </>
                    )}
                    {pausedItem.remaining_term_count === 0 &&
                      pausedItem.recovery_available && (
                        <> 所有搜索词均已完成，继续后将结束本次采集。</>
                      )}
                  </>
                )}
              </p>
              {!pausedItem.recovery_available && (
                <p
                  id="recovery-unavailable"
                  className="text-sm text-destructive"
                >
                  无法确认从哪里继续，请跳过本次采集或取消采集。
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 sm:min-h-8"
                  disabled={pending}
                  aria-busy={manualMutation.isPending}
                  onClick={() => act('open', pausedItem)}
                >
                  {manualMutation.isPending ? '正在打开…' : '打开平台'}
                </Button>
                <Button
                  type="button"
                  className="min-h-11 sm:min-h-8"
                  disabled={pending || !pausedItem.recovery_available}
                  aria-describedby={
                    !pausedItem.recovery_available
                      ? 'recovery-unavailable'
                      : undefined
                  }
                  onClick={() => act('continue', pausedItem)}
                >
                  {continuing ? '正在继续…' : '继续采集'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 sm:min-h-8"
                  disabled={pending}
                  onClick={() => act('skip', pausedItem)}
                >
                  {skipping ? '正在跳过…' : '跳过本次采集'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 sm:min-h-8"
                  disabled={controlMutation.isPending}
                  onClick={() => act('cancel')}
                >
                  {cancelling ? '正在取消…' : '取消采集'}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

      <div
        ref={feedbackRef}
        tabIndex={-1}
        aria-live="polite"
        aria-atomic="true"
      >
        {feedback && (
          <p
            className={
              feedback.error
                ? 'text-sm text-destructive'
                : 'text-sm text-muted-foreground'
            }
            role={feedback.error ? 'alert' : 'status'}
          >
            {feedback.message}
          </p>
        )}
      </div>

      <section aria-labelledby="platform-progress-title">
        <h2
          id="platform-progress-title"
          className="mb-3 font-display text-xl font-semibold"
        >
          采集进度
        </h2>
        <BatchRail
          batch={batch}
          pending={pending}
          recoveringPosition={
            controlMutation.isPending &&
            controlMutation.variables.kind === 'recover'
              ? controlMutation.variables.input.item_position
              : null
          }
          onRecover={(item) => act('recover', item)}
        />
      </section>
    </div>
  )
}
