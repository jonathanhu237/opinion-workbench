import { z } from 'zod'

import { safeCount, safeId } from '@/lib/api/analysis-shared'
import { getApiBaseUrl } from '@/lib/api/client'
import { searchBatchStatusSchema } from '@/lib/api/search-batches'
import {
  isoDateSchema,
  SEARCH_PLATFORM_ORDER,
  searchPlatformSchema,
} from '@/lib/api/search-runs'
import {
  codePointLength,
  trimRuleValue,
} from '@/lib/monitoring-rule-composition'

export const COLLECTION_SCHEDULES_QUERY_KEY = ['collection-schedules'] as const
export const MAX_COLLECTION_INTERVAL_MINUTES = 43_200
const utcDate = isoDateSchema.refine((value) => /(?:Z|\+00:00)$/.test(value))
const platformsSchema = z
  .array(searchPlatformSchema)
  .min(1)
  .max(5)
  .refine((platforms) => new Set(platforms).size === platforms.length)
export const collectionIntervalSchema = z
  .strictObject({
    value: safeId.max(MAX_COLLECTION_INTERVAL_MINUTES),
    unit: z.enum(['minutes', 'hours']),
  })
  .refine(
    (interval) =>
      interval.value * (interval.unit === 'hours' ? 60 : 1) <=
      MAX_COLLECTION_INTERVAL_MINUTES,
  )

const occurrenceReasonSchema = z.enum([
  'browser_operation_active',
  'browser_unavailable',
  'monitoring_rule_not_found',
  'monitoring_rule_disabled',
  'invalid_monitoring_rule',
  'too_many_search_terms',
  'schedule_changed',
  'storage_unavailable',
  'dispatch_interrupted',
  'offline',
  'clock_jump',
])
const occurrenceSchema = z
  .strictObject({
    id: safeId,
    schedule_id: safeId,
    schedule_revision: safeId,
    due_at: utcDate,
    status: z.enum([
      'claimed',
      'dispatched',
      'skipped',
      'missed',
      'interrupted',
    ]),
    reason: occurrenceReasonSchema.nullable(),
    batch_id: safeId.nullable(),
    batch_status: searchBatchStatusSchema.nullable(),
    missed_count: safeCount,
    missed_until: utcDate.nullable(),
    created_at: utcDate,
    dispatched_at: utcDate.nullable(),
  })
  .superRefine((value, ctx) => {
    const linked = value.batch_id !== null
    const missed = value.status === 'missed'
    const validState =
      (value.status === 'claimed' && !linked && value.reason === null) ||
      (value.status === 'dispatched' && linked && value.reason === null) ||
      (value.status === 'skipped' &&
        !linked &&
        value.reason !== null &&
        !['offline', 'clock_jump', 'dispatch_interrupted'].includes(
          value.reason,
        )) ||
      (missed &&
        !linked &&
        (value.reason === 'offline' || value.reason === 'clock_jump')) ||
      (value.status === 'interrupted' &&
        value.reason === 'dispatch_interrupted')
    if (
      !validState ||
      linked !== (value.batch_status !== null) ||
      linked !== (value.dispatched_at !== null) ||
      (missed
        ? value.missed_count < 1 ||
          value.missed_until === null ||
          Date.parse(value.missed_until) < Date.parse(value.due_at)
        : value.missed_count !== 0 || value.missed_until !== null)
    ) {
      ctx.addIssue({ code: 'custom', message: 'invalid occurrence state' })
    }
  })
const scheduleSchema = z
  .strictObject({
    id: safeId,
    monitoring_rule_id: safeId.nullable(),
    rule_name: z
      .string()
      .refine(
        (value) =>
          value === trimRuleValue(value) &&
          codePointLength(value) >= 1 &&
          codePointLength(value) <= 80,
      ),
    rule_state: z.enum(['enabled', 'disabled', 'deleted', 'invalid']),
    platforms: platformsSchema,
    max_results_per_term: safeId.max(50),
    interval_minutes: safeId.max(MAX_COLLECTION_INTERVAL_MINUTES),
    enabled: z.boolean(),
    revision: safeId,
    anchor_at: utcDate.nullable(),
    next_due_at: utcDate.nullable(),
    created_at: utcDate,
    updated_at: utcDate,
    latest_occurrence: occurrenceSchema.nullable(),
    available: z.boolean(),
  })
  .superRefine((value, ctx) => {
    const indexes = value.platforms.map((platform) =>
      SEARCH_PLATFORM_ORDER.indexOf(platform),
    )
    if (
      indexes.some(
        (index, position) => position > 0 && index <= indexes[position - 1],
      ) ||
      (value.monitoring_rule_id === null) !==
        (value.rule_state === 'deleted') ||
      (value.enabled
        ? value.anchor_at === null ||
          value.next_due_at === null ||
          Date.parse(value.next_due_at) <= Date.parse(value.anchor_at)
        : value.anchor_at !== null || value.next_due_at !== null) ||
      (value.latest_occurrence !== null &&
        (value.latest_occurrence.schedule_id !== value.id ||
          value.latest_occurrence.schedule_revision > value.revision))
    )
      ctx.addIssue({ code: 'custom', message: 'invalid schedule state' })
  })
