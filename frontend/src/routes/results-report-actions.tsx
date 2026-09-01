import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
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
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cacheSavedReport } from '@/hooks/use-topic-reports'
import {
  AI_SETTINGS_QUERY_KEY,
  fetchAISettings,
  type AISettings,
} from '@/lib/api/ai-settings'
import {
  ANALYSIS_SETTINGS_QUERY_KEY,
  fetchAnalysisSettings,
  promptInstructionsSchema,
  type AnalysisSettings,
  type PromptVersion,
} from '@/lib/api/analysis-settings'
import { shanghaiDateBoundary } from '@/lib/api/results'
import {
  cancelTopicReport,
  createTopicReport,
  fetchTopicReport,
  isActiveReport,
  isAmbiguousReportError,
  reportErrorMessage,
  retryTopicReport,
  TOPIC_REPORTS_QUERY_KEY,
  type CancelReportRequest,
  type CreateReportRequest,
  type ReportRun,
  type RetryReportRequest,
} from '@/lib/api/topic-reports'

type ReportIntent =
  | {
      kind: 'interval'
      request: CreateReportRequest
      provider: AISettings
      instructions: string
    }
  | {
      kind: 'retry'
      id: number
      request: RetryReportRequest
      provider: AISettings
      instructions: string
    }
  | { kind: 'cancel'; id: number; request: CancelReportRequest }
type ReportDraft =
  | { kind: 'interval'; provider: AISettings; prompt: PromptVersion }
  | { kind: 'override'; provider: AISettings; report: ReportRun }

export function reportRequestFormSchema(interval: boolean) {
  return z
    .object({
      from: z.string(),
      to: z.string(),
      override: z.boolean(),
      instructions: z.string(),
    })
    .superRefine((value, ctx) => {
      if (interval) {
        const from = shanghaiDateBoundary(value.from)
        const to = shanghaiDateBoundary(value.to, true)
        if (!from)
          ctx.addIssue({
            code: 'custom',
            path: ['from'],
            message: '请选择有效的首次发现开始日期。',
          })
        if (!to || (from !== null && from >= (to ?? '')))
          ctx.addIssue({
            code: 'custom',
            path: ['to'],
            message: '请选择不早于开始日期的结束日期。',
          })
      }
      if (
        (!interval || value.override) &&
        !promptInstructionsSchema.safeParse(value.instructions).success
      )
        ctx.addIssue({
          code: 'custom',
          path: ['instructions'],
          message: '提示词须为 1 至 8000 字的有效非空文本。',
        })
    })
}
type FormValues = z.infer<ReturnType<typeof reportRequestFormSchema>>
function RequestDisclosure({
  provider,
  instructions,
}: {
  provider: AISettings
  instructions: string
}) {
  return (
    <div className="space-y-3 text-sm">
      <p className="leading-6 text-muted-foreground">
        根据已保存的内容判断相关性并生成报告，可能消耗 API
        额度；不会重新采集、上传媒体或分析媒体。范围越大，模型请求可能越多；已有结果和旧报告会保留。
      </p>
      <p className="wrap-anywhere">
        模型：{provider.model}
        <br />
        {provider.base_url}
      </p>
      <details className="rounded-lg border p-3">
        <summary className="min-h-8 cursor-pointer font-medium">
          本次报告提示词
        </summary>
        <p className="mt-2 leading-6 wrap-anywhere whitespace-pre-wrap">
          {instructions}
        </p>
      </details>
    </div>
  )
}
function IntentDescription({ intent }: { intent: ReportIntent }) {
  if (intent.kind === 'cancel')
    return (
      <p className="text-sm leading-6">
        只取消报告 #{intent.id}{' '}
        的生成，不影响初步分析、已保存内容和其他报告版本。
      </p>
    )
  return (
    <div className="space-y-3">
      <p className="text-sm">
        {intent.kind === 'retry'
          ? `使用报告 #${intent.id} 的内容生成新版本，不加入之后的新内容。`
          : `首次发现时间范围：${intent.request.selection.first_seen_from}（含）至 ${intent.request.selection.first_seen_to}（不含）。`}
      </p>
      <RequestDisclosure
        provider={intent.provider}
        instructions={intent.instructions}
      />
    </div>
  )
}

