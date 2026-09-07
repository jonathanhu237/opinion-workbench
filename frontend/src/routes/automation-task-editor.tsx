import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch, Info } from 'lucide-react'
import { useEffect } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
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
  FieldContent,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PromptChoiceField } from '@/components/prompt-choice-field'
import { useMonitoringRules } from '@/hooks/use-monitoring-rules'
import { usePlatformConnections } from '@/hooks/use-platform-connections'
import {
  MAX_AUTOMATION_INTERVAL_MINUTES,
  AUTOMATION_PLATFORM_ORDER,
  AUTOMATION_TASKS_QUERY_KEY,
  AutomationApiError,
  automationErrorMessage,
  createAutomationTask,
  replaceAutomationTask,
  type AutomationTask,
  type AutomationTaskCreate,
  type AutomationTaskReplace,
} from '@/lib/api/automation-workflows'
import {
  ANALYSIS_SETTINGS_QUERY_KEY,
  fetchAnalysisSettings,
  promptChoiceSchema,
  type PromptChoice,
} from '@/lib/api/analysis-settings'
import {
  cacheSavedAutomationTask,
  automationTaskDetailKey,
} from '@/hooks/use-automation-workflows'

const defaultTimeZone =
  Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai'

const formSchema = z
  .object({
    name: z.string().max(80, '任务名称不能超过 80 个字符。'),
    ruleId: z.string(),
    platforms: z
      .array(z.enum(AUTOMATION_PLATFORM_ORDER))
      .min(1, '至少选择一个采集平台。')
      .max(5, '最多选择五个平台。')
      .refine(
        (platforms) =>
          new Set(platforms).size === platforms.length &&
          JSON.stringify(platforms) ===
            JSON.stringify(
              AUTOMATION_PLATFORM_ORDER.filter((platform) =>
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
    initialPrompt: promptChoiceSchema,
    reportPrompt: promptChoiceSchema,
    scheduleKind: z.enum(['interval', 'daily']),
    intervalMinutes: z.coerce
      .number<number>()
      .int('请输入整数分钟。')
      .min(1, '间隔至少为 1 分钟。')
      .max(MAX_AUTOMATION_INTERVAL_MINUTES, '间隔最多为 30 天。'),
    dailyTime: z
      .string()
      .regex(/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/u, '请输入 HH:MM 格式的时间。'),
    timezone: z.string().max(64, '时区名称不能超过 64 个字符。'),
  })
  .superRefine((value, context) => {
    if (value.name.trim().length === 0 || value.name.includes('\0')) {
      context.addIssue({
        code: 'custom',
        path: ['name'],
        message: '请输入自动任务名称。',
      })
    }
    if (value.scheduleKind === 'daily' && !isValidTimeZone(value.timezone)) {
      context.addIssue({
        code: 'custom',
        path: ['timezone'],
        message: '请输入有效时区，例如 Asia/Shanghai。',
      })
    }
    if (
      value.scheduleKind === 'interval' &&
      value.intervalMinutes > MAX_AUTOMATION_INTERVAL_MINUTES
    ) {
      context.addIssue({
        code: 'custom',
        path: ['intervalMinutes'],
        message: '间隔最多为 30 天。',
      })
    }
  })

type FormValues = z.infer<typeof formSchema>

function choiceFromSnapshot(
  snapshot: AutomationTask['initial_prompt'] | AutomationTask['report_prompt'],
): PromptChoice {
  return snapshot?.mode === 'custom' || snapshot?.mode === 'legacy'
    ? { mode: 'custom', instructions: snapshot.instructions }
    : { mode: 'default' }
}

function isValidTimeZone(value: string) {
  if (
    !value ||
    value.startsWith('/') ||
    value.startsWith('..') ||
    value.includes('..')
  ) {
    return false
  }
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: value }).format()
    return true
  } catch {
    return false
  }
}

function initialValues(task: AutomationTask | null): FormValues {
  const schedule = task?.schedule
  return {
    name: task?.name ?? '',
    ruleId:
      task?.monitoring_rule_id === null || task === null
        ? ''
        : String(task.monitoring_rule_id),
    platforms: task?.platforms ?? [...AUTOMATION_PLATFORM_ORDER],
    maxResultsPerTerm: task?.max_results_per_term ?? 10,
    initialPrompt: choiceFromSnapshot(task?.initial_prompt),
    reportPrompt: choiceFromSnapshot(task?.report_prompt),
    scheduleKind: schedule?.kind ?? 'interval',
    intervalMinutes:
      schedule?.kind === 'interval' ? schedule.interval_minutes : 60,
    dailyTime: schedule?.kind === 'daily' ? schedule.daily_time : '09:00',
    timezone: schedule?.kind === 'daily' ? schedule.timezone : defaultTimeZone,
  }
}