const createSchema = z.strictObject({
  monitoring_rule_id: safeId,
  platforms: platformsSchema,
  max_results_per_term: safeId.max(50),
  interval: collectionIntervalSchema,
})
const updateSchema = createSchema
  .extend({
    monitoring_rule_id: safeId.nullable(),
    expected_revision: safeId.max(Number.MAX_SAFE_INTEGER - 1),
    enabled: z.boolean(),
  })
  .refine((value) => !value.enabled || value.monitoring_rule_id !== null)

export type CollectionSchedule = z.infer<typeof scheduleSchema>
export type CollectionOccurrence = z.infer<typeof occurrenceSchema>
export type CollectionOccurrenceReason = z.infer<typeof occurrenceReasonSchema>
export type CreateCollectionSchedule = z.infer<typeof createSchema>
export type UpdateCollectionSchedule = z.infer<typeof updateSchema>
export type CollectionSchedulePage = {
  schedules: CollectionSchedule[]
  next_before_id: number | null
}

export const SCHEDULE_ERROR_CONTRACTS = {
  collection_schedule_not_found: {
    status: 404,
    message: '未找到定时采集计划。',
  },
  collection_schedule_changed: {
    status: 409,
    message: '定时采集计划已更新，请刷新后重试。',
  },
  invalid_collection_interval: {
    status: 422,
    message: '采集间隔须为 1 至 43200 个整分钟（最多 30 天）。',
  },
  invalid_collection_schedule: {
    status: 422,
    message: '定时采集配置不正确，请检查监控规则和平台。',
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
  collection_schedule_storage_unavailable: {
    status: 503,
    message: '定时采集数据暂时无法读取或保存，请稍后重试。',
  },
  collection_schedule_unavailable: {
    status: 503,
    message: '定时采集服务暂时不可用，请稍后重试。',
  },
  invalid_request: { status: 422, message: '请求内容不正确。' },
  ai_request_forbidden: {
    status: 403,
    message: '请从本机应用页面操作 AI 配置。',
  },
  ai_json_required: { status: 415, message: '请使用 JSON 提交 AI 配置。' },
} as const
type ProductCode = keyof typeof SCHEDULE_ERROR_CONTRACTS
type ErrorCode = ProductCode | 'invalid_response' | 'service_unavailable'
export class CollectionScheduleApiError extends Error {
  override name = 'CollectionScheduleApiError'
  readonly code: ErrorCode
  readonly status?: number
  constructor(code: ErrorCode, status?: number) {
    super(
      code === 'invalid_response'
        ? '定时采集接口返回的数据与当前应用不匹配。'
        : code === 'service_unavailable'
          ? '无法连接本机后端服务，请确认服务已经启动。'
          : SCHEDULE_ERROR_CONTRACTS[code].message,
    )
    this.code = code
    this.status = status
  }
}
export function scheduleErrorMessage(error: unknown) {
  return error instanceof CollectionScheduleApiError
    ? error.message
    : '定时采集操作未完成，请稍后重试。'
}
function isProductCode(value: string): value is ProductCode {
  return Object.hasOwn(SCHEDULE_ERROR_CONTRACTS, value)
}
function decode<T>(
  schema: z.ZodType<T>,
  value: unknown,
  code: ErrorCode = 'invalid_response',
): T {
  const result = schema.safeParse(value)
  if (!result.success) throw new CollectionScheduleApiError(code)
  return result.data
}
async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit,
  status = 200,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}/collection-schedules${path}`, {
      ...init,
      cache: 'no-store',
      redirect: 'error',
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch (error) {
    if (
      (error instanceof Error || error instanceof DOMException) &&
      error.name === 'AbortError'
    )
      throw error
    throw new CollectionScheduleApiError('service_unavailable')
  }
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new CollectionScheduleApiError('invalid_response', response.status)
  }
  if (!response.ok) {
    const parsed = z
      .strictObject({
        detail: z.strictObject({ code: z.string(), message: z.string() }),
      })
      .safeParse(value)
    if (parsed.success && isProductCode(parsed.data.detail.code)) {
      const { code, message } = parsed.data.detail
      if (
        SCHEDULE_ERROR_CONTRACTS[code].status === response.status &&
        SCHEDULE_ERROR_CONTRACTS[code].message === message
      )
        throw new CollectionScheduleApiError(code, response.status)
    }
    throw new CollectionScheduleApiError('invalid_response', response.status)
  }
  if (response.status !== status)
    throw new CollectionScheduleApiError('invalid_response', response.status)
  return decode(schema, value)
}
type PageOptions = { limit?: number; beforeId?: number }
function pageQuery({ limit = 50, beforeId }: PageOptions) {
  decode(safeId.max(100), limit, 'invalid_request')
  if (beforeId !== undefined) decode(safeId, beforeId, 'invalid_request')
  const query = new URLSearchParams({ limit: String(limit) })
  if (beforeId !== undefined) query.set('before_id', String(beforeId))
  return { query, limit, beforeId }
}
function checkCursor<T extends { id: number }>(
  items: T[],
  next: number | null,
  limit: number,
  beforeId?: number,
) {
  if (
    items.length > limit ||
    items.some(
      (item, index) =>
        (beforeId !== undefined && item.id >= beforeId) ||
        (index > 0 && item.id >= items[index - 1].id),
    ) ||
    (next !== null && (items.length !== limit || next !== items.at(-1)?.id))
  )
    throw new CollectionScheduleApiError('invalid_response')
}
export async function fetchCollectionSchedules(
  signal: AbortSignal,
  options: PageOptions = {},
) {
  const { query, limit, beforeId } = pageQuery(options)
  const page = await request(
    `?${query}`,
    z.strictObject({
      schedules: z.array(scheduleSchema).max(100),
      next_before_id: safeId.nullable(),
    }),
    { signal },
  )
  checkCursor(page.schedules, page.next_before_id, limit, beforeId)
  return page
}
export async function fetchCollectionSchedule(id: number, signal: AbortSignal) {
  decode(safeId, id, 'invalid_request')
  const schedule = await request(`/${id}`, scheduleSchema, { signal })
  if (schedule.id !== id)
    throw new CollectionScheduleApiError('invalid_response')
  return schedule
}
export async function fetchCollectionOccurrences(
  id: number,
  signal: AbortSignal,
  options: PageOptions = {},
) {
  decode(safeId, id, 'invalid_request')
  const { query, limit, beforeId } = pageQuery(options)
  const page = await request(
    `/${id}/occurrences?${query}`,
    z.strictObject({
      occurrences: z.array(occurrenceSchema).max(100),
      next_before_id: safeId.nullable(),
    }),
    { signal },
  )
  checkCursor(page.occurrences, page.next_before_id, limit, beforeId)
  if (page.occurrences.some((item) => item.schedule_id !== id))
    throw new CollectionScheduleApiError('invalid_response')
  return page
}
function mutation(
  method: 'POST' | 'PUT',
  value: unknown,
  signal?: AbortSignal,
): RequestInit {
  return {
    method,
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  }
}
export async function createCollectionSchedule(
  input: CreateCollectionSchedule,
  signal?: AbortSignal,
) {
  decode(
    collectionIntervalSchema,
    input.interval,
    'invalid_collection_interval',
  )
  decode(createSchema, input, 'invalid_collection_schedule')
  const schedule = await request(
    '',
    scheduleSchema,
    mutation('POST', input, signal),
    201,
  )
  if (schedule.enabled) throw new CollectionScheduleApiError('invalid_response')
  return schedule
}
export async function updateCollectionSchedule(
  id: number,
  input: UpdateCollectionSchedule,
  signal?: AbortSignal,
) {
  decode(safeId, id, 'invalid_request')
  decode(
    collectionIntervalSchema,
    input.interval,
    'invalid_collection_interval',
  )
  decode(updateSchema, input, 'invalid_collection_schedule')
  const schedule = await request(
    `/${id}`,
    scheduleSchema,
    mutation('PUT', input, signal),
  )
  if (
    schedule.id !== id ||
    schedule.revision !== input.expected_revision + 1 ||
    schedule.enabled !== input.enabled
  )
    throw new CollectionScheduleApiError('invalid_response')
  return schedule
}

export function scheduleUpdatePayload(
  schedule: CollectionSchedule,
  enabled = schedule.enabled,
): UpdateCollectionSchedule {
  return {
    monitoring_rule_id: schedule.monitoring_rule_id,
    platforms: schedule.platforms,
    max_results_per_term: schedule.max_results_per_term,
    interval: { value: schedule.interval_minutes, unit: 'minutes' },
    expected_revision: schedule.revision,
    enabled,
  }
}
