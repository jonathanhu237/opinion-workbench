import { z } from 'zod'

import {
  promptChoiceSchema,
  promptSnapshotSchema,
  type PromptChoice,
} from '@/lib/api/analysis-settings'
import { safeCount, safeId } from '@/lib/api/analysis-shared'
import { getApiBaseUrl } from '@/lib/api/client'
import {
  isoDateSchema,
  SEARCH_PLATFORM_ORDER,
  searchPlatformSchema,
  type SearchPlatform,
} from '@/lib/api/search-runs'

export const AUTOMATION_TASKS_QUERY_KEY = ['automation-tasks'] as const
export const AUTOMATION_RUNS_QUERY_KEY = ['automation-runs'] as const
export const AUTOMATION_PLATFORM_ORDER = SEARCH_PLATFORM_ORDER
export const MAX_AUTOMATION_INTERVAL_MINUTES = 43_200
export const MAX_AUTOMATION_GOAL_LENGTH = 4_000

const utcDateSchema = isoDateSchema.refine((value) =>
  /(?:Z|\+00:00)$/u.test(value),
)
const safeRevision = safeId
const safeExpectedRevision = safeId.max(Number.MAX_SAFE_INTEGER - 1)

const requestIdSchema = z
  .string()
  .uuid()
  .refine((value) => {
    const version = value.split('-')[2]
    return version?.startsWith('4') ?? false
  })

const failureSchema = z
  .strictObject({
    code: z
      .string()
      .regex(/^[a-z][a-z0-9_]*$/u)
      .min(1)
      .max(80),
    message: z.string().min(1).max(300),
  })
  .refine(
    (value) => value.message.trim().length > 0 && !value.message.includes('\0'),
  )

const stageNames = ['collection', 'initial_analysis', 'topic_report'] as const
const stageStatuses = [
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
  'interrupted',
  'configuration_blocked',
] as const
const runStatuses = [
  'queued',
  'collecting',
  'analysing',
  'reporting',
  'completed',
  'failed',
  'cancelled',
  'interrupted',
  'configuration_blocked',
] as const

const platformListSchema = z
  .array(searchPlatformSchema)
  .min(1)
  .max(5)
  .refine((platforms) => new Set(platforms).size === platforms.length)
  .refine((platforms) =>
    platforms.every(
      (platform, index) =>
        index === 0 ||
        SEARCH_PLATFORM_ORDER.indexOf(platform) >
          SEARCH_PLATFORM_ORDER.indexOf(platforms[index - 1]),
    ),
  )

const intervalScheduleSchema = z.strictObject({
  kind: z.literal('interval'),
  interval_minutes: safeId.max(MAX_AUTOMATION_INTERVAL_MINUTES),
})

const dailyScheduleSchema = z
  .strictObject({
    kind: z.literal('daily'),
    daily_time: z.string().regex(/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/u),
    timezone: z.string().min(1).max(64),
  })
  .refine((value) => isValidTimeZone(value.timezone))

export const automationScheduleSchema = z.discriminatedUnion('kind', [
  intervalScheduleSchema,
  dailyScheduleSchema,
])

const initialPromptSnapshotSchema = promptSnapshotSchema.refine(
  (value) => value.schema_version === 'initial-understanding-v1',
  '自动任务初始分析提示词版本不匹配。',
)
const reportPromptSnapshotSchema = promptSnapshotSchema.refine(
  (value) => value.schema_version === 'topic-report-v1',
  '自动任务专题报告提示词版本不匹配。',
)

