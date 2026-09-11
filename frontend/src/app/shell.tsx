import {
  CircleUserRound,
  ClipboardList,
  FileSearch,
  ListChecks,
  Settings2,
} from 'lucide-react'
import { useEffect, useReducer, useRef } from 'react'
import { NavLink, Outlet, useLocation, useOutletContext } from 'react-router'

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar'
import { fetchHealth, type HealthResponse } from '@/lib/api/health'

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
  retryHealth: () => void
}

const pageTitles: Record<string, string> = {
  '/': '平台账号',
  '/platform-accounts': '平台账号',
  '/monitoring-rules': '监控规则',
  '/collection-runs': '舆情爬取',
  '/automation-tasks': '自动任务',
  '/reports/new': '生成报告',
  '/reports/history': '报告记录',
  '/reports': '舆情报告',
  '/settings': '设置',
  '/results': '生成报告',
  '/ai-settings': 'AI 配置',
}

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
    <div className="flex min-w-0 items-center gap-3">
      <FourCommunityMark />
      <div className="min-w-0">
        <p className="font-display text-lg leading-none font-semibold tracking-[-0.03em] text-sidebar-foreground">
          舆情分析平台
        </p>
      </div>
    </div>
  )
}

function PrimaryNavigation() {
  const location = useLocation()
  const { setOpenMobile } = useSidebar()
  const settingsActive =
    location.pathname.startsWith('/settings') ||
    location.pathname === '/ai-settings'

  const navigationItems = [
    {
      label: '平台账号',
      to: '/platform-accounts',
      icon: CircleUserRound,
      isActive: location.pathname === '/platform-accounts',
    },
    {
      label: '监控规则',
      to: '/monitoring-rules',
      icon: ListChecks,
      isActive: location.pathname === '/monitoring-rules',
    },
    {
      label: '舆情爬取',
      to: '/collection-runs',
      icon: ClipboardList,
      isActive:
        location.pathname.startsWith('/collection-runs') ||
        location.pathname.startsWith('/collection-batches'),
    },
    {
      label: '舆情报告',
      to: '/reports',
      icon: FileSearch,
      isActive:
        location.pathname.startsWith('/reports') ||
        location.pathname === '/results',
    },
  ] as const

  const renderLink = (item: (typeof navigationItems)[number]) => {
    const Icon = item.icon

    return (
      <SidebarMenuItem key={item.to}>
        <SidebarMenuButton
          render={
            <NavLink to={item.to} end onClick={() => setOpenMobile(false)} />
          }
          isActive={item.isActive}
          className="min-h-11 gap-3 rounded-lg px-3 text-sidebar-foreground/78 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:min-h-10 data-active:bg-sidebar-primary data-active:text-sidebar-primary-foreground data-active:shadow-[inset_3px_0_0_var(--sidebar-ring)]"
        >
          <Icon className="size-4" aria-hidden />
          <span>{item.label}</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    )
  }

  return (
    <SidebarMenu>
      {navigationItems.map(renderLink)}
      <SidebarMenuItem>
        <SidebarMenuButton
          render={
            <NavLink
              to="/automation-tasks"
              onClick={() => setOpenMobile(false)}
            />
          }
          isActive={
            location.pathname.startsWith('/automation-tasks') ||
            location.pathname.startsWith('/automation-runs')
          }
          className="min-h-11 gap-3 rounded-lg px-3 text-sidebar-foreground/78 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:min-h-10 data-active:bg-sidebar-primary data-active:text-sidebar-primary-foreground data-active:shadow-[inset_3px_0_0_var(--sidebar-ring)]"
        >
          <ClipboardList className="size-4" aria-hidden />
          <span>自动任务</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
        <SidebarMenuButton
          render={
            <NavLink to="/settings" onClick={() => setOpenMobile(false)} />
          }
          isActive={settingsActive}
          className="min-h-11 gap-3 rounded-lg px-3 text-sidebar-foreground/78 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:min-h-10 data-active:bg-sidebar-primary data-active:text-sidebar-primary-foreground data-active:shadow-[inset_3px_0_0_var(--sidebar-ring)]"
        >
          <Settings2 className="size-4" aria-hidden />
          <span>设置</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

export function useAppShell() {
  return useOutletContext<ShellContext>()
}

export function AppShell() {
  const location = useLocation()
  const previousPath = useRef(location.pathname)
  const [healthState, dispatch] = useReducer(healthReducer, {
    status: 'loading',
  })
  const [healthCheckSequence, retryHealth] = useReducer(
    (sequence: number) => sequence + 1,
    0,
  )

  useEffect(() => {
    // The packaged build is served by the local API process.  A WebSocket
    // keeps the process aware of open pages even when a background tab's
    // JavaScript timers are throttled; development's separate Vite/API
    // processes intentionally keep their historical lifetime.
    if (import.meta.env.VITE_LIFECYCLE_ENABLED !== '1') return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const endpoint = `${protocol}//${window.location.host}/api/v1/lifecycle/ws`
    let socket: WebSocket | null = null
    let retryTimer: number | undefined
    let retryDelay = 250
    let stopped = false

    const scheduleReconnect = () => {
      if (stopped || retryTimer !== undefined) return
      retryTimer = window.setTimeout(() => {
        retryTimer = undefined
        connect()
      }, retryDelay)
      retryDelay = Math.min(retryDelay * 2, 4000)
    }

    const connect = () => {
      if (stopped) return
      const candidate = new WebSocket(endpoint)
      socket = candidate
      candidate.onopen = () => {
        retryDelay = 250
        if (candidate.readyState === WebSocket.OPEN) {
          candidate.send(JSON.stringify({ type: 'heartbeat' }))
        }
      }
      candidate.onclose = () => {
        if (socket === candidate) socket = null
        scheduleReconnect()
      }
      candidate.onerror = () => {
        // Browsers report the useful retry signal through close; closing here
        // also handles implementations that leave an errored socket open.
        candidate.close()
      }
    }

    const heartbeat = window.setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'heartbeat' }))
      }
    }, 4000)
    connect()
    return () => {
      stopped = true
      window.clearInterval(heartbeat)
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
      socket?.close()
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'check' })

    void fetchHealth(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          dispatch({ type: 'connected', data })
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          dispatch({
            type: 'unavailable',
            message: '无法连接服务，请确认后端已启动。',
          })
        }
      })

    return () => controller.abort()
  }, [healthCheckSequence])

  useEffect(() => {
    if (previousPath.current === location.pathname) {
      return
    }

    previousPath.current = location.pathname
    document.getElementById('main-content')?.focus()
  }, [location.pathname])

  const pageTitle = location.pathname.startsWith('/collection-batches/')
    ? '批次进度'
    : location.pathname.startsWith('/collection-runs/')
      ? '采集任务详情'
      : location.pathname.startsWith('/automation-runs/')
        ? '自动任务运行详情'
        : location.pathname.startsWith('/automation-tasks/')
          ? '自动任务运行记录'
          : (pageTitles[location.pathname] ?? '当前页面')

  return (
    <SidebarProvider>
      <a
        href="#main-content"
        className="fixed top-2 left-2 z-100 -translate-y-20 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-lg transition-transform focus-visible:translate-y-0 focus-visible:ring-3 focus-visible:ring-ring/50 motion-reduce:transition-none"
      >
        跳到主要内容
      </a>

      <Sidebar collapsible="offcanvas" className="border-sidebar-border">
        <SidebarHeader className="flex-row items-center justify-between px-5 pt-6 pb-5">
          <ProductIdentity />
          <SidebarTrigger
            aria-label="关闭主导航"
            className="size-11 text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:hidden"
          />
        </SidebarHeader>
        <SidebarSeparator />
        <nav aria-label="主导航" className="flex min-h-0 flex-1 flex-col">
          <SidebarContent className="px-2 py-3">
            <SidebarGroup className="p-0">
              <SidebarGroupContent>
                <PrimaryNavigation />
              </SidebarGroupContent>
            </SidebarGroup>
          </SidebarContent>
        </nav>
      </Sidebar>

      <SidebarInset
        id="main-content"
        tabIndex={-1}
        aria-labelledby="page-title"
        className="min-w-0 scroll-mt-20 outline-none"
      >
        <header className="sticky top-0 z-30 flex min-h-16 items-center gap-3 border-b border-border bg-background/94 px-3 backdrop-blur-sm sm:px-6 lg:px-8">
          <SidebarTrigger
            aria-label="切换主导航"
            className="size-11 border border-border bg-card hover:bg-secondary md:size-8"
          />

          <div className="min-w-0">
            <h1
              id="page-title"
              className="truncate text-base font-semibold text-foreground"
            >
              {pageTitle}
            </h1>
          </div>
        </header>

        <div className="mx-auto w-full max-w-[92rem] p-4 sm:p-6 lg:p-8">
          <Outlet
            context={{ healthState, retryHealth } satisfies ShellContext}
          />
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
