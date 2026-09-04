import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
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
} from '@/lib/api/analysis-settings'
import { analysisErrorMessage } from '@/lib/api/analysis-shared'
import {
  CONTENT_ANALYSES_QUERY_KEY,
  CONTENT_ANALYSIS_JOBS_QUERY_KEY,
} from '@/lib/api/content-analyses'
import {
  fetchResults,
  isActiveResult,
  readId,
  readOffset,
  RESULT_PAGE_SIZE,
  RESULTS_QUERY_KEY,
  type SharedResult,
} from '@/lib/api/results'
import {
  fetchReportGenerations,
  GENERATIONS_QUERY_KEY,
  isActiveGeneration,
} from '@/lib/api/report-generations'
import { ResultEvidence } from '@/routes/results-evidence'
import {
  ResultSourceLink,
  ResultsPagination,
  useResultSourceControls,
} from '@/routes/results-presenters'
import {
  LegacyReportRecord,
  ReportGenerations,
} from '@/routes/report-generations'
import { ReportSelectionActions } from '@/routes/report-selection-actions'
import { ResultsJobs } from '@/routes/results-jobs'
import { isReportRecordContext } from '@/lib/report-route-state'
import { searchPlatformPresenters } from '@/routes/search-run-presenters'

const selectionDraftKey = 'longtian:report-selection-draft:v1'

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
    // Session storage is an enhancement; in-memory selection remains usable.
  }
}

const analysisStateLabels: Record<string, string> = {
  never_started: '待分析',
  pending_new: '待分析',
  completed: '已总结',
  legacy_completed: '已总结',
  queued: '处理中',
  acquiring: '处理中',
  analysing: '处理中',
  failed: '分析失败',
  input_incomplete: '分析失败',
  unsupported: '分析失败',
  cancelled: '分析失败',
  interrupted: '分析失败',
  legacy_attempted: '分析失败',
}

function resultStatus(result: SharedResult) {
  return analysisStateLabels[result.analysis_state] ?? '待分析'
}

function resultStatusVariant(result: SharedResult) {
  if (isActiveResult(result)) return 'outline' as const
  if (
    result.analysis_state === 'completed' ||
    result.analysis_state === 'legacy_completed'
  ) {
    return 'secondary' as const
  }
  if (
    result.analysis_state === 'failed' ||
    result.analysis_state === 'input_incomplete' ||
    result.analysis_state === 'unsupported' ||
    result.analysis_state === 'cancelled' ||
    result.analysis_state === 'interrupted' ||
    result.analysis_state === 'legacy_attempted'
  )
    return 'destructive' as const
  return 'outline' as const
}

function materialLabels(result: SharedResult) {
  if (result.material) {
    const material = result.material
    const labels = [material.text_available ? '正文' : '正文缺失']
    if (material.inventory_complete) {
      labels.push(
        `图片 ${material.image_count}`,
        `视频 ${material.video_count}`,
      )
    } else {
      labels.push(
        material.image_count > 0
          ? `图片 ${material.image_count}`
          : '图片待补全',
        material.video_count > 0
          ? `视频 ${material.video_count}`
          : '视频待补全',
      )
    }
    if (material.missing) labels.push('有缺失')
    return labels
  }
  const type = result.source.content_type.toLowerCase()
  const labels = ['正文（搜索摘要）']
  if (type.includes('video')) labels.push('视频待补全')
  else if (type.includes('image') || type.includes('photo'))
    labels.push('图片待补全')
  else if (type.includes('audio')) labels.push('音频待补全')
  else labels.push('图片/视频待补全')
  return labels
}

function summaryText(result: SharedResult) {
  const title = result.source.title.trim()
  const snippet = result.source.snippet.trim()
  if (title && snippet && title !== snippet) return `${title} · ${snippet}`
  return title || snippet || `内容 #${result.id}`
}

