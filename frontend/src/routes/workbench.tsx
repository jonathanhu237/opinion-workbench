import { ArrowRight, CircleCheck, CircleDashed, Radio } from 'lucide-react'
import { Link } from 'react-router'

import { useAppShell } from '@/app/shell'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { usePlatformConnections } from '@/hooks/use-platform-connections'
import { cn } from '@/lib/utils'

function SummaryCard({
  label,
  value,
  detail,
  state,
}: {
  label: string
  value: string
  detail: string
  state: 'live' | 'attention' | 'quiet'
}) {
  return (
    <Card size="sm" className="min-h-32 bg-card/88">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardAction>
          <span
            className={cn(
              'block size-2 rounded-full bg-muted-foreground',
              state === 'live' && 'bg-live',
              state === 'attention' && 'bg-warning',
            )}
            aria-hidden="true"
          />
        </CardAction>
      </CardHeader>
      <CardContent>
        <p className="font-display text-2xl font-semibold tracking-[-0.035em] text-foreground">
          {value}
        </p>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  )
}

export function Workbench() {
  const { healthState } = useAppShell()
  const connectionsQuery = usePlatformConnections()
  const platforms = connectionsQuery.data?.platforms ?? []
  const connectedCount = platforms.filter(
    (platform) => platform.status === 'connected',
  ).length
  const comingSoonCount = platforms.filter(
    (platform) => platform.availability === 'coming_soon',
  ).length
  const catalogReadable = connectionsQuery.data !== undefined
  const weibo = platforms.find((platform) => platform.platform === 'wb')

  const serviceValue =
    healthState.status === 'connected'
      ? '已连接'
      : healthState.status === 'unavailable'
        ? '不可用'
        : '检测中'
  const serviceDetail =
    healthState.status === 'connected'
      ? 'FastAPI 本机服务响应正常'
      : healthState.status === 'unavailable'
        ? '请先启动或重试本机服务'
        : '正在确认本机服务状态'

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-utility text-[10px] font-semibold tracking-[0.18em] text-primary uppercase">
            System readiness
          </p>
          <h2 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em] text-foreground">
            系统准备情况
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            这里仅显示当前本机服务与平台连接的真实状态。采集任务和舆情数据尚未建立。
          </p>
        </div>
        <Badge
          variant="outline"
          className="w-fit border-primary/20 bg-primary/5 text-primary"
        >
          单人本机模式
        </Badge>
      </section>

      <section className="grid gap-3 sm:grid-cols-3" aria-label="系统状态概览">
        <SummaryCard
          label="本机服务"
          value={serviceValue}
          detail={serviceDetail}
          state={
            healthState.status === 'connected'
              ? 'live'
              : healthState.status === 'unavailable'
                ? 'attention'
                : 'quiet'
          }
        />
        <SummaryCard
          label="已连接平台"
          value={
            catalogReadable ? `${connectedCount} / ${platforms.length}` : '—'
          }
          detail={
            connectionsQuery.isError
              ? '平台状态暂时无法读取'
              : '基于本次后端会话的在线检测结果'
          }
          state={connectedCount > 0 ? 'live' : 'quiet'}
        />
        <SummaryCard
          label="待接入平台"
          value={catalogReadable ? `${comingSoonCount}` : '—'}
          detail="抖音、快手、小红书与今日头条仍在规划中"
          state="quiet"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="bg-card/90">
          <CardHeader className="border-b border-border/70">
            <CardTitle>运行准备</CardTitle>
            <CardDescription>
              先确认平台账号，再进入后续采集能力建设。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
              <div
                className="grid size-14 shrink-0 place-items-center rounded-xl border border-primary/20 bg-secondary text-primary"
                aria-hidden="true"
              >
                {weibo?.status === 'connected' ? (
                  <CircleCheck className="size-6" />
                ) : (
                  <Radio className="size-6" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-foreground">
                  {weibo?.status === 'connected'
                    ? '微博连接已确认'
                    : '平台账号仍需确认'}
                </p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {weibo?.status === 'connected'
                    ? '在线登录探针已通过；采集任务功能仍未接入。'
                    : '前往平台账号页面检测微博登录状态，其他平台暂不提供连接操作。'}
                </p>
              </div>
              <Link
                to="/platform-accounts"
                className={buttonVariants({ variant: 'outline' })}
              >
                管理平台账号
                <ArrowRight data-icon="inline-end" aria-hidden="true" />
              </Link>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/90">
          <CardHeader className="border-b border-border/70">
            <CardTitle>今日采集</CardTitle>
            <CardDescription>采集任务模块尚未接入。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-start gap-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
                <CircleDashed className="size-5" aria-hidden="true" />
              </span>
              <div>
                <p className="font-medium text-foreground">尚未建立采集任务</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  当前没有采集结果、风险事件或待处理任务可展示。
                </p>
                <Badge variant="outline" className="mt-3 text-muted-foreground">
                  规划中
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
