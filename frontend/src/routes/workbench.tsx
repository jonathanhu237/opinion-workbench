import {
  ArrowRight,
  CircleCheck,
  CircleDashed,
  CircleUserRound,
  ListChecks,
  MapPinned,
  Server,
} from 'lucide-react'
import { Link } from 'react-router'

import { useAppShell } from '@/app/shell'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { usePlatformConnections } from '@/hooks/use-platform-connections'
import { cn } from '@/lib/utils'

type DutyMetricProps = {
  icon: typeof Server
  label: string
  value: string
  detail: string
  state: 'live' | 'attention' | 'quiet'
  stateLabel: string
}

function DutyMetric({
  icon: Icon,
  label,
  value,
  detail,
  state,
  stateLabel,
}: DutyMetricProps) {
  return (
    <div className="min-w-0 p-4 sm:p-5">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Icon className="size-4" aria-hidden="true" />
        <span>{label}</span>
      </div>
      <p className="mt-4 font-display text-2xl font-semibold tracking-[-0.035em] text-foreground">
        {value}
      </p>
      <div className="mt-2 flex items-center gap-2 text-xs leading-5 text-muted-foreground">
        <span
          className={cn(
            'size-2 shrink-0 rounded-full bg-muted-foreground',
            state === 'live' && 'bg-live',
            state === 'attention' && 'bg-warning',
          )}
          aria-hidden="true"
        />
        <span className="sr-only">{stateLabel}：</span>
        <span>{detail}</span>
      </div>
    </div>
  )
}

