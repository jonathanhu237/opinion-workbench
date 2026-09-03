import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { PromptChoiceField } from '@/components/prompt-choice-field'
import {
  promptChoiceSchema,
  type AnalysisSettings,
  type PromptChoice,
} from '@/lib/api/analysis-settings'
import type { AISettings } from '@/lib/api/ai-settings'
import {
  createReportGeneration,
  fetchGenerationEligibility,
  GENERATIONS_QUERY_KEY,
  generationCreateSchema,
  previewReportSelection,
  type GenerationCreate,
  type ReportGeneration,
  type SelectionPreview,
} from '@/lib/api/report-generations'
import {
  analysisErrorMessage,
  isAmbiguousAnalysisError,
} from '@/lib/api/analysis-shared'

const pendingIntentKey = 'longtian:report-generation:pending-intent:v1'

function defaultReportName(date = new Date()) {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
    .formatToParts(date)
    .reduce<Record<string, string>>((result, part) => {
      if (part.type !== 'literal') result[part.type] = part.value
      return result
    }, {})
  const dateText = `${parts.year}-${parts.month}-${parts.day}`
  return `${dateText} 舆情分析报告`
}

function restoredIntent(): GenerationCreate | null {
  try {
    const raw = sessionStorage.getItem(pendingIntentKey)
    if (!raw) return null
    const value = generationCreateSchema.safeParse(JSON.parse(raw))
    return value.success ? value.data : null
  } catch {
    return null
  }
}

function clearSavedIntent() {
  try {
    sessionStorage.removeItem(pendingIntentKey)
  } catch {
    /* Replaying a retained UUID is safe. */
  }
}

