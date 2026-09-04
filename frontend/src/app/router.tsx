import {
  createBrowserRouter,
  Navigate,
  useLocation,
  type RouteObject,
} from 'react-router'

import { AppShell } from '@/app/shell'
import { PlatformAccounts } from '@/routes/platform-accounts'
import { RouteErrorBoundary } from '@/routes/route-error-boundary'
import { Workbench } from '@/routes/workbench'

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        index: true,
        element: <Workbench />,
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
        path: 'settings/ai',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载 AI 配置…
          </p>
        ),
        lazy: async () => {
          const { AISettings } = await import('@/routes/ai-settings')
          return { Component: AISettings }
        },
      },
      {
        path: 'settings/media',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载媒体缓存…
          </p>
        ),
        lazy: async () => {
          const { MediaSettings } = await import('@/routes/media-settings')
          return { Component: MediaSettings }
        },
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
        path: 'reports/new',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载生成报告…
          </p>
        ),
        lazy: async () => {
          const { ReportGeneration } = await import('@/routes/results')
          return { Component: ReportGeneration }
        },
      },
      {
        path: 'reports/history',
        hydrateFallbackElement: (
          <p role="status" className="text-sm text-muted-foreground">
            正在加载报告记录…
          </p>
        ),
        lazy: async () => {
          const { ReportRecords } = await import('@/routes/results')
          return { Component: ReportRecords }
        },
      },
      {
        path: 'ai-settings',
        element: <LegacyPathRedirect to="/settings/ai" />,
      },
      {
        path: 'media-settings',
        element: <LegacyPathRedirect to="/settings/media" />,
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
  const records =
    params.get('view') === 'records' ||
    params.has('generation') ||
    params.has('report') ||
    params.has('job')
  params.delete('view')
  const nextSearch = params.toString()
  return {
    pathname: records ? '/reports/history' : '/reports/new',
    search: nextSearch ? `?${nextSearch}` : '',
  }
}

function LegacyResultsRedirect() {
  const location = useLocation()
  return <Navigate replace to={legacyResultsDestination(location.search)} />
}

function LegacyPathRedirect({ to }: { to: string }) {
  const location = useLocation()
  return (
    <Navigate
      replace
      to={{ pathname: to, search: location.search, hash: location.hash }}
    />
  )
}

export const router = createBrowserRouter(appRoutes)
