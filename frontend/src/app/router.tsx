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
    ],
  },
]

export const router = createBrowserRouter(appRoutes)