function saveIntent(value: GenerationCreate) {
  try {
    sessionStorage.setItem(pendingIntentKey, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

function fallbackCounts(
  selectedIds: number[],
  eligibility?: { pending: number; failed: number },
): SelectionPreview['counts'] {
  const pending = Math.min(selectedIds.length, eligibility?.pending ?? 0)
  const failed = Math.min(
    Math.max(0, selectedIds.length - pending),
    eligibility?.failed ?? 0,
  )
  return {
    total: selectedIds.length,
    pending,
    already_summarized: selectedIds.length - pending - failed,
    failed,
    active: 0,
  }
}

function previewMatchesSelection(
  preview: SelectionPreview | undefined,
  selectedIds: number[],
) {
  if (!preview || preview.selection.result_ids.length !== selectedIds.length)
    return false
  const selected = new Set(selectedIds)
  return preview.selection.result_ids.every((id) => selected.has(id))
}

export function ReportSelectionActions({
  selectedIds,
  provider,
  settings,
  active = false,
  onSelectionChange,
  onStarted,
}: {
  selectedIds: number[]
  provider?: AISettings
  settings?: AnalysisSettings
  active?: boolean
  onSelectionChange?: (ids: number[]) => void
  onStarted: (report: ReportGeneration) => void
}) {
  const [internalIds, setInternalIds] = useState(selectedIds)
  const ids = onSelectionChange ? selectedIds : internalIds
  const idsRef = useRef(ids)
  useEffect(() => {
    idsRef.current = ids
  }, [ids])
  const changeSelection = (next: number[]) => {
    const unique = [...new Set(next)]
    idsRef.current = unique
    if (onSelectionChange) onSelectionChange(unique)
    else setInternalIds(unique)
  }
  const [dialogOpen, setDialogOpen] = useState(false)
  const [storageError, setStorageError] = useState(false)
  const [intent, setIntent] = useState<GenerationCreate | null>(restoredIntent)
  const [name, setName] = useState(() => defaultReportName())
  const [initialPrompt, setInitialPrompt] = useState<PromptChoice>({
    mode: 'default',
  })
  const [reportPrompt, setReportPrompt] = useState<PromptChoice>({
    mode: 'default',
  })
  const currentIntent = intent
  // Once a request has been persisted for an ambiguous retry, the original
  // concrete selection is the source of truth even if the surrounding page
  // remounts with a newer draft selection.
  const effectiveIds = currentIntent
    ? currentIntent.selection.kind === 'explicit'
      ? currentIntent.selection.result_ids
      : ids
    : ids
  const eligibility = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, 'eligibility'],
    queryFn: ({ signal }) => fetchGenerationEligibility(signal),
    retry: false,
    refetchInterval: (query) => (query.state.data?.active ? 1000 : false),
  })
  const preview = useMutation({
    mutationFn: previewReportSelection,
    retry: false,
  })
  const bulk = useMutation({
    mutationFn: (include_failed: boolean) =>
      previewReportSelection({ kind: 'library', include_failed }),
    retry: false,
    onSuccess: (value) => {
      changeSelection([...idsRef.current, ...value.selection.result_ids])
    },
  })
  const start = useMutation({
    mutationFn: createReportGeneration,
    retry: false,
    onSuccess: (report) => {
      setIntent(null)
      clearSavedIntent()
      setDialogOpen(false)
      setName(defaultReportName())
      setInitialPrompt({ mode: 'default' })
      setReportPrompt({ mode: 'default' })
      onStarted(report)
    },
  })
  const counts = previewMatchesSelection(preview.data, effectiveIds)
    ? preview.data!.counts
    : fallbackCounts(effectiveIds, eligibility.data)
  const modelConfigured = Boolean(
    provider?.has_api_key && provider.model && provider.base_url,
  )
  const initialValid = promptChoiceSchema.safeParse(initialPrompt).success
  const reportValid = promptChoiceSchema.safeParse(reportPrompt).success
  const canSubmit =
    effectiveIds.length > 0 &&
    modelConfigured &&
    Boolean(settings) &&
    initialValid &&
    reportValid &&
    name.trim().length > 0 &&
    !active

  function openDialog() {
    if (effectiveIds.length === 0 || active || !modelConfigured) return
    const saved = currentIntent
    if (saved) {
      setName(saved.name ?? defaultReportName())
      setInitialPrompt(saved.initial_prompt)
      setReportPrompt(saved.report_prompt)
    }
    setDialogOpen(true)
    preview.reset()
    preview.mutate({ kind: 'explicit', result_ids: [...effectiveIds] })
  }

  function submit() {
    if (!canSubmit || !provider || !settings) return
    const request = currentIntent ?? {
      request_id: crypto.randomUUID(),
      name: name.trim(),
      configuration_revision: provider.revision,
      initial_prompt: initialPrompt,
      report_prompt: reportPrompt,
      selection: { kind: 'explicit' as const, result_ids: [...effectiveIds] },
    }
    if (!saveIntent(request)) {
      setStorageError(true)
      return
    }
    setStorageError(false)
    setIntent(request)
    start.mutate(request)
  }

  return (
    <div
      className="flex flex-col gap-3"
      aria-busy={start.isPending || bulk.isPending}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          className="min-h-10"
          disabled={bulk.isPending || Boolean(currentIntent)}
          onClick={() => bulk.mutate(false)}
        >
          {bulk.isPending ? '正在形成选材快照…' : '选中全部待分析内容'}
        </Button>
        <details className="relative">
          <summary
            className="flex min-h-10 cursor-pointer list-none items-center rounded-lg border px-3 text-sm [&::-webkit-details-marker]:hidden"
            aria-label="更多选材方式"
          >
            更多选材
          </summary>
          <div className="absolute top-full left-0 z-20 mt-2 min-w-56 rounded-lg border bg-background p-1 shadow-lg">
            <button
              type="button"
              className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
              disabled={bulk.isPending || Boolean(currentIntent)}
              onClick={(event) => {
                event.currentTarget.closest('details')?.removeAttribute('open')
                bulk.mutate(true)
              }}
            >
              同时加入分析失败内容
            </button>
          </div>
        </details>
        <span className="text-sm text-muted-foreground">
          待分析 {eligibility.data?.pending ?? '—'} · 失败{' '}
          {eligibility.data?.failed ?? '—'}
        </span>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        批量选材只把点击当时的具体条目加入当前选材，不会启动补全、模型调用或报告任务；之后新增的内容不会自动加入。
      </p>
      {bulk.isError && (
        <p role="alert" className="text-sm text-destructive">
          {analysisErrorMessage(bulk.error)}
        </p>
      )}
      {eligibility.isError && (
        <p role="alert" className="text-sm text-destructive">
          无法读取待分析数量。{analysisErrorMessage(eligibility.error)}
        </p>
      )}
      <div className="fixed inset-x-4 bottom-4 z-40 flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-background/95 p-3 text-sm shadow-lg backdrop-blur sm:inset-x-8 lg:inset-x-12">
        <span>已选 {effectiveIds.length} 条</span>
        <span className="text-muted-foreground">
          选材可跨页保留，提交前可逐条移除。
        </span>
        <div className="flex shrink-0 gap-2">
          {effectiveIds.length > 0 && (
            <Button
              variant="ghost"
              className="min-h-10"
              onClick={() => changeSelection([])}
              disabled={
                start.isPending || bulk.isPending || Boolean(currentIntent)
              }
            >
              清空
            </Button>
          )}
          <Button
            className="min-h-11"
            disabled={effectiveIds.length === 0 || active || !modelConfigured}
            onClick={openDialog}
          >
            生成报告
          </Button>
        </div>
      </div>
      {!modelConfigured && (
        <p className="text-sm text-destructive" role="status">
          尚未配置 AI 模型，请先到 AI 设置完成配置后再生成报告。
        </p>
      )}
      {active && (
        <p className="text-sm text-muted-foreground" role="status">
          当前已有报告正在生成。可以继续浏览和准备选材，任务结束前不能提交另一份报告。
        </p>
      )}
      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          if (!open && !start.isPending) setDialogOpen(false)
        }}
      >
        <DialogContent
          className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-2xl"
          showCloseButton={!start.isPending}
        >
          <DialogHeader>
            <DialogTitle>填写报告信息</DialogTitle>
            <DialogDescription>
              选材已固定为当前 {effectiveIds.length}{' '}
              条。确认后才会开始补全、生成单条总结和汇总报告。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-5">
            <div className="space-y-2">
              <FieldLabel htmlFor="report-name">报告名称</FieldLabel>
              <Input
                id="report-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={200}
                disabled={Boolean(currentIntent) || start.isPending}
              />
            </div>
            <div className="grid gap-5">
              <PromptChoiceField
                id="generation-initial-prompt"
                label="内容理解提示词"
                description="用于生成单条总结；已有可用总结会复用。修改只影响本次报告。"
                value={currentIntent?.initial_prompt ?? initialPrompt}
                onChange={setInitialPrompt}
                defaultInstructions={settings?.initial_prompt.instructions}
                disabled={
                  Boolean(currentIntent) || start.isPending || !settings
                }
                error={
                  !currentIntent && !initialValid
                    ? '请输入有效提示词。'
                    : undefined
                }
              />
              <PromptChoiceField
                id="generation-report-prompt"
                label="报告生成提示词"
                description="用于汇总本次选材并生成报告；修改只影响本次报告。"
                value={currentIntent?.report_prompt ?? reportPrompt}
                onChange={setReportPrompt}
                defaultInstructions={settings?.report_prompt.instructions}
                disabled={
                  Boolean(currentIntent) || start.isPending || !settings
                }
                error={
                  !currentIntent && !reportValid
                    ? '请输入有效提示词。'
                    : undefined
                }
              />
            </div>
            <dl className="grid gap-3 rounded-lg border p-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-muted-foreground">选中总数</dt>
                <dd className="text-lg font-medium">{counts.total}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">待分析</dt>
                <dd className="text-lg font-medium">{counts.pending}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">已有总结</dt>
                <dd className="text-lg font-medium">
                  {counts.already_summarized}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">失败重试</dt>
                <dd className="text-lg font-medium">{counts.failed}</dd>
              </div>
            </dl>
            {counts.active > 0 && (
              <p className="text-sm text-destructive" role="alert">
                有 {counts.active} 条内容正在处理中，请刷新内容库后再提交。
              </p>
            )}
            <div className="rounded-lg bg-muted/50 p-3 text-sm">
              <p>模型：{provider?.model ?? '未配置'}</p>
              <p className="mt-1 text-muted-foreground">
                提交后会发送正文及必要媒体，可能产生模型调用和用量费用。模型设置和自动任务授权请到对应页面管理。
              </p>
            </div>
            {preview.isError && (
              <p role="status" className="text-sm text-muted-foreground">
                暂时无法刷新选材状态，仍将按当前固定集合提交；如果状态已变化，服务端会提示刷新。
              </p>
            )}
            {!modelConfigured && (
              <p role="alert" className="text-sm text-destructive">
                尚未配置 AI 模型，确认生成报告暂不可用。请先到 AI 设置完成配置。
              </p>
            )}
            {start.isError && (
              <p role="alert" className="text-sm text-destructive">
                {analysisErrorMessage(start.error)}
              </p>
            )}
            {storageError && (
              <p role="alert" className="text-sm text-destructive">
                浏览器无法保存本次提交草稿，尚未发送。请允许本应用使用会话存储后重试。
              </p>
            )}
            {start.isError && (
              <div className="flex flex-wrap gap-2">
                {isAmbiguousAnalysisError(start.error) && currentIntent && (
                  <Button
                    variant="outline"
                    disabled={start.isPending}
                    onClick={() => start.mutate(currentIntent)}
                  >
                    重试提交（保持原选材）
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={() => {
                    start.reset()
                    setIntent(null)
                    clearSavedIntent()
                  }}
                >
                  重新选择
                </Button>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={start.isPending}
              onClick={() => setDialogOpen(false)}
            >
              返回选材
            </Button>
            <Button
              disabled={!canSubmit || start.isPending || counts.active > 0}
              aria-busy={start.isPending}
              onClick={submit}
            >
              {start.isPending ? '正在创建报告…' : '确认生成报告'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export { defaultReportName }
