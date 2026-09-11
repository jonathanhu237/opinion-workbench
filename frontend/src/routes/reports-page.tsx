import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  FileText,
  RefreshCw,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { z } from 'zod'

import { PromptChoiceField } from '@/components/prompt-choice-field'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { AI_SETTINGS_QUERY_KEY, fetchAISettings } from '@/lib/api/ai-settings'
import {
  ANALYSIS_SETTINGS_QUERY_KEY,
  fetchAnalysisSettings,
  promptChoiceSchema,
  type PromptChoice,
} from '@/lib/api/analysis-settings'
import {
  analysisErrorMessage,
  isAmbiguousAnalysisError,
} from '@/lib/api/analysis-shared'
import {
  CONTENT_ANALYSES_QUERY_KEY,
  CONTENT_ANALYSIS_JOBS_QUERY_KEY,
  fetchAnalysisJobItems,
} from '@/lib/api/content-analyses'
import {
  fetchReportGeneration,
  fetchReportRecordByReport,
  fetchReportGenerations,
  fetchGenerationEligibility,
  controlReportGeneration,
  createReportGeneration,
  fetchReportRecords,
  generationCreateSchema,
  GENERATIONS_QUERY_KEY,
  isActiveGeneration,
  previewReportSelection,
  REPORT_RECORDS_QUERY_KEY,
  summaryConcurrencySchema,
  type GenerationCreate,
  type ReportGeneration,
  type ReportRecord,
} from '@/lib/api/report-generations'
import {
  fetchResults,
  isActiveResult,
  readId,
  readOffset,
  RESULTS_QUERY_KEY,
  type SharedResult,
} from '@/lib/api/results'
import {
  cancelTopicReport,
  fetchTopicReport,
  isActiveReport,
  retryTopicReport,
  TOPIC_REPORTS_QUERY_KEY,
} from '@/lib/api/topic-reports'
import { ResultEvidence } from '@/routes/results-evidence'
import { ResultReadingDetail } from '@/routes/result-reading-detail'
import { ReadableReport } from '@/routes/readable-report'
import { ResultsJobs } from '@/routes/results-jobs'
import {
  formatEvidenceDate,
  ResultSourceLink,
} from '@/routes/results-presenters'
import {
  ReportCoverage,
  reportStatusLabels,
} from '@/routes/results-report-details'
import { searchPlatformPresenters } from '@/routes/search-run-presenters'
import { cn } from '@/lib/utils'
import { saveSummaryPreference } from '@/lib/api/summary-preferences'

const selectionDraftKey = 'longtian:report-selection-draft:v1'
const selectionPageSize = 5
const pendingIntentKey = 'longtian:report-generation:pending-intent:v1'
const summaryConcurrencyPreferenceKey =
  'longtian:report-generation:summary-concurrency:v1'
const DEFAULT_SUMMARY_CONCURRENCY = 8

type SummaryConcurrency = z.infer<typeof summaryConcurrencySchema>

function readSummaryConcurrencyPreference(): SummaryConcurrency {
  try {
    const raw = localStorage.getItem(summaryConcurrencyPreferenceKey)
    const value = summaryConcurrencySchema.safeParse(Number(raw))
    return value.success ? value.data : DEFAULT_SUMMARY_CONCURRENCY
  } catch {
    return DEFAULT_SUMMARY_CONCURRENCY
  }
}

function saveSummaryConcurrencyPreference(value: SummaryConcurrency) {
  try {
    localStorage.setItem(summaryConcurrencyPreferenceKey, String(value))
    void saveSummaryPreference(value)
  } catch {
    // Preference storage is optional and must not block a valid submission.
  }
}

const recordStatusLabels: Record<ReportRecord['status'], string> = {
  summarising: '正在总结内容',
  paused_for_manual_action: '等待人工处理',
  reporting: '正在生成报告',
  completed: '已完成',
  empty: '没有可生成内容',
  failed: '生成失败',
  configuration_blocked: '模型配置需要处理',
  cancelled: '已取消',
  interrupted: '已中断',
  queued: '等待生成',
  judging: '正在判断相关性',
  composing: '正在生成报告',
}

function readSelectionDraft() {
  try {
    const value = JSON.parse(sessionStorage.getItem(selectionDraftKey) ?? '[]')
    if (!Array.isArray(value)) return []
    return [...new Set(value)].filter(
      (id): id is number => Number.isSafeInteger(id) && id > 0,
    )
  } catch {
    return []
  }
}

function writeSelectionDraft(ids: number[]) {
  try {
    if (ids.length === 0) sessionStorage.removeItem(selectionDraftKey)
    else sessionStorage.setItem(selectionDraftKey, JSON.stringify(ids))
  } catch {
    // Session storage is an enhancement; the in-memory selection remains usable.
  }
}

function readPendingIntent(): GenerationCreate | null {
  try {
    const raw = sessionStorage.getItem(pendingIntentKey)
    if (!raw) return null
    const parsed = generationCreateSchema.safeParse(JSON.parse(raw))
    return parsed.success ? parsed.data : null
  } catch {
    return null
  }
}

