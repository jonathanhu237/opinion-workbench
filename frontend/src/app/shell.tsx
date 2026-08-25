import { CircleUserRound, ListChecks, SlidersHorizontal } from 'lucide-react'
import { useEffect, useReducer, useRef } from 'react'
import { NavLink, Outlet, useLocation, useOutletContext } from 'react-router'

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
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
  '/': '工作台',
  '/platform-accounts': '平台账号',
  '/monitoring-rules': '监控规则',
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

  const navigationItems = [
    {
      label: '工作台',
      to: '/',
      icon: SlidersHorizontal,
      isActive: location.pathname === '/',
    },
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
  ] as const

  return (
    <nav aria-label="主导航">
      <SidebarMenu>
        {navigationItems.map((item) => {
          const Icon = item.icon

          return (
            <SidebarMenuItem key={item.to}>
              <SidebarMenuButton
                render={
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    onClick={() => setOpenMobile(false)}
                  />
                }
                isActive={item.isActive}
                className="min-h-11 gap-3 rounded-lg px-3 text-sidebar-foreground/78 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:min-h-10 data-active:bg-sidebar-primary data-active:text-sidebar-primary-foreground data-active:shadow-[inset_3px_0_0_var(--sidebar-ring)]"
              >
                <Icon className="size-4" aria-hidden />
                <span>{item.label}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    </nav>
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
  }, [healthCheckSequence])

  useEffect(() => {
    if (previousPath.current === location.pathname) {
      return
    }

    previousPath.current = location.pathname
    document.getElementById('main-content')?.focus()
  }, [location.pathname])

  const pageTitle = pageTitles[location.pathname] ?? '当前页面'

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
        <SidebarContent className="px-2 py-3">
          <SidebarGroup className="p-0">
            <SidebarGroupLabel className="px-3 text-[10px] tracking-[0.16em] text-sidebar-foreground/60">
              值守功能
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <PrimaryNavigation />
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
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
            <p className="truncate text-[10px] tracking-[0.12em] text-muted-foreground">
              龙田街道舆情值守
            </p>
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
