import { z } from 'zod'

import { getApiBaseUrl } from '@/lib/api/client'
import {
  isoDateSchema,
  SEARCH_PLATFORM_ORDER,
  searchPlatformSchema,
  searchRunSummarySchema,
  type SearchPlatform,
} from '@/lib/api/search-runs'

export const SEARCH_BATCHES_QUERY_KEY = ['search-batches'] as const

const activeStatuses = ['queued', 'running'] as const
const searchBatchStatusSchema = z.enum([
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
const searchBatchAttemptSchema = z.strictObject({
  attempt_number: z.number().int().min(1),
  run: searchRunSummarySchema,
})
const searchBatchItemSchema = z
  .strictObject({
    position: z.number().int().min(0).max(4),
    platform: searchPlatformSchema,
    status: searchBatchItemStatusSchema,
    attempt_count: nonnegativeSafeIntegerSchema,
    latest_attempt: searchBatchAttemptSchema.nullable(),
    created_at: isoDateSchema,
    started_at: isoDateSchema.nullable(),
    finished_at: isoDateSchema.nullable(),
  })
  .superRefine((value, context) => {
    const runStatus = value.latest_attempt?.run.status
    if (
      (value.latest_attempt === null) !== (value.attempt_count === 0) ||
      (value.latest_attempt !== null &&
        (value.latest_attempt.attempt_number !== value.attempt_count ||
          value.latest_attempt.run.platform !== value.platform))
    ) {
      context.addIssue({ code: 'custom', message: 'invalid batch item' })
    }
    if (
      (value.status === 'queued' && value.latest_attempt !== null) ||
      (value.status === 'running' &&
        runStatus !== 'queued' &&
        runStatus !== 'running') ||
      (value.status === 'paused_for_manual_action' &&
        runStatus !== 'manual_challenge_required') ||
      (value.status === 'completed' &&
        runStatus !== 'completed_with_results' &&
        runStatus !== 'completed_empty') ||
      (value.status === 'failed' &&
        runStatus !== undefined &&
        (runStatus === 'queued' ||
          runStatus === 'running' ||
          runStatus === 'completed_with_results' ||
          runStatus === 'completed_empty' ||
          runStatus === 'manual_challenge_required'))
    ) {
      context.addIssue({ code: 'custom', message: 'invalid batch item status' })
    }
  })
const summaryShape = {
  id: positiveSafeIntegerSchema,
  monitoring_rule_id: positiveSafeIntegerSchema.nullable(),
  rule_name: z.string(),
  term_count: z.number().int().min(1).max(20),
  platform_count: z.number().int().min(1).max(5),
  terminal_item_count: z.number().int().min(0).max(5),
  max_results_per_term: z.number().int().min(1).max(50),
  status: searchBatchStatusSchema,
  current_item_position: z.number().int().min(0).max(4).nullable(),
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
    items: z.array(searchBatchItemSchema).min(1).max(5),
  })
  .superRefine((value, context) => {
    const terminalCount = value.items.filter((item) =>
      ['completed', 'failed', 'cancelled'].includes(item.status),
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
        value.finished_at === null) ||
      (value.status === 'paused_for_manual_action' &&
        pausedItems.length === 1 &&
        value.current_item_position === pausedItems[0]?.position &&
        value.finished_at === null) ||
      (value.status === 'completed' &&
        allTerminal &&
        value.items.every((item) => item.status === 'completed') &&
        value.finished_at !== null) ||
      (value.status === 'completed_with_failures' &&
        allTerminal &&
        value.items.some((item) => item.status !== 'completed') &&
        value.finished_at !== null) ||
      (value.status === 'cancelled' && value.finished_at !== null) ||
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
      !ordered ||
      !validAggregateState
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
const errorEnvelopeSchema = z.strictObject({
  detail: z.strictObject({ code: z.string(), message: z.string() }),
})

export type SearchBatchStatus = z.infer<typeof searchBatchStatusSchema>
export type SearchBatchItemStatus = z.infer<typeof searchBatchItemStatusSchema>
export type SearchBatchAttempt = z.infer<typeof searchBatchAttemptSchema>
export type SearchBatchItem = z.infer<typeof searchBatchItemSchema>
export type SearchBatchSummary = z.infer<typeof searchBatchSummarySchema>
export type SearchBatchDetail = z.infer<typeof searchBatchDetailSchema>

type ProductErrorCode =
  | 'invalid_request'
  | 'monitoring_rule_not_found'
  | 'monitoring_rule_disabled'
  | 'too_many_search_terms'
  | 'browser_operation_active'
  | 'search_batch_not_found'
  | 'search_batch_not_active'
  | 'search_batch_not_paused'
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
    platforms: SearchPlatform[]
    max_results_per_term: number
  },
  signal?: AbortSignal,
) {
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

export async function cancelSearchBatch(batchId: number, signal?: AbortSignal) {
  const response = await request(
    `/search-batches/${encodeURIComponent(String(batchId))}/cancel`,
    { method: 'POST', headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 202, searchBatchDetailSchema)
}

export async function continueSearchBatch(
  batchId: number,
  signal?: AbortSignal,
) {
  const response = await request(
    `/search-batches/${encodeURIComponent(String(batchId))}/continue`,
    { method: 'POST', headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 202, searchBatchDetailSchema)
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
