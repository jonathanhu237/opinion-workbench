import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { useAppShell } from '@/app/shell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
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

const platformMarks: Record<PlatformId, string> = {
  wb: 'WB',
  dy: 'DY',
  ks: 'KS',
  xhs: 'RED',
  toutiao: 'TT',
}

const statusLabels: Record<PlatformConnectionStatus, string> = {
  not_checked: '待检测',
  checking: '检测中',
  action_required: '需要人工操作',
  connected: '已连接',
  disconnected: '未连接',
  failed: '检测失败',
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
    return '尚未检测'
  }

  return `上次检测 ${new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(timestamp))}`
}

function guidanceFor(connection: PlatformConnection | undefined) {
  if (connection === undefined) {
    return '正在读取平台连接状态…'
  }

  switch (connection.guidance) {
    case 'enable_remote_debugging':
      return 'Chrome 已打开远程调试设置，请在其中启用本机调试连接。'
    case 'approve_connection':
      return '请在 Chrome 中批准本机连接，然后保留浏览器窗口。'
    case 'complete_login':
      return `请在 Chrome 的${connection.display_name}官方页面完成扫码或安全验证。`
    case 'retry':
      return '本次检测未完成。确认 Chrome 可用后，可以重新检测。'
    case 'none':
      break
  }

  switch (connection.status) {
    case 'not_checked':
      return `先检测${connection.display_name}是否仍然登录。需要登录时，系统会把操作交给可见的 Chrome。`
    case 'checking':
      return `正在检查${connection.display_name}登录状态，请暂时保留 Chrome 窗口。`
    case 'connected':
      return `${connection.display_name}账号已通过在线检测，可以继续准备后续采集功能。`
    case 'disconnected':
      return `${connection.display_name}尚未连接。重新检测后，请在可见的 Chrome 中完成登录。`
    case 'failed':
      return '连接检测遇到技术问题。确认本机 Chrome 可用后重新检测。'
    case 'action_required':
      return `请按 Chrome 中${connection.display_name}官方页面的提示完成当前操作。`
    case 'coming_soon':
      return '该平台将在后续版本中接入。'
  }
}

function relevantConnection(platforms: PlatformConnection[]) {
  const enabled = platforms.filter(
    (connection) => connection.availability === 'enabled',
  )
  const active = enabled.find(isPlatformConnectionActive)
  if (active !== undefined) {
    return active
  }

  const lastChecked = enabled
    .filter((connection) => connection.last_checked_at !== null)
    .sort((left, right) =>
      (right.last_checked_at ?? '').localeCompare(left.last_checked_at ?? ''),
    )[0]

  return lastChecked ?? enabled[0]
}

function attemptButtonLabel(status: PlatformConnectionStatus) {
  if (status === 'checking' || status === 'action_required') {
    return '处理中…'
  }
  if (status === 'not_checked') {
    return '检测连接'
  }
  return '重新检测'
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

  return (
    <li
      className={cn('platform-row', active && 'platform-row-active')}
      data-status={connection.status}
    >
      <span className="platform-node" aria-hidden="true" />
      <div className="platform-identity">
        <span className="platform-mark" aria-hidden="true">
          {platformMarks[connection.platform]}
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
  const { healthState } = useAppShell()
  const queryClient = useQueryClient()
  const attemptController = useRef<AbortController | null>(null)
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
  const operationActive =
    attemptMutation.isPending || platforms.some(isPlatformConnectionActive)
  const mutationMessage =
    attemptMutation.error instanceof PlatformConnectionApiError
      ? attemptMutation.error.message
      : attemptMutation.error instanceof Error
        ? '连接任务未能启动，请重新尝试。'
        : null
  const queryMessage = connectionsQuery.error
    ? connectionsQuery.error instanceof PlatformConnectionApiError
      ? connectionsQuery.error.message
      : '平台状态暂时无法读取。'
    : null
  const currentGuidance =
    mutationMessage ??
    queryMessage ??
    (healthState.status === 'unavailable'
      ? '本机服务不可用。请确认 FastAPI 已在 127.0.0.1:8000 启动。'
      : guidanceFor(relevantConnection(platforms)))

  const startAttempt = (platform: PlatformId) => {
    if (operationActive || healthState.status !== 'connected') {
      return
    }
    attemptMutation.reset()
    attemptMutation.mutate(platform)
  }

  return (
    <div className="space-y-5">
      <section>
        <p className="text-xs font-medium tracking-[0.12em] text-primary">
          账号接入
        </p>
        <h2 className="mt-1.5 font-display text-2xl font-semibold tracking-[-0.035em] text-foreground sm:text-[1.75rem]">
          平台账号连接
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          检测平台账号能否在本机 Chrome
          中继续使用。登录、扫码和安全验证都由你在可见浏览器中完成。
        </p>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="connection-panel self-start bg-card/94">
          <CardHeader className="border-b border-border/75 sm:grid-cols-[1fr_auto]">
            <div>
              <p className="text-[10px] tracking-[0.14em] text-muted-foreground">
                本机浏览器通道
              </p>
              <CardTitle className="mt-1.5 font-display text-xl font-semibold tracking-[-0.03em]">
                平台连接信号
              </CardTitle>
            </div>
            <CardDescription className="max-w-64 leading-5 sm:text-right">
              共用一个本机浏览器通道，同一时间只运行一个连接任务。
            </CardDescription>
          </CardHeader>

          {connectionsQuery.isPending && (
            <CardContent className="grid min-h-80 place-items-center text-center">
              <div role="status" aria-live="polite">
                <span
                  className="signal-loader mx-auto block"
                  aria-hidden="true"
                />
                <p className="mt-4 text-sm text-muted-foreground">
                  正在读取平台状态…
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
                  状态读取失败
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
                  onClick={() => void connectionsQuery.refetch()}
                >
                  重新读取
                </Button>
              </div>
            </CardContent>
          )}

          {platforms.length > 0 && (
            <ol className="platform-bus" aria-label="平台账号连接状态">
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

        <Card className="self-start bg-card/90 xl:sticky xl:top-20">
          <CardHeader>
            <CardTitle>当前操作指引</CardTitle>
            <CardDescription>
              系统只会打开官方页面并检测登录状态。
            </CardDescription>
          </CardHeader>
          <Separator />
          <CardContent>
            <div
              className="min-h-20 text-sm leading-6 text-foreground"
              role={mutationMessage ? 'alert' : 'status'}
              aria-live="polite"
              aria-atomic="true"
            >
              {currentGuidance}
            </div>
            <div className="mt-5 rounded-lg bg-secondary/65 p-3 text-xs leading-5 text-muted-foreground">
              Chrome
              出现授权、扫码或验证码时，请由你本人完成。系统不会读取密码，也不会自动绕过安全验证。
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
