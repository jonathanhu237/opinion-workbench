import { isRouteErrorResponse, useRouteError } from 'react-router'

export function RouteErrorBoundary() {
  const error = useRouteError()
  const detail = isRouteErrorResponse(error)
    ? error.statusText || '无法打开此页面。'
    : '无法打开此页面。'

  return (
    <main className="grid min-h-svh place-items-center px-6 py-16">
      <div className="max-w-md text-center">
        <p className="font-utility text-xs font-semibold tracking-[0.18em] text-primary uppercase">
          Local watch desk
        </p>
        <h1 className="mt-4 font-display text-3xl font-semibold tracking-[-0.04em] text-foreground">
          页面暂时无法显示
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{detail}</p>
      </div>
    </main>
  )
}
