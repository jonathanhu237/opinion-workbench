import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, LoaderCircle, Pause, Search } from 'lucide-react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'

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
import { useSearchBatches } from '@/hooks/use-search-batches'
import { useSearchRuns } from '@/hooks/use-search-runs'
import { usePlatformConnections } from '@/hooks/use-platform-connections'
import {
  isActiveSearchBatch,
  SEARCH_BATCHES_QUERY_KEY,
  SearchBatchApiError,
  startSearchBatch,
  type SearchBatchStatus,
  type SearchBatchSummary,
} from '@/lib/api/search-batches'
import {
  isActiveSearchRun,
  type SearchRunStatus,
  type SearchRunSummary,
} from '@/lib/api/search-runs'
import {
  formatLocalDate,
  searchBatchStatusLabel,
  searchPlatformPresenters,
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

function batchBadgeVariant(status: SearchBatchStatus) {
  if (status === 'completed') return 'secondary' as const
  if (isActiveSearchBatch(status)) return 'default' as const
  if (status === 'paused_for_manual_action' || status === 'cancelled') {
    return 'outline' as const
  }
  return 'destructive' as const
}

function runBadgeVariant(status: SearchRunStatus) {
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

function ActiveBatch({ batch }: { batch: SearchBatchSummary }) {
  const paused = batch.status === 'paused_for_manual_action'

  return (
    <Card aria-live="polite" className="border-primary/30 bg-card">
      <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {paused ? (
              <Pause className="size-4 text-primary" aria-hidden />
            ) : (
              <LoaderCircle
                className="size-4 animate-spin text-primary motion-reduce:animate-none"
                aria-hidden
              />
            )}
            <p className="font-medium">
              {paused
                ? '采集已暂停，等待你处理'
                : `正在采集“${batch.rule_name}”`}
            </p>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            已结束 {batch.terminal_item_count} / {batch.platform_count} 个采集项
          </p>
        </div>
        <Link
          className={buttonVariants({ variant: 'outline' })}
          to={`/collection-batches/${batch.id}`}
        >
          查看进度
          <ArrowRight aria-hidden />
        </Link>
      </CardContent>
    </Card>
  )
}

function BatchHistory({ batches }: { batches: SearchBatchSummary[] }) {
  if (batches.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center">
        <p className="font-medium">还没有采集任务</p>
        <p className="mt-1 text-sm text-muted-foreground">
          选择监控规则，开始第一次微博采集。
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
          <TableHead>采集进度</TableHead>
          <TableHead>创建时间</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {batches.map((batch) => (
          <TableRow key={batch.id}>
            <TableCell>
              <Badge variant={batchBadgeVariant(batch.status)}>
                {searchBatchStatusLabel(batch.status)}
              </Badge>
            </TableCell>
            <TableCell>
              <p className="max-w-72 truncate font-medium">{batch.rule_name}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {batch.term_count} 个搜索词 · 每词最多{' '}
                {batch.max_results_per_term} 条
              </p>
            </TableCell>
            <TableCell>
              <span className="font-medium text-foreground">
                {batch.terminal_item_count} / {batch.platform_count}
              </span>
              <span className="ml-1 text-muted-foreground">个微博采集项</span>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {formatLocalDate(batch.created_at)}
            </TableCell>
            <TableCell className="text-right">
              <Link
                className={buttonVariants({ variant: 'ghost', size: 'sm' })}
                to={`/collection-batches/${batch.id}`}
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

function RunHistory({ runs }: { runs: SearchRunSummary[] }) {
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
        {runs.map((run) => {
          const platform = searchPlatformPresenters[run.platform]
          return (
            <TableRow key={run.id}>
              <TableCell>
                <Badge variant={runBadgeVariant(run.status)}>
                  {searchRunStatusLabel(run.status, run.failure_reason)}
                </Badge>
              </TableCell>
              <TableCell>
                <p className="max-w-72 truncate font-medium">{run.rule_name}</p>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <img src={platform.logoSrc} alt="" className="size-4" />
                  <span>{platform.label}</span>
                </div>
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
          )
        })}
      </TableBody>
    </Table>
  )
}

export function CollectionRuns() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const rulesQuery = useMonitoringRules()
  const batchesQuery = useSearchBatches()
  const runsQuery = useSearchRuns()
  const platformsQuery = usePlatformConnections()
  const availablePlatforms =
    platformsQuery.data?.platforms
      .filter((platform) => platform.availability === 'enabled')
      .map((platform) => platform.platform) ?? []
  const enabledRules =
    rulesQuery.data?.rules.filter((rule) => rule.enabled) ?? []
  const ruleOptions = enabledRules.map((rule) => ({
    label: `${rule.name}（${rule.terms.length} 个词）`,
    value: String(rule.id),
  }))
  const openBatch = batchesQuery.data?.batches.find(
    (batch) =>
      isActiveSearchBatch(batch.status) ||
      batch.status === 'paused_for_manual_action',
  )
  const activeStandaloneRun = runsQuery.data?.runs.find((run) =>
    isActiveSearchRun(run.status),
  )
  const form = useForm<StartValues>({
    resolver: zodResolver(startSchema),
    mode: 'onBlur',
    defaultValues: {
      ruleId: '',
      maxResultsPerTerm: 10,
    },
  })
  const startMutation = useMutation({
    mutationFn: (input: Parameters<typeof startSearchBatch>[0]) =>
      startSearchBatch(input),
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
      if (!platformsQuery.isSuccess || !availablePlatforms.includes('wb')) {
        form.setError('root.server', {
          message: '微博采集能力暂时不可用，请稍后重试。',
        })
        return
      }
      const batch = await startMutation.mutateAsync({
        monitoring_rule_id: rule.id,
        max_results_per_term: values.maxResultsPerTerm,
      })
      await queryClient.invalidateQueries({
        queryKey: SEARCH_BATCHES_QUERY_KEY,
      })
      void navigate(`/collection-batches/${batch.id}`)
    } catch (error) {
      form.setError('root.server', {
        message:
          error instanceof SearchBatchApiError
            ? error.message
            : '批量采集未能开始，请重新尝试。',
      })
    }
  })

  const controlsDisabled =
    !platformsQuery.isSuccess ||
    availablePlatforms.length === 0 ||
    startMutation.isPending ||
    openBatch !== undefined ||
    activeStandaloneRun !== undefined

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
            <form onSubmit={submit} noValidate className="grid gap-5">
              <div className="grid gap-5 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto] lg:items-end">
                <Controller
                  name="ruleId"
                  control={form.control}
                  render={({ field, fieldState }) => (
                    <Field data-invalid={fieldState.invalid}>
                      <FieldLabel htmlFor="collection-rule">
                        监控规则
                      </FieldLabel>
                      <Select
                        items={ruleOptions}
                        value={field.value || null}
                        onValueChange={(value) => field.onChange(value ?? '')}
                        disabled={rulesQuery.isPending || controlsDisabled}
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
                        disabled={controlsDisabled}
                      />
                      <FieldError errors={[fieldState.error]} />
                    </Field>
                  )}
                />

                <Button
                  type="submit"
                  className="min-h-11 sm:min-h-8"
                  disabled={controlsDisabled || enabledRules.length === 0}
                >
                  <Search aria-hidden />
                  {startMutation.isPending ? '正在创建…' : '开始采集'}
                </Button>
              </div>

              <div className="flex min-h-11 items-center gap-3 rounded-lg border border-border bg-card px-3 text-sm">
                <img
                  src={searchPlatformPresenters.wb.logoSrc}
                  alt=""
                  className="size-6"
                />
                <span className="font-medium">采集平台：微博</span>
                <span className="text-muted-foreground">
                  当前版本仅支持微博
                </span>
              </div>

              {form.formState.errors.root?.server?.message && (
                <p role="alert" className="text-sm text-destructive">
                  {form.formState.errors.root.server.message}
                </p>
              )}
              {rulesQuery.isError && (
                <p role="alert" className="text-sm text-destructive">
                  监控规则暂时无法读取，请稍后重试。
                </p>
              )}
              {platformsQuery.isError && (
                <div role="alert" className="text-sm">
                  <p>平台能力暂时无法读取，没有开始采集。</p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void platformsQuery.refetch()}
                  >
                    重试读取平台能力
                  </Button>
                </div>
              )}
              {!rulesQuery.isPending &&
                !rulesQuery.isError &&
                enabledRules.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    还没有启用的监控规则，请先到“监控规则”创建或启用一条规则。
                  </p>
                )}
            </form>
          </CardContent>
        </Card>
      </section>

      {openBatch && <ActiveBatch batch={openBatch} />}

      <section aria-labelledby="collection-history-title">
        <h2
          id="collection-history-title"
          className="mb-3 font-display text-xl font-semibold"
        >
          历史任务
        </h2>
        <Card>
          <CardContent className="p-0">
            {batchesQuery.isPending ? (
              <div className="space-y-3 p-5" aria-label="正在加载采集记录">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            ) : batchesQuery.isError ? (
              <div className="p-8 text-center" role="alert">
                <p className="font-medium">采集记录暂时无法读取</p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => batchesQuery.refetch()}
                >
                  重新加载
                </Button>
              </div>
            ) : (
              <>
                <BatchHistory batches={batchesQuery.data?.batches ?? []} />
                {batchesQuery.hasNextPage && (
                  <div className="border-t p-3 text-center">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={batchesQuery.isFetchingNextPage}
                      onClick={() => batchesQuery.fetchNextPage()}
                    >
                      {batchesQuery.isFetchingNextPage
                        ? '正在加载…'
                        : '加载更多任务'}
                    </Button>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </section>

      {(runsQuery.data?.runs.length ?? 0) > 0 && (
        <section aria-labelledby="standalone-history-title">
          <h2
            id="standalone-history-title"
            className="mb-3 font-display text-lg font-semibold"
          >
            独立采集任务
          </h2>
          <Card>
            <CardContent className="p-0">
              <RunHistory runs={runsQuery.data?.runs ?? []} />
              {runsQuery.hasNextPage && (
                <div className="border-t p-3 text-center">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={runsQuery.isFetchingNextPage}
                    onClick={() => runsQuery.fetchNextPage()}
                  >
                    {runsQuery.isFetchingNextPage
                      ? '正在加载…'
                      : '加载更多独立采集任务'}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  )
}
