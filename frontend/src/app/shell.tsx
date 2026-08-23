import {
  CircleUserRound,
  FileClock,
  FileSearch,
  ListChecks,
  Menu,
  MessageSquareText,
  Settings2,
  SlidersHorizontal,
} from 'lucide-react'
import { useEffect, useReducer, useState, type ComponentType } from 'react'
import { NavLink, Outlet, useLocation, useOutletContext } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { fetchHealth, type HealthResponse } from '@/lib/api/health'
import { cn } from '@/lib/utils'

export type HealthState =
  | { status: 'loading' }
  | { status: 'connected'; data: HealthResponse }
  | { status: 'unavailable'; message: string }

type HealthAction =
  | { type: 'check' }
  | { type: 'connected'; data: HealthResponse }
  | { type: 'unavailable'; message: string }

type ShellContext = {
  healthState: HealthState
}

type NavigationItem = {
  label: string
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  to?: string
}

const navigationItems: NavigationItem[] = [
  { label: '工作台', icon: SlidersHorizontal, to: '/' },
  { label: '平台账号', icon: CircleUserRound, to: '/platform-accounts' },
  { label: '采集任务', icon: ListChecks },
  { label: '舆情信息', icon: MessageSquareText },
  { label: '监控关键词', icon: FileSearch },
  { label: '舆情日报', icon: FileClock },
  { label: '系统设置', icon: Settings2 },
]

function healthReducer(_state: HealthState, action: HealthAction): HealthState {
  switch (action.type) {
    case 'check':
      return { status: 'loading' }
    case 'connected':
      return { status: 'connected', data: action.data }
    case 'unavailable':
      return { status: 'unavailable', message: action.message }
  }
}

function FourCommunityMark() {
  return (
    <span className="community-watch-mark" aria-hidden="true">
      <span className="community-watch-cell community-watch-cell-a" />
      <span className="community-watch-cell community-watch-cell-b" />
      <span className="community-watch-cell community-watch-cell-c" />
      <span className="community-watch-cell community-watch-cell-d" />
      <span className="community-watch-core" />
    </span>
  )
}

function ProductIdentity() {
  return (
    <div className="flex items-center gap-3">
      <FourCommunityMark />
      <div>
        <p className="font-display text-lg leading-none font-semibold tracking-[-0.03em] text-foreground">
          龙田舆情
        </p>
        <p className="mt-1.5 font-utility text-[9px] tracking-[0.18em] text-muted-foreground uppercase">
          Local watch desk
        </p>
      </div>
    </div>
  )
}

function PrimaryNavigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="主导航" className="space-y-1">
      {navigationItems.map((item) => {
        const Icon = item.icon

        if (item.to !== undefined) {
          return (
            <NavLink
              key={item.label}
              to={item.to}
              end={item.to === '/'}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  'flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors outline-none hover:bg-secondary/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring',
                  isActive &&
                    'bg-primary text-primary-foreground shadow-sm hover:bg-primary hover:text-primary-foreground',
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              <span>{item.label}</span>
            </NavLink>
          )
        }

        return (
          <div
            key={item.label}
            className="flex min-h-10 cursor-not-allowed items-center gap-3 rounded-lg px-3 text-sm text-muted-foreground/65"
            aria-disabled="true"
          >
            <Icon className="size-4" aria-hidden />
            <span>{item.label}</span>
            <Badge
              variant="outline"
              className="ml-auto h-4 border-border/80 px-1.5 text-[9px] font-normal text-muted-foreground"
            >
              规划中
            </Badge>
          </div>
        )
      })}
    </nav>
  )
}

function LocalServiceStatus({
  state,
  onRetry,
}: {
  state: HealthState
  onRetry: () => void
}) {
  return (
    <div
      className="flex min-h-8 items-center gap-2 rounded-full border border-border bg-card/85 py-1 pr-1 pl-3 shadow-sm"
      role={state.status === 'unavailable' ? 'alert' : 'status'}
      aria-live="polite"
    >
      <span
        className={cn(
          'size-2 rounded-full bg-muted-foreground',
          state.status === 'connected' && 'bg-live',
          state.status === 'unavailable' && 'bg-warning',
        )}
        aria-hidden="true"
      />
      <span className="text-xs whitespace-nowrap text-muted-foreground">
        {state.status === 'loading' && '本机服务检测中'}
        {state.status === 'connected' && '本机服务已连接'}
        {state.status === 'unavailable' && '本机服务不可用'}
      </span>
      {state.status === 'unavailable' && (
        <Button type="button" size="xs" variant="ghost" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  )
}

export function useAppShell() {
  return useOutletContext<ShellContext>()
}

export function AppShell() {
  const location = useLocation()
  const [navigationOpen, setNavigationOpen] = useState(false)
  const [healthState, dispatch] = useReducer(healthReducer, {
    status: 'loading',
  })
  const [checkSequence, requestCheck] = useReducer(
    (value: number) => value + 1,
    0,
  )

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'check' })

    void fetchHealth(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          dispatch({ type: 'connected', data })
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          dispatch({
            type: 'unavailable',
            message:
              error instanceof Error ? error.message : '无法连接本机后端服务',
          })
        }
      })

    return () => controller.abort()
  }, [checkSequence])

  const pageTitle =
    location.pathname === '/platform-accounts' ? '平台账号' : '工作台'

  return (
    <div className="min-h-svh lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="hidden border-r border-border/80 bg-card/72 lg:sticky lg:top-0 lg:flex lg:h-svh lg:flex-col">
        <div className="px-5 pt-6 pb-5">
          <ProductIdentity />
        </div>
        <Separator />
        <div className="flex-1 px-3 py-5">
          <PrimaryNavigation />
        </div>
        <div className="px-5 py-5">
          <p className="text-xs leading-5 text-muted-foreground">
            单机值守模式
            <br />
            数据与浏览器操作仅留在本机
          </p>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border/80 bg-background/88 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <Sheet open={navigationOpen} onOpenChange={setNavigationOpen}>
            <SheetTrigger
              render={
                <Button
                  type="button"
                  size="icon"
                  variant="outline"
                  className="lg:hidden"
                  aria-label="打开主导航"
                />
              }
            >
              <Menu aria-hidden="true" />
            </SheetTrigger>
            <SheetContent
              side="left"
              className="w-[18rem] max-w-[88vw] gap-0 bg-card"
            >
              <SheetHeader className="border-b border-border px-5 py-5 text-left">
                <ProductIdentity />
                <SheetTitle className="sr-only">主导航</SheetTitle>
                <SheetDescription className="sr-only">
                  选择龙田舆情系统的功能页面
                </SheetDescription>
              </SheetHeader>
              <div className="flex-1 px-3 py-5">
                <PrimaryNavigation
                  onNavigate={() => setNavigationOpen(false)}
                />
              </div>
            </SheetContent>
          </Sheet>

          <div className="min-w-0">
            <p className="font-utility text-[9px] tracking-[0.16em] text-muted-foreground uppercase">
              龙田街道 · 本机值守台
            </p>
            <h1 className="truncate text-base font-semibold text-foreground">
              {pageTitle}
            </h1>
          </div>

          <div className="ml-auto">
            <LocalServiceStatus state={healthState} onRetry={requestCheck} />
          </div>
        </header>

        <main className="mx-auto w-full max-w-[92rem] p-4 sm:p-6 lg:p-8">
          <Outlet context={{ healthState } satisfies ShellContext} />
        </main>
      </div>
    </div>
  )
}
