import { z } from 'zod'

import { getApiBaseUrl } from '@/lib/api/client'
import {
  isoDateSchema,
  SEARCH_PLATFORM_ORDER,
  searchPlatformSchema,
  searchRunSummarySchema,
  searchResultSchema,
  searchTermDiagnosticSchema,
  type SearchPlatform,
  type SearchResultFilter,
} from '@/lib/api/search-runs'

export const SEARCH_BATCHES_QUERY_KEY = ['search-batches'] as const

const activeStatuses = ['queued', 'running'] as const
export const searchBatchStatusSchema = z.enum([
  ...activeStatuses,
  'paused_for_manual_action',
  'completed',
  'completed_with_failures',
  'cancelled',
  'internal_error',
])
const searchBatchItemStatusSchema = z.enum([
  'queued',
  'running',
  'paused_for_manual_action',
  'completed',
  'failed',
  'skipped',
  'cancelled',
])
const positiveSafeIntegerSchema = z
  .number()
  .int()
  .positive()
  .max(Number.MAX_SAFE_INTEGER)
const nonnegativeSafeIntegerSchema = z
  .number()
  .int()
  .nonnegative()
  .max(Number.MAX_SAFE_INTEGER)
// A damaged historical child snapshot must remain visible so its batch can be
// skipped or cancelled. Normal recoverable items are checked against the batch
// snapshot below; standalone run decoding stays unchanged.
const searchBatchRunSummarySchema = searchRunSummarySchema.safeExtend({
  term_count: z.number().int().min(0).max(20),
  current_term_position: nonnegativeSafeIntegerSchema.nullable(),
})
const searchBatchAttemptSchema = z.strictObject({
  attempt_number: z.number().int().min(1),
  run: searchBatchRunSummarySchema,
})
const searchBatchItemSchema = z
  .strictObject({
    position: z.number().int().min(0).max(0),
    platform: searchPlatformSchema,
    status: searchBatchItemStatusSchema,
    attempt_count: nonnegativeSafeIntegerSchema,
    latest_attempt: searchBatchAttemptSchema.nullable(),
    completed_term_count: z.number().int().min(0).max(20),
    remaining_term_count: z.number().int().min(0).max(20),
    next_term_position: z.number().int().min(0).max(19).nullable(),
    checkpoint_basis: z.enum([
      'explicit',
      'legacy_inferred',
      'mixed',
      'unknown',
    ]),
    recovery_available: z.boolean(),
    pause_reason: z.enum(['attempt_failed', 'process_interrupted']).nullable(),
    completion_basis: z.enum(['attempt_success', 'confirmed_terms']).nullable(),
    new_count: nonnegativeSafeIntegerSchema,
    repeated_count: nonnegativeSafeIntegerSchema,
    total_count: nonnegativeSafeIntegerSchema,
    created_at: isoDateSchema,
    started_at: isoDateSchema.nullable(),
    finished_at: isoDateSchema.nullable(),
    incomplete_terms: z.array(searchTermDiagnosticSchema).max(20).optional(),
  })
  .superRefine((value, context) => {
    const runStatus = value.latest_attempt?.run.status
    const runActive = runStatus === 'queued' || runStatus === 'running'
    const runSuccess =
      runStatus === 'completed_with_results' ||
      runStatus === 'completed_empty' ||
      runStatus === 'completed_with_incomplete'
    if (
      (value.latest_attempt === null) !== (value.attempt_count === 0) ||
      (value.latest_attempt !== null &&
        (value.latest_attempt.attempt_number !== value.attempt_count ||
          value.latest_attempt.run.platform !== value.platform))
    ) {
      context.addIssue({ code: 'custom', message: 'invalid batch item' })
    }
    if (
      value.new_count + value.repeated_count !== value.total_count ||
      (value.latest_attempt !== null &&
        value.latest_attempt.run.total_count > value.total_count) ||
      (value.status === 'queued' && (runActive || runSuccess)) ||
      // The run result commits before the runner finalizes its batch item.
      (value.status === 'running' && runStatus === undefined) ||
      (value.status === 'paused_for_manual_action' &&
        (runActive ||
          runSuccess ||
          value.pause_reason === null ||
          (runStatus === undefined &&
            value.pause_reason !== 'process_interrupted'))) ||
      (value.status !== 'paused_for_manual_action' &&
        value.pause_reason !== null) ||
      (value.status === 'completed' &&
        (value.completion_basis === null ||
          (value.completion_basis === 'attempt_success' && !runSuccess) ||
          (value.completion_basis === 'confirmed_terms' &&
            (!value.recovery_available ||
              value.remaining_term_count !== 0 ||
              runStatus === undefined ||
              runActive ||
              runSuccess)))) ||
      (value.status !== 'completed' && value.completion_basis !== null) ||
      (value.status === 'failed' && (runActive || runSuccess)) ||
      (['skipped', 'cancelled'].includes(value.status) && runActive)
    ) {
      context.addIssue({ code: 'custom', message: 'invalid batch item status' })
    }
  })