function ContentLibrary({
  actions,
  selectedIds,
  onSelectionChange,
  onOpen,
}: {
  actions: ReactNode
  selectedIds: number[]
  onSelectionChange: (ids: number[]) => void
  onOpen: (id: number) => void
}) {
  const [params, setParams] = useSearchParams()
  const controls = useResultSourceControls()
  const offset = readOffset(params.get('offset'))
  const results = useQuery({
    queryKey: [...RESULTS_QUERY_KEY, 'report-library', offset],
    queryFn: ({ signal }) => fetchResults({ offset }, signal),
    retry: false,
    refetchInterval: (query) => (query.state.data?.active_count ? 1000 : false),
  })
  const items = results.data?.items ?? []
  const selectable = items.filter((result) => !isActiveResult(result))
  useEffect(() => {
    const activeIds = new Set(
      items
        .filter((result) => isActiveResult(result))
        .map((result) => result.id),
    )
    const next = selectedIds.filter((id) => !activeIds.has(id))
    if (next.length !== selectedIds.length) onSelectionChange(next)
  }, [items, onSelectionChange, selectedIds])
  const allSelected =
    selectable.length > 0 &&
    selectable.every((result) => selectedIds.includes(result.id))
  const someSelected = selectable.some((result) =>
    selectedIds.includes(result.id),
  )
  const toggle = (id: number, checked: boolean) => {
    onSelectionChange(
      checked
        ? [...selectedIds, id]
        : selectedIds.filter((selectedId) => selectedId !== id),
    )
  }
  const togglePage = (checked: boolean) => {
    const pageIds = new Set(selectable.map((result) => result.id))
    onSelectionChange(
      checked
        ? [...new Set([...selectedIds, ...pageIds])]
        : selectedIds.filter((id) => !pageIds.has(id)),
    )
  }
  const goPage = (nextOffset: number) => {
    const next = new URLSearchParams(params)
    if (nextOffset === 0) next.delete('offset')
    else next.set('offset', String(nextOffset))
    setParams(next)
  }
  return (
    <Card className="min-w-0">
      <CardHeader className="min-w-0 border-b sm:grid-cols-[minmax(0,1fr)_auto] sm:gap-x-4">
        <div className="min-w-0">
          <CardTitle>
            <h2 className="font-display text-xl">舆情内容</h2>
          </CardTitle>
          <CardDescription className="mt-1 flex min-w-0 flex-col gap-1">
            <span>
              内容库是报告选材来源，按最新入库优先展示；暂不提供筛选。
            </span>
            <span className="text-xs sm:hidden">
              共 {results.data?.total ?? '—'} 条 · 每页 {RESULT_PAGE_SIZE} 条
            </span>
          </CardDescription>
        </div>
        <span className="hidden self-start text-sm whitespace-nowrap text-muted-foreground sm:block">
          共 {results.data?.total ?? '—'} 条 · 每页 {RESULT_PAGE_SIZE} 条
        </span>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-4">
        {actions}
        {results.isPending && <p role="status">正在读取舆情内容…</p>}
        {results.isError && (
          <p role="alert" className="text-sm text-destructive">
            {analysisErrorMessage(results.error)}
          </p>
        )}
        {results.data?.items.length === 0 && (
          <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            还没有舆情内容。请先到“舆情爬取”完成一次搜索。
          </p>
        )}
        {results.data && results.data.items.length > 0 && (
          <>
            <Table aria-label="舆情内容表格">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <Checkbox
                      aria-label="选择当前页"
                      checked={allSelected}
                      indeterminate={someSelected && !allSelected}
                      disabled={selectable.length === 0}
                      onCheckedChange={(checked) =>
                        togglePage(checked === true)
                      }
                    />
                  </TableHead>
                  <TableHead>平台</TableHead>
                  <TableHead className="min-w-64">内容摘要</TableHead>
                  <TableHead>素材</TableHead>
                  <TableHead>发布时间</TableHead>
                  <TableHead>分析状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((result) => (
                  <TableRow
                    key={result.id}
                    data-state={
                      selectedIds.includes(result.id) ? 'selected' : undefined
                    }
                  >
                    <TableCell>
                      <Checkbox
                        aria-label={`选择内容：${result.source.title}`}
                        checked={selectedIds.includes(result.id)}
                        disabled={isActiveResult(result)}
                        onCheckedChange={(checked) =>
                          toggle(result.id, checked === true)
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {searchPlatformPresenters[result.source.platform].label}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[28rem] whitespace-normal">
                      <p className="line-clamp-2 font-medium [overflow-wrap:anywhere]">
                        {summaryText(result)}
                      </p>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1 text-sm">
                        {materialLabels(result).map((label) => (
                          <span key={label}>{label}</span>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {result.source.published_at_text || '未知'}
                    </TableCell>
                    <TableCell>
                      <Badge variant={resultStatusVariant(result)}>
                        {resultStatus(result)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          variant="outline"
                          className="min-h-9"
                          onClick={() => onOpen(result.id)}
                          aria-label={`查看内容详情：${result.source.title}`}
                        >
                          查看详情
                        </Button>
                        <ResultSourceLink
                          source={result.source}
                          controls={controls}
                          disabled={isActiveResult(result)}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <ResultsPagination
              label="舆情内容"
              offset={offset}
              limit={RESULT_PAGE_SIZE}
              total={results.data.total}
              onChange={goPage}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function Results({ mode }: { mode?: 'compose' | 'records' } = {}) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const resultId = readId(params.get('result'))
  const legacyReportId = readId(params.get('report'))
  const requestedJobId = readId(params.get('job'))
  const resultControls = useResultSourceControls()
  const resultFocus = useRef<HTMLElement | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>(readSelectionDraft)
  const inferredMode = isReportRecordContext(params) ? 'records' : 'compose'
  const activeMode = mode ?? inferredMode
  const settings = useQuery({
    queryKey: ANALYSIS_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAnalysisSettings(signal),
    retry: false,
  })
  const provider = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    retry: false,
  })
  const activeGenerations = useQuery({
    queryKey: [...GENERATIONS_QUERY_KEY, 'list'],
    queryFn: ({ signal }) => fetchReportGenerations(signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => isActiveGeneration(item.status))
        ? 1000
        : false,
  })
  const active = Boolean(
    activeGenerations.data?.items.some((item) =>
      isActiveGeneration(item.status),
    ),
  )
  useEffect(() => {
    writeSelectionDraft(selectedIds)
  }, [selectedIds])
  const openResult = (id: number) => {
    resultFocus.current = document.activeElement as HTMLElement | null
    setParams((current) => {
      const next = new URLSearchParams(current)
      next.set('result', String(id))
      for (const key of [
        'attempt',
        'attempt_offset',
        'origin_offset',
        'legacy_offset',
      ])
        next.delete(key)
      return next
    })
  }
  const closeResult = () => {
    setParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('result')
      next.delete('attempt')
      return next
    })
    resultFocus.current?.focus()
  }
  const refresh = () => {
    void client.invalidateQueries({ queryKey: RESULTS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: GENERATIONS_QUERY_KEY })
    void client.invalidateQueries({ queryKey: CONTENT_ANALYSES_QUERY_KEY })
    void client.invalidateQueries({ queryKey: CONTENT_ANALYSIS_JOBS_QUERY_KEY })
    void settings.refetch()
    void provider.refetch()
  }
  return (
    <div className="space-y-5">
      <section aria-label="报告操作" className="flex justify-end">
        <Button
          variant="outline"
          className="min-h-10 shrink-0 self-start sm:self-auto"
          onClick={refresh}
          disabled={settings.isFetching || provider.isFetching}
        >
          <RefreshCw aria-hidden />
          刷新
        </Button>
      </section>
      {activeMode === 'compose' ? (
        <div className="space-y-5">
          {(settings.isError || provider.isError) && (
            <p role="alert" className="text-sm text-destructive">
              无法读取报告所需的提示词或模型配置，请刷新后重试。
            </p>
          )}
          <ContentLibrary
            actions={
              <ReportSelectionActions
                selectedIds={selectedIds}
                onSelectionChange={setSelectedIds}
                provider={provider.data}
                settings={settings.data}
                active={active}
                onStarted={(generation) => {
                  setSelectedIds([])
                  navigate({
                    pathname: '/reports/history',
                    search: `?generation=${generation.id}`,
                  })
                  void client.invalidateQueries({
                    queryKey: GENERATIONS_QUERY_KEY,
                  })
                  void client.invalidateQueries({
                    queryKey: RESULTS_QUERY_KEY,
                  })
                }}
              />
            }
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
            onOpen={openResult}
          />
        </div>
      ) : (
        <div>
          <ReportGenerations
            selectedId={readId(params.get('generation'))}
            autoSelectLatest={
              legacyReportId === null && requestedJobId === null
            }
            onSelect={(id) => {
              setParams((current) => {
                const next = new URLSearchParams(current)
                if (id === null) next.delete('generation')
                else next.set('generation', String(id))
                next.delete('view')
                return next
              })
            }}
            onSelectReport={(id) => {
              setParams((current) => {
                const next = new URLSearchParams(current)
                next.delete('generation')
                next.set('report', String(id))
                next.delete('view')
                return next
              })
            }}
          />
          {legacyReportId !== null && (
            <div className="mt-5">
              <LegacyReportRecord
                key={legacyReportId}
                reportId={legacyReportId}
              />
            </div>
          )}
          <div className="mt-5">
            <ResultsJobs
              settings={settings.data}
              provider={provider.data}
              includeReports={false}
            />
          </div>
        </div>
      )}
      {resultId !== null && (
        <ResultEvidence
          key={resultId}
          resultId={resultId}
          controls={resultControls}
          onSelect={(result) =>
            setSelectedIds((ids) =>
              ids.includes(result.id) ? ids : [...ids, result.id],
            )
          }
          selected={selectedIds.includes(resultId)}
          onClose={closeResult}
          asSheet
        />
      )}
    </div>
  )
}

export function ReportGeneration() {
  return <Results mode="compose" />
}

export function ReportRecords() {
  return <Results mode="records" />
}
