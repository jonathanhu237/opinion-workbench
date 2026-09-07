import { z } from 'zod'

import { safeCount, safeId } from '@/lib/api/analysis-shared'
import { automationScheduleSchema } from '@/lib/api/automation-workflows'
import { getApiBaseUrl } from '@/lib/api/client'
import { isoDateSchema, searchPlatformSchema } from '@/lib/api/search-runs'

export const WORKBENCH_QUERY_KEY = ['workbench'] as const

const utcDateSchema = isoDateSchema.refine((value) =>
  /(?:Z|\+00:00)$/u.test(value),
)
const attentionStatusSchema = z.enum([
  'invalid',
  'skipped',
  'missed',
  'interrupted',
  'paused_for_manual_action',
  'completed_with_failures',
  'internal_error',
  'configuration_blocked',
  'failed',
  'unsuccessful_members',
  'previous_run_active',
  'configuration_unavailable',
])
const attentionReasonSchema = z.enum([
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
  'attempt_failed',
  'process_interrupted',
  'login_required',
  'manual_challenge_required',
  'platform_blocked_or_rate_limited',
  'structure_changed',
  'timed_out',
  'browser_unavailable_run',
  'internal_error',
  'configuration_blocked',
  'interrupted',
  'unsuccessful_members',
])
const attentionSchema = z.strictObject({
  kind: z.enum([
    'automation_task',
    'automation_run',
    'collection_batch',
    'initial_analysis',
    'report',
  ]),
  severity: z.enum(['action_required', 'warning', 'error']),
  status: attentionStatusSchema,
  reason: attentionReasonSchema.nullable(),
  resource_id: safeId,
  owner: z.string().trim().min(1).max(80),
  occurred_at: utcDateSchema,
  unsuccessful_count: safeCount.nullable(),
})
const collectionActivitySchema = z
  .strictObject({
    id: safeId,
    status: z.enum(['queued', 'running', 'paused_for_manual_action']),
    rule_name: z.string().trim().min(1).max(80),
    current_platform: searchPlatformSchema.nullable(),
    current_item_position: safeCount.nullable(),
    completed_item_count: safeCount,
    item_count: safeCount,
    created_at: utcDateSchema,
    started_at: utcDateSchema.nullable(),
  })
  .refine(
    (value) =>
      value.completed_item_count <= value.item_count &&
      (value.current_item_position === null ||
        value.current_item_position < value.item_count),
  )
const analysisActivitySchema = z
  .strictObject({
    id: safeId,
    status: z.enum(['queued', 'running']),
    total_count: safeCount,
    completed_count: safeCount,
    unsuccessful_count: safeCount,
    created_at: utcDateSchema,
    started_at: utcDateSchema.nullable(),
  })
  .refine(
    (value) =>
      value.completed_count + value.unsuccessful_count <= value.total_count,
  )
const reportActivitySchema = z
  .strictObject({
    id: safeId,
    status: z.enum(['queued', 'judging', 'composing']),
    total_count: safeCount,
    completed_count: safeCount,
    failed_count: safeCount,
    created_at: utcDateSchema,
    started_at: utcDateSchema.nullable(),
  })
  .refine(
    (value) => value.completed_count + value.failed_count <= value.total_count,
  )
const automationActivitySchema = z.strictObject({
  run_id: safeId,
  task_id: safeId,
  task_name: z.string().trim().min(1).max(80),
  status: z.enum(['queued', 'collecting', 'analysing', 'reporting']),
  active_stage: z
    .enum(['collection', 'initial_analysis', 'topic_report'])
    .nullable(),
  created_at: utcDateSchema,
  started_at: utcDateSchema.nullable(),
})
const coverageSchema = z
  .strictObject({
    total: safeCount,
    ready: safeCount,
    unavailable: safeCount,
    pending: safeCount,
    judging: safeCount,
    relevant: safeCount,
    irrelevant: safeCount,
    uncertain: safeCount,
    failed: safeCount,
    cancelled: safeCount,
    interrupted: safeCount,
  })
  .refine(
    (value) =>
      value.total === value.ready + value.unavailable &&
      value.ready ===
        value.pending +
          value.judging +
          value.relevant +
          value.irrelevant +
          value.uncertain +
          value.failed +
          value.cancelled +
          value.interrupted,
  )