const summaryShape = {
  id: positiveSafeIntegerSchema,
  monitoring_rule_id: positiveSafeIntegerSchema.nullable(),
  rule_name: z.string(),
  term_count: z.number().int().min(1).max(20),
  platform_count: z.number().int().min(1).max(1),
  terminal_item_count: z.number().int().min(0).max(1),
  max_results_per_term: z.number().int().min(1).max(50),
  max_total_results: z.number().int().min(1).max(50).nullish(),
  status: searchBatchStatusSchema,
  control_revision: nonnegativeSafeIntegerSchema,
  current_item_position: z.number().int().min(0).max(0).nullable(),
  created_at: isoDateSchema,
  started_at: isoDateSchema.nullable(),
  finished_at: isoDateSchema.nullable(),
} as const
const searchBatchSummarySchema = z
  .strictObject(summaryShape)
  .superRefine((value, context) => {
    if (value.terminal_item_count > value.platform_count) {
      context.addIssue({ code: 'custom', message: 'invalid batch counts' })
    }
  })
const searchBatchDetailSchema = z
  .strictObject({
    ...summaryShape,
    terms: z.array(z.string()).min(1).max(20),
    items: z.array(searchBatchItemSchema).min(1).max(1),
  })
  .superRefine((value, context) => {
    const terminalCount = value.items.filter((item) =>
      ['completed', 'failed', 'skipped', 'cancelled'].includes(item.status),
    ).length
    const platformIndexes = value.items.map((item) =>
      SEARCH_PLATFORM_ORDER.indexOf(item.platform),
    )
    const ordered = platformIndexes.every(
      (platformIndex, index) =>
        index === 0 || platformIndex > platformIndexes[index - 1],
    )
    const pausedItems = value.items.filter(
      (item) => item.status === 'paused_for_manual_action',
    )
    const runningItems = value.items.filter((item) => item.status === 'running')
    const allTerminal = terminalCount === value.platform_count
    const validAggregateState =
      (value.status === 'queued' &&
        value.terminal_item_count === 0 &&
        value.items.every((item) => item.status === 'queued') &&
        value.current_item_position === null &&
        value.started_at === null &&
        value.finished_at === null) ||
      (value.status === 'running' &&
        pausedItems.length === 0 &&
        runningItems.length <= 1 &&
        (runningItems.length === 0 ||
          value.current_item_position === runningItems[0]?.position) &&
        value.finished_at === null) ||
      (value.status === 'paused_for_manual_action' &&
        pausedItems.length === 1 &&
        runningItems.length === 0 &&
        value.current_item_position === pausedItems[0]?.position &&
        value.finished_at === null) ||
      (value.status === 'completed' &&
        allTerminal &&
        value.items.every((item) => item.status === 'completed') &&
        value.finished_at !== null) ||
      (value.status === 'completed_with_failures' &&
        allTerminal &&
        (value.items.some((item) => item.status !== 'completed') ||
          value.items.some(
            (item) => (item.incomplete_terms?.length ?? 0) > 0,
          )) &&
        value.finished_at !== null) ||
      (value.status === 'cancelled' &&
        allTerminal &&
        value.finished_at !== null) ||
      (value.status === 'internal_error' &&
        allTerminal &&
        value.finished_at !== null)
    if (
      value.terms.length !== value.term_count ||
      value.items.length !== value.platform_count ||
      terminalCount !== value.terminal_item_count ||
      value.items.some((item, index) => item.position !== index) ||
      new Set(value.items.map((item) => item.platform)).size !==
        value.items.length ||
      value.items.some((item) => {
        const diagnostics = item.incomplete_terms ?? []
        return (
          new Set(diagnostics.map((diagnostic) => diagnostic.position)).size !==
            diagnostics.length ||
          diagnostics.some(
            (diagnostic) =>
              diagnostic.position >= value.terms.length ||
              value.terms[diagnostic.position] !== diagnostic.term,
          )
        )
      }) ||
      !ordered ||
      !validAggregateState ||
      (value.current_item_position !== null &&
        value.current_item_position >= value.platform_count) ||
      value.items.some((item) => {
        if (
          item.completed_term_count + item.remaining_term_count !==
          value.term_count
        )
          return true
        if (
          item.latest_attempt &&
          (item.latest_attempt.run.max_results_per_term !==
            value.max_results_per_term ||
            (item.latest_attempt.run.max_total_results ?? null) !==
              (value.max_total_results ?? null) ||
            (item.recovery_available &&
              (item.latest_attempt.run.term_count !== value.term_count ||
                (item.latest_attempt.run.current_term_position !== null &&
                  item.latest_attempt.run.current_term_position >=
                    value.term_count))))
        )
          return true
        if (!item.recovery_available)
          return (
            item.checkpoint_basis !== 'unknown' ||
            item.completed_term_count !== 0 ||
            item.next_term_position !== null
          )
        return (
          item.next_term_position !==
            (item.remaining_term_count === 0
              ? null
              : item.completed_term_count) ||
          (item.checkpoint_basis === 'unknown') !==
            (item.completed_term_count === 0)
        )
      })
    ) {
      context.addIssue({ code: 'custom', message: 'invalid batch detail' })
    }
  })
