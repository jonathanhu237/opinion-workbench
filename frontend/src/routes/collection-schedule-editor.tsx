import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Field,
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
import {
  cacheSavedSchedule,
  scheduleConfigurationChanged,
  useCollectionSchedule,
} from '@/hooks/use-collection-schedules'
import { useMonitoringRules } from '@/hooks/use-monitoring-rules'
import {
  COLLECTION_SCHEDULES_QUERY_KEY,
  collectionIntervalSchema,
  CollectionScheduleApiError,
  createCollectionSchedule,
  MAX_COLLECTION_INTERVAL_MINUTES,
  scheduleErrorMessage,
  updateCollectionSchedule,
  type CollectionSchedule,
} from '@/lib/api/collection-schedules'
import {
  searchPlatformOrder,
  searchPlatformPresenters,
} from '@/routes/search-run-presenters'

export const scheduleFormSchema = z
  .object({
    ruleId: z.string(),
    platforms: z
      .array(z.enum(searchPlatformOrder))
      .min(1, '请至少选择一个采集平台。')
      .max(5)
      .refine(
        (value) => new Set(value).size === value.length,
        '采集平台不能重复。',
      ),
    intervalValue: z.coerce
      .number<number>()
      .int('请输入整数间隔。')
      .min(1, '采集间隔至少为 1。')
      .max(MAX_COLLECTION_INTERVAL_MINUTES, '采集间隔最多为 30 天。'),
    intervalUnit: z.enum(['minutes', 'hours']),
    maxResultsPerTerm: z.coerce
      .number<number>()
      .int('请输入整数。')
      .min(1, '每词至少采集 1 条。')
      .max(50, '每词最多采集 50 条。'),
  })
  .superRefine((value, ctx) => {
    if (
      !collectionIntervalSchema.safeParse({
        value: value.intervalValue,
        unit: value.intervalUnit,
      }).success
    )
      ctx.addIssue({
        code: 'custom',
        path: ['intervalValue'],
        message: '采集间隔须为 1 至 43200 个整分钟（最多 720 小时）。',
      })
  })