function ReportRequestEditor({
  draft,
  open,
  intent,
  pending,
  ambiguous,
  error,
  refreshing,
  onClose,
  onSubmit,
  onReplay,
  onReconfirm,
}: {
  draft: ReportDraft
  open: boolean
  intent: ReportIntent | null
  pending: boolean
  ambiguous: boolean
  error: string | null
  refreshing: boolean
  onClose: () => void
  onSubmit: (values: FormValues) => void
  onReplay: () => void
  onReconfirm: () => void
}) {
  const interval = draft.kind === 'interval'
  const [discard, setDiscard] = useState(false)
  const form = useForm<FormValues>({
    resolver: zodResolver(reportRequestFormSchema(interval)),
    mode: 'onBlur',
    defaultValues: {
      from: '',
      to: '',
      override: !interval,
      instructions: interval
        ? draft.prompt.instructions
        : draft.report.prompt.instructions,
    },
  })
  const override = form.watch('override')
  const isDirty = form.formState.isDirty
  const locked = pending || intent !== null || refreshing
  const close = () => {
    if (pending || refreshing) return
    if (!intent && isDirty) setDiscard(true)
    else onClose()
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) close()
      }}
    >
      <DialogContent
        className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-xl"
        showCloseButton={!pending && !refreshing}
      >
        <DialogHeader>
          <DialogTitle>
            {interval ? '按首次发现时间生成报告' : '用其他提示词重新生成'}
          </DialogTitle>
          <DialogDescription>
            这是可选的报告操作，不会修改默认提示词。
          </DialogDescription>
        </DialogHeader>
        <form
          id="report-request-form"
          className="min-w-0 space-y-4"
          noValidate
          onSubmit={form.handleSubmit(onSubmit)}
        >
          {interval && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Controller
                  name="from"
                  control={form.control}
                  render={({ field, fieldState }) => (
                    <Field data-invalid={fieldState.invalid}>
                      <FieldLabel htmlFor="report-from">
                        报告首次发现开始日期
                      </FieldLabel>
                      <Input
                        {...field}
                        type="date"
                        id="report-from"
                        className="min-h-11"
                        disabled={locked}
                        aria-invalid={fieldState.invalid}
                        aria-describedby="report-date-help report-from-error"
                      />
                      <FieldError
                        id="report-from-error"
                        errors={[fieldState.error]}
                      />
                    </Field>
                  )}
                />
                <Controller
                  name="to"
                  control={form.control}
                  render={({ field, fieldState }) => (
                    <Field data-invalid={fieldState.invalid}>
                      <FieldLabel htmlFor="report-to">
                        报告首次发现结束日期
                      </FieldLabel>
                      <Input
                        {...field}
                        type="date"
                        id="report-to"
                        className="min-h-11"
                        disabled={locked}
                        aria-invalid={fieldState.invalid}
                        aria-describedby="report-date-help report-to-error"
                      />
                      <FieldError
                        id="report-to-error"
                        errors={[fieldState.error]}
                      />
                    </Field>
                  )}
                />
              </div>
              <p
                id="report-date-help"
                className="text-sm leading-6 text-muted-foreground"
              >
                按北京时间计算，结束日期当天也包含在内。跨采集任务按首次发现时间选择内容；没有可用初步分析的内容不会自动重做。
              </p>
              <Controller
                name="override"
                control={form.control}
                render={({ field }) => (
                  <FieldLabel className="min-h-11">
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                      disabled={locked}
                    />
                    仅本报告使用其他提示词（可选）
                  </FieldLabel>
                )}
              />
            </>
          )}
          {(!interval || override) && (
            <Controller
              name="instructions"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="report-override">
                    本次专用报告提示词
                  </FieldLabel>
                  <Textarea
                    {...field}
                    id="report-override"
                    rows={6}
                    disabled={locked}
                    aria-invalid={fieldState.invalid}
                    aria-describedby="report-override-help report-override-error"
                  />
                  <p
                    id="report-override-help"
                    className="text-sm text-muted-foreground"
                  >
                    只影响这份新报告，不会保存为默认提示词，也不会重新获取媒体。
                  </p>
                  <FieldError
                    id="report-override-error"
                    errors={[fieldState.error]}
                  />
                </Field>
              )}
            />
          )}
          <RequestDisclosure
            provider={draft.provider}
            instructions={
              intent && intent.kind !== 'cancel'
                ? intent.instructions
                : !interval || override
                  ? form.watch('instructions')
                  : draft.prompt.instructions
            }
          />
        </form>
        {intent && (
          <p className="text-sm text-muted-foreground">
            这次提交的内容已确定，字段暂时不能修改；再次确认不会重复创建报告。
          </p>
        )}
        {ambiguous && (
          <p role="status" className="text-sm text-warning-foreground">
            上次提交结果不确定。再次确认可以继续上次操作，不会重复创建报告。
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {discard && (
          <div role="alert" className="space-y-2 rounded-lg border p-3">
            <p>有未保存的报告设置，是否放弃？</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => setDiscard(false)}>
                继续编辑报告
              </Button>
              <Button variant="destructive" onClick={onClose}>
                放弃报告设置
              </Button>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            disabled={pending || refreshing}
            onClick={close}
          >
            {ambiguous ? '暂时关闭' : '取消'}
          </Button>
          {intent ? (
            <Button
              disabled={pending || refreshing}
              aria-busy={pending || refreshing}
              onClick={ambiguous ? onReplay : onReconfirm}
            >
              {pending
                ? '正在提交…'
                : refreshing
                  ? '正在刷新…'
                  : ambiguous
                    ? '确认上次报告提交'
                    : '保留草稿并重新核对'}
            </Button>
          ) : (
            <Button
              form="report-request-form"
              type="submit"
              disabled={pending || refreshing || form.formState.isSubmitting}
              aria-busy={pending}
            >
              {interval ? '提交文字报告' : '创建专用提示词新版本'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ReportActions({
  report,
  provider,
  settings,
  onSaved,
}: {
  report?: ReportRun
  provider?: AISettings
  settings?: AnalysisSettings
  onSaved: (report: ReportRun) => void
}) {
  const client = useQueryClient()
  const [intent, setIntent] = useState<ReportIntent | null>(null)
  const [draft, setDraft] = useState<ReportDraft | null>(null)
  const [open, setOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: (value: ReportIntent) =>
      value.kind === 'interval'
        ? createTopicReport(value.request)
        : value.kind === 'retry'
          ? retryTopicReport(value.id, value.request)
          : cancelTopicReport(value.id, value.request),
    retry: false,
    onSuccess: async (saved) => {
      await cacheSavedReport(client, saved)
      setIntent(null)
      setDraft(null)
      setOpen(false)
      onSaved(saved)
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
    },
  })
  const ambiguous = mutation.isError && isAmbiguousReportError(mutation.error)
  const error =
    refreshError ??
    (mutation.isError ? reportErrorMessage(mutation.error) : null)
  const blocked = intent !== null || mutation.isPending || refreshing
  const begin = (value: ReportIntent) => {
    mutation.reset()
    setRefreshError(null)
    setDraft(null)
    setIntent(value)
    setOpen(true)
  }
  const close = () => {
    if (mutation.isPending || refreshing) return
    setOpen(false)
    if (!ambiguous) {
      setIntent(null)
      setDraft(null)
      mutation.reset()
      setRefreshError(null)
    }
  }
  const submitDraft = (values: FormValues) => {
    if (!draft || intent || mutation.isPending) return
    let value: ReportIntent
    if (draft.kind === 'interval') {
      const from = shanghaiDateBoundary(values.from)
      const to = shanghaiDateBoundary(values.to, true)
      if (!from || !to) return
      value = {
        kind: 'interval',
        provider: draft.provider,
        instructions: values.override
          ? values.instructions
          : draft.prompt.instructions,
        request: {
          request_id: crypto.randomUUID(),
          configuration_revision: draft.provider.revision,
          report_prompt_version_id: draft.prompt.id,
          instructions_override: values.override ? values.instructions : null,
          selection: {
            kind: 'first_seen_interval',
            first_seen_from: from,
            first_seen_to: to,
          },
        },
      }
    } else
      value = {
        kind: 'retry',
        id: draft.report.id,
        provider: draft.provider,
        instructions: values.instructions,
        request: {
          request_id: crypto.randomUUID(),
          expected_revision: draft.report.revision,
          configuration_revision: draft.provider.revision,
          instructions_override: values.instructions,
        },
      }
    setIntent(value)
    mutation.mutate(value)
  }
  const reconfirm = async () => {
    if (!draft) {
      close()
      void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
      return
    }
    setRefreshing(true)
    setRefreshError(null)
    try {
      const currentProvider = await client.fetchQuery({
        queryKey: AI_SETTINGS_QUERY_KEY,
        queryFn: ({ signal }) => fetchAISettings(signal),
        staleTime: 0,
      })
      if (!currentProvider.has_api_key) {
        setRefreshError('请先保存可用的 AI 配置。草稿仍保留。')
        return
      }
      if (draft.kind === 'interval') {
        const currentSettings = await client.fetchQuery({
          queryKey: ANALYSIS_SETTINGS_QUERY_KEY,
          queryFn: ({ signal }) => fetchAnalysisSettings(signal),
          staleTime: 0,
        })
        setDraft({
          ...draft,
          provider: currentProvider,
          prompt: currentSettings.report_prompt,
        })
      } else {
        const latest = await fetchTopicReport(
          draft.report.id,
          new AbortController().signal,
        )
        if (isActiveReport(latest.status)) {
          setRefreshError('原报告仍在处理中，请等待或取消；草稿已保留。')
          return
        }
        setDraft({ ...draft, provider: currentProvider, report: latest })
      }
      setIntent(null)
      mutation.reset()
    } catch {
      setRefreshError('无法读取最新报告或模型设置，草稿仍保留，请稍后重试。')
    } finally {
      setRefreshing(false)
    }
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {intent && !open && (
          <Button variant="outline" onClick={() => setOpen(true)}>
            继续确认上次报告请求
          </Button>
        )}
        <Button
          variant="outline"
          disabled={blocked || !provider?.has_api_key || !settings}
          onClick={() => {
            if (provider && settings) {
              mutation.reset()
              setRefreshError(null)
              setDraft({
                kind: 'interval',
                provider: { ...provider },
                prompt: settings.report_prompt,
              })
              setOpen(true)
            }
          }}
        >
          可选：按首次发现时间报告
        </Button>
        {report && isActiveReport(report.status) && (
          <Button
            variant="outline"
            disabled={blocked}
            onClick={() =>
              begin({
                kind: 'cancel',
                id: report.id,
                request: {
                  request_id: crypto.randomUUID(),
                  expected_revision: report.revision,
                },
              })
            }
          >
            取消文字报告 #{report.id}
          </Button>
        )}
        {report && !isActiveReport(report.status) && (
          <>
            {report.status !== 'completed' && report.status !== 'empty' && (
              <Button
                variant="outline"
                disabled={blocked || !provider?.has_api_key}
                onClick={() => {
                  if (provider)
                    begin({
                      kind: 'retry',
                      id: report.id,
                      provider: { ...provider },
                      instructions: report.prompt.instructions,
                      request: {
                        request_id: crypto.randomUUID(),
                        expected_revision: report.revision,
                        configuration_revision: provider.revision,
                        instructions_override: null,
                      },
                    })
                }}
              >
                仅重试文字报告
              </Button>
            )}
            <Button
              variant="ghost"
              disabled={blocked || !provider?.has_api_key}
              onClick={() => {
                if (provider) {
                  mutation.reset()
                  setRefreshError(null)
                  setDraft({
                    kind: 'override',
                    provider: { ...provider },
                    report,
                  })
                  setOpen(true)
                }
              }}
            >
              用其他提示词重新生成
            </Button>
          </>
        )}
      </div>
      {!provider?.has_api_key && (
        <p className="text-sm text-muted-foreground">
          报告历史仍可查看。新的文字报告需要先保存 AI 配置。
        </p>
      )}
      {draft ? (
        <ReportRequestEditor
          draft={draft}
          open={open}
          intent={intent}
          pending={mutation.isPending}
          ambiguous={ambiguous}
          error={error}
          refreshing={refreshing}
          onClose={close}
          onSubmit={submitDraft}
          onReplay={() => {
            if (intent) mutation.mutate(intent)
          }}
          onReconfirm={() => void reconfirm()}
        />
      ) : (
        intent && (
          <Dialog
            open={open}
            onOpenChange={(value) => {
              if (!value) close()
            }}
          >
            <DialogContent
              className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-xl"
              showCloseButton={!mutation.isPending}
            >
              <DialogHeader>
                <DialogTitle>
                  {intent.kind === 'cancel'
                    ? '取消此份文字报告？'
                    : '仅重试文字报告'}
                </DialogTitle>
                <DialogDescription>
                  只影响报告生成，不会重新分析内容，也不会改动旧报告。
                </DialogDescription>
              </DialogHeader>
              <IntentDescription intent={intent} />
              {ambiguous && (
                <p role="status" className="text-sm text-warning-foreground">
                  上次操作结果不确定。再次确认可以继续上次操作，不会重复创建报告。
                </p>
              )}
              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}
              <DialogFooter>
                <Button
                  variant="outline"
                  disabled={mutation.isPending}
                  onClick={close}
                >
                  {ambiguous ? '暂时关闭' : '返回'}
                </Button>
                {mutation.isError && !ambiguous ? (
                  <Button onClick={() => void reconfirm()}>
                    关闭并刷新报告
                  </Button>
                ) : (
                  <Button
                    disabled={mutation.isPending}
                    aria-busy={mutation.isPending}
                    onClick={() => mutation.mutate(intent)}
                  >
                    {mutation.isPending
                      ? '正在提交…'
                      : ambiguous
                        ? '确认上次报告提交'
                        : intent.kind === 'cancel'
                          ? '确认取消文字报告'
                          : '确认文字重试'}
                  </Button>
                )}
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )
      )}
    </div>
  )
}