const searchBatchListSchema = z.strictObject({
  batches: z.array(searchBatchSummarySchema),
  next_before_id: positiveSafeIntegerSchema.nullable(),
})
const searchBatchAttemptListSchema = z.strictObject({
  attempts: z.array(searchBatchAttemptSchema),
})
const searchBatchResultSchema = searchResultSchema.safeExtend({
  source_run_id: positiveSafeIntegerSchema,
})
const searchBatchResultListSchema = z
  .strictObject({
    results: z.array(searchBatchResultSchema),
    total: nonnegativeSafeIntegerSchema,
    limit: z.number().int().min(1).max(50),
    offset: nonnegativeSafeIntegerSchema,
  })
  .superRefine((value, context) => {
    if (
      value.results.length > value.limit ||
      value.results.length > Math.max(0, value.total - value.offset) ||
      new Set(value.results.map((result) => result.id)).size !==
        value.results.length
    ) {
      context.addIssue({
        code: 'custom',
        message: 'invalid aggregate result page',
      })
    }
  })
const manualPageResponseSchema = z.strictObject({
  outcome: z.enum([
    'opened_existing',
    'opened_homepage',
    'browser_unavailable',
    'navigation_failed',
    'internal_error',
    'cancelled',
  ]),
})
const errorEnvelopeSchema = z.strictObject({
  detail: z.strictObject({ code: z.string(), message: z.string() }),
})

export type SearchBatchStatus = z.infer<typeof searchBatchStatusSchema>
export type SearchBatchItemStatus = z.infer<typeof searchBatchItemStatusSchema>
export type SearchBatchAttempt = z.infer<typeof searchBatchAttemptSchema>
export type SearchBatchItem = z.infer<typeof searchBatchItemSchema>
export type SearchBatchSummary = z.infer<typeof searchBatchSummarySchema>
export type SearchBatchDetail = z.infer<typeof searchBatchDetailSchema>
export type SearchBatchResult = z.infer<typeof searchBatchResultSchema>
export type ManualPageOutcome = z.infer<
  typeof manualPageResponseSchema