type ScheduleValues = z.infer<typeof scheduleFormSchema>
function initialValues(schedule: CollectionSchedule | null): ScheduleValues {
  const hours = schedule !== null && schedule.interval_minutes % 60 === 0
  return {
    ruleId: schedule?.monitoring_rule_id
      ? String(schedule.monitoring_rule_id)
      : '',
    platforms: schedule?.platforms ?? [...searchPlatformOrder],
    intervalValue: schedule ? schedule.interval_minutes / (hours ? 60 : 1) : 1,
    intervalUnit: hours || !schedule ? 'hours' : 'minutes',
    maxResultsPerTerm: schedule?.max_results_per_term ?? 10,
  }
}
export function CollectionScheduleEditor({
  schedule,
  onClose,
  onSaved,
}: {
  schedule: CollectionSchedule | null
  onClose: () => void
  onSaved: (saved: CollectionSchedule) => void
}) {
  const client = useQueryClient()
  const rules = useMonitoringRules()
  const latestQuery = useCollectionSchedule(schedule?.id ?? null)
  const [base, setBase] = useState(schedule)
  const [discard, setDiscard] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const form = useForm<ScheduleValues>({
    resolver: zodResolver(scheduleFormSchema),
    mode: 'onBlur',
    defaultValues: initialValues(schedule),
  })
  const { isDirty, isSubmitting, errors } = form.formState
  const mutation = useMutation({
    mutationFn: async (values: ScheduleValues) => {
      const payload = {
        monitoring_rule_id: values.ruleId ? Number(values.ruleId) : null,
        platforms: searchPlatformOrder.filter((platform) =>
          values.platforms.includes(platform),
        ),
        interval: { value: values.intervalValue, unit: values.intervalUnit },
        max_results_per_term: values.maxResultsPerTerm,
      }
      if (base)
        return updateCollectionSchedule(base.id, {
          ...payload,
          expected_revision: base.revision,
          enabled: base.enabled,
        })
      if (payload.monitoring_rule_id === null)
        throw new CollectionScheduleApiError('invalid_collection_schedule')
      return createCollectionSchedule({
        ...payload,
        monitoring_rule_id: payload.monitoring_rule_id,
      })
    },
    retry: false,
    onSuccess: async (saved) => {
      await cacheSavedSchedule(client, saved)
      onSaved(saved)
    },
    onError: () => {
      void client.invalidateQueries({
        queryKey: COLLECTION_SCHEDULES_QUERY_KEY,
      })
    },
  })
  const latest = latestQuery.data
  const stale =
    base !== null &&
    latest !== undefined &&
    scheduleConfigurationChanged(base, latest)
  useEffect(() => {
    if (
      latest &&
      base &&
      scheduleConfigurationChanged(base, latest) &&
      !isDirty &&
      !mutation.isPending
    ) {
      form.reset(initialValues(latest))
      setBase(latest)
    }
  }, [latest, base, isDirty, mutation.isPending, form])
  function close() {
    if (mutation.isPending) return
    if (isDirty) setDiscard(true)
    else onClose()
  }
  const submit = form.handleSubmit((values) => {
    form.clearErrors('root')
    const rule = rules.data?.rules.find(
      (item) => String(item.id) === values.ruleId,
    )
    const retainedDeleted =
      base?.monitoring_rule_id === null && !base.enabled && values.ruleId === ''
    if (!rule && !retainedDeleted) {
      form.setError(
        'ruleId',
        { message: '请选择仍然存在的监控规则。' },
        { shouldFocus: true },
      )
      return
    }
    if (base?.enabled && rule && (!rule.enabled || rule.terms.length > 20)) {
      form.setError(
        'ruleId',
        {
          message:
            '已启用的定时任务需要启用且不超过 20 个搜索词的规则。请先停用定时任务，或选择其他规则。',
        },
        { shouldFocus: true },
      )
      return
    }
    mutation.mutate(values)
  })
  const options =
    rules.data?.rules.map((rule) => ({
      value: String(rule.id),
      label: `${rule.name}（${rule.terms.length} 个词${rule.enabled ? '' : ' · 已停用'}）`,
    })) ?? []
  if (base?.monitoring_rule_id === null)
    options.unshift({
      value: 'deleted',
      label: `${base.rule_name}（规则已删除）`,
    })
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close()
      }}
    >
      <DialogContent
        className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-xl"
        showCloseButton={!mutation.isPending}
      >
        <DialogHeader>
          <DialogTitle>{base ? '编辑定时采集' : '新建定时采集'}</DialogTitle>
          <DialogDescription>
            按固定间隔采集所选规则。新任务保存后为停用状态，需单独启用；规则本身不包含定时或分析设置。
          </DialogDescription>
        </DialogHeader>
        <form
          id="schedule-editor"
          onSubmit={submit}
          noValidate
          className="min-w-0 space-y-5"
        >
          <Controller
            name="ruleId"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid} className="min-w-0">
                <FieldLabel htmlFor="schedule-rule">
                  定时采集的监控规则
                </FieldLabel>
                <Select
                  items={options}
                  value={
                    field.value ||
                    (base?.monitoring_rule_id === null ? 'deleted' : null)
                  }
                  onValueChange={(value) =>
                    field.onChange(value === 'deleted' ? '' : (value ?? ''))
                  }
                  disabled={rules.isPending || mutation.isPending}
                >
                  <SelectTrigger
                    id="schedule-rule"
                    ref={field.ref}
                    onBlur={field.onBlur}
                    className="min-h-11 w-full min-w-0"
                    aria-invalid={fieldState.invalid}
                    aria-describedby="schedule-rule-help schedule-rule-error"
                  >
                    <SelectValue
                      placeholder="选择监控规则"
                      className="min-w-0 truncate"
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {options.map((option) => (
                      <SelectItem
                        key={option.value}
                        value={option.value}
                        className="wrap-anywhere whitespace-normal"
                      >
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription id="schedule-rule-help">
                  用规则名称标识此任务；每次执行保存当时的规则快照。停用或超过
                  20 个搜索词的规则不能启用定时任务。
                </FieldDescription>
                <FieldError
                  id="schedule-rule-error"
                  errors={[fieldState.error]}
                />
              </Field>
            )}
          />
          {rules.isError && (
            <div role="alert" className="space-y-2 text-sm text-destructive">
              <p>监控规则暂时无法读取，草稿仍保留。</p>
              <Button
                type="button"
                variant="outline"
                onClick={() => rules.refetch()}
              >
                重新加载规则
              </Button>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Controller
              name="intervalValue"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="schedule-interval">采集间隔</FieldLabel>
                  <Input
                    {...field}
                    id="schedule-interval"
                    className="min-h-11"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    step={1}
                    aria-invalid={fieldState.invalid}
                    aria-describedby="schedule-interval-help schedule-interval-error"
                    disabled={mutation.isPending}
                  />
                  <FieldError
                    id="schedule-interval-error"
                    errors={[fieldState.error]}
                  />
                </Field>
              )}
            />
            <Controller
              name="intervalUnit"
              control={form.control}
              render={({ field }) => (
                <Field>
                  <FieldLabel htmlFor="schedule-unit">间隔单位</FieldLabel>
                  <Select
                    items={[
                      { value: 'minutes', label: '分钟' },
                      { value: 'hours', label: '小时' },
                    ]}
                    value={field.value}
                    onValueChange={field.onChange}
                    disabled={mutation.isPending}
                  >
                    <SelectTrigger
                      id="schedule-unit"
                      ref={field.ref}
                      className="min-h-11 w-full"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="minutes">分钟</SelectItem>
                      <SelectItem value="hours">小时</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              )}
            />
          </div>
          <p
            id="schedule-interval-help"
            className="text-sm text-muted-foreground"
          >
            整分钟或整小时，最多 30
            天。启用或编辑后，从保存时间重新计算下一次采集；不补采停机期间错过的轮次。
          </p>
          <Controller
            name="platforms"
            control={form.control}
            render={({ field, fieldState }) => (
              <FieldSet aria-describedby="schedule-platform-error">
                <FieldLegend variant="label">定时采集平台</FieldLegend>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {searchPlatformOrder.map((platform, index) => (
                    <FieldLabel
                      key={platform}
                      className="min-h-11 cursor-pointer gap-2 rounded-lg border p-3"
                    >
                      <Checkbox
                        ref={index === 0 ? field.ref : undefined}
                        checked={field.value.includes(platform)}
                        onCheckedChange={(checked) =>
                          field.onChange(
                            checked
                              ? [...field.value, platform]
                              : field.value.filter(
                                  (value) => value !== platform,
                                ),
                          )
                        }
                        disabled={mutation.isPending}
                        aria-invalid={fieldState.invalid}
                        aria-describedby="schedule-platform-error"
                      />
                      <img
                        src={searchPlatformPresenters[platform].logoSrc}
                        className="size-5"
                        alt=""
                      />
                      {searchPlatformPresenters[platform].label}
                    </FieldLabel>
                  ))}
                </div>
                <FieldError
                  id="schedule-platform-error"
                  errors={[fieldState.error]}
                />
              </FieldSet>
            )}
          />
          <Controller
            name="maxResultsPerTerm"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="schedule-limit">
                  定时采集每词上限
                </FieldLabel>
                <Input
                  {...field}
                  id="schedule-limit"
                  className="min-h-11"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={50}
                  step={1}
                  aria-invalid={fieldState.invalid}
                  aria-describedby="schedule-limit-error"
                  disabled={mutation.isPending}
                />
                <FieldError
                  id="schedule-limit-error"
                  errors={[fieldState.error]}
                />
              </Field>
            )}
          />
          {base?.enabled && (
            <p className="text-sm text-warning-foreground">
              此任务已启用。保存后将重设下一次执行时间，已提交的采集批次不受影响。
            </p>
          )}
          {base && (
            <p className="text-xs text-muted-foreground">
              正在编辑版本 {base.revision}
            </p>
          )}
          {stale && (
            <div className="space-y-2">
              <p role="alert" className="text-sm text-warning-foreground">
                定时任务已在其他位置更新，当前草稿已保留。请核对最新状态后采用新版本，再单独保存。
              </p>
              <Button
                type="button"
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => {
                  setBase(latest)
                  mutation.reset()
                  setNotice('已采用最新版本并保留草稿；请核对后保存。')
                }}
              >
                保留草稿并采用最新版本
              </Button>
            </div>
          )}
          {latestQuery.isError && (
            <div role="alert" className="space-y-2 text-sm text-destructive">
              <p>{scheduleErrorMessage(latestQuery.error)}</p>
              <Button
                type="button"
                variant="outline"
                onClick={() => latestQuery.refetch()}
              >
                重新加载任务版本
              </Button>
            </div>
          )}
          {mutation.isError && (
            <p role="alert" className="text-sm text-destructive">
              {scheduleErrorMessage(mutation.error)}
            </p>
          )}
          {errors.root && <FieldError>{errors.root.message}</FieldError>}
          {notice && (
            <p role="status" className="text-sm text-muted-foreground">
              {notice}
            </p>
          )}
        </form>
        {discard && (
          <div role="alert" className="space-y-3 rounded-lg border p-3">
            <p>有未保存的更改，是否放弃草稿？</p>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setDiscard(false)}
              >
                继续编辑
              </Button>
              <Button type="button" variant="destructive" onClick={onClose}>
                放弃更改
              </Button>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={mutation.isPending}
            onClick={close}
          >
            取消
          </Button>
          <Button
            type="submit"
            form="schedule-editor"
            aria-busy={mutation.isPending}
            disabled={
              mutation.isPending ||
              isSubmitting ||
              stale ||
              (base !== null && !isDirty) ||
              rules.isPending ||
              rules.isError ||
              latestQuery.isError
            }
          >
            {mutation.isPending
              ? '正在保存…'
              : base
                ? '保存定时采集'
                : '创建停用的定时任务'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