const latestReportSchema = z
  .strictObject({
    id: safeId,
    status: z.enum(['completed', 'empty']),
    created_at: utcDateSchema,
    finished_at: utcDateSchema,
    overview: z.string().trim().min(1).max(2000).nullable(),
    empty_reason: z
      .enum(['no_ready_sources', 'no_relevant_sources', 'text_insufficient'])
      .nullable(),
    coverage: coverageSchema,
  })
  .refine((value) =>
    value.status === 'completed'
      ? value.overview !== null && value.empty_reason === null
      : value.overview === null && value.empty_reason !== null,
  )

export const workbenchSnapshotSchema = z.strictObject({
  observed_at: utcDateSchema,
  attention: z.array(attentionSchema).max(100),
  activity: z.strictObject({
    automation: automationActivitySchema.nullable(),
    collection: collectionActivitySchema.nullable(),
    initial_analysis: analysisActivitySchema.nullable(),
    report: reportActivitySchema.nullable(),
  }),
  next_automation: z
    .strictObject({
      id: safeId,
      name: z.string().trim().min(1).max(80),
      rule_name: z.string().trim().min(1).max(80),
      due_at: utcDateSchema,
      schedule: automationScheduleSchema,
    })
    .nullable(),
  latest_report: latestReportSchema.nullable(),
})

export type WorkbenchSnapshot = z.infer<typeof workbenchSnapshotSchema>
export type WorkbenchAttention = z.infer<typeof attentionSchema>
export type WorkbenchCollectionActivity = z.infer<
  typeof collectionActivitySchema
>
export type WorkbenchAutomationActivity = z.infer<
  typeof automationActivitySchema
>
export type WorkbenchAnalysisActivity = z.infer<typeof analysisActivitySchema>
export type WorkbenchReportActivity = z.infer<typeof reportActivitySchema>

const ERROR_CONTRACTS = {
  workbench_storage_unavailable: {
    status: 503,
    message: '工作台数据暂时无法读取，请稍后重试。',
  },
  workbench_unavailable: {
    status: 503,
    message: '工作台服务暂时不可用，请稍后重试。',
  },
} as const

type ProductErrorCode = keyof typeof ERROR_CONTRACTS
type WorkbenchErrorCode =
  ProductErrorCode | 'invalid_response' | 'service_unavailable'

export class WorkbenchApiError extends Error {
  override name = 'WorkbenchApiError'
  readonly code: WorkbenchErrorCode
  readonly status?: number

  constructor(code: WorkbenchErrorCode, status?: number) {
    super(
      code === 'invalid_response'
        ? '工作台接口返回的数据与当前应用不匹配。'
        : code === 'service_unavailable'
          ? '无法连接本机后端服务，请确认服务已经启动。'
          : ERROR_CONTRACTS[code].message,
    )
    this.code = code
    this.status = status
  }
}

function isProductErrorCode(value: string): value is ProductErrorCode {
  return Object.hasOwn(ERROR_CONTRACTS, value)
}

export async function fetchWorkbench(
  signal: AbortSignal,
): Promise<WorkbenchSnapshot> {
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}/workbench`, {
      cache: 'no-store',
      redirect: 'error',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch (error) {
    if (
      (error instanceof Error || error instanceof DOMException) &&
      error.name === 'AbortError'
    ) {
      throw error
    }
    throw new WorkbenchApiError('service_unavailable')
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new WorkbenchApiError('invalid_response', response.status)
  }

  if (!response.ok) {
    const result = z
      .strictObject({
        detail: z.strictObject({ code: z.string(), message: z.string() }),
      })
      .safeParse(payload)
    if (
      result.success &&
      isProductErrorCode(result.data.detail.code) &&
      ERROR_CONTRACTS[result.data.detail.code].status === response.status &&
      ERROR_CONTRACTS[result.data.detail.code].message ===
        result.data.detail.message
    ) {
      throw new WorkbenchApiError(result.data.detail.code, response.status)
    }
    throw new WorkbenchApiError('invalid_response', response.status)
  }

  if (response.status !== 200) {
    throw new WorkbenchApiError('invalid_response', response.status)
  }
  const result = workbenchSnapshotSchema.safeParse(payload)
  if (!result.success) {
    throw new WorkbenchApiError('invalid_response', response.status)
  }
  return result.data
}