const snapshotSchema = z
  .strictObject({
    task_id: safeId,
    task_revision: safeRevision,
    task_name: z.string().min(1).max(80),
    monitoring_rule_id: safeId.nullable(),
    rule_name: z.string().min(1).max(80),
    terms: z.array(z.string().min(1).max(200)).min(1).max(100),
    platforms: platformListSchema,
    max_results_per_term: safeId.max(50),
    analysis_goal: z.string().min(1).max(MAX_AUTOMATION_GOAL_LENGTH),
    analysis_goal_hash: z.string().regex(/^[a-f0-9]{64}$/u),
    initial_prompt: initialPromptSnapshotSchema.optional(),
    report_prompt: reportPromptSnapshotSchema.optional(),
    ai_configuration_revision: safeRevision.nullable(),
    ai_base_url: z.string().max(2048).nullable(),
    ai_model: z.string().max(200).nullable(),
    initial_prompt_version_id: safeRevision.nullable(),
    report_prompt_version_id: safeRevision.nullable(),
    initial_template_version: z.string().min(1).max(120),
    report_template_version: z.string().min(1).max(120),
    admitted_at: utcDateSchema,
  })
  .refine((value) => proseIsValid(value.task_name))
  .refine((value) => proseIsValid(value.rule_name))
  .refine((value) => proseIsValid(value.analysis_goal))
  .superRefine((value, context) => {
    if (
      value.initial_prompt !== undefined &&
      value.initial_prompt_version_id !== value.initial_prompt.version_id
    ) {
      context.addIssue({
        code: 'custom',
        path: ['initial_prompt_version_id'],
        message: '初步分析提示词版本不一致。',
      })
    }
    if (
      value.report_prompt !== undefined &&
      value.report_prompt_version_id !== value.report_prompt.version_id
    ) {
      context.addIssue({
        code: 'custom',
        path: ['report_prompt_version_id'],
        message: '报告提示词版本不一致。',
      })
    }
  })

const stageSchema = z
  .strictObject({
    name: z.enum(stageNames),
    attempt_number: safeRevision,
    status: z.enum(stageStatuses),
    child_kind: z.string().min(1).max(80).nullable(),
    child_id: safeId.nullable(),
    input_count: safeCount,
    success_count: safeCount,
    failure_count: safeCount,
    usage_attempted: safeCount,
    usage_tokens: safeCount.nullable(),
    error: failureSchema.nullable(),
    created_at: utcDateSchema,
    started_at: utcDateSchema.nullable(),
    finished_at: utcDateSchema.nullable(),
  })
  .superRefine((value, context) => {
    if (value.success_count + value.failure_count > value.input_count) {
      context.addIssue({ code: 'custom', message: 'invalid stage counts' })
    }
    const active = value.status === 'queued' || value.status === 'running'
    if (active !== (value.finished_at === null)) {
      context.addIssue({
        code: 'custom',
        message: 'invalid stage completion time',
      })
    }
    if (!active && value.finished_at === null) {
      context.addIssue({
        code: 'custom',
        message: 'terminal stage must finish',
      })
    }
    if (active && value.error !== null) {
      context.addIssue({
        code: 'custom',
        message: 'active stage cannot contain error',
      })
    }
    if ((value.child_kind === null) !== (value.child_id === null)) {
      context.addIssue({
        code: 'custom',
        message: 'stage child link must be paired',
      })
    }
  })

