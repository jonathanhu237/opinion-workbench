import { createBrowserRouter, type RouteObject } from 'react-router'

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
        path: 'platform-accounts',
        element: <PlatformAccounts />,
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

export const router = createBrowserRouter(appRoutes)