export function Workbench() {
  const { healthState } = useAppShell()
  const connectionsQuery = usePlatformConnections()
  const platforms = connectionsQuery.data?.platforms ?? []
  const connectedCount = platforms.filter(
    (platform) => platform.status === 'connected',
  ).length
  const enabledPlatforms = platforms.filter(
    (platform) => platform.availability === 'enabled',
  )
  const enabledPlatformNames = enabledPlatforms
    .map((platform) => platform.display_name)
    .join('、')
  const comingSoonCount = platforms.length - enabledPlatforms.length
  const enabledConnectedCount = enabledPlatforms.filter(
    (platform) => platform.status === 'connected',
  ).length
  const catalogReadable = connectionsQuery.data !== undefined
  const allEnabledConnected =
    enabledPlatforms.length > 0 &&
    enabledConnectedCount === enabledPlatforms.length
  const pendingPlatformCopy =
    comingSoonCount > 0 ? `；其余 ${comingSoonCount} 个平台仍待接入。` : '。'
  const accountReadinessCopy = allEnabledConnected
    ? `${enabledPlatformNames}在线检测均已通过${pendingPlatformCopy}`
    : enabledConnectedCount > 0
      ? `已连接 ${enabledConnectedCount} / ${enabledPlatforms.length} 个可用平台；可以继续检测${enabledPlatformNames}。`
      : enabledPlatforms.length > 0
        ? `先检测${enabledPlatformNames}登录状态${pendingPlatformCopy}`
        : '当前暂无可检测的平台账号。'

  const serviceValue =
    healthState.status === 'connected'
      ? '已连接'
      : healthState.status === 'unavailable'
        ? '不可用'
        : '检测中'
  const serviceDetail =
    healthState.status === 'connected'
      ? '本机后端响应正常'
      : healthState.status === 'unavailable'
        ? '请启动或重试本机服务'
        : '正在确认服务状态'
  const platformDetail = connectionsQuery.isPending
    ? '正在读取平台状态'
    : connectionsQuery.isError
      ? catalogReadable
        ? '显示上次成功读取的状态'
        : '平台状态暂时无法读取'
      : '本次后端会话的在线结果'
  const platformStateLabel = connectionsQuery.isPending
    ? '读取中'
    : connectionsQuery.isError
      ? '读取失败'
      : connectedCount > 0
        ? '已有连接'
        : '尚未连接'

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium tracking-[0.12em] text-primary">
            今日值守
          </p>
          <h2 className="mt-1.5 font-display text-2xl font-semibold tracking-[-0.035em] text-foreground sm:text-[1.75rem]">
            系统准备情况
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            这里只记录本机服务与平台账号的真实状态；尚未建立的数据保持为空。
          </p>
        </div>
        <Badge
          variant="outline"
          className="w-fit border-primary/20 bg-primary/5 text-primary"
        >
          单人本机模式
        </Badge>
      </section>

      <Card
        className="duty-ledger gap-0 bg-card py-0"
        aria-label="值守准备台账"
      >
        <CardHeader className="gap-1 border-b border-border px-4 py-3 sm:px-5">
          <CardTitle className="text-sm">值守准备台账</CardTitle>
          <CardDescription className="text-xs">
            当前状态会随本机服务和平台在线检测更新。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid divide-y divide-border px-0 lg:grid-cols-3 lg:divide-x lg:divide-y-0">
          <DutyMetric
            icon={Server}
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
            stateLabel={
              healthState.status === 'connected'
                ? '正常'
                : healthState.status === 'unavailable'
                  ? '异常'
                  : '检测中'
            }
          />
          <DutyMetric
            icon={CircleUserRound}
            label="平台账号"
            value={
              catalogReadable ? `${connectedCount} / ${platforms.length}` : '—'
            }
            detail={platformDetail}
            state={connectedCount > 0 ? 'live' : 'quiet'}
            stateLabel={platformStateLabel}
          />
          <DutyMetric
            icon={MapPinned}
            label="监控范围"
            value="尚未配置"
            detail="关键词与地址范围功能尚未接入"
            state="quiet"
            stateLabel="规划中"
          />
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="gap-0 bg-card py-0">
          <CardHeader className="border-b border-border px-4 py-4 sm:px-5">
            <CardTitle>值守启用顺序</CardTitle>
            <CardDescription>
              先确认平台登录，再配置范围和采集任务。
            </CardDescription>
          </CardHeader>
          <CardContent className="divide-y divide-border px-0">
            <div className="grid gap-4 p-4 sm:grid-cols-[2.5rem_minmax(0,1fr)_auto] sm:items-center sm:px-5">
              <span className="font-utility text-xs text-primary">01</span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {allEnabledConnected ? (
                    <CircleCheck
                      className="size-4 text-live"
                      aria-hidden="true"
                    />
                  ) : (
                    <CircleUserRound
                      className="size-4 text-primary"
                      aria-hidden="true"
                    />
                  )}
                  <p className="font-medium text-foreground">确认平台账号</p>
                </div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {accountReadinessCopy}
                </p>
              </div>
              <Link
                to="/platform-accounts"
                className={cn(
                  buttonVariants({ variant: 'outline' }),
                  'min-h-11 w-full sm:min-h-8 sm:w-auto',
                )}
              >
                管理平台账号
                <ArrowRight data-icon="inline-end" aria-hidden="true" />
              </Link>
            </div>

            <div className="grid gap-3 p-4 sm:grid-cols-[2.5rem_minmax(0,1fr)_auto] sm:items-center sm:px-5">
              <span className="font-utility text-xs text-muted-foreground">
                02
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <MapPinned
                    className="size-4 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <p className="font-medium text-foreground">配置监控范围</p>
                </div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  龙田街道、四个社区与地址关键词将在后续接入。
                </p>
              </div>
              <Badge variant="outline" className="text-muted-foreground">
                规划中
              </Badge>
            </div>

            <div className="grid gap-3 p-4 sm:grid-cols-[2.5rem_minmax(0,1fr)_auto] sm:items-center sm:px-5">
              <span className="font-utility text-xs text-muted-foreground">
                03
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <ListChecks
                    className="size-4 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <p className="font-medium text-foreground">建立采集任务</p>
                </div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  目前没有可运行的定时采集或舆情处理任务。
                </p>
              </div>
              <Badge variant="outline" className="text-muted-foreground">
                规划中
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card className="gap-0 bg-card py-0">
          <CardHeader className="border-b border-border px-4 py-4 sm:px-5">
            <CardTitle>今日采集</CardTitle>
            <CardDescription>采集任务模块尚未接入。</CardDescription>
          </CardHeader>
          <CardContent className="p-5">
            <div className="flex items-start gap-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-border bg-muted text-muted-foreground">
                <CircleDashed className="size-5" aria-hidden="true" />
              </span>
              <div>
                <p className="font-medium text-foreground">尚未建立采集任务</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  当前没有采集结果、风险事件或待处理任务可展示。
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
