import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, LoaderCircle, Search, Square } from 'lucide-react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'

import toutiaoLogo from '@/assets/platforms/toutiao.svg'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useMonitoringRules } from '@/hooks/use-monitoring-rules'
import { useSearchRuns } from '@/hooks/use-search-runs'
import {
  cancelSearchRun,
  isActiveSearchRun,
  SEARCH_RUNS_QUERY_KEY,
  SearchRunApiError,
  startSearchRun,
  type SearchRunSummary,
} from '@/lib/api/search-runs'
import {
  formatLocalDate,
  searchRunStatusLabel,
} from '@/routes/search-run-presenters'

const startSchema = z.object({
  ruleId: z.string().min(1, '请选择监控规则。'),
  maxResultsPerTerm: z.coerce
    .number<number>()
    .int('请输入整数。')
    .min(1, '每个搜索词至少采集 1 条。')
    .max(50, '每个搜索词最多采集 50 条。'),
})

type StartValues = z.infer<typeof startSchema>

function runBadgeVariant(status: SearchRunSummary['status']) {
  if (status === 'completed_with_results') return 'secondary' as const
  if (isActiveSearchRun(status)) return 'default' as const
  if (
    status === 'completed_empty' ||
    status === 'cancelled' ||
    status === 'login_required' ||
    status === 'manual_challenge_required'
  ) {
    return 'outline' as const
  }
  return 'destructive' as const
}

function cancelErrorMessage(error: unknown) {
  return error instanceof SearchRunApiError
    ? error.message
    : '取消任务失败，请重新尝试。'
}