export function nextRunPreview(
  values: Pick<
    FormValues,
    'scheduleKind' | 'intervalMinutes' | 'dailyTime' | 'timezone'
  >,
) {
  const now = new Date()
  if (values.scheduleKind === 'interval') {
    return new Date(now.getTime() + values.intervalMinutes * 60_000)
  }
  if (
    !isValidTimeZone(values.timezone) ||
    !/^\d{2}:\d{2}$/u.test(values.dailyTime)
  )
    return null
  const [hour, minute] = values.dailyTime.split(':').map(Number)
  const today = zonedParts(now, values.timezone)
  for (let dayOffset = 0; dayOffset < 3; dayOffset += 1) {
    const calendar = new Date(
      Date.UTC(today.year, today.month - 1, today.day + dayOffset),
    )
    const candidate = instantForWallTime(
      calendar.getUTCFullYear(),
      calendar.getUTCMonth() + 1,
      calendar.getUTCDate(),
      hour,
      minute,
      values.timezone,
      now,
    )
    if (candidate !== null) return candidate
  }
  return null
}

type ZonedParts = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
}

function zonedParts(value: Date, timeZone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value)
  const read = (kind: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === kind)?.value)
  return {
    year: read('year'),
    month: read('month'),
    day: read('day'),
    hour: read('hour'),
    minute: read('minute'),
  }
}

function instantForWallTime(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  timeZone: string,
  after: Date,
) {
  const wallUtc = Date.UTC(year, month - 1, day, hour, minute)
  const offsets = new Set<number>()
  for (const delta of [-172_800_000, 0, 172_800_000]) {
    const probe = new Date(wallUtc + delta)
    const parts = zonedParts(probe, timeZone)
    offsets.add(
      Date.UTC(
        parts.year,
        parts.month - 1,
        parts.day,
        parts.hour,
        parts.minute,
      ) -
        Math.floor(probe.getTime() / 60_000) * 60_000,
    )
  }
  const matching = [...offsets]
    .map((offset) => new Date(wallUtc - offset))
    .filter((candidate) => {
      const parts = zonedParts(candidate, timeZone)
      return (
        parts.year === year &&
        parts.month === month &&
        parts.day === day &&
        parts.hour === hour &&
        parts.minute === minute
      )
    })
    .sort((left, right) => left.getTime() - right.getTime())
  const exact = matching.filter(
    (candidate) => candidate.getTime() > after.getTime(),
  )
  if (exact[0]) return exact[0]
  if (matching.length > 0) return null

  // DST gaps have no exact instant. Match the backend contract by selecting
  // the first valid local minute after the requested wall time.
  const requestedMinute = hour * 60 + minute
  for (
    let timestamp = wallUtc - 15 * 60 * 60_000;
    timestamp <= wallUtc + 15 * 60 * 60_000;
    timestamp += 60_000
  ) {
    if (timestamp <= after.getTime()) continue
    const candidate = new Date(timestamp)
    const parts = zonedParts(candidate, timeZone)
    if (
      parts.year === year &&
      parts.month === month &&
      parts.day === day &&
      parts.hour * 60 + parts.minute >= requestedMinute
    )
      return candidate
  }
  return null
}