function savePendingIntent(value: GenerationCreate) {
  try {
    sessionStorage.setItem(pendingIntentKey, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

function clearPendingIntent() {
  try {
    sessionStorage.removeItem(pendingIntentKey)
  } catch {
    // Replaying a retained UUID remains safe when storage is unavailable.
  }
}

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
  return `${parts.year}-${parts.month}-${parts.day} 舆情分析报告`
}

function recordStatusVariant(status: ReportRecord['status']) {
  if (
    ['failed', 'configuration_blocked', 'cancelled', 'interrupted'].includes(
      status,
    )
  )
    return 'destructive' as const
  if (status === 'completed') return 'secondary' as const
  return 'outline' as const
}

function isActiveRecord(record: ReportRecord) {
  return record.record_type === 'generation'
    ? isActiveGeneration(record.status as ReportGeneration['status'])
    : ['queued', 'judging', 'composing'].includes(record.status)
}

function recordTriggerLabel(trigger: ReportRecord['trigger']) {
  return {
    manual: '手动生成',
    automatic: '自动任务',
    interval: '时间范围',
    retry: '重试报告',
  }[trigger]
}

function resultSummary(result: SharedResult) {
  const title = result.source.title.trim()
  const snippet = result.source.snippet.trim()
  if (title && snippet && title !== snippet) return `${title} · ${snippet}`
  return title || snippet || `内容 #${result.id}`
}

function resultStateLabel(result: SharedResult) {
  if (isActiveResult(result)) return '处理中'
  if (
    result.analysis_state === 'completed' ||
    result.analysis_state === 'legacy_completed'
  )
    return '已总结'
  if (
    [
      'failed',
      'input_incomplete',
      'unsupported',
      'cancelled',
      'interrupted',
      'legacy_attempted',
    ].includes(result.analysis_state)
  )
    return '分析失败'
  return '待分析'
}

function resultStateVariant(result: SharedResult) {
  if (isActiveResult(result)) return 'outline' as const
  if (
    result.analysis_state === 'completed' ||
    result.analysis_state === 'legacy_completed'
  )
    return 'secondary' as const
  if (
    [
      'failed',
      'input_incomplete',
      'unsupported',
      'cancelled',
      'interrupted',
      'legacy_attempted',
    ].includes(result.analysis_state)
  )
    return 'destructive' as const
  return 'outline' as const
}

function platformLabel(platform: SharedResult['source']['platform']) {
  return searchPlatformPresenters[platform]?.label ?? platform
}

function SelectionLibrary({
  open,
  selectedIds,
  onSelectionChange,
  onOpenResult,
}: {
  open: boolean
  selectedIds: number[]
  onSelectionChange: (ids: number[]) => void
  onOpenResult: (id: number) => void
}) {
  const [offset, setOffset] = useState(0)
  const results = useQuery({
    queryKey: [
      ...RESULTS_QUERY_KEY,
      'report-wizard',
      selectionPageSize,
      offset,
    ],
    queryFn: ({ signal }) =>
      fetchResults({ offset }, signal, selectionPageSize),
    enabled: open,
    retry: false,
    refetchInterval: (query) => (query.state.data?.active_count ? 1000 : false),
  })
  const page = results.data
  const items = page?.items ?? []
  const selectable = items.filter((item) => !isActiveResult(item))
  const pageIds = selectable.map((item) => item.id)
  const selected = new Set(selectedIds)
  const allSelected =
    pageIds.length > 0 && pageIds.every((id) => selected.has(id))
  const someSelected = pageIds.some((id) => selected.has(id))

  useEffect(() => {
    const activeIds = new Set(
      items.filter((item) => isActiveResult(item)).map((item) => item.id),
    )
    const next = selectedIds.filter((id) => !activeIds.has(id))
    if (next.length !== selectedIds.length) onSelectionChange(next)
  }, [items, onSelectionChange, selectedIds])

  const toggle = (id: number, checked: boolean) => {
    onSelectionChange(
      checked
        ? [...new Set([...selectedIds, id])]
        : selectedIds.filter((value) => value !== id),
    )
  }
  const togglePage = (checked: boolean) => {
    const ids = new Set(pageIds)
    onSelectionChange(
      checked
        ? [...new Set([...selectedIds, ...ids])]
        : selectedIds.filter((id) => !ids.has(id)),
    )
  }

  return (
    <section
      aria-labelledby="report-selection-library-heading"
      className="space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 id="report-selection-library-heading" className="font-medium">
            选择内容
          </h3>
          <p className="text-sm text-muted-foreground">
            从内容库固定本次选材；跨页勾选会一直保留，处理中内容不可重复选择。
          </p>
        </div>
        <span className="text-sm font-medium tabular-nums" aria-live="polite">
          已选 {selectedIds.length} 条
        </span>
      </div>
      {results.isPending && <p role="status">正在读取舆情内容…</p>}
      {results.isError && (
        <p role="alert" className="text-sm text-destructive">
          {analysisErrorMessage(results.error)}
        </p>
      )}
      {page && page.total === 0 && (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          还没有舆情内容，请先到“舆情爬取”完成一次搜索。
        </p>
      )}
      {page && items.length > 0 && (
        <>
          <div className="max-h-[40dvh] overflow-y-auto rounded-lg border">
            <Table aria-label="报告选材内容表格">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      aria-label="选择当前页"
                      checked={allSelected}
                      indeterminate={someSelected && !allSelected}
                      disabled={pageIds.length === 0}
                      onCheckedChange={(checked) =>
                        togglePage(checked === true)
                      }
                    />
                  </TableHead>
                  <TableHead>内容</TableHead>
                  <TableHead>平台</TableHead>
                  <TableHead>时间</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow
                    key={item.id}
                    data-state={selected.has(item.id) ? 'selected' : undefined}
                  >
                    <TableCell>
                      <Checkbox
                        aria-label={`选择内容：${item.source.title}`}
                        checked={selected.has(item.id)}
                        disabled={isActiveResult(item)}
                        onCheckedChange={(checked) =>
                          toggle(item.id, checked === true)
                        }
                      />
                    </TableCell>
                    <TableCell className="max-w-[28rem] whitespace-normal">
                      <p className="line-clamp-2 font-medium [overflow-wrap:anywhere]">
                        {resultSummary(item)}
                      </p>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {platformLabel(item.source.platform)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.source.published_at_text || '未知'}
                    </TableCell>
                    <TableCell>
                      <Badge variant={resultStateVariant(item)}>
                        {resultStateLabel(item)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-1">
                        <Button
                          variant="outline"
                          className="min-h-9"
                          onClick={() => onOpenResult(item.id)}
                          aria-label={`查看内容详情：${item.source.title}`}
                        >
                          查看详情
                        </Button>
                        <ResultSourceLink source={item.source} />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
            <span className="text-sm text-muted-foreground">
              {page.offset + 1}–
              {Math.min(page.total, page.offset + selectionPageSize)} /{' '}
              {page.total} 条
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="min-h-9"
                disabled={offset === 0 || results.isFetching}
                onClick={() =>
                  setOffset(Math.max(0, offset - selectionPageSize))
                }
              >
                <ChevronLeft aria-hidden /> 上一页
              </Button>
              <Button
                variant="outline"
                className="min-h-9"
                disabled={
                  page.total - offset <= selectionPageSize || results.isFetching
                }
                onClick={() => setOffset(offset + selectionPageSize)}
              >
                下一页 <ChevronRight aria-hidden />
              </Button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}

function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  const labels = ['选择内容', '内容分析', '报告总结']
  return (
    <ol aria-label="报告生成步骤" className="grid grid-cols-3 gap-2">
      {labels.map((label, index) => {
        const current = index + 1 === step
        const done = index + 1 < step
        return (
          <li
            key={label}
            aria-current={current ? 'step' : undefined}
            className={cn(
              'flex min-h-10 items-center gap-2 rounded-lg border px-2 text-sm',
              current && 'border-primary bg-primary/5 font-medium',
              done && 'text-muted-foreground',
            )}
          >
            <span className="grid size-5 shrink-0 place-items-center rounded-full border text-xs">
              {done ? <Check aria-hidden className="size-3.5" /> : index + 1}
            </span>
            <span>{label}</span>
          </li>
        )
      })}
    </ol>
  )
}

function ReportGenerationWizard({
  open,
  onOpenChange,
  onStarted,
  initialResultId = null,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStarted: (generation: ReportGeneration) => void
  initialResultId?: number | null
}) {
  const client = useQueryClient()
  const restored = useMemo(readPendingIntent, [])
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [selectedIds, setSelectedIds] = useState<number[]>(() =>
    restored?.selection.kind === 'explicit'
      ? restored.selection.result_ids
      : initialResultId !== null
        ? [initialResultId]
        : readSelectionDraft(),
  )
  const [intent, setIntent] = useState<GenerationCreate | null>(restored)
  const [name, setName] = useState(() => restored?.name ?? defaultReportName())
  const [initialPrompt, setInitialPrompt] = useState<PromptChoice>(
    () => restored?.initial_prompt ?? { mode: 'default' },
  )
  const [reportPrompt, setReportPrompt] = useState<PromptChoice>(
    () => restored?.report_prompt ?? { mode: 'default' },
  )
  const [summaryConcurrency, setSummaryConcurrency] =
    useState<SummaryConcurrency>(
      () => restored?.summary_concurrency ?? readSummaryConcurrencyPreference(),
    )
  const [detailId, setDetailId] = useState<number | null>(null)
  const [detailParams, setDetailParams] = useSearchParams()
  const savedDetailParams = useRef(new URLSearchParams())
  const dialogRef = useRef<HTMLDivElement>(null)
  const detailReturn = useRef<{ element: HTMLElement | null; scroll: number }>({
    element: null,
    scroll: 0,
  })
  const openDetail = (id: number) => {
    savedDetailParams.current = new URLSearchParams(detailParams)
    detailReturn.current = {
      element: document.activeElement as HTMLElement | null,
      scroll: dialogRef.current?.scrollTop ?? 0,
    }
    setDetailId(id)
  }
  const closeDetail = () => {
    setDetailId(null)
    setDetailParams(
      (current) => {
        const next = new URLSearchParams(current)
        for (const key of [
          'attempt',
          'attempt_offset',
          'origin_offset',
          'legacy_offset',
        ]) {
          const previous = savedDetailParams.current.get(key)
          if (previous === null) next.delete(key)
          else next.set(key, previous)
        }
        return next
      },
      { replace: true },
    )
    window.setTimeout(() => {
      detailReturn.current.element?.focus({ preventScroll: true })
      if (dialogRef.current)
        dialogRef.current.scrollTop = detailReturn.current.scroll
    }, 0)
  }
  const [bulkError, setBulkError] = useState<string | null>(null)
  const [storageError, setStorageError] = useState(false)
  const [activeError, setActiveError] = useState<string | null>(null)
  const ids =
    intent?.selection.kind === 'explicit'
      ? intent.selection.result_ids
      : selectedIds
  const settings = useQuery({
    queryKey: ANALYSIS_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAnalysisSettings(signal),
    enabled: open,
    retry: false,
  })
  const provider = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    enabled: open,
    retry: false,
  })
  const eligibility = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, 'eligibility'],
    queryFn: ({ signal }) => fetchGenerationEligibility(signal),
    enabled: open && intent === null,
    retry: false,
  })
  const generations = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, 'list'],
    queryFn: ({ signal }) => fetchReportGenerations(signal),
    enabled: open,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => isActiveGeneration(item.status))
        ? 1000
        : false,
  })
  const active = Boolean(
    generations.data?.items.some((item) => isActiveGeneration(item.status)),
  )
  const preview = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, 'wizard-preview', ids],
    queryFn: () =>
      previewReportSelection({ kind: 'explicit', result_ids: [...ids] }),
    enabled: open && step === 3 && ids.length > 0,
    retry: false,
  })
  const bulk = useMutation({
    mutationFn: () => previewReportSelection({ kind: 'library' }),
    retry: false,
    onSuccess: (value) => {
      setBulkError(null)
      setSelectedIds((current) => {
        const next = [...new Set([...current, ...value.selection.result_ids])]
        writeSelectionDraft(next)
        return next
      })
    },
    onError: (error) => setBulkError(analysisErrorMessage(error)),
  })
  const start = useMutation({
    mutationFn: createReportGeneration,
    retry: false,
    onSuccess: (generation, request) => {
      saveSummaryConcurrencyPreference(
        request.summary_concurrency ?? DEFAULT_SUMMARY_CONCURRENCY,
      )
      setIntent(null)
      clearPendingIntent()
      setSelectedIds([])
      writeSelectionDraft([])
      setStep(1)
      setName(defaultReportName())
      setInitialPrompt({ mode: 'default' })
      setReportPrompt({ mode: 'default' })
      setSummaryConcurrency(readSummaryConcurrencyPreference())
      setStorageError(false)
      onOpenChange(false)
      onStarted(generation)
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY })
    },
  })
  const previewReady =
    preview.data !== undefined &&
    preview.data.selection.result_ids.length === ids.length &&
    preview.data.selection.result_ids.every((id) => ids.includes(id))
  const modelConfigured = Boolean(
    provider.data?.has_api_key && provider.data.model && provider.data.base_url,
  )
  const initialValid = promptChoiceSchema.safeParse(initialPrompt).success
  const reportValid = promptChoiceSchema.safeParse(reportPrompt).success
  const canSubmit =
    ids.length > 0 &&
    modelConfigured &&
    settings.data !== undefined &&
    initialValid &&
    reportValid &&
    name.trim().length > 0 &&
    !active &&
    previewReady &&
    preview.data?.counts.active === 0 &&
    !preview.isFetching &&
    !start.isPending

  useEffect(() => {
    if (intent === null) writeSelectionDraft(selectedIds)
  }, [intent, selectedIds])

  function updateSelection(next: number[]) {
    if (intent !== null) return
    setSelectedIds([...new Set(next)])
  }

  function submit() {
    if (!canSubmit || !provider.data || !settings.data) return
    if (active) {
      setActiveError('已有报告正在生成，请等待当前任务结束后再提交。')
      return
    }
    const request = intent ?? {
      request_id: crypto.randomUUID(),
      name: name.trim(),
      configuration_revision: provider.data.revision,
      initial_prompt: initialPrompt,
      report_prompt: reportPrompt,
      summary_concurrency: summaryConcurrency,
      selection: { kind: 'explicit' as const, result_ids: [...ids] },
    }
    if (!savePendingIntent(request)) {
      setStorageError(true)
      return
    }
    setStorageError(false)
    setIntent(request)
    start.mutate(request)
  }

  const close = (next: boolean) => {
    if (start.isPending) return
    if (!next && detailId !== null) {
      closeDetail()
      return
    }
    if (!next && intent === null) {
      setSummaryConcurrency(readSummaryConcurrencyPreference())
    }
    onOpenChange(next)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={close}>
        <DialogContent
          ref={dialogRef}
          className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-5xl"
          showCloseButton={!start.isPending}
        >
          {detailId !== null && (
            <>
              <DialogTitle className="sr-only">内容详情</DialogTitle>
              <div className="mx-auto w-full max-w-3xl">
                <ResultReadingDetail
                  key={detailId}
                  resultId={detailId}
                  onClose={closeDetail}
                />
              </div>
            </>
          )}
          <div hidden={detailId !== null}>
            <div className="flex flex-col gap-4">
              {detailId === null && (
                <DialogHeader>
                  <DialogTitle>生成报告</DialogTitle>
                  <DialogDescription>
                    先固定选材，再填写两套提示词；只有最后一步才会开始处理。
                  </DialogDescription>
                </DialogHeader>
              )}
              <StepIndicator step={step} />
              {intent && (
                <p
                  className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm"
                  role="status"
                >
                  上次提交结果不确定。本次选材和提示词已经固定，再次提交会重放同一个请求，不会重复创建。
                </p>
              )}
              {step === 1 && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="outline"
                      disabled={bulk.isPending || intent !== null}
                      onClick={() => bulk.mutate()}
                    >
                      {bulk.isPending
                        ? '正在形成选材快照…'
                        : '选中全部未纳入报告的内容'}
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      未纳入报告{' '}
                      {eligibility.data
                        ? eligibility.data.pending + eligibility.data.failed
                        : '—'}{' '}
                      条（包含曾失败内容）
                    </span>
                    {ids.length > 0 && (
                      <Button
                        variant="ghost"
                        disabled={intent !== null || start.isPending}
                        onClick={() => updateSelection([])}
                      >
                        清空选择
                      </Button>
                    )}
                  </div>
                  {bulkError && (
                    <p role="alert" className="text-sm text-destructive">
                      {bulkError}
                    </p>
                  )}
                  <SelectionLibrary
                    open={open && step === 1}
                    selectedIds={ids}
                    onSelectionChange={updateSelection}
                    onOpenResult={openDetail}
                  />
                </div>
              )}
              {step === 2 && settings.data && (
                <PromptChoiceField
                  id="report-wizard-initial-prompt"
                  label="内容分析提示词"
                  description="用于理解每条内容并生成单条总结；已有可用总结会复用，修改只影响本次生成。"
                  value={initialPrompt}
                  onChange={setInitialPrompt}
                  defaultInstructions={
                    settings.data.initial_prompt.instructions
                  }
                  disabled={intent !== null || start.isPending}
                  error={!initialValid ? '请输入有效提示词。' : undefined}
                />
              )}
              {step === 2 && settings.isPending && (
                <p role="status">正在读取默认提示词…</p>
              )}
              {step === 2 && settings.isError && (
                <p role="alert" className="text-sm text-destructive">
                  无法读取默认提示词，请刷新后重试。
                </p>
              )}
              {step === 3 && (
                <div className="space-y-5">
                  <Field data-invalid={!name.trim()}>
                    <FieldLabel htmlFor="report-wizard-name">
                      报告名称
                    </FieldLabel>
                    <Input
                      id="report-wizard-name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      maxLength={200}
                      disabled={intent !== null || start.isPending}
                      aria-invalid={!name.trim()}
                    />
                    <FieldError
                      errors={
                        !name.trim() ? [{ message: '请输入报告名称。' }] : []
                      }
                    />
                  </Field>
                  {settings.data ? (
                    <PromptChoiceField
                      id="report-wizard-report-prompt"
                      label="报告总结提示词"
                      description="用于汇总已选内容并组织整份报告；修改只影响本次生成。"
                      value={reportPrompt}
                      onChange={setReportPrompt}
                      defaultInstructions={
                        settings.data.report_prompt.instructions
                      }
                      disabled={intent !== null || start.isPending}
                      error={!reportValid ? '请输入有效提示词。' : undefined}
                    />
                  ) : settings.isPending ? (
                    <p role="status">正在读取默认提示词…</p>
                  ) : (
                    <p role="alert" className="text-sm text-destructive">
                      无法读取默认提示词，请刷新后重试。
                    </p>
                  )}
                  <div className="rounded-lg border bg-background p-3">
                    <label
                      className="text-sm font-medium"
                      htmlFor="report-wizard-summary-concurrency"
                    >
                      单条总结并发数
                    </label>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      只控制已取得正文后的模型总结；内容补全仍逐条执行。新任务默认
                      8 条同时总结。
                    </p>
                    <Select
                      value={String(summaryConcurrency)}
                      onValueChange={(value) => {
                        const parsed = Number(value)
                        const valid = summaryConcurrencySchema.safeParse(parsed)
                        if (valid.success) setSummaryConcurrency(valid.data)
                      }}
                      disabled={intent !== null || start.isPending}
                    >
                      <SelectTrigger
                        id="report-wizard-summary-concurrency"
                        className="mt-3 min-h-10 w-full sm:w-48"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[1, 2, 4, 8, 16].map((value) => (
                          <SelectItem key={value} value={String(value)}>
                            {value} 条同时总结
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <dl className="grid gap-3 rounded-lg border p-3 text-sm sm:grid-cols-4">
                    <div>
                      <dt className="text-muted-foreground">选中总数</dt>
                      <dd className="text-lg font-medium">{ids.length}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">待分析</dt>
                      <dd className="text-lg font-medium">
                        {preview.data?.counts.pending ?? '—'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">已有总结</dt>
                      <dd className="text-lg font-medium">
                        {preview.data?.counts.already_summarized ?? '—'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">失败重试</dt>
                      <dd className="text-lg font-medium">
                        {preview.data?.counts.failed ?? '—'}
                      </dd>
                    </div>
                  </dl>
                  {preview.isFetching && (
                    <p role="status">正在核对当前选材状态…</p>
                  )}
                  {preview.isError && (
                    <p role="alert" className="text-sm text-destructive">
                      无法确认当前选材状态，请返回第一步刷新后重试。
                    </p>
                  )}
                  {preview.data?.counts.active ? (
                    <p role="alert" className="text-sm text-destructive">
                      有 {preview.data.counts.active}{' '}
                      条内容正在处理中，请刷新内容库后再提交。
                    </p>
                  ) : null}
                  <div className="rounded-lg bg-muted/50 p-3 text-sm">
                    <p>当前模型：{provider.data?.model ?? '未配置'}</p>
                    {provider.data?.base_url && (
                      <p className="mt-1 wrap-anywhere text-muted-foreground">
                        {provider.data.base_url}
                      </p>
                    )}
                    {!modelConfigured && (
                      <p className="mt-2 text-destructive">
                        尚未配置 AI 模型，确认生成报告暂不可用。请前往{' '}
                        <Link className="underline" to="/settings#ai">
                          设置
                        </Link>
                        。
                      </p>
                    )}
                    {modelConfigured && (
                      <Link
                        className="mt-2 inline-block underline"
                        to="/settings#ai"
                      >
                        前往设置修改模型
                      </Link>
                    )}
                  </div>
                  {active && (
                    <p role="alert" className="text-sm text-destructive">
                      已有报告正在生成，提交会被服务端拒绝；可以先保留本次准备。
                    </p>
                  )}
                  {activeError && (
                    <p role="alert" className="text-sm text-destructive">
                      {activeError}
                    </p>
                  )}
                  {start.isError && (
                    <div className="space-y-2">
                      <p role="alert" className="text-sm text-destructive">
                        {analysisErrorMessage(start.error)}
                      </p>
                      {isAmbiguousAnalysisError(start.error) && intent && (
                        <Button
                          variant="outline"
                          onClick={() => start.mutate(intent)}
                        >
                          重试提交（保持原选材）
                        </Button>
                      )}
                      {!isAmbiguousAnalysisError(start.error) && (
                        <Button
                          variant="outline"
                          onClick={() => {
                            start.reset()
                            setIntent(null)
                            clearPendingIntent()
                          }}
                        >
                          返回修改
                        </Button>
                      )}
                    </div>
                  )}
                  {storageError && (
                    <p role="alert" className="text-sm text-destructive">
                      浏览器无法保存本次提交草稿，尚未发送。
                    </p>
                  )}
                </div>
              )}
              <DialogFooter className="sticky -bottom-6 z-10 border-t bg-background py-3">
                {step > 1 && (
                  <Button
                    variant="outline"
                    disabled={start.isPending}
                    onClick={() => setStep((value) => (value - 1) as 1 | 2 | 3)}
                  >
                    上一步
                  </Button>
                )}
                <Button
                  variant="outline"
                  disabled={start.isPending}
                  onClick={() => close(false)}
                >
                  暂时关闭
                </Button>
                {step < 3 ? (
                  <Button
                    disabled={
                      step === 1
                        ? ids.length === 0
                        : !initialValid || !settings.data
                    }
                    onClick={() => setStep((value) => (value + 1) as 1 | 2 | 3)}
                  >
                    下一步
                  </Button>
                ) : (
                  <Button
                    disabled={!canSubmit}
                    aria-busy={start.isPending}
                    onClick={submit}
                  >
                    {start.isPending ? '正在创建报告…' : '开始生成'}
                  </Button>
                )}
              </DialogFooter>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function GenerationProgress({
  generation,
  onViewReport,
}: {
  generation: ReportGeneration
  onViewReport: (id: number) => void
}) {
  const client = useQueryClient()
  const [errorOffset, setErrorOffset] = useState(0)
  const attempts = useQuery({
    queryKey: [
      ...CONTENT_ANALYSIS_JOBS_QUERY_KEY,
      generation.analysis.id,
      'progress-items',
      errorOffset,
    ],
    queryFn: ({ signal }) =>
      fetchAnalysisJobItems(generation.analysis.id, signal, errorOffset),
    retry: false,
    refetchInterval: isActiveGeneration(generation.status) ? 1000 : false,
  })
  const provider = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    retry: false,
  })
  const control = useMutation({
    mutationFn: (action: 'continue' | 'manual-page' | 'cancel') =>
      controlReportGeneration(
        generation.id,
        generation.control_revision,
        action,
      ),
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: REPORT_RECORDS_QUERY_KEY })
      void client.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY })
    },
  })
  const retry = useMutation({
    mutationFn: () => {
      if (!generation.report) throw new Error('missing report')
      if (
        !provider.data?.has_api_key ||
        !provider.data.model ||
        !provider.data.base_url
      )
        throw new Error('请先保存有效的 AI 配置。')
      return retryTopicReport(generation.report.id, {
        request_id: crypto.randomUUID(),
        expected_revision: generation.report.revision,
        configuration_revision: provider.data.revision,
      })
    },
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: REPORT_RECORDS_QUERY_KEY })
      void client.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY })
      void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
    },
  })
  const counts = generation.analysis.counts
  const failed = counts.failed + counts.input_incomplete + counts.unsupported
  const processed =
    counts.total - counts.queued - counts.acquiring - counts.analysing
  const canRetry =
    generation.report?.status === 'failed' ||
    generation.report?.status === 'configuration_blocked'
  const allFailed =
    generation.status === 'empty' && counts.completed === 0 && failed > 0
  return (
    <div className="space-y-4">
      <div>
        <p className="font-medium" role="status">
          {allFailed
            ? '生成失败：没有内容完成分析'
            : recordStatusLabels[generation.status]}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          {generation.name} · 创建于 {formatEvidenceDate(generation.created_at)}
        </p>
      </div>
      <progress
        aria-label="内容处理进度"
        max={counts.total}
        value={Math.max(0, processed)}
        className={cn(
          'h-2 w-full',
          failed + counts.interrupted + counts.cancelled > 0
            ? 'accent-destructive'
            : 'accent-primary',
        )}
      />
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">已处理</dt>
          <dd className="text-lg font-medium">
            {Math.max(0, processed)}/{counts.total}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">处理中</dt>
          <dd className="text-lg font-medium">
            {counts.acquiring + counts.analysing}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">已总结</dt>
          <dd className="text-lg font-medium">{counts.completed}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">失败</dt>
          <dd className="text-lg font-medium">{failed}</dd>
        </div>
      </dl>
      {counts.interrupted + counts.cancelled > 0 && (
        <p className="text-sm">
          其中 {counts.interrupted} 条中断、{counts.cancelled} 条取消。
        </p>
      )}
      {attempts.isError && (
        <p role="alert">
          无法读取条目错误详情。
          <Button variant="link" onClick={() => void attempts.refetch()}>
            重试
          </Button>
        </p>
      )}
      {attempts.data && failed + counts.interrupted + counts.cancelled > 0 && (
        <section
          aria-label="条目处理详情"
          className="space-y-2 rounded-lg border p-3"
        >
          <h3 className="font-medium">条目处理详情</h3>
          {attempts.data.items.map(
            (item) =>
              item.error && (
                <div key={item.id} className="border-t pt-2 text-sm">
                  <p className="font-medium">{item.source.title}</p>
                  <p>
                    {item.error.diagnostic?.stage === 'browser' &&
                    item.error.diagnostic.basis === 'transport'
                      ? '专用浏览器不可用，未能获取原文。请在平台账号中检查浏览器。'
                      : item.error.message}
                  </p>
                  {item.error.validation_issues?.map((issue) => (
                    <p key={issue} className="text-muted-foreground">
                      {issue}
                    </p>
                  ))}
                  {item.error.code === 'invalid_schema' &&
                    !item.error.validation_issues?.length && (
                      <p className="text-muted-foreground">
                        该历史记录未保存具体字段校验原因。
                      </p>
                    )}
                </div>
              ),
          )}
          {attempts.data.total > 20 && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={errorOffset === 0}
                onClick={() => setErrorOffset(Math.max(0, errorOffset - 20))}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                disabled={errorOffset + 20 >= attempts.data.total}
                onClick={() => setErrorOffset(errorOffset + 20)}
              >
                下一页
              </Button>
            </div>
          )}
        </section>
      )}
      {generation.analysis.queue_reason === 'browser_operation_active' && (
        <p className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm">
          平台浏览器操作正在进行，其他依赖浏览器的任务会等待。
        </p>
      )}
      {generation.analysis.access_waiting && (
        <p
          className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm"
          role="status"
        >
          正在等待平台访问间隔；合法的访问等待不会被计入浏览器或模型超时。本次任务已固定启动时的间隔配置。
        </p>
      )}
      {generation.analysis.access_notice && (
        <p
          className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm"
          role="alert"
        >
          已记录平台访问限制
          {generation.analysis.access_notice.status_code
            ? `（HTTP ${generation.analysis.access_notice.status_code}）`
            : ''}
          ，不会自动绕过限制。请确认平台状态后手动继续；
          {generation.analysis.access_notice.manual_challenge_required
            ? '平台还要求完成安全验证。'
            : '系统保留了本次限制证据。'}
        </p>
      )}
      {generation.analysis.model_retry_notice && (
        <p
          className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm"
          role="status"
        >
          {generation.analysis.model_retry_notice.action === 'retrying'
            ? `模型服务暂时限流，正在等待 ${generation.analysis.model_retry_notice.wait_seconds.toFixed(1)} 秒后有限重试。`
            : '模型服务持续限流，已达到本次自动重试上限；没有继续重复请求。'}
        </p>
      )}
      {generation.pause_reason && (
        <div className="rounded-lg border p-3 text-sm">
          <p>
            {generation.pause_reason === 'login_required'
              ? '当前平台需要重新登录。'
              : generation.pause_reason === 'platform_blocked_or_rate_limited'
                ? '当前平台提示限流，请在专用浏览器确认状态。'
                : '当前平台需要完成安全验证。'}
            已保存的结果不会丢失。
          </p>
          <p className="mt-2">
            打开窗口、刷新页面或登录成功都不会自动继续；确认处理完成后，请明确点击继续。
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={control.isPending}
              onClick={() => control.mutate('manual-page')}
            >
              打开平台专用窗口
            </Button>
            <Button
              disabled={control.isPending}
              onClick={() => control.mutate('continue')}
            >
              继续生成报告
            </Button>
          </div>
        </div>
      )}
      {isActiveGeneration(generation.status) && !generation.pause_reason && (
        <Button
          variant="outline"
          disabled={control.isPending}
          onClick={() => control.mutate('cancel')}
        >
          取消本次报告生成
        </Button>
      )}
      {control.isError && (
        <p role="alert" className="text-sm text-destructive">
          {analysisErrorMessage(control.error)}
        </p>
      )}
      {generation.report?.error && (
        <p role="alert" className="text-sm text-destructive">
          {generation.report.error.message} 已完成的内容仍保留。
        </p>
      )}
      {canRetry && generation.report && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            disabled={
              retry.isPending ||
              provider.isPending ||
              !provider.data?.has_api_key ||
              !provider.data.model ||
              !provider.data.base_url
            }
            onClick={() => retry.mutate()}
          >
            {retry.isPending ? '正在重试报告…' : '仅重试报告'}
          </Button>
          <span className="text-sm text-muted-foreground">
            复用已保存的内容和单条总结，不重复下载。
          </span>
        </div>
      )}
      {retry.isError && (
        <p role="alert" className="text-sm text-destructive">
          {analysisErrorMessage(retry.error)}
        </p>
      )}
      {generation.report &&
        !allFailed &&
        ['completed', 'empty'].includes(generation.report.status) && (
          <Button onClick={() => onViewReport(generation.report!.id)}>
            查看报告
          </Button>
        )}
      {generation.status === 'interrupted' && (
        <p className="text-sm text-muted-foreground">
          任务已中断，已完成的总结仍保留；不会自动重试可能收费的请求。
        </p>
      )}
    </div>
  )
}

