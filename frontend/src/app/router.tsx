import {
  createBrowserRouter,
  Navigate,
  useLocation,
  type RouteObject,
} from 'react-router'

import { AppShell } from '@/app/shell'
import { isReportRecordContext } from '@/lib/report-route-state'
import { PlatformAccounts } from '@/routes/platform-accounts'
import { RouteErrorBoundary } from '@/routes/route-error-boundary'

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        index: true,
        element: <Navigate replace to="/platform-accounts" />,
      },
      {
        path: 'automation-tasks',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载自动任务…
          </p>
        ),
        lazy: async () => {
          const { AutomationTasks } = await import('@/routes/automation-tasks')
          return { Component: AutomationTasks }
        },
      },
      {
        path: 'automation-tasks/:taskId/runs',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载运行记录…
          </p>
        ),
        lazy: async () => {
          const { AutomationTaskRuns } =
            await import('@/routes/automation-tasks')
          return { Component: AutomationTaskRuns }
        },
      },
      {
        path: 'automation-runs/:runId',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载运行详情…
          </p>
        ),
        lazy: async () => {
          const { AutomationRunDetail } =
            await import('@/routes/automation-run-detail')
          return { Component: AutomationRunDetail }
        },
      },
      {
        path: 'platform-accounts',
        element: <PlatformAccounts />,
      },
      {
        path: 'settings',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载设置…
          </p>
        ),
        lazy: async () => {
          const { Settings } = await import('@/routes/settings')
          return { Component: Settings }
        },
      },
      {
        path: 'settings/ai',
        element: <LegacyPathRedirect to="/settings" hash="#ai" />,
      },
      {
        path: 'settings/media',
        element: <LegacyPathRedirect to="/settings" hash="#media" />,
      },
      {
        path: 'monitoring-rules',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载监控规则…
          </p>
        ),
        lazy: async () => {
          const { MonitoringRules } = await import('@/routes/monitoring-rules')
          return { Component: MonitoringRules }
        },
      },
      {
        path: 'results',
        element: <LegacyResultsRedirect />,
      },
      {
        path: 'reports',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载舆情报告…
          </p>
        ),
        lazy: async () => {
          const { ReportHub } = await import('@/routes/reports-page')
          return { Component: ReportHub }
        },
      },
      {
        path: 'reports/new',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载生成报告…
          </p>
        ),
        element: <LegacyReportRedirect mode="generate" />,
      },
      {
        path: 'reports/history',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载报告记录…
          </p>
        ),
        element: <LegacyReportRedirect mode="history" />,
      },
      {
        path: 'ai-settings',
        element: <LegacyPathRedirect to="/settings" hash="#ai" />,
      },
      {
        path: 'media-settings',
        element: <LegacyPathRedirect to="/settings" hash="#media" />,
      },
      {
        path: 'collection-runs',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载采集任务…
          </p>
        ),
        lazy: async () => {
          const { CollectionRuns } = await import('@/routes/collection-runs')
          return { Component: CollectionRuns }
        },
      },
      {
        path: 'collection-batches/:batchId',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载批次进度…
          </p>
        ),
        lazy: async () => {
          const { CollectionBatchDetail } =
            await import('@/routes/collection-batch-detail')
          return { Component: CollectionBatchDetail }
        },
      },
      {
        path: 'collection-runs/:runId',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载采集任务…
          </p>
        ),
        lazy: async () => {
          const { CollectionRunDetail } =
            await import('@/routes/collection-run-detail')
          return { Component: CollectionRunDetail }
        },
      },
    ],
  },
]

export function legacyResultsDestination(search: string) {
  const params = new URLSearchParams(search)
  params.delete('view')
  if (!isReportRecordContext(new URLSearchParams(search))) {
    params.set('generate', '1')
  }
  const nextSearch = params.toString()
  return {
    pathname: '/reports',
    search: nextSearch ? `?${nextSearch}` : '',
  }
}

function LegacyReportRedirect({ mode }: { mode: 'generate' | 'history' }) {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  params.delete('view')
  if (mode === 'generate') params.set('generate', '1')
  const search = params.toString()
  return (
    <Navigate
      replace
      to={{ pathname: '/reports', search: search ? `?${search}` : '' }}
    />
  )
}

function LegacyResultsRedirect() {
  const location = useLocation()
  return <Navigate replace to={legacyResultsDestination(location.search)} />
}

function LegacyPathRedirect({ to, hash }: { to: string; hash?: string }) {
  const location = useLocation()
  return (
    <Navigate
      replace
      to={{
        pathname: to,
        search: location.search,
        hash: hash ?? location.hash,
      }}
    />
  )
}

export const router = createBrowserRouter(appRoutes)