function previewLabel(date: Date | null, timeZone: string) {
  if (date === null || Number.isNaN(date.getTime()))
    return '填写有效的时区后显示预览。'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: isValidTimeZone(timeZone) ? timeZone : 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function makePayload(values: FormValues): AutomationTaskCreate {
  return {
    name: values.name.trim(),
    monitoring_rule_id: Number(values.ruleId),
    platforms: values.platforms,
    max_results_per_term: values.maxResultsPerTerm,
    max_total_results: null,
    initial_prompt: values.initialPrompt,
    report_prompt: values.reportPrompt,
    schedule:
      values.scheduleKind === 'interval'
        ? { kind: 'interval', interval_minutes: values.intervalMinutes }
        : {
            kind: 'daily',
            daily_time: values.dailyTime,
            timezone: values.timezone.trim(),
          },
  }
}

export function AutomationTaskEditor({
  task,
  onClose,
  onSaved,
}: {
  task: AutomationTask | null
  onClose: () => void
  onSaved: (task: AutomationTask, message: string) => void
}) {
  const client = useQueryClient()
  const rules = useMonitoringRules()
  const platformsQuery = usePlatformConnections()
  const analysisSettings = useQuery({
    queryKey: ANALYSIS_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAnalysisSettings(signal),
    retry: false,
  })
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    mode: 'onBlur',
    defaultValues: initialValues(task),
  })
  const scheduleKind = useWatch({ control: form.control, name: 'scheduleKind' })
  const intervalMinutes = useWatch({
    control: form.control,
    name: 'intervalMinutes',
  })
  const dailyTime = useWatch({ control: form.control, name: 'dailyTime' })
  const timezone = useWatch({ control: form.control, name: 'timezone' })
  const preview = nextRunPreview({
    scheduleKind,
    intervalMinutes,
    dailyTime,
    timezone,
  })
  const saveMutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const payload = makePayload(values)
      if (task === null) return createAutomationTask(payload)
      const replacement: AutomationTaskReplace = {
        ...payload,
        monitoring_rule_id: payload.monitoring_rule_id,
        expected_revision: task.revision,
        enabled: task.enabled,
      }
      return replaceAutomationTask(task.id, replacement)
    },
    retry: false,
  })
  const { isDirty, isSubmitting } = form.formState

  useEffect(() => {
    if (task !== null)
      client.setQueryData(automationTaskDetailKey(task.id), task)
  }, [client, task])

  const submit = form.handleSubmit(async (values) => {
    form.clearErrors('root.server')
    const selectedRule = rules.data?.rules.find(
      (rule) => String(rule.id) === values.ruleId,
    )
    if (selectedRule === undefined) {
      form.setError(
        'ruleId',
        { message: '请选择仍然存在的监控规则。' },
        { shouldFocus: true },
      )
      return
    }
    try {
      const saved = await saveMutation.mutateAsync(values)
      await cacheSavedAutomationTask(client, saved)
      onSaved(
        saved,
        task === null
          ? '任务已创建，当前为停用状态。确认设置后可启用。'
          : '自动任务已保存；正在运行的任务仍使用原来的设置。',
      )
    } catch (error) {
      if (
        error instanceof AutomationApiError &&
        error.code === 'automation_task_changed'
      ) {
        await client.invalidateQueries({ queryKey: AUTOMATION_TASKS_QUERY_KEY })
      }
      form.setError('root.server', {
        type: 'server',
        message: automationErrorMessage(error),
      })
    }
  })

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saveMutation.isPending) onClose()
      }}
    >
      <DialogContent
        className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-2xl"
        showCloseButton={!saveMutation.isPending}
      >
        <DialogHeader>
          <DialogTitle>
            {task === null ? '新建自动任务' : '编辑自动任务'}
          </DialogTitle>
          <DialogDescription>
            新任务默认停用，确认规则和计划后再启用。
          </DialogDescription>
        </DialogHeader>

        <form
          id="automation-task-editor"
          onSubmit={submit}
          noValidate
          className="space-y-5"
        >
          <div className="grid gap-5 sm:grid-cols-2">
            <Controller
              name="name"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field
                  data-invalid={fieldState.invalid}
                  className="sm:col-span-2"
                >
                  <FieldLabel htmlFor="automation-task-name">
                    任务名称
                  </FieldLabel>
                  <Input
                    {...field}
                    id="automation-task-name"
                    maxLength={80}
                    placeholder="例如：龙田街道公共事务值守"
                    aria-invalid={fieldState.invalid}
                    aria-describedby="automation-task-name-error"
                    disabled={saveMutation.isPending}
                  />
                  <FieldError
                    id="automation-task-name-error"
                    errors={[fieldState.error]}
                  />
                </Field>
              )}
            />

            <Controller
              name="ruleId"
              control={form.control}
              render={({ field, fieldState }) => {
                const options =
                  rules.data?.rules.map((rule) => ({
                    value: String(rule.id),
                    label: `${rule.name}（${rule.terms.length} 个词${rule.enabled ? '' : ' · 已停用'}）`,
                  })) ?? []
                return (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor="automation-task-rule">
                      监控规则
                    </FieldLabel>
                    <Select
                      items={options}
                      value={field.value || null}
                      onValueChange={(value) => field.onChange(value ?? '')}
                      disabled={rules.isPending || saveMutation.isPending}
                    >
                      <SelectTrigger
                        id="automation-task-rule"
                        ref={field.ref}
                        onBlur={field.onBlur}
                        className="min-h-11 w-full"
                        aria-invalid={fieldState.invalid}
                        aria-describedby="automation-task-rule-error"
                      >
                        <SelectValue placeholder="选择监控规则" />
                      </SelectTrigger>
                      <SelectContent>
                        {options.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldDescription>
                      搜索规则决定采集哪些内容；下面分别设置两个分析阶段的提示词。
                    </FieldDescription>
                    <FieldError
                      id="automation-task-rule-error"
                      errors={[fieldState.error]}
                    />
                  </Field>
                )
              }}
            />

            <Controller
              name="maxResultsPerTerm"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="automation-task-limit">
                    每词最多采集
                  </FieldLabel>
                  <Input
                    {...field}
                    id="automation-task-limit"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={50}
                    className="min-h-11"
                    aria-invalid={fieldState.invalid}
                    disabled={saveMutation.isPending}
                  />
                  <FieldError errors={[fieldState.error]} />
                </Field>
              )}
            />
          </div>

          <p className="text-sm text-muted-foreground">
            平台支持最新排序时按最新优先，否则保留平台实际顺序；每个搜索词分别计算上限，不足上限时按实际数量保存，跨词重复内容会合并。
            {task !== null && task.max_total_results != null
              ? ' 此任务原为合计上限，保存后将改为每词上限；历史运行不变。'
              : ''}
          </p>

          <Controller
            name="platforms"
            control={form.control}
            render={({ field, fieldState }) => (
              <FieldSet
                data-invalid={fieldState.invalid}
                className="rounded-xl border bg-muted/25 p-4"
              >
                <FieldLegend variant="label">采集平台</FieldLegend>
                <FieldDescription id="automation-platforms-description">
                  新任务默认选择全部五个平台；编辑既有任务时保留已保存的平台范围，可以按需要调整。
                </FieldDescription>
                <div
                  role="group"
                  aria-describedby="automation-platforms-description"
                  className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3"
                >
                  {AUTOMATION_PLATFORM_ORDER.map((platform) => {
                    const connection = platformsQuery.data?.platforms.find(
                      (item) => item.platform === platform,
                    )
                    const enabled = connection?.availability === 'enabled'
                    const label = {
                      wb: '微博',
                      dy: '抖音',
                      ks: '快手',
                      xhs: '小红书',
                      toutiao: '今日头条',
                    }[platform]
                    const checked = field.value.includes(platform)
                    return (
                      <Field
                        key={platform}
                        orientation="horizontal"
                        data-disabled={
                          saveMutation.isPending || (!enabled && !checked)
                        }
                        className="rounded-lg border bg-background/70 p-3"
                      >
                        <Checkbox
                          id={`automation-platform-${platform}`}
                          checked={checked}
                          disabled={
                            saveMutation.isPending || (!enabled && !checked)
                          }
                          aria-invalid={fieldState.invalid}
                          aria-label={`选择采集平台：${label}`}
                          onCheckedChange={(nextChecked) => {
                            const next = nextChecked
                              ? [...field.value, platform]
                              : field.value.filter((item) => item !== platform)
                            field.onChange(
                              AUTOMATION_PLATFORM_ORDER.filter((item) =>
                                next.includes(item),
                              ),
                            )
                          }}
                        />
                        <FieldContent>
                          <FieldLabel
                            htmlFor={`automation-platform-${platform}`}
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

          <div className="grid gap-5">
            <Controller
              name="initialPrompt"
              control={form.control}
              render={({ field, fieldState }) => (
                <PromptChoiceField
                  id="automation-initial-prompt"
                  label="内容理解提示词"
                  description="先理解每条来源，保留地点、时间、文字证据和不确定性。"
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message}
                  defaultInstructions={
                    analysisSettings.data?.initial_prompt.instructions
                  }
                  disabled={
                    saveMutation.isPending || !analysisSettings.isSuccess
                  }
                />
              )}
            />
            <Controller
              name="reportPrompt"
              control={form.control}
              render={({ field, fieldState }) => (
                <PromptChoiceField
                  id="automation-report-prompt"
                  label="相关性判断与报告提示词"
                  description="再根据内容理解判断相关性，并整理文字报告。"
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message}
                  defaultInstructions={
                    analysisSettings.data?.report_prompt.instructions
                  }
                  disabled={
                    saveMutation.isPending || !analysisSettings.isSuccess
                  }
                />
              )}
            />
          </div>
          {analysisSettings.isPending && (
            <p role="status" className="text-sm text-muted-foreground">
              正在读取固定提示词…
            </p>
          )}
          {analysisSettings.isError && (
            <p role="alert" className="text-sm text-destructive">
              固定提示词暂时无法读取，请刷新后重试。
            </p>
          )}

          <FieldSet className="rounded-xl border bg-muted/25 p-4">
            <FieldLegend variant="label">执行计划</FieldLegend>
            <Controller
              name="scheduleKind"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="automation-schedule-kind">
                    计划方式
                  </FieldLabel>
                  <Select
                    items={[
                      { value: 'interval', label: '固定间隔' },
                      { value: 'daily', label: '每天固定时间' },
                    ]}
                    value={field.value}
                    onValueChange={(value) =>
                      field.onChange(value ?? 'interval')
                    }
                    disabled={saveMutation.isPending}
                  >
                    <SelectTrigger
                      id="automation-schedule-kind"
                      className="min-h-11 w-full sm:w-56"
                      aria-invalid={fieldState.invalid}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="interval">固定间隔</SelectItem>
                      <SelectItem value="daily">每天固定时间</SelectItem>
                    </SelectContent>
                  </Select>
                  <FieldError errors={[fieldState.error]} />
                </Field>
              )}
            />

            {scheduleKind === 'interval' ? (
              <Controller
                name="intervalMinutes"
                control={form.control}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor="automation-interval">
                      间隔（分钟）
                    </FieldLabel>
                    <Input
                      {...field}
                      id="automation-interval"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={MAX_AUTOMATION_INTERVAL_MINUTES}
                      className="min-h-11 sm:w-56"
                      aria-invalid={fieldState.invalid}
                      disabled={saveMutation.isPending}
                    />
                    <FieldDescription>
                      支持 1 至 43,200 分钟（最多 30 天）。
                    </FieldDescription>
                    <FieldError errors={[fieldState.error]} />
                  </Field>
                )}
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <Controller
                  name="dailyTime"
                  control={form.control}
                  render={({ field, fieldState }) => (
                    <Field data-invalid={fieldState.invalid}>
                      <FieldLabel htmlFor="automation-daily-time">
                        每天时间
                      </FieldLabel>
                      <Input
                        {...field}
                        id="automation-daily-time"
                        type="time"
                        step={60}
                        className="min-h-11"
                        aria-invalid={fieldState.invalid}
                        disabled={saveMutation.isPending}
                      />
                      <FieldError errors={[fieldState.error]} />
                    </Field>
                  )}
                />
                <Controller
                  name="timezone"
                  control={form.control}
                  render={({ field, fieldState }) => (
                    <Field data-invalid={fieldState.invalid}>
                      <FieldLabel htmlFor="automation-timezone">
                        时区
                      </FieldLabel>
                      <Input
                        {...field}
                        id="automation-timezone"
                        placeholder="Asia/Shanghai"
                        className="min-h-11"
                        aria-invalid={fieldState.invalid}
                        disabled={saveMutation.isPending}
                      />
                      <FieldError errors={[fieldState.error]} />
                    </Field>
                  )}
                />
              </div>
            )}
            <p
              role="status"
              className="flex items-start gap-2 text-sm text-muted-foreground"
            >
              <Info
                className="mt-0.5 size-4 shrink-0 text-primary"
                aria-hidden
              />
              <span>
                预计下次执行：{previewLabel(preview, timezone)}
                {scheduleKind === 'daily' && isValidTimeZone(timezone)
                  ? `（${timezone}）`
                  : ''}
              </span>
            </p>
          </FieldSet>

          <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
            <div className="flex items-center gap-2 font-medium">
              <GitBranch className="size-4 text-primary" aria-hidden />
              处理流程
            </div>
            <ol className="mt-3 grid gap-2 text-sm text-muted-foreground sm:grid-cols-3">
              <li className="rounded-lg bg-background/70 p-3">
                <span className="font-utility text-xs text-primary">01</span>
                <br />
                采集内容
              </li>
              <li className="rounded-lg bg-background/70 p-3">
                <span className="font-utility text-xs text-primary">02</span>
                <br />
                初步理解内容
              </li>
              <li className="rounded-lg bg-background/70 p-3">
                <span className="font-utility text-xs text-primary">03</span>
                <br />
                相关性判断与报告
              </li>
            </ol>
          </div>

          {form.formState.errors.root?.server?.message && (
            <p role="alert" className="text-sm text-destructive">
              {form.formState.errors.root.server.message}
            </p>
          )}
          {rules.isError && (
            <p role="alert" className="text-sm text-destructive">
              监控规则暂时无法读取，请刷新后重试。
            </p>
          )}
        </form>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={saveMutation.isPending}
            onClick={() => onClose()}
          >
            取消
          </Button>
          <Button
            type="submit"
            form="automation-task-editor"
            disabled={
              saveMutation.isPending ||
              isSubmitting ||
              !analysisSettings.isSuccess
            }
          >
            {saveMutation.isPending
              ? '正在保存…'
              : task === null
                ? '创建自动任务'
                : '保存自动任务'}
          </Button>
        </DialogFooter>
        {isDirty && !saveMutation.isPending && (
          <p className="sr-only">表单有未保存的更改。</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