const runSchema = z
  .strictObject({
    id: safeId,
    admission_key: z.string().min(1).max(200),
    request_id: requestIdSchema.nullable(),
    task_id: safeId,
    trigger: z.enum(['scheduled', 'manual']),
    task_revision: safeRevision,
    snapshot: snapshotSchema,
    status: z.enum(runStatuses),
    active_stage: z.enum(stageNames).nullable(),
    stages: z.array(stageSchema).length(3),
    attempts: z.array(stageSchema).min(3),
    cancel_requested: z.boolean(),
    outcome: z.enum(['completed', 'no_new_sources', 'cancelled']).nullable(),
    topic_report_id: safeId.nullable(),
    error: failureSchema.nullable(),
    revision: safeRevision,
    created_at: utcDateSchema,
    started_at: utcDateSchema.nullable(),
    finished_at: utcDateSchema.nullable(),
  })
  .superRefine((value, context) => {
    if (
      !stageNames.every((name, index) => value.stages[index]?.name === name)
    ) {
      context.addIssue({ code: 'custom', message: 'invalid fixed stage order' })
    }
    const positions = new Map(stageNames.map((name, index) => [name, index]))
    if (
      value.attempts.some(
        (attempt, index) =>
          index > 0 &&
          (positions.get(value.attempts[index - 1]!.name) ?? 0) >
            (positions.get(attempt.name) ?? 0),
      )
    ) {
      context.addIssue({
        code: 'custom',
        message: 'invalid attempt stage order',
      })
    }
    stageNames.forEach((name, stageIndex) => {
      const history = value.attempts.filter((attempt) => attempt.name === name)
      const current = value.stages[stageIndex]
      if (
        history.length === 0 ||
        history.some(
          (attempt, index) => attempt.attempt_number !== index + 1,
        ) ||
        history.at(-1)?.attempt_number !== current?.attempt_number ||
        history.at(-1)?.status !== current?.status ||
        history.at(-1)?.child_id !== current?.child_id
      ) {
        context.addIssue({ code: 'custom', message: 'invalid attempt history' })
      }
    })
    if (value.snapshot.task_id !== value.task_id) {
      context.addIssue({ code: 'custom', message: 'snapshot task mismatch' })
    }
    const active =
      value.status === 'queued' ||
      value.status === 'collecting' ||
      value.status === 'analysing' ||
      value.status === 'reporting'
    if (active !== (value.finished_at === null)) {
      context.addIssue({
        code: 'custom',
        message: 'invalid run completion time',
      })
    }
    if (value.status === 'completed' && value.outcome === null) {
      context.addIssue({
        code: 'custom',
        message: 'completed run requires outcome',
      })
    }
    if (value.status === 'cancelled' && value.outcome !== 'cancelled') {
      context.addIssue({
        code: 'custom',
        message: 'cancelled run requires outcome',
      })
    }
    if (
      !active &&
      value.stages.some(
        (stage) => stage.status === 'queued' || stage.status === 'running',
      )
    ) {
      context.addIssue({
        code: 'custom',
        message: 'terminal run has active stage',
      })
    }
  })

const taskSchema = z
  .strictObject({
    id: safeId,
    name: z.string().min(1).max(80),
    monitoring_rule_id: safeId.nullable(),
    rule_name: z.string().min(1).max(80),
    rule_state: z.enum(['enabled', 'disabled', 'deleted', 'invalid']),
    platforms: platformListSchema,
    max_results_per_term: safeId.max(50),
    analysis_goal: z.string().min(1).max(MAX_AUTOMATION_GOAL_LENGTH),
    initial_prompt: initialPromptSnapshotSchema.optional(),
    report_prompt: reportPromptSnapshotSchema.optional(),
    schedule: automationScheduleSchema,
    enabled: z.boolean(),
    revision: safeRevision,
    anchor_at: utcDateSchema.nullable(),
    next_due_at: utcDateSchema.nullable(),
    created_at: utcDateSchema,
    updated_at: utcDateSchema,
    latest_run: runSchema.nullable(),
    available: z.boolean(),
  })
  .superRefine((value, context) => {
    if (
      (value.monitoring_rule_id === null) !==
      (value.rule_state === 'deleted')
    ) {
      context.addIssue({ code: 'custom', message: 'invalid task rule state' })
    }
    const scheduled = value.anchor_at !== null && value.next_due_at !== null
    if (value.enabled !== scheduled) {
      context.addIssue({
        code: 'custom',
        message: 'invalid task schedule state',
      })
    }
    const anchorAt = value.anchor_at
    const nextDueAt = value.next_due_at
    if (
      scheduled &&
      anchorAt !== null &&
      nextDueAt !== null &&
      Date.parse(nextDueAt) <= Date.parse(anchorAt)
    ) {
      context.addIssue({
        code: 'custom',
        message: 'next due must be after anchor',
      })
    }
    if (value.latest_run !== null && value.latest_run.task_id !== value.id) {
      context.addIssue({ code: 'custom', message: 'invalid latest run' })
    }
  })

