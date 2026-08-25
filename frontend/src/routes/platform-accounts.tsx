import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { useAppShell } from '@/app/shell'
import douyinLogo from '@/assets/platforms/douyin.svg'
import kuaishouLogo from '@/assets/platforms/kuaishou.svg'
import toutiaoLogo from '@/assets/platforms/toutiao.svg'
import weiboLogo from '@/assets/platforms/weibo.svg'
import xiaohongshuLogo from '@/assets/platforms/xiaohongshu.svg'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  isPlatformConnectionActive,
  usePlatformConnections,
} from '@/hooks/use-platform-connections'
import {
  PLATFORM_CONNECTIONS_QUERY_KEY,
  PlatformConnectionApiError,
  startPlatformConnectionAttempt,
  type PlatformConnection,
  type PlatformConnectionStatus,
  type PlatformId,
} from '@/lib/api/platform-connections'
import { cn } from '@/lib/utils'

const platformLogos: Record<PlatformId, string> = {
  wb: weiboLogo,
  dy: douyinLogo,
  ks: kuaishouLogo,
  xhs: xiaohongshuLogo,
  toutiao: toutiaoLogo,
}

const statusLabels: Record<PlatformConnectionStatus, string> = {
  not_checked: '待检查',
  checking: '检查中',
  action_required: '需要操作',
  connected: '已登录',
  disconnected: '未登录',
  failed: '检查失败',
  coming_soon: '待接入',
}

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
    case 'coming_soon':
      return 'border-border bg-secondary/60 text-muted-foreground'
    case 'not_checked':
      return 'border-border bg-background text-muted-foreground'
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
  if (status === 'checking' || status === 'action_required') {
    return '处理中…'
  }
  if (status === 'not_checked') {
    return '检查状态'
  }
  return '重新检查'
}

function rowRecoveryMessage(connection: PlatformConnection) {
  if (
    connection.status === 'action_required' &&
    connection.guidance === 'complete_login'
  ) {
    return `请在当前打开的 Chrome 浏览器中登录${connection.display_name}，完成后系统会继续检测。`
  }
  if (connection.status === 'action_required') {
    return `请在当前打开的 Chrome 浏览器中完成${connection.display_name}的操作，完成后系统会继续检测。`
  }
  if (connection.status === 'disconnected') {
    return `请在当前打开的 Chrome 浏览器中登录${connection.display_name}，然后重新检查。`
  }
  if (connection.status === 'failed') {
    return `本次检查未通过。请在当前打开的 Chrome 浏览器中登录${connection.display_name}，然后重新检查。`
  }
  return null
}

type BatchPlatform = Pick<PlatformConnection, 'platform' | 'display_name'>

type BatchDetection = {
  runId: number
  platforms: BatchPlatform[]
  currentIndex: number
  phase: 'starting' | 'waiting'
}

type PlatformRowProps = {
  connection: PlatformConnection
  operationActive: boolean
  serviceAvailable: boolean
  onStart: (platform: PlatformId) => void
}

function PlatformRow({
  connection,
  operationActive,
  serviceAvailable,
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
              src={platformLogos[connection.platform]}
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
          <Button
            type="button"
            size="sm"
            variant={connection.status === 'connected' ? 'outline' : 'default'}
            className="min-h-11 min-w-24 sm:min-h-7 sm:min-w-20"
            disabled={disabled}
            onClick={() => onStart(connection.platform)}
          >
            {attemptButtonLabel(connection.status)}
          </Button>
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
  const batchRunSequence = useRef(0)
  const launchedBatchStep = useRef<string | null>(null)
  const [batchDetection, setBatchDetection] = useState<BatchDetection | null>(
    null,
  )
  const connectionsQuery = usePlatformConnections()
  const attemptMutation = useMutation({
    mutationFn: (platform: PlatformId) => {
      attemptController.current?.abort()
      const controller = new AbortController()
      attemptController.current = controller
      return startPlatformConnectionAttempt(platform, controller.signal)
    },
    onSuccess: (result) => {
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
    onSettled: () => {
      attemptController.current = null
    },
  })

  useEffect(
    () => () => {
      attemptController.current?.abort()
    },
    [],
  )

  const platforms = connectionsQuery.data?.platforms ?? []
  const enabledPlatforms = platforms.filter(
    (connection) => connection.availability === 'enabled',
  )
  const platformOperationActive =
    attemptMutation.isPending || platforms.some(isPlatformConnectionActive)
  const operationActive = batchDetection !== null || platformOperationActive
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
      ? '本机服务不可用。请确认 FastAPI 已在 127.0.0.1:8000 启动。'
      : null
  const panelAlertMessage =
    platforms.length > 0
      ? (mutationMessage ?? queryMessage ?? healthMessage)
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

  const startAttempt = (platform: PlatformId) => {
    if (operationActive || healthState.status !== 'connected') {
      return
    }
    attemptMutation.reset()
    attemptMutation.mutate(platform)
  }

  const startBatchDetection = () => {
    if (batchUnavailable) {
      return
    }

    attemptMutation.reset()
    batchRunSequence.current += 1
    setBatchDetection({
      runId: batchRunSequence.current,
      platforms: enabledPlatforms.map(({ platform, display_name }) => ({
        platform,
        display_name,
      })),
      currentIndex: 0,
      phase: 'starting',
    })
  }

  const mutateAttempt = attemptMutation.mutate
  const resetAttempt = attemptMutation.reset

  useEffect(() => {
    if (batchDetection === null) {
      return
    }

    const current = batchDetection.platforms[batchDetection.currentIndex]
    if (current === undefined) {
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
        onError: () => {
          setBatchDetection((activeBatch) =>
            activeBatch?.runId === batchDetection.runId ? null : activeBatch,
          )
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
  }, [batchDetection, mutateAttempt, platforms, resetAttempt])

  const retryPlatformState = () => {
    retryHealth()
    void connectionsQuery.refetch()
  }

  return (
    <div className="space-y-5">
      <section>
        <h2 className="font-display text-2xl font-semibold tracking-[-0.035em] text-foreground sm:text-[1.75rem]">
          平台账号
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          在这里查看各平台账号的登录状态。需要登录、扫码或安全验证时，请在打开的
          Chrome 浏览器中完成。
        </p>
      </section>

      <section>
        <Card className="connection-panel bg-card/94">
          <CardHeader className="border-b border-border/75 sm:grid-cols-[minmax(0,1fr)_auto]">
            <div>
              <CardTitle className="font-display text-xl font-semibold tracking-[-0.03em]">
                登录状态
              </CardTitle>
              <CardDescription className="mt-1.5 max-w-xl leading-5">
                为避免浏览器操作相互影响，每次只能检查一个平台。
              </CardDescription>
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
              <Button
                type="button"
                size="sm"
                className="ml-auto min-h-11 min-w-24 sm:min-h-7"
                disabled={batchUnavailable}
                onClick={startBatchDetection}
              >
                {batchDetection === null ? '一键检测' : '检测中…'}
              </Button>
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
                  请确认 FastAPI 已在 127.0.0.1:8000 启动。
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