function ActiveRun({ run }: { run: SearchRunSummary }) {
  const queryClient = useQueryClient()
  const cancelMutation = useMutation({
    mutationFn: () => cancelSearchRun(run.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: SEARCH_RUNS_QUERY_KEY })
    },
  })
  const position = run.current_term_position
  const progress =
    position === null
      ? '正在连接今日头条…'
      : `第 ${position + 1} / ${run.term_count} 个搜索词`

  return (
    <Card aria-live="polite" className="border-primary/30 bg-card">
      <CardContent className="py-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <LoaderCircle
                className="size-4 animate-spin text-primary motion-reduce:animate-none"
                aria-hidden
              />
              <p className="font-medium">正在采集“{run.rule_name}”</p>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{progress}</p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 shrink-0 sm:min-h-8"
            disabled={cancelMutation.isPending}
            onClick={() => cancelMutation.mutate()}
          >
            <Square className="size-3" aria-hidden />
            {cancelMutation.isPending ? '正在取消…' : '取消任务'}
          </Button>
        </div>
        {cancelMutation.isError && (
          <p className="mt-3 text-sm text-destructive" role="alert">
            {cancelErrorMessage(cancelMutation.error)}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function RunHistory({ runs }: { runs: SearchRunSummary[] }) {
  if (runs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center">
        <p className="font-medium">还没有采集记录</p>
        <p className="mt-1 text-sm text-muted-foreground">
          选择一条监控规则，开始第一次今日头条搜索。
        </p>
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>状态</TableHead>
          <TableHead>监控规则</TableHead>
          <TableHead>采集结果</TableHead>
          <TableHead>创建时间</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.id}>
            <TableCell>
              <Badge variant={runBadgeVariant(run.status)}>
                {searchRunStatusLabel(run.status)}
              </Badge>
            </TableCell>
            <TableCell>
              <p className="max-w-72 truncate font-medium">{run.rule_name}</p>
              <p className="text-xs text-muted-foreground">
                {run.term_count} 个搜索词 · 每词最多 {run.max_results_per_term}{' '}
                条
              </p>
            </TableCell>
            <TableCell>
              <span className="font-medium text-foreground">
                新增 {run.new_count}
              </span>
              <span className="mx-2 text-border">/</span>
              <span className="text-muted-foreground">
                再次命中 {run.repeated_count}
              </span>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {formatLocalDate(run.created_at)}
            </TableCell>
            <TableCell className="text-right">
              <Link
                className={buttonVariants({ variant: 'ghost', size: 'sm' })}
                to={`/collection-runs/${run.id}`}
              >
                查看
                <ArrowRight aria-hidden />
              </Link>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function CollectionRuns() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const rulesQuery = useMonitoringRules()
  const runsQuery = useSearchRuns()
  const enabledRules =
    rulesQuery.data?.rules.filter((rule) => rule.enabled) ?? []
  const ruleOptions = enabledRules.map((rule) => ({
    label: `${rule.name}（${rule.terms.length} 个词）`,
    value: String(rule.id),
  }))
  const activeRun = runsQuery.data?.runs.find((run) =>
    isActiveSearchRun(run.status),
  )
  const form = useForm<StartValues>({
    resolver: zodResolver(startSchema),
    mode: 'onBlur',
    defaultValues: { ruleId: '', maxResultsPerTerm: 10 },
  })
  const startMutation = useMutation({
    mutationFn: (input: Parameters<typeof startSearchRun>[0]) =>
      startSearchRun(input),
  })
  const submit = form.handleSubmit(async (values) => {
    form.clearErrors('root.server')
    const rule = enabledRules.find((item) => String(item.id) === values.ruleId)
    if (rule === undefined) {
      form.setError(
        'ruleId',
        { message: '请选择仍然启用的监控规则。' },
        { shouldFocus: true },
      )
      return
    }
    if (rule.terms.length > 20) {
      form.setError(
        'ruleId',
        { message: '这条规则超过 20 个搜索词，请拆分后再采集。' },
        { shouldFocus: true },
      )
      return
    }
    try {
      const run = await startMutation.mutateAsync({
        monitoring_rule_id: rule.id,
        platform: 'toutiao',
        max_results_per_term: values.maxResultsPerTerm,
      })
      await queryClient.invalidateQueries({ queryKey: SEARCH_RUNS_QUERY_KEY })
      void navigate(`/collection-runs/${run.id}`)
    } catch (error) {
      form.setError('root.server', {
        message:
          error instanceof SearchRunApiError
            ? error.message
            : '采集任务未能开始，请重新尝试。',
      })
    }
  })

  return (
    <div className="space-y-6">
      <section aria-labelledby="start-collection-title">
        <Card>
          <CardHeader className="border-b">
            <CardTitle
              id="start-collection-title"
              className="font-display text-2xl"
            >
              开始采集
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-5">
            <form
              onSubmit={submit}
              noValidate
              className="grid gap-5 lg:grid-cols-[minmax(16rem,1fr)_15rem_12rem_auto] lg:items-end"
            >
              <Controller
                name="ruleId"
                control={form.control}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor="collection-rule">监控规则</FieldLabel>
                    <Select
                      items={ruleOptions}
                      value={field.value || null}
                      onValueChange={(value) => field.onChange(value ?? '')}
                      disabled={rulesQuery.isPending || startMutation.isPending}
                    >
                      <SelectTrigger
                        ref={field.ref}
                        id="collection-rule"
                        className="min-h-11 w-full sm:min-h-8"
                        aria-invalid={fieldState.invalid}
                      >
                        <SelectValue placeholder="选择监控规则" />
                      </SelectTrigger>
                      <SelectContent>
                        {ruleOptions.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldError errors={[fieldState.error]} />
                  </Field>
                )}
              />

              <Field>
                <FieldLabel>采集平台</FieldLabel>
                <div className="flex min-h-11 items-center gap-2 rounded-lg border bg-secondary/45 px-3 sm:min-h-8">
                  <img src={toutiaoLogo} alt="" className="size-5" />
                  <span className="text-sm font-medium">今日头条</span>
                </div>
              </Field>

              <Controller
                name="maxResultsPerTerm"
                control={form.control}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor="collection-limit">
                      每词最多采集
                    </FieldLabel>
                    <Input
                      {...field}
                      id="collection-limit"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={50}
                      className="min-h-11 sm:min-h-8"
                      aria-invalid={fieldState.invalid}
                      disabled={startMutation.isPending}
                    />
                    <FieldError errors={[fieldState.error]} />
                  </Field>
                )}
              />

              <Button
                type="submit"
                className="min-h-11 sm:min-h-8"
                disabled={
                  startMutation.isPending ||
                  activeRun !== undefined ||
                  enabledRules.length === 0
                }
              >
                <Search aria-hidden />
                {startMutation.isPending ? '正在创建…' : '开始采集'}
              </Button>

              {form.formState.errors.root?.server?.message && (
                <p
                  role="alert"
                  className="text-sm text-destructive lg:col-span-full"
                >
                  {form.formState.errors.root.server.message}
                </p>
              )}
              {rulesQuery.isError && (
                <p
                  role="alert"
                  className="text-sm text-destructive lg:col-span-full"
                >
                  监控规则暂时无法读取，请稍后重试。
                </p>
              )}
              {!rulesQuery.isPending &&
                !rulesQuery.isError &&
                enabledRules.length === 0 && (
                  <p className="text-sm text-muted-foreground lg:col-span-full">
                    还没有启用的监控规则，请先到“监控规则”创建或启用一条规则。
                  </p>
                )}
            </form>
          </CardContent>
        </Card>
      </section>

      {activeRun && <ActiveRun run={activeRun} />}

      <section aria-labelledby="collection-history-title">
        <div className="mb-3 flex items-center justify-between">
          <h2
            id="collection-history-title"
            className="font-display text-xl font-semibold"
          >
            历史任务
          </h2>
        </div>
        <Card>
          <CardContent className="p-0">
            {runsQuery.isPending ? (
              <div className="space-y-3 p-5" aria-label="正在加载采集记录">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            ) : runsQuery.isError ? (
              <div className="p-8 text-center" role="alert">
                <p className="font-medium">采集记录暂时无法读取</p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => runsQuery.refetch()}
                >
                  重新加载
                </Button>
              </div>
            ) : (
              <>
                <RunHistory runs={runsQuery.data?.runs ?? []} />
                {runsQuery.hasNextPage && (
                  <div className="border-t p-3 text-center">
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11 sm:min-h-8"
                      disabled={runsQuery.isFetchingNextPage}
                      onClick={() => runsQuery.fetchNextPage()}
                    >
                      {runsQuery.isFetchingNextPage
                        ? '正在加载…'
                        : '加载更多任务'}
                    </Button>
                    {runsQuery.isFetchNextPageError && (
                      <p className="mt-2 text-sm text-destructive" role="alert">
                        更多采集记录暂时无法读取，请重新尝试。
                      </p>
                    )}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