const taskPageSchema = z.strictObject({
  tasks: z.array(taskSchema).max(100),
  next_before_id: safeId.nullable(),
})
const occurrenceSchema = z.strictObject({
  id: safeId,
  task_id: safeId,
  task_revision: safeRevision,
  due_at: utcDateSchema,
  status: z.enum(['claimed', 'admitted', 'skipped', 'missed', 'interrupted']),
  reason: z.string().min(1).max(80).nullable(),
  run_id: safeId.nullable(),
  missed_count: safeCount,
  missed_until: utcDateSchema.nullable(),
  created_at: utcDateSchema,
  admitted_at: utcDateSchema.nullable(),
  run_status: z.enum(runStatuses).nullable(),
})
const occurrencePageSchema = z.strictObject({
  occurrences: z.array(occurrenceSchema).max(100),
  next_before_id: safeId.nullable(),
})
const runPageSchema = z.strictObject({
  runs: z.array(runSchema),
  next_before_id: safeId.nullable(),
})

const createSchema = z.strictObject({
  name: z.string().min(1).max(80).refine(proseIsValid),
  monitoring_rule_id: safeId,
  platforms: platformListSchema,
  max_results_per_term: safeId.max(50),
  initial_prompt: promptChoiceSchema,
  report_prompt: promptChoiceSchema,
  schedule: automationScheduleSchema,
})
const replaceSchema = createSchema.extend({
  monitoring_rule_id: safeId.nullable(),
  expected_revision: safeExpectedRevision,
  enabled: z.boolean(),
})
const deletePayloadSchema = z.strictObject({
  expected_revision: safeExpectedRevision,
})

export type AutomationSchedule = z.infer<typeof automationScheduleSchema>
export type AutomationTask = z.infer<typeof taskSchema>
export type AutomationRun = z.infer<typeof runSchema>
export type AutomationStage = z.infer<typeof stageSchema>
export type AutomationFailure = z.infer<typeof failureSchema>
export type AutomationOccurrence = z.infer<typeof occurrenceSchema>
export type AutomationTaskPage = z.infer<typeof taskPageSchema>
export type AutomationOccurrencePage = z.infer<typeof occurrencePageSchema>
export type AutomationRunPage = z.infer<typeof runPageSchema>
export type AutomationPlatform = SearchPlatform
export type AutomationTaskCreate = z.infer<typeof createSchema>
export type AutomationTaskReplace = z.infer<typeof replaceSchema>
export type AutomationTaskDelete = { expectedRevision: number }

export const AUTOMATION_ERROR_CONTRACTS = {
  invalid_request: { status: 422, message: '请求内容不正确。' },
  automation_task_not_found: { status: 404, message: '未找到自动任务。' },
  automation_task_name_conflict: {
    status: 409,
    message: '已存在同名自动任务。',
  },
  automation_task_changed: {
    status: 409,
    message: '自动任务已更新，请刷新后重试。',
  },
  automation_invalid_schedule: {
    status: 422,
    message: '自动任务计划不正确，请检查时间和时区。',
  },
  automation_invalid_goal: {
    status: 422,
    message: '请输入有效的舆情分析目标。',
  },
  automation_rule_not_found: { status: 404, message: '未找到该监控规则。' },
  automation_rule_disabled: {
    status: 409,
    message: '该监控规则已停用，请先启用后再保存。',
  },
  automation_rule_invalid: {
    status: 422,
    message: '监控规则当前不可用于自动任务。',
  },
  automation_run_active: {
    status: 409,
    message: '该自动任务已有运行中的实例，请稍后重试。',
  },
  automation_run_not_found: {
    status: 404,
    message: '未找到自动任务运行记录。',
  },
  automation_run_changed: {
    status: 409,
    message: '运行状态已更新，请刷新后重试。',
  },
  automation_run_not_retryable: {
    status: 409,
    message: '该运行当前不能从失败阶段重试。',
  },
  automation_run_not_active: {
    status: 409,
    message: '该运行已经结束，无需取消。',
  },
  automation_request_conflict: {
    status: 409,
    message: '请求标识已用于其他自动任务操作，请重新确认。',
  },
  automation_storage_unavailable: {
    status: 503,
    message: '自动任务数据暂时无法读取或保存，请稍后重试。',
  },
  automation_unavailable: {
    status: 503,
    message: '自动任务服务暂时不可用，请稍后重试。',
  },
  automation_stage_failed: {
    status: 409,
    message: '自动任务阶段未完成，请从失败阶段重试。',
  },
  ai_configuration_required: {
    status: 409,
    message: '请先配置可用的 AI 服务。',
  },
  ai_configuration_changed: {
    status: 409,
    message: 'AI 配置已变化，请重新运行自动任务。',
  },
} as const

