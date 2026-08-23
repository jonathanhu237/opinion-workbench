import { createBrowserRouter, Outlet } from 'react-router'

import { Home } from '@/routes/home'
import { RouteErrorBoundary } from '@/routes/route-error-boundary'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Outlet />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        index: true,
        element: <Home />,
      },
    ],
  },
])
