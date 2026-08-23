import { useEffect, useReducer } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { fetchHealth, type HealthResponse } from '@/lib/api/health'

type HealthState =
  | { status: 'loading' }
  | { status: 'connected'; data: HealthResponse }
  | { status: 'unavailable'; message: string }

type HealthAction =
  | { type: 'check' }
  | { type: 'connected'; data: HealthResponse }
  | { type: 'unavailable'; message: string }

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

function ConnectionMark({ state }: { state: HealthState['status'] }) {
  return (
    <div className="connection-mark" data-state={state} aria-hidden="true">
      <span className="community-cell community-cell-a" />
      <span className="community-cell community-cell-b" />
      <span className="community-cell community-cell-c" />
      <span className="community-cell community-cell-d" />
      <span className="connection-core" />
    </div>
  )
}

export function Home() {
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

  const isLoading = healthState.status === 'loading'

  return (
    <main className="min-h-svh px-5 py-5 sm:px-8 sm:py-8">
      <div className="mx-auto flex min-h-[calc(100svh-2.5rem)] max-w-6xl flex-col sm:min-h-[calc(100svh-4rem)]">
        <header className="flex items-center justify-between gap-4 border-b border-foreground/10 pb-4">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-md bg-primary font-utility text-xs font-semibold tracking-[0.16em] text-primary-foreground">
              LT
            </span>
            <div>
              <p className="text-sm font-semibold tracking-[0.08em] text-foreground">
                龙田街道舆情系统
              </p>
              <p className="font-utility text-[10px] tracking-[0.18em] text-muted-foreground uppercase">
                Local watch desk
              </p>
            </div>
          </div>
          <Badge variant="outline" className="bg-background/70 font-normal">
            本机运行
          </Badge>
        </header>

        <section className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[1.08fr_0.92fr] lg:gap-16 lg:py-14">
          <div className="max-w-2xl">
            <p className="mb-5 font-utility text-xs font-semibold tracking-[0.22em] text-primary uppercase">
              系统初始化 · 连接检测
            </p>
            <h1 className="font-display text-[clamp(3rem,8vw,6.5rem)] leading-[0.94] font-semibold tracking-[-0.06em] text-foreground">
              舆情值守，
              <br />
              <span className="text-primary">从连通开始。</span>
            </h1>
            <p className="mt-7 max-w-lg text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
              当前页面只验证本机前端与后端服务。平台登录、采集与舆情处置将在后续模块中逐步接入。
            </p>
          </div>

          <Card className="status-card relative overflow-hidden bg-card/90">
            <div className="absolute inset-x-0 top-0 h-1 bg-primary/20" />
            <CardHeader className="grid grid-cols-[1fr_auto] items-start gap-4 sm:gap-6">
              <div>
                <CardDescription className="font-utility text-[11px] tracking-[0.18em] uppercase">
                  API connection
                </CardDescription>
                <CardTitle className="mt-3 font-display text-2xl tracking-[-0.035em] sm:text-3xl">
                  {healthState.status === 'loading' && '正在连接本机服务'}
                  {healthState.status === 'connected' && '后端已连接'}
                  {healthState.status === 'unavailable' && '后端暂时不可用'}
                </CardTitle>
              </div>
              <ConnectionMark state={healthState.status} />
            </CardHeader>

            <CardContent>
              <div
                className="min-h-32 rounded-lg border border-border/80 bg-secondary/45 p-5"
                role={healthState.status === 'unavailable' ? 'alert' : 'status'}
                aria-live="polite"
              >
                {healthState.status === 'loading' && (
                  <div className="space-y-3">
                    <Badge variant="secondary">检测中</Badge>
                    <p className="text-sm leading-6 text-muted-foreground">
                      正在通过本机接口确认服务状态…
                    </p>
                  </div>
                )}

                {healthState.status === 'connected' && (
                  <div className="space-y-3">
                    <Badge className="bg-live text-white hover:bg-live">
                      运行正常
                    </Badge>
                    <p className="text-sm leading-6 text-muted-foreground">
                      前后端健康检查已完成，可以继续搭建业务功能。
                    </p>
                    <p className="font-utility text-[11px] tracking-[0.08em] break-all text-foreground/65">
                      {healthState.data.service}
                    </p>
                  </div>
                )}

                {healthState.status === 'unavailable' && (
                  <div className="space-y-4">
                    <Badge
                      variant="outline"
                      className="border-warning/35 text-warning"
                    >
                      需要检查
                    </Badge>
                    <div>
                      <p className="text-sm leading-6 text-foreground">
                        请确认 FastAPI 已在 127.0.0.1:8000 启动。
                      </p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {healthState.message}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-5 flex items-center justify-between gap-4 border-t border-border/70 pt-5">
                <p className="font-utility text-[10px] tracking-[0.16em] text-muted-foreground uppercase">
                  /api/v1/health
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant={
                    healthState.status === 'unavailable' ? 'default' : 'outline'
                  }
                  disabled={isLoading}
                  onClick={requestCheck}
                >
                  {isLoading ? '检测中…' : '重新检测'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        <footer className="flex flex-col gap-2 border-t border-foreground/10 py-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>服务仅监听本机地址</span>
          <span className="font-utility tracking-[0.14em] uppercase">
            Longtian · Shenzhen
          </span>
        </footer>
      </div>
    </main>
  )
}