type AutomationProductCode = keyof typeof AUTOMATION_ERROR_CONTRACTS
export type AutomationApiErrorCode =
  AutomationProductCode | 'invalid_response' | 'service_unavailable'

export class AutomationApiError extends Error {
  override name = 'AutomationApiError'
  readonly code: AutomationApiErrorCode
  readonly status: number | undefined

  constructor(code: AutomationApiErrorCode, status?: number) {
    super(
      code === 'invalid_response'
        ? '自动任务接口返回的数据与当前应用不匹配。'
        : code === 'service_unavailable'
          ? '无法连接本机后端服务，请确认服务已经启动。'
          : AUTOMATION_ERROR_CONTRACTS[code].message,
    )
    this.code = code
    this.status = status
  }
}

function isProductCode(value: string): value is AutomationProductCode {
  return Object.hasOwn(AUTOMATION_ERROR_CONTRACTS, value)
}

function proseIsValid(value: string) {
  return value.trim().length > 0 && !value.includes('\0')
}

function isValidTimeZone(value: string) {
  if (
    !value ||
    value.startsWith('/') ||
    value.startsWith('..') ||
    value.includes('..')
  )
    return false
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: value }).format()
    return true
  } catch {
    return false
  }
}

function isUuid4(value: string) {
  return requestIdSchema.safeParse(value).success
}

function invalidResponse(status?: number) {
  return new AutomationApiError('invalid_response', status)
}