function TopicReportProgress({
  reportId,
  onViewReport,
}: {
  reportId: number
  onViewReport: (id: number) => void
}) {
  const client = useQueryClient()
  const report = useQuery({
    queryKey: [...TOPIC_REPORTS_QUERY_KEY, 'detail', reportId],
    queryFn: ({ signal }) => fetchTopicReport(reportId, signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveReport(query.state.data.status)
        ? 1000
        : false,
  })
  const provider = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    retry: false,
  })
  const cancel = useMutation({
    mutationFn: () => {
      if (!report.data) throw new Error('missing report')
      return cancelTopicReport(reportId, {
        request_id: crypto.randomUUID(),
        expected_revision: report.data.revision,
      })
    },
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: REPORT_RECORDS_QUERY_KEY })
      void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
    },
  })
  const retry = useMutation({
    mutationFn: () => {
      if (!report.data) throw new Error('missing report')
      if (
        !provider.data?.has_api_key ||
        !provider.data.model ||
        !provider.data.base_url
      )
        throw new Error('请先保存有效的 AI 配置。')
      return retryTopicReport(reportId, {
        request_id: crypto.randomUUID(),
        expected_revision: report.data.revision,
        configuration_revision: provider.data.revision,
      })
    },
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: REPORT_RECORDS_QUERY_KEY })
      void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
    },
  })
  if (report.isPending) return <p role="status">正在读取报告进度…</p>
  if (report.isError)
    return (
      <p role="alert" className="text-sm text-destructive">
        {analysisErrorMessage(report.error)}
      </p>
    )
  if (!report.data) return null
  const canRetry =
    report.data.status === 'failed' ||
    report.data.status === 'configuration_blocked'
  return (
    <div className="space-y-4">
      <div>
        <p className="font-medium" role="status">
          {reportStatusLabels[report.data.status]}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          报告 #{report.data.id} · 创建于{' '}
          {formatEvidenceDate(report.data.created_at)}
        </p>
      </div>
      <ReportCoverage report={report.data} />
      {isActiveReport(report.data.status) && (
        <Button
          variant="outline"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate()}
        >
          取消报告生成
        </Button>
      )}
      {cancel.isError && (
        <p role="alert" className="text-sm text-destructive">
          {analysisErrorMessage(cancel.error)}
        </p>
      )}
      {canRetry && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            disabled={
              retry.isPending ||
              provider.isPending ||
              !provider.data?.has_api_key ||
              !provider.data.model ||
              !provider.data.base_url
            }
            onClick={() => retry.mutate()}
          >
            {retry.isPending ? '正在重试报告…' : '仅重试报告'}
          </Button>
          <span className="text-sm text-muted-foreground">
            已保存的来源和证据会继续复用。
          </span>
        </div>
      )}
      {retry.isError && (
        <p role="alert" className="text-sm text-destructive">
          {analysisErrorMessage(retry.error)}
        </p>
      )}
      {!isActiveReport(report.data.status) && (
        <Button onClick={() => onViewReport(report.data!.id)}>查看报告</Button>
      )}
    </div>
  )
}

