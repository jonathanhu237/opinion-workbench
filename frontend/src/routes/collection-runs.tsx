import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, LoaderCircle, Pause, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from '@/components/ui/field'
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
import { collectionLimitLabel } from '@/lib/collection-limit'
import { useSearchBatches } from '@/hooks/use-search-batches'
import { useSearchRuns } from '@/hooks/use-search-runs'
import { usePlatformConnections } from '@/hooks/use-platform-connections'
import {
  intervalValues,
  usePlatformAccessSettings,
  useSavePlatformAccessSettings,
} from '@/hooks/use-platform-access'
import {
  platformAccessErrorMessage,
  PLATFORM_ACCESS_PLATFORMS,
} from '@/lib/api/platform-access'
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
  SEARCH_PLATFORM_ORDER,
  type SearchRunStatus,
  type SearchRunSummary,
} from '@/lib/api/search-runs'
import {
  formatLocalDate,
  searchBatchStatusLabel,
  searchPlatformPresenters,
  searchRunDisplayLabel,
} from '@/routes/search-run-presenters'

const startSchema = z.object({
  ruleId: z.string().min(1, '请选择监控规则。'),
  platforms: z
    .array(z.enum(SEARCH_PLATFORM_ORDER))
    .min(1, '至少选择一个采集平台。')
    .max(5, '最多选择五个平台。')
    .refine(
      (platforms) =>
        new Set(platforms).size === platforms.length &&
        JSON.stringify(platforms) ===
          JSON.stringify(
            SEARCH_PLATFORM_ORDER.filter((platform) =>
              platforms.includes(platform),
            ),
          ),
      '请按平台目录顺序选择采集平台。',
    ),
  maxResultsPerTerm: z.coerce
    .number<number>()
    .int('请输入整数。')
    .min(1, '每词采集上限至少为 1 条。')
    .max(50, '每词采集上限最多为 50 条。'),
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
    status === 'completed_with_incomplete' ||
    status === 'cancelled' ||
    status === 'login_required' ||
    status === 'manual_challenge_required'
  ) {
    return 'outline' as const
  }
  return 'destructive' as const
}