async function request(
  resource: 'automation-tasks' | 'automation-runs',
  path: string,
  init: RequestInit,
  expectedStatus = 200,
) {
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}/${resource}${path}`, {
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
    throw new AutomationApiError('service_unavailable')
  }
  if (response.status === 204) {
    if (!response.ok || response.status !== expectedStatus)
      throw invalidResponse(response.status)
    return undefined
  }
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw invalidResponse(response.status)
  }
  if (!response.ok) {
    const parsed = z
      .strictObject({
        detail: z.strictObject({ code: z.string(), message: z.string() }),
      })
      .safeParse(payload)
    if (parsed.success && isProductCode(parsed.data.detail.code)) {
      const code = parsed.data.detail.code
      const contract = AUTOMATION_ERROR_CONTRACTS[code]
      if (
        contract.status === response.status &&
        contract.message === parsed.data.detail.message
      )
        throw new AutomationApiError(code, response.status)
    }
    throw invalidResponse(response.status)
  }
  if (response.status !== expectedStatus) throw invalidResponse(response.status)
  return payload
}

function decode<T>(schema: z.ZodType<T>, payload: unknown, status?: number) {
  const parsed = schema.safeParse(payload)
  if (!parsed.success) throw invalidResponse(status)
  return parsed.data
}

function pageQuery(options: { limit?: number; beforeId?: number }) {
  const limit = options.limit ?? 50
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
    throw new AutomationApiError('invalid_request')
  }
  if (
    options.beforeId !== undefined &&
    (!Number.isSafeInteger(options.beforeId) || options.beforeId < 1)
  ) {
    throw new AutomationApiError('invalid_request')
  }
  const query = new URLSearchParams({ limit: String(limit) })
  if (options.beforeId !== undefined)
    query.set('before_id', String(options.beforeId))
  return { query, limit, beforeId: options.beforeId }
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
    throw invalidResponse()
}

export async function fetchAutomationTasks(
  signal: AbortSignal,
  options: { limit?: number; beforeId?: number } = {},
) {
  const { query, limit, beforeId } = pageQuery(options)
  const payload = await request('automation-tasks', `?${query}`, { signal })
  const page = decode(taskPageSchema, payload)
  checkCursor(page.tasks, page.next_before_id, limit, beforeId)
  return page
}

export async function fetchAutomationTask(id: number, signal: AbortSignal) {
  if (!Number.isSafeInteger(id) || id < 1)
    throw new AutomationApiError('invalid_request')
  const task = decode(
    taskSchema,
    await request('automation-tasks', `/${encodeURIComponent(id)}`, { signal }),
  )
  if (task.id !== id) throw invalidResponse()
  return task
}

export async function createAutomationTask(
  input: AutomationTaskCreate,
  signal?: AbortSignal,
) {
  decode(createSchema, input)
  const task = decode(
    taskSchema,
    await request('automation-tasks', '', mutation('POST', input, signal), 201),
  )
  if (task.enabled) throw invalidResponse()
  return task
}

export async function replaceAutomationTask(
  id: number,
  input: AutomationTaskReplace,
  signal?: AbortSignal,
) {
  if (!Number.isSafeInteger(id) || id < 1)
    throw new AutomationApiError('invalid_request')
  decode(replaceSchema, input)
  const task = decode(
    taskSchema,
    await request(
      'automation-tasks',
      `/${encodeURIComponent(id)}`,
      mutation('PUT', input, signal),
    ),
  )
  if (task.id !== id || task.revision !== input.expected_revision + 1) {
    throw invalidResponse()
  }
  return task
}

export async function deleteAutomationTask(
  id: number,
  input: AutomationTaskDelete,
  signal?: AbortSignal,
): Promise<void> {
  if (!Number.isSafeInteger(id) || id < 1)
    throw new AutomationApiError('invalid_request')
  const payload = { expected_revision: input.expectedRevision }
  decode(deletePayloadSchema, payload)
  await request(
    'automation-tasks',
    `/${encodeURIComponent(id)}`,
    mutation('DELETE', payload, signal),
    204,
  )
}

export async function fetchAutomationOccurrences(
  taskId: number,
  signal: AbortSignal,
  options: { limit?: number; beforeId?: number } = {},
) {
  if (!Number.isSafeInteger(taskId) || taskId < 1) {
    throw new AutomationApiError('invalid_request')
  }
  const { query, limit, beforeId } = pageQuery(options)
  const page = decode(
    occurrencePageSchema,
    await request(
      'automation-tasks',
      `/${encodeURIComponent(taskId)}/occurrences?${query}`,
      { signal },
    ),
  )
  checkCursor(page.occurrences, page.next_before_id, limit, beforeId)
  if (page.occurrences.some((item) => item.task_id !== taskId))
    throw invalidResponse()
  return page
}

export async function fetchAutomationRuns(
  taskId: number,
  signal: AbortSignal,
  options: { limit?: number; beforeId?: number } = {},
) {
  if (!Number.isSafeInteger(taskId) || taskId < 1) {
    throw new AutomationApiError('invalid_request')
  }
  const { query, limit, beforeId } = pageQuery(options)
  const page = decode(
    runPageSchema,
    await request(
      'automation-tasks',
      `/${encodeURIComponent(taskId)}/runs?${query}`,
      { signal },
    ),
  )
  checkCursor(page.runs, page.next_before_id, limit, beforeId)
  if (page.runs.some((item) => item.task_id !== taskId)) throw invalidResponse()
  return page
}

export async function fetchAutomationRun(id: number, signal: AbortSignal) {
  if (!Number.isSafeInteger(id) || id < 1)
    throw new AutomationApiError('invalid_request')
  const run = decode(
    runSchema,
    await request('automation-runs', `/${encodeURIComponent(id)}`, { signal }),
  )
  if (run.id !== id) throw invalidResponse()
  return run
}

export async function runAutomationTaskNow(
  taskId: number,
  requestId: string,
  signal?: AbortSignal,
) {
  assertRequestId(requestId)
  const run = decode(
    runSchema,
    await request(
      'automation-tasks',
      `/${encodeURIComponent(taskId)}/run-now`,
      mutation('POST', { request_id: requestId }, signal),
      202,
    ),
  )
  if (run.task_id !== taskId || run.request_id !== requestId)
    throw invalidResponse()
  return run
}

export async function cancelAutomationRun(
  runId: number,
  input: { requestId: string; expectedRevision: number },
  signal?: AbortSignal,
) {
  assertRequestId(input.requestId)
  const run = decode(
    runSchema,
    await request(
      'automation-runs',
      `/${encodeURIComponent(runId)}/cancel`,
      mutation(
        'POST',
        {
          request_id: input.requestId,
          expected_revision: input.expectedRevision,
        },
        signal,
      ),
      202,
    ),
  )
  if (run.id !== runId) throw invalidResponse()
  return run
}

export async function retryAutomationRun(
  runId: number,
  input: { requestId: string; expectedRevision: number },
  signal?: AbortSignal,
) {
  assertRequestId(input.requestId)
  const run = decode(
    runSchema,
    await request(
      'automation-runs',
      `/${encodeURIComponent(runId)}/retry`,
      mutation(
        'POST',
        {
          request_id: input.requestId,
          expected_revision: input.expectedRevision,
        },
        signal,
      ),
      202,
    ),
  )
  if (run.id !== runId) throw invalidResponse()
  return run
}

function assertRequestId(value: string) {
  if (!isUuid4(value)) throw new AutomationApiError('invalid_request')
}

function mutation(
  method: 'DELETE' | 'POST' | 'PUT',
  payload: unknown,
  signal?: AbortSignal,
): RequestInit {
  return {
    method,
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

export function automationErrorMessage(error: unknown) {
  return error instanceof AutomationApiError
    ? error.message
    : '自动任务操作未完成，请稍后重试。'
}

export function isAutomationRunActive(run: AutomationRun) {
  return ['queued', 'collecting', 'analysing', 'reporting'].includes(run.status)
}

export function isAutomationTaskActive(task: AutomationTask) {
  return task.latest_run !== null && isAutomationRunActive(task.latest_run)
}

export function automationTaskUpdatePayload(
  task: AutomationTask,
  enabled = task.enabled,
): AutomationTaskReplace {
  return {
    name: task.name,
    monitoring_rule_id: task.monitoring_rule_id,
    platforms: task.platforms,
    max_results_per_term: task.max_results_per_term,
    initial_prompt: promptChoiceFromSnapshot(task.initial_prompt),
    report_prompt: promptChoiceFromSnapshot(task.report_prompt),
    schedule: task.schedule,
    expected_revision: task.revision,
    enabled,
  }
}

function promptChoiceFromSnapshot(
  prompt: AutomationTask['initial_prompt'] | AutomationTask['report_prompt'],
): PromptChoice {
  return prompt?.mode === 'custom' || prompt?.mode === 'legacy'
    ? { mode: 'custom', instructions: prompt.instructions }
    : { mode: 'default' }
}

export function newAutomationRequestId() {
  const value = globalThis.crypto?.randomUUID?.()
  if (value && isUuid4(value)) return value
  return '00000000-0000-4000-8000-000000000001'
}

export function formatAutomationDate(
  value: string | null,
  timeZone = 'Asia/Shanghai',
) {
  if (value === null) return '未安排'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

export function automationScheduleLabel(schedule: AutomationSchedule) {
  return schedule.kind === 'interval'
    ? schedule.interval_minutes % 60 === 0
      ? `每 ${schedule.interval_minutes / 60} 小时`
      : `每 ${schedule.interval_minutes} 分钟`
    : `每天 ${schedule.daily_time}（${schedule.timezone}）`
}
