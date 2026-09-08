import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { useAppShell } from '@/app/shell'
import douyinLogo from '@/assets/platforms/douyin.svg'
import kuaishouLogo from '@/assets/platforms/kuaishou.svg'
import toutiaoLogo from '@/assets/platforms/toutiao.svg'
import weiboLogo from '@/assets/platforms/weibo.svg'
import xiaohongshuLogo from '@/assets/platforms/xiaohongshu.svg'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  isPlatformConnectionActive,
  usePlatformConnections,
} from '@/hooks/use-platform-connections'
import {
  PLATFORM_CONNECTIONS_QUERY_KEY,
  PlatformConnectionApiError,
  openManagedBrowser,
  startPlatformConnectionAttempt,
  type PlatformConnection,
  type PlatformConnectionStatus,
  type PlatformId,
} from '@/lib/api/platform-connections'
import { cn } from '@/lib/utils'

const platformLogos: Partial<Record<PlatformId, string>> = {
  toutiao: toutiaoLogo,
  wb: weiboLogo,
  ks: kuaishouLogo,
  dy: douyinLogo,
  xhs: xiaohongshuLogo,
}

const statusLabels: Record<PlatformConnectionStatus, string> = {
  not_checked: '待检查',
  checking: '检查中',
  action_required: '需要操作',
  connected: '已登录',
  disconnected: '未登录',
  failed: '检查失败',
  coming_soon: '暂不可用',
}

const BATCH_CHECK_DEADLINE_MS = 100_000

function statusBadgeClass(status: PlatformConnectionStatus) {
  switch (status) {
    case 'connected':
      return 'border-live/25 bg-live/10 text-foreground'
    case 'action_required':
      return 'border-warning/30 bg-warning/10 text-warning-foreground'
    case 'failed':
    case 'disconnected':
      return 'border-destructive/25 bg-destructive/8 text-destructive'
    case 'checking':
      return 'border-primary/25 bg-primary/10 text-primary'
    case 'not_checked':
      return 'border-border bg-background text-muted-foreground'
    case 'coming_soon':
      return 'border-border bg-muted text-muted-foreground'
  }
}

function formatLastChecked(timestamp: string | null) {
  if (timestamp === null) {
    return '尚未检查'
  }

  return `上次检查 ${new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(timestamp))}`
}

function attemptButtonLabel(status: PlatformConnectionStatus) {
  if (status === 'checking') {
    return '处理中…'
  }
  if (status === 'not_checked') {
    return '检查状态'
  }
  return '重新检查'
}

function rowRecoveryMessage(connection: PlatformConnection) {
  if (connection.status === 'disconnected') {
    return '尚未登录，请在专用浏览器中登录后重新检查。'
  }
  if (
    connection.status === 'failed' &&
    connection.guidance === 'complete_verification'
  ) {
    return '请在专用浏览器中完成安全验证后重新检查。'
  }
  if (
    connection.status === 'failed' &&
    connection.guidance === 'retry_browser'
  ) {
    return '专用浏览器已关闭，请打开后重新检查。'
  }
  if (connection.status === 'failed') {
    return '检查失败，请稍后重试。'
  }
  return null
}

type BatchPlatform = Pick<PlatformConnection, 'platform' | 'display_name'>

type BatchDetection = {
  runId: number
  platforms: BatchPlatform[]
  currentIndex: number
  phase: 'starting' | 'waiting'
  deadlineAt: number
}

type AttemptMutationContext = {
  token: number
}

type BatchStep = Pick<BatchDetection, 'runId' | 'currentIndex'>

type PlatformRowProps = {
  connection: PlatformConnection
  operationActive: boolean
  serviceAvailable: boolean
  onOpen: (platform: PlatformId) => void
  onStart: (platform: PlatformId) => void
}