function PlatformAccessSettingsCard({
  platforms,
}: {
  platforms: readonly (typeof SEARCH_PLATFORM_ORDER)[number][]
}) {
  const settingsQuery = usePlatformAccessSettings()
  const saveMutation = useSavePlatformAccessSettings()
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      PLATFORM_ACCESS_PLATFORMS.map((platform) => [platform, '5']),
    ),
  )
  const loadedRevision = useRef<number | null>(null)
  useEffect(() => {
    if (
      !settingsQuery.data ||
      loadedRevision.current === settingsQuery.data.revision
    )
      return
    loadedRevision.current = settingsQuery.data.revision
    setValues(
      Object.fromEntries(
        PLATFORM_ACCESS_PLATFORMS.map((platform) => [
          platform,
          String(settingsQuery.data.interval_seconds[platform]),
        ]),
      ),
    )
  }, [settingsQuery.data])
  if (platforms.length === 0) return null
  const invalid = PLATFORM_ACCESS_PLATFORMS.some((platform) => {
    if (!platforms.includes(platform)) return false
    const value = Number(values[platform])
    return !Number.isInteger(value) || value < 1 || value > 300
  })
  const submit = () => {
    if (!settingsQuery.data || invalid || saveMutation.isPending) return
    const next = { ...intervalValues(settingsQuery.data.interval_seconds) }
    for (const platform of PLATFORM_ACCESS_PLATFORMS) {
      next[platform] = Number(values[platform])
    }
    saveMutation.mutate({
      expected_revision: settingsQuery.data.revision,
      interval_seconds: next,
    })
  }
  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle className="font-display text-xl">平台访问间隔</CardTitle>
        <p className="text-sm text-muted-foreground">
          约束搜索换词、翻页和报告原帖补全的访问开始时间；不控制单条总结并发。保存后仅影响新任务。
        </p>
      </CardHeader>
      <CardContent className="pt-5">
        {settingsQuery.isPending ? (
          <p role="status" className="text-sm text-muted-foreground">
            正在读取最近的平台访问配置…
          </p>
        ) : settingsQuery.isError ? (
          <div role="alert" className="space-y-3 text-sm">
            <p>{platformAccessErrorMessage(settingsQuery.error)}</p>
            <Button variant="outline" onClick={() => settingsQuery.refetch()}>
              重试读取
            </Button>
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {PLATFORM_ACCESS_PLATFORMS.filter((platform) =>
                platforms.includes(platform),
              ).map((platform) => (
                <Field key={platform}>
                  <FieldLabel htmlFor={`platform-access-${platform}`}>
                    {searchPlatformPresenters[platform].label}
                  </FieldLabel>
                  <div className="flex items-center gap-2">
                    <Input
                      id={`platform-access-${platform}`}
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={300}
                      step={1}
                      value={values[platform]}
                      onChange={(event) =>
                        setValues((current) => ({
                          ...current,
                          [platform]: event.target.value,
                        }))
                      }
                      aria-invalid={invalid}
                    />
                    <span className="shrink-0 text-sm text-muted-foreground">
                      秒
                    </span>
                  </div>
                </Field>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="outline"
                disabled={invalid || saveMutation.isPending}
                onClick={submit}
              >
                {saveMutation.isPending ? '正在保存…' : '保存访问间隔'}
              </Button>
              {invalid && (
                <p role="alert" className="text-sm text-destructive">
                  请输入 1 至 300 秒的整数。
                </p>
              )}
              {saveMutation.isSuccess && (
                <p role="status" className="text-sm text-muted-foreground">
                  已保存；进行中的任务仍使用启动时的配置。
                </p>
              )}
              {saveMutation.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {platformAccessErrorMessage(saveMutation.error)}
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
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
          选择监控规则，开始第一次多平台采集。
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
                {batch.term_count} 个搜索词 · {collectionLimitLabel(batch)}
              </p>
            </TableCell>
            <TableCell>
              <span className="font-medium text-foreground">
                {batch.terminal_item_count} / {batch.platform_count}
              </span>
              <span className="ml-1 text-muted-foreground">个平台采集项</span>
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
                  {searchRunDisplayLabel(run)}
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
  const configuredPlatforms =
    platformsQuery.data?.platforms.map((platform) => platform.platform) ?? []
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
      platforms: [],
      maxResultsPerTerm: 10,
    },
  })
  const initializedPlatforms = useRef(false)
  useEffect(() => {
    if (!platformsQuery.isSuccess || initializedPlatforms.current) return
    initializedPlatforms.current = true
    form.setValue('platforms', availablePlatforms, {
      shouldDirty: false,
      shouldValidate: true,
    })
  }, [availablePlatforms, form, platformsQuery.isSuccess])
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
      if (!platformsQuery.isSuccess || availablePlatforms.length === 0) {
        form.setError('root.server', {
          message: '没有可用的平台采集能力，请稍后重试。',
        })
        return
      }
      if (
        values.platforms.some(
          (platform) => !availablePlatforms.includes(platform),
        )
      ) {
        form.setError('platforms', {
          message: '所选平台当前不可用，请调整后再试。',
        })
        return
      }
      const batch = await startMutation.mutateAsync({
        monitoring_rule_id: rule.id,
        platforms: values.platforms,
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

              <Controller
                name="platforms"
                control={form.control}
                render={({ field, fieldState }) => (
                  <FieldSet
                    data-invalid={fieldState.invalid}
                    className="rounded-xl border bg-muted/25 p-4"
                  >
                    <FieldLegend variant="label">采集平台</FieldLegend>
                    <FieldDescription id="collection-platforms-description">
                      新任务默认选择全部五个平台，可以按本次需要调整；平台按目录顺序依次采集。
                    </FieldDescription>
                    <div
                      role="group"
                      aria-describedby="collection-platforms-description"
                      className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3"
                    >
                      {SEARCH_PLATFORM_ORDER.map((platform) => {
                        const connection = platformsQuery.data?.platforms.find(
                          (item) => item.platform === platform,
                        )
                        const enabled = connection?.availability === 'enabled'
                        const label = searchPlatformPresenters[platform].label
                        return (
                          <Field
                            key={platform}
                            orientation="horizontal"
                            data-disabled={!enabled || controlsDisabled}
                            className="rounded-lg border bg-background/70 p-3"
                          >
                            <Checkbox
                              id={`collection-platform-${platform}`}
                              checked={field.value.includes(platform)}
                              disabled={!enabled || controlsDisabled}
                              aria-invalid={fieldState.invalid}
                              aria-label={`选择采集平台：${label}`}
                              onCheckedChange={(checked) => {
                                const next = checked
                                  ? [...field.value, platform]
                                  : field.value.filter(
                                      (item) => item !== platform,
                                    )
                                field.onChange(
                                  SEARCH_PLATFORM_ORDER.filter((item) =>
                                    next.includes(item),
                                  ),
                                )
                              }}
                            />
                            <FieldContent>
                              <FieldLabel
                                htmlFor={`collection-platform-${platform}`}
                              >
                                {label}
                              </FieldLabel>
                              {!enabled && (
                                <FieldDescription>暂未接入</FieldDescription>
                              )}
                            </FieldContent>
                          </Field>
                        )
                      })}
                    </div>
                    <FieldError errors={[fieldState.error]} />
                  </FieldSet>
                )}
              />

              <p className="text-sm text-muted-foreground">
                平台支持最新排序时按最新优先，否则保留平台实际顺序；每个搜索词分别计算上限，不足上限时按实际数量保存，跨词重复内容会合并。采集完成后仍可自行选材生成报告。
              </p>

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

      <PlatformAccessSettingsCard platforms={configuredPlatforms} />

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