function ProgressSheet({
  record,
  onClose,
  onViewReport,
}: {
  record: ReportRecord | null
  onClose: () => void
  onViewReport: (id: number) => void
}) {
  const generation = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, record?.generation_id],
    queryFn: ({ signal }) =>
      fetchReportGeneration(record!.generation_id!, signal),
    enabled:
      record?.record_type === 'generation' && record.generation_id !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveGeneration(query.state.data.status)
        ? 1000
        : false,
  })
  return (
    <Sheet open={record !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-2xl"
      >
        <SheetHeader>
          <SheetTitle>
            {record ? `${record.name} · 进度` : '报告进度'}
          </SheetTitle>
          <SheetDescription>
            查看阶段、数量和异常处理；关闭抽屉不会停止后台任务。
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6">
          {record?.record_type === 'generation' && (
            <>
              {generation.isPending && <p role="status">正在读取生成任务…</p>}
              {generation.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {analysisErrorMessage(generation.error)}
                </p>
              )}
              {generation.data && (
                <GenerationProgress
                  generation={generation.data}
                  onViewReport={onViewReport}
                />
              )}
            </>
          )}
          {record?.record_type === 'report' && record.report_id !== null && (
            <TopicReportProgress
              reportId={record.report_id}
              onViewReport={onViewReport}
            />
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function ReportList({
  onOpenDetail,
  initialWizardOpen = false,
  initialGenerationId = null,
  initialResultId = null,
  onClearLegacyQuery,
}: {
  onOpenDetail: (id: number) => void
  initialWizardOpen?: boolean
  initialGenerationId?: number | null
  initialResultId?: number | null
  onClearLegacyQuery?: () => void
}) {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const offset = readOffset(params.get('offset'))
  const [wizardOpen, setWizardOpen] = useState(initialWizardOpen)
  const [progressRecord, setProgressRecord] = useState<ReportRecord | null>(
    null,
  )
  const legacyGeneration = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, 'legacy', initialGenerationId],
    queryFn: ({ signal }) =>
      fetchReportGeneration(initialGenerationId!, signal),
    enabled: initialGenerationId !== null,
    retry: false,
  })
  const records = useQuery({
    queryKey: [...REPORT_RECORDS_QUERY_KEY, offset],
    queryFn: ({ signal }) => fetchReportRecords(signal, offset),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some(isActiveRecord) ? 1000 : false,
  })
  const refresh = () => {
    void client.invalidateQueries({ queryKey: REPORT_RECORDS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: RESULTS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: CONTENT_ANALYSES_QUERY_KEY })
    void client.invalidateQueries({ queryKey: CONTENT_ANALYSIS_JOBS_QUERY_KEY })
  }
  const changePage = (next: number) => {
    setParams((current) => {
      const value = new URLSearchParams(current)
      if (next === 0) value.delete('offset')
      else value.set('offset', String(next))
      return value
    })
  }
  const openReport = (id: number) => {
    setProgressRecord(null)
    onOpenDetail(id)
  }
  useEffect(() => {
    if (initialGenerationId === null || progressRecord !== null) return
    const listed = records.data?.items.find(
      (item) =>
        item.record_type === 'generation' &&
        item.generation_id === initialGenerationId,
    )
    if (listed) {
      setProgressRecord(listed)
      return
    }
    if (legacyGeneration.data) {
      const counts = legacyGeneration.data.analysis.counts
      setProgressRecord({
        record_type: 'generation',
        record_id: legacyGeneration.data.id,
        generation_id: legacyGeneration.data.id,
        report_id: legacyGeneration.data.report?.id ?? null,
        automation_run_id: null,
        name: legacyGeneration.data.name ?? `报告 #${legacyGeneration.data.id}`,
        trigger: 'manual',
        status: legacyGeneration.data.status,
        created_at: legacyGeneration.data.created_at,
        selection_count: counts.total,
        processed_count:
          counts.total - counts.queued - counts.acquiring - counts.analysing,
        failed_count:
          counts.failed +
          counts.input_incomplete +
          counts.unsupported +
          counts.cancelled +
          counts.interrupted,
        active_count: counts.queued + counts.acquiring + counts.analysing,
        parent_report_id: null,
      })
    }
  }, [initialGenerationId, legacyGeneration.data, progressRecord, records.data])
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          className="min-h-10"
          aria-label="刷新报告列表"
          disabled={records.isFetching}
          onClick={refresh}
        >
          <RefreshCw
            className={
              records.isFetching
                ? 'animate-spin motion-reduce:animate-none'
                : undefined
            }
            aria-hidden
          />
          刷新
        </Button>
        <Button
          type="button"
          className="min-h-10"
          onClick={() => setWizardOpen(true)}
        >
          <FileText aria-hidden /> 生成报告
        </Button>
      </div>
      {records.isPending && <p role="status">正在读取报告记录…</p>}
      {records.isError && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 text-sm text-destructive"
        >
          <span>{analysisErrorMessage(records.error)}</span>
          <Button variant="outline" onClick={() => void records.refetch()}>
            重试读取
          </Button>
        </div>
      )}
      {records.data && records.data.items.length === 0 && (
        <div className="rounded-xl border border-dashed p-12 text-center">
          <p className="font-medium">还没有报告记录</p>
          <p className="mt-2 text-sm text-muted-foreground">
            点击“生成报告”从已采集内容中选择材料。
          </p>
        </div>
      )}
      {records.data && records.data.items.length > 0 && (
        <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
          <Table aria-label="舆情报告列表">
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-56">报告名称</TableHead>
                <TableHead>生成方式</TableHead>
                <TableHead>状态 / 进度</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead>选材数量</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.data.items.map((record) => {
                const active = isActiveRecord(record)
                const failedEmpty =
                  record.status === 'empty' &&
                  record.selection_count > 0 &&
                  record.failed_count === record.selection_count
                const canView = record.report_id !== null && !failedEmpty
                return (
                  <TableRow key={`${record.record_type}:${record.record_id}`}>
                    <TableCell className="whitespace-normal">
                      <div className="max-w-[22rem]">
                        <p className="font-medium [overflow-wrap:anywhere]">
                          {record.name}
                        </p>
                        {record.parent_report_id !== null && (
                          <p className="mt-1 text-xs text-muted-foreground">
                            重试自报告 #{record.parent_report_id}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {recordTriggerLabel(record.trigger)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex min-w-40 flex-col items-start gap-1">
                        <Badge
                          variant={recordStatusVariant(
                            failedEmpty ? 'failed' : record.status,
                          )}
                        >
                          {failedEmpty
                            ? '生成失败'
                            : recordStatusLabels[record.status]}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {active
                            ? `已处理 ${record.processed_count}/${record.selection_count} · 进行中 ${record.active_count}`
                            : record.status === 'completed'
                              ? `已处理 ${record.processed_count}/${record.selection_count}`
                              : `已处理 ${record.processed_count}/${record.selection_count}${record.failed_count > 0 ? ` · 失败 ${record.failed_count}` : ''}`}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatEvidenceDate(record.created_at)}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {record.selection_count} 条
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-2">
                        {(active ||
                          !canView ||
                          [
                            'failed',
                            'configuration_blocked',
                            'cancelled',
                            'interrupted',
                          ].includes(record.status)) && (
                          <Button
                            variant="outline"
                            className="min-h-9"
                            onClick={() => setProgressRecord(record)}
                          >
                            {active ? '查看进度' : '查看处理'}
                          </Button>
                        )}
                        {canView && (
                          <Button
                            variant="outline"
                            className="min-h-9"
                            onClick={() => openReport(record.report_id!)}
                          >
                            查看报告
                          </Button>
                        )}
                        {record.automation_run_id !== null && (
                          <Link
                            className={buttonVariants({
                              variant: 'link',
                              className: 'min-h-9 px-0',
                            })}
                            to={`/automation-runs/${record.automation_run_id}`}
                          >
                            查看自动任务
                          </Link>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t p-4">
            <span className="text-sm text-muted-foreground">
              第 {Math.floor(offset / 20) + 1} 页 · 本页{' '}
              {records.data.items.length} 条
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="min-h-9"
                disabled={offset === 0 || records.isFetching}
                onClick={() => changePage(Math.max(0, offset - 20))}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                className="min-h-9"
                disabled={
                  records.data.next_offset === null || records.isFetching
                }
                onClick={() =>
                  changePage(records.data!.next_offset ?? offset + 20)
                }
              >
                下一页
              </Button>
            </div>
          </div>
        </div>
      )}
      <ReportGenerationWizard
        open={wizardOpen}
        onOpenChange={(next) => {
          setWizardOpen(next)
          if (!next) onClearLegacyQuery?.()
        }}
        initialResultId={initialResultId}
        onStarted={() => {
          setParams((current) => {
            const value = new URLSearchParams(current)
            value.delete('offset')
            return value
          })
          refresh()
        }}
      />
      <ProgressSheet
        record={progressRecord}
        onClose={() => {
          setProgressRecord(null)
          if (initialGenerationId !== null) onClearLegacyQuery?.()
        }}
        onViewReport={openReport}
      />
    </div>
  )
}

function ReportDetailView({
  reportId,
  onBack,
}: {
  reportId: number
  onBack: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [params, setParams] = useSearchParams()
  const resultId = readId(params.get('result'))
  const report = useQuery({
    queryKey: [...TOPIC_REPORTS_QUERY_KEY, 'detail', reportId],
    queryFn: ({ signal }) => fetchTopicReport(reportId, signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveReport(query.state.data.status)
        ? 1000
        : false,
  })
  const record = useQuery({
    queryKey: [...REPORT_RECORDS_QUERY_KEY, 'by-report', reportId],
    queryFn: ({ signal }) => fetchReportRecordByReport(reportId, signal),
    retry: false,
  })
  const reportName = record.data?.name ?? `报告 #${reportId}`
  useEffect(() => {
    const timer = window.setTimeout(
      () => heading.current?.focus({ preventScroll: true }),
      0,
    )
    return () => window.clearTimeout(timer)
  }, [reportId])
  const closeResult = () => {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const key of [
        'result',
        'attempt',
        'attempt_offset',
        'origin_offset',
        'legacy_offset',
      ])
        next.delete(key)
      return next
    })
  }
  return (
    <>
      <div className="mx-auto flex w-full max-w-6xl min-w-0 flex-col gap-8 pb-12">
        <div className="flex flex-col items-start gap-5">
          <Button variant="ghost" onClick={onBack}>
            <ArrowLeft data-icon="inline-start" aria-hidden /> 返回报告列表
          </Button>
          <h2
            ref={heading}
            tabIndex={-1}
            className="font-display text-2xl leading-snug font-semibold wrap-anywhere outline-none sm:text-3xl"
          >
            {reportName}
          </h2>
          {report.data?.finished_at && report.data.status === 'completed' && (
            <time
              dateTime={report.data.finished_at}
              className="text-sm text-muted-foreground"
            >
              {formatEvidenceDate(report.data.finished_at)}
            </time>
          )}
        </div>
        {report.isPending && <p role="status">正在读取报告…</p>}
        {report.isError && (
          <div role="alert" className="space-y-2 text-sm text-destructive">
            <p>{analysisErrorMessage(report.error)}</p>
            <Button variant="outline" onClick={() => void report.refetch()}>
              重试读取报告
            </Button>
          </div>
        )}
        {report.data && <ReadableReport report={report.data} />}
      </div>
      {resultId !== null && (
        <ResultEvidence
          key={resultId}
          resultId={resultId}
          selected={false}
          onSelect={() => undefined}
          onClose={closeResult}
          selectionEnabled={false}
          asSheet
        />
      )}
    </>
  )
}

function LegacyAnalysisJobView({ onBack }: { onBack: () => void }) {
  return (
    <div className="w-full space-y-5">
      <Button variant="outline" className="min-h-10" onClick={onBack}>
        <ArrowLeft aria-hidden /> 返回报告列表
      </Button>
      <ResultsJobs includeReports={false} />
    </div>
  )
}

export function ReportHub() {
  const [params, setParams] = useSearchParams()
  const reportId = readId(params.get('report'))
  const generationId = readId(params.get('generation'))
  const resultId = readId(params.get('result'))
  const jobId = readId(params.get('job'))
  const generate = params.get('generate') === '1'
  const clearLegacyQuery = () => {
    setParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('generate')
      next.delete('generation')
      next.delete('result')
      next.delete('job')
      return next
    })
  }
  if (reportId !== null)
    return (
      <ReportDetailView
        reportId={reportId}
        onBack={() => {
          setParams((current) => {
            const next = new URLSearchParams(current)
            next.delete('report')
            next.delete('report_section')
            next.delete('report_sources_offset')
            next.delete('report_sections_offset')
            next.delete('result')
            next.delete('attempt')
            next.delete('attempt_offset')
            next.delete('origin_offset')
            next.delete('legacy_offset')
            return next
          })
        }}
      />
    )
  if (jobId !== null) return <LegacyAnalysisJobView onBack={clearLegacyQuery} />
  return (
    <ReportList
      initialWizardOpen={generate}
      initialGenerationId={generationId}
      initialResultId={resultId}
      onClearLegacyQuery={clearLegacyQuery}
      onOpenDetail={(id) => {
        setParams((current) => {
          const next = new URLSearchParams(current)
          next.set('report', String(id))
          next.delete('report_section')
          next.delete('report_sources_offset')
          next.delete('report_sections_offset')
          return next
        })
      }}
    />
  )
}