function PlatformRow({
  connection,
  operationActive,
  serviceAvailable,
  onOpen,
  onStart,
}: PlatformRowProps) {
  const active = isPlatformConnectionActive(connection)
  const actionable = connection.availability === 'enabled'
  const disabled = operationActive || !serviceAvailable
  const recoveryMessage = rowRecoveryMessage(connection)

  return (
    <li
      className={cn('platform-row', active && 'platform-row-active')}
      data-status={connection.status}
    >
      <span className="platform-node" aria-hidden="true" />
      <div className="min-w-0">
        <div className="platform-identity">
          <span className="platform-mark" aria-hidden="true">
            <img
              src={platformLogos[connection.platform] ?? weiboLogo}
              alt=""
              aria-hidden="true"
              className="size-6 object-contain"
            />
          </span>
          <div className="min-w-0">
            <p className="font-semibold text-foreground">
              {connection.display_name}
            </p>
            <p className="mt-1 font-utility text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
              {formatLastChecked(connection.last_checked_at)}
            </p>
          </div>
        </div>
        {recoveryMessage && (
          <p className="mt-2 pl-[3.55rem] text-xs leading-5 text-muted-foreground">
            {recoveryMessage}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 sm:justify-end">
        <Badge
          variant="outline"
          className={cn('font-normal', statusBadgeClass(connection.status))}
        >
          {statusLabels[connection.status]}
        </Badge>
        {actionable ? (
          <>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="min-h-11 min-w-20 sm:min-h-7"
              disabled={disabled}
              onClick={() => onOpen(connection.platform)}
            >
              打开平台
            </Button>
            <Button
              type="button"
              size="sm"
              variant={
                connection.status === 'connected' ? 'outline' : 'default'
              }
              className="min-h-11 min-w-24 sm:min-h-7 sm:min-w-20"
              disabled={disabled}
              onClick={() => onStart(connection.platform)}
            >
              {attemptButtonLabel(connection.status)}
            </Button>
          </>
        ) : (
          <span className="w-20 text-right text-xs text-muted-foreground">
            暂不可用
          </span>
        )}
      </div>
    </li>
  )
}

export function PlatformAccounts() {
  const { healthState, retryHealth } = useAppShell()
  const queryClient = useQueryClient()
  const attemptController = useRef<AbortController | null>(null)
  const attemptSequence = useRef(0)
  const browserController = useRef<AbortController | null>(null)
  const batchRunSequence = useRef(0)
  const launchedBatchStep = useRef<string | null>(null)
  const [batchDetection, setBatchDetection] = useState<BatchDetection | null>(
    null,
  )
  const batchDetectionRef = useRef<BatchDetection | null>(null)
  batchDetectionRef.current = batchDetection
  const [batchMessage, setBatchMessage] = useState<string | null>(null)
  const connectionsQuery = usePlatformConnections()
  const attemptMutation = useMutation({
    mutationFn: (platform: PlatformId) => {
      attemptController.current?.abort()
      const controller = new AbortController()
      attemptController.current = controller
      return startPlatformConnectionAttempt(platform, controller.signal)
    },
    onMutate: (): AttemptMutationContext => ({
      token: ++attemptSequence.current,
    }),
    onSuccess: (result, _platform, context) => {
      if (context?.token !== attemptSequence.current) {
        return
      }
      queryClient.setQueryData(
        PLATFORM_CONNECTIONS_QUERY_KEY,
        (current: { platforms: PlatformConnection[] } | undefined) => {
          if (current === undefined) {
            return current
          }
          return {
            platforms: current.platforms.map((connection) =>
              connection.platform === result.platform.platform
                ? result.platform
                : connection,
            ),
          }
        },
      )
      void queryClient.invalidateQueries({
        queryKey: PLATFORM_CONNECTIONS_QUERY_KEY,
      })
    },
    onSettled: (_result, _error, _platform, context) => {
      if (context?.token === attemptSequence.current) {
        attemptController.current = null
      }
    },
  })
  const browserMutation = useMutation({
    mutationFn: (platform: PlatformId | undefined) => {
      browserController.current?.abort()
      const controller = new AbortController()
      browserController.current = controller
      return openManagedBrowser(platform, controller.signal)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: PLATFORM_CONNECTIONS_QUERY_KEY,
      })
    },
    onSettled: () => {
      browserController.current = null
    },
  })

  useEffect(
    () => () => {
      attemptController.current?.abort()
      browserController.current?.abort()
    },
    [],
  )

  const platforms = connectionsQuery.data?.platforms ?? []
  const enabledPlatforms = platforms.filter(
    (connection) => connection.availability === 'enabled',
  )
  const platformOperationActive =
    attemptMutation.isPending || platforms.some(isPlatformConnectionActive)
  const operationActive =
    batchDetection !== null ||
    platformOperationActive ||
    browserMutation.isPending
  const browserMessage =
    browserMutation.error instanceof PlatformConnectionApiError
      ? browserMutation.error.message
      : browserMutation.error instanceof Error
        ? '专用浏览器打开失败，请重试。'
        : null
  const mutationMessage =
    attemptMutation.error instanceof PlatformConnectionApiError
      ? attemptMutation.error.message
      : attemptMutation.error instanceof Error
        ? '检查未能启动，请重新尝试。'
        : null
  const queryMessage = connectionsQuery.error
    ? connectionsQuery.error instanceof PlatformConnectionApiError
      ? connectionsQuery.error.message
      : '登录状态暂时无法读取。'
    : null
  const healthMessage =
    healthState.status === 'unavailable'
      ? '应用服务暂时不可用，请重新启动应用。'
      : null
  const panelAlertMessage =
    platforms.length > 0
      ? (browserMessage ??
        mutationMessage ??
        queryMessage ??
        healthMessage ??
        batchMessage)
      : null

  const currentBatchPlatform =
    batchDetection?.platforms[batchDetection.currentIndex]
  const batchProgress =
    batchDetection !== null && currentBatchPlatform !== undefined
      ? `正在检测${currentBatchPlatform.display_name} · ${batchDetection.currentIndex + 1}/${batchDetection.platforms.length}`
      : ''
  const batchUnavailable =
    healthState.status !== 'connected' ||
    connectionsQuery.isPending ||
    connectionsQuery.error !== null ||
    enabledPlatforms.length === 0 ||
    operationActive

  const mutateAttempt = attemptMutation.mutate
  const resetAttempt = attemptMutation.reset

  const stopBatch = useCallback(
    (message: string | null, expectedStep?: BatchStep) => {
      const activeBatch = batchDetectionRef.current
      if (
        expectedStep !== undefined &&
        (activeBatch === null ||
          activeBatch.runId !== expectedStep.runId ||
          activeBatch.currentIndex !== expectedStep.currentIndex)
      ) {
        return
      }
      // An aborted request may still settle after the next batch starts.
      // Invalidate its callbacks before releasing the current batch state.
      attemptSequence.current += 1
      attemptController.current?.abort()
      resetAttempt()
      queryClient.setQueryData(
        PLATFORM_CONNECTIONS_QUERY_KEY,
        (current: { platforms: PlatformConnection[] } | undefined) => {
          if (current === undefined) {
            return current
          }
          return {
            platforms: current.platforms.map((connection) =>
              connection.status === 'checking'
                ? {
                    ...connection,
                    status: 'failed' as const,
                    guidance: 'retry' as const,
                    active_attempt_id: null,
                  }
                : connection,
            ),
          }
        },
      )
      batchDetectionRef.current = null
      setBatchDetection(null)
      setBatchMessage(message)
    },
    [queryClient, resetAttempt],
  )

  const startAttempt = (platform: PlatformId) => {
    if (operationActive || healthState.status !== 'connected') {
      return
    }
    browserMutation.reset()
    attemptMutation.reset()
    setBatchMessage(null)
    attemptMutation.mutate(platform)
  }

  const startBatchDetection = () => {
    if (batchUnavailable) {
      return
    }

    browserMutation.reset()
    attemptMutation.reset()
    setBatchMessage(null)
    batchRunSequence.current += 1
    const nextBatch: BatchDetection = {
      runId: batchRunSequence.current,
      platforms: enabledPlatforms.map(({ platform, display_name }) => ({
        platform,
        display_name,
      })),
      currentIndex: 0,
      phase: 'starting',
      deadlineAt: Date.now() + BATCH_CHECK_DEADLINE_MS,
    }
    batchDetectionRef.current = nextBatch
    setBatchDetection(nextBatch)
  }

  useEffect(() => {
    if (batchDetection === null) {
      return
    }

    const remaining = batchDetection.deadlineAt - Date.now()
    if (remaining <= 0) {
      stopBatch('检查失败，请稍后重试。', batchDetection)
      return
    }

    const timer = window.setTimeout(
      () => stopBatch('检查失败，请稍后重试。', batchDetection),
      remaining,
    )
    return () => window.clearTimeout(timer)
  }, [batchDetection, stopBatch])

  useEffect(() => {
    if (batchDetection === null) {
      return
    }
    if (healthState.status !== 'connected' || connectionsQuery.error) {
      stopBatch(
        connectionsQuery.error instanceof PlatformConnectionApiError
          ? connectionsQuery.error.message
          : '无法连接本地服务，请确认服务已启动。',
        batchDetection,
      )
    }
  }, [batchDetection, connectionsQuery.error, healthState.status, stopBatch])

  useEffect(() => {
    if (batchDetection === null) {
      return
    }

    const current = batchDetection.platforms[batchDetection.currentIndex]
    if (current === undefined) {
      batchDetectionRef.current = null
      setBatchDetection(null)
      return
    }

    if (batchDetection.phase === 'starting') {
      const stepKey = `${batchDetection.runId}:${batchDetection.currentIndex}`
      if (launchedBatchStep.current === stepKey) {
        return
      }

      launchedBatchStep.current = stepKey
      resetAttempt()
      mutateAttempt(current.platform, {
        onSuccess: () => {
          setBatchDetection((activeBatch) =>
            activeBatch?.runId === batchDetection.runId &&
            activeBatch.currentIndex === batchDetection.currentIndex
              ? { ...activeBatch, phase: 'waiting' }
              : activeBatch,
          )
        },
        onError: (error) => {
          const expectedStep: BatchStep = batchDetection
          const canSkipPlatform =
            error instanceof PlatformConnectionApiError &&
            (error.code === 'platform_not_found' ||
              error.code === 'platform_not_available')
          if (!canSkipPlatform) {
            stopBatch(null, expectedStep)
            return
          }
          const activeBatch = batchDetectionRef.current
          if (
            activeBatch === null ||
            activeBatch.runId !== expectedStep.runId ||
            activeBatch.currentIndex !== expectedStep.currentIndex
          ) {
            return
          }

          queryClient.setQueryData(
            PLATFORM_CONNECTIONS_QUERY_KEY,
            (snapshot: { platforms: PlatformConnection[] } | undefined) => {
              if (snapshot === undefined) {
                return snapshot
              }
              return {
                platforms: snapshot.platforms.map((connection) =>
                  connection.platform === current.platform
                    ? {
                        ...connection,
                        status: 'failed' as const,
                        guidance: 'retry' as const,
                        active_attempt_id: null,
                      }
                    : connection,
                ),
              }
            },
          )
          setBatchMessage(error.message)
          setBatchDetection((activeBatch) => {
            if (
              activeBatch?.runId !== expectedStep.runId ||
              activeBatch.currentIndex !== expectedStep.currentIndex
            ) {
              return activeBatch
            }
            const nextIndex = activeBatch.currentIndex + 1
            return nextIndex < activeBatch.platforms.length
              ? { ...activeBatch, currentIndex: nextIndex, phase: 'starting' }
              : null
          })
        },
      })
      return
    }

    const currentConnection = platforms.find(
      (connection) => connection.platform === current.platform,
    )
    if (
      currentConnection === undefined ||
      isPlatformConnectionActive(currentConnection)
    ) {
      return
    }

    setBatchDetection((activeBatch) => {
      if (
        activeBatch?.runId !== batchDetection.runId ||
        activeBatch.currentIndex !== batchDetection.currentIndex
      ) {
        return activeBatch
      }

      const nextIndex = activeBatch.currentIndex + 1
      return nextIndex < activeBatch.platforms.length
        ? { ...activeBatch, currentIndex: nextIndex, phase: 'starting' }
        : null
    })
  }, [batchDetection, mutateAttempt, platforms, resetAttempt, stopBatch])

  const retryPlatformState = () => {
    retryHealth()
    void connectionsQuery.refetch()
  }

  const openBrowser = (platform?: PlatformId) => {
    if (operationActive || healthState.status !== 'connected') {
      return
    }
    attemptMutation.reset()
    browserMutation.reset()
    setBatchMessage(null)
    browserMutation.mutate(platform)
  }

  return (
    <div className="space-y-5">
      <section>
        <Card className="connection-panel bg-card/94">
          <CardHeader className="border-b border-border/75 sm:grid-cols-[minmax(0,1fr)_auto]">
            <div>
              <CardTitle className="font-display text-xl font-semibold tracking-[-0.03em]">
                登录状态
              </CardTitle>
            </div>
            <div className="mt-3 flex min-w-0 items-center justify-between gap-3 sm:mt-0 sm:justify-end">
              {batchProgress && (
                <div
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  className="text-xs text-muted-foreground"
                >
                  {batchProgress}
                </div>
              )}
              <div className="ml-auto flex flex-wrap justify-end gap-2">
                <Button
                  type="button"
                  size="sm"
                  className="min-h-11 min-w-32 sm:min-h-7"
                  disabled={
                    operationActive || healthState.status !== 'connected'
                  }
                  onClick={() => openBrowser()}
                >
                  {browserMutation.isPending ? '打开中…' : '打开专用浏览器'}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="min-h-11 min-w-24 sm:min-h-7"
                  disabled={batchUnavailable}
                  onClick={startBatchDetection}
                >
                  {batchDetection === null ? '检查全部' : '检查中…'}
                </Button>
              </div>
            </div>
          </CardHeader>

          {connectionsQuery.isPending && (
            <CardContent className="grid min-h-80 place-items-center text-center">
              <div role="status" aria-live="polite">
                <span
                  className="signal-loader mx-auto block"
                  aria-hidden="true"
                />
                <p className="mt-4 text-sm text-muted-foreground">
                  正在读取登录状态…
                </p>
              </div>
            </CardContent>
          )}

          {queryMessage && platforms.length === 0 && (
            <CardContent className="grid min-h-80 place-items-center py-10 text-center">
              <div role="alert" className="max-w-sm">
                <Badge
                  variant="outline"
                  className="border-warning/30 text-warning-foreground"
                >
                  读取失败
                </Badge>
                <p className="mt-4 text-sm leading-6 text-foreground">
                  {queryMessage}
                </p>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  请重新启动应用后再试。
                </p>
                <Button
                  type="button"
                  size="sm"
                  className="mt-5 min-h-11 sm:min-h-7"
                  onClick={retryPlatformState}
                >
                  重新读取
                </Button>
              </div>
            </CardContent>
          )}

          {panelAlertMessage && (
            <div
              className="border-b border-warning/20 bg-warning/8 px-4 py-3 text-sm leading-6 text-foreground sm:px-6"
              role="alert"
              aria-live="assertive"
            >
              {panelAlertMessage}
            </div>
          )}

          {platforms.length > 0 && (
            <ol className="platform-bus" aria-label="平台账号登录状态">
              {platforms.map((connection) => (
                <PlatformRow
                  key={connection.platform}
                  connection={connection}
                  operationActive={operationActive}
                  serviceAvailable={healthState.status === 'connected'}
                  onOpen={openBrowser}
                  onStart={startAttempt}
                />
              ))}
            </ol>
          )}
        </Card>
      </section>
    </div>
  )
}