>['outcome']
export type SearchBatchControl = {
  item_position: number
  expected_run_id: number | null
  expected_revision: number
}
export type SearchBatchRecovery = Omit<SearchBatchControl, 'item_position'>

type ProductErrorCode =
  | 'search_platform_not_available'
  | 'invalid_request'
  | 'monitoring_rule_not_found'
  | 'monitoring_rule_disabled'
  | 'too_many_search_terms'
  | 'browser_operation_active'
  | 'search_batch_not_found'
  | 'search_batch_not_active'
  | 'search_batch_not_paused'
  | 'search_batch_state_changed'
  | 'search_batch_recovery_unavailable'
  | 'search_batch_item_not_recoverable'
  | 'search_storage_unavailable'

type SearchBatchApiErrorCode =
  | ProductErrorCode
  | 'invalid_response'
  | 'request_failed'
  | 'service_unavailable'

const productErrorContracts: Record<
  ProductErrorCode,
  { status: number; message: string }
> = {
  invalid_request: { status: 422, message: '请求内容不正确。' },
  search_platform_not_available: {
    status: 409,
    message: '当前版本仅支持微博采集，历史内容仍可查看。',
  },
  monitoring_rule_not_found: { status: 404, message: '未找到该监控规则。' },
  monitoring_rule_disabled: {
    status: 409,
    message: '该监控规则已停用，请先启用后再采集。',
  },
  too_many_search_terms: {
    status: 422,
    message: '一次最多采集 20 个搜索词，请拆分监控规则后重试。',
  },
  browser_operation_active: {
    status: 409,
    message: '谷歌浏览器正在执行其他操作，请稍后重试。',
  },
  search_batch_not_found: { status: 404, message: '未找到该批采集任务。' },
  search_batch_not_active: {
    status: 409,
    message: '该批采集任务已经结束，无法取消。',
  },
  search_batch_not_paused: {
    status: 409,
    message: '该批采集任务当前不需要继续操作。',
  },
  search_batch_state_changed: {
    status: 409,
    message: '采集任务状态已变化，请刷新后重试。',
  },
  search_batch_recovery_unavailable: {
    status: 409,
    message: '无法确认可靠的续采位置，请跳过本次采集或取消批次。',
  },
  search_batch_item_not_recoverable: {
    status: 409,
    message: '本次采集当前不能重新处理。',
  },
  search_storage_unavailable: {
    status: 503,
    message: '采集任务暂时无法读取或保存，请稍后重试。',
  },
}

export class SearchBatchApiError extends Error {
  readonly code: SearchBatchApiErrorCode
  readonly status?: number

  constructor(message: string, code: SearchBatchApiErrorCode, status?: number) {
    super(message)
    this.name = 'SearchBatchApiError'
    this.code = code
    this.status = status
  }
}

export function isActiveSearchBatch(status: SearchBatchStatus) {
  return activeStatuses.includes(status as (typeof activeStatuses)[number])
}

async function request(path: string, init: RequestInit) {
  try {
    return await fetch(`${getApiBaseUrl()}${path}`, init)
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new SearchBatchApiError(
      '无法连接本机后端服务，请确认服务已经启动。',
      'service_unavailable',
    )
  }
}

function invalidResponse(status: number) {
  return new SearchBatchApiError(
    '后端返回了无法识别的数据，请重新启动服务后再试。',
    'invalid_response',
    status,
  )
}

async function parseResponse<T>(
  response: Response,
  expectedStatus: number,
  schema: z.ZodType<T>,
) {
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw invalidResponse(response.status)
  }
  if (!response.ok) {
    const parsed = errorEnvelopeSchema.safeParse(payload)
    if (parsed.success && parsed.data.detail.code in productErrorContracts) {
      const code = parsed.data.detail.code as ProductErrorCode
      const contract = productErrorContracts[code]
      if (
        contract.status === response.status &&
        contract.message === parsed.data.detail.message
      ) {
        throw new SearchBatchApiError(contract.message, code, response.status)
      }
      throw invalidResponse(response.status)
    }
    throw new SearchBatchApiError(
      `批量采集请求失败（HTTP ${response.status}）`,
      'request_failed',
      response.status,
    )
  }
  if (response.status !== expectedStatus) throw invalidResponse(response.status)
  const parsed = schema.safeParse(payload)
  if (!parsed.success) throw invalidResponse(response.status)
  return parsed.data
}

export async function startSearchBatch(
  input: {
    monitoring_rule_id: number
    platforms?: SearchPlatform[]
    max_results_per_term: number
    max_total_results?: number
  },
  signal?: AbortSignal,
) {
  if (
    input.platforms !== undefined &&
    (input.platforms.length !== 1 || input.platforms[0] !== 'wb')
  ) {
    throw new SearchBatchApiError('当前版本仅支持微博采集。', 'invalid_request')
  }
  const response = await request('/search-batches', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  })
  return parseResponse(response, 202, searchBatchDetailSchema)
}

export async function fetchSearchBatches(
  signal: AbortSignal,
  options: { limit?: number; beforeId?: number } = {},
) {
  const query = new URLSearchParams({ limit: String(options.limit ?? 20) })
  if (options.beforeId !== undefined) {
    query.set('before_id', String(options.beforeId))
  }
  const response = await request(`/search-batches?${query}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  return parseResponse(response, 200, searchBatchListSchema)
}

export async function fetchSearchBatch(batchId: number, signal: AbortSignal) {
  const response = await request(
    `/search-batches/${encodeURIComponent(String(batchId))}`,
    { headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 200, searchBatchDetailSchema)
}

export async function cancelSearchBatch(
  batchId: number,
  input: { expected_revision: number },
  signal?: AbortSignal,
) {
  const response = await request(
    `/search-batches/${encodeURIComponent(String(batchId))}/cancel`,
    controlRequest(input, signal),
  )
  return parseResponse(response, 202, searchBatchDetailSchema)
}

export async function continueSearchBatch(
  batchId: number,
  input: SearchBatchControl,
  signal?: AbortSignal,
) {
  const response = await request(
    `/search-batches/${encodeURIComponent(String(batchId))}/continue`,
    controlRequest(input, signal),
  )
  return parseResponse(response, 202, searchBatchDetailSchema)
}

function controlRequest(input: object, signal?: AbortSignal): RequestInit {
  return {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  }
}

export async function skipSearchBatchPlatform(
  batchId: number,
  input: SearchBatchControl,
  signal?: AbortSignal,
) {
  const response = await request(
    `/search-batches/${batchId}/skip`,
    controlRequest(input, signal),
  )
  return parseResponse(response, 202, searchBatchDetailSchema)
}

export async function showSearchBatchManualPage(
  batchId: number,
  input: SearchBatchControl,
  signal?: AbortSignal,
) {
  const response = await request(
    `/search-batches/${batchId}/manual-page`,
    controlRequest(input, signal),
  )
  return parseResponse(response, 200, manualPageResponseSchema)
}

export async function recoverSearchBatchPlatform(
  batchId: number,
  position: number,
  input: SearchBatchRecovery,
  signal?: AbortSignal,
) {
  const response = await request(
    `/search-batches/${batchId}/items/${position}/recover`,
    controlRequest(input, signal),
  )
  return parseResponse(response, 202, searchBatchDetailSchema)
}

export async function fetchSearchBatchResults(
  batchId: number,
  position: number,
  kind: SearchResultFilter,
  offset: number,
  signal: AbortSignal,
) {
  const query = new URLSearchParams({
    kind,
    limit: '50',
    offset: String(offset),
  })
  const response = await request(
    `/search-batches/${batchId}/items/${position}/results?${query}`,
    {
      headers: { Accept: 'application/json' },
      signal,
    },
  )
  return parseResponse(response, 200, searchBatchResultListSchema)
}

export async function fetchSearchBatchAttempts(
  batchId: number,
  position: number,
  signal: AbortSignal,
) {
  const response = await request(
    `/search-batches/${encodeURIComponent(String(batchId))}/items/${encodeURIComponent(String(position))}/attempts`,
    { headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 200, searchBatchAttemptListSchema)
}
