import { z } from 'zod'

import { AI_ERROR_CONTRACTS } from '@/lib/api/ai-settings'
import {
  boundedAnalysisText,
  summaryFailureSchema,
  summarySourceSchema,
  tokenUsageSchema,
} from '@/lib/api/ai-summaries'
import { promptInstructionsSchema } from '@/lib/api/analysis-settings'
import {
  ANALYSIS_ERROR_CONTRACTS,
  isValidAnalysisProse,
  jsonMutation,
  safeCount,
  safeId,
  uniqueIds,
} from '@/lib/api/analysis-shared'
import { getApiBaseUrl } from '@/lib/api/client'
import {
  analysisUsageSchema,
  attemptStatusSchema,
} from '@/lib/api/content-analyses'
import { isoDateSchema } from '@/lib/api/search-runs'

export const TOPIC_REPORTS_QUERY_KEY = ['topic-reports'] as const
export const REPORT_PAGE_SIZE = 20
export const REPORT_SECTION_PAGE_SIZE = 5
const utcDate = isoDateSchema.refine((value) => /(?:Z|\+00:00)$/.test(value))
const uuid = z.uuidv4().refine((value) => value === value.toLowerCase())
const prose = (max: number) =>
  boundedAnalysisText(max, 1).refine(isValidAnalysisProse)
const configurationFailureSchema = z
  .strictObject({
    stage: z.literal('execution'),
    code: z.enum([
      'ai_configuration_required',
      'ai_configuration_changed',
      'ai_credentials_unavailable',
      'ai_settings_storage_unavailable',
    ]),
    message: z.string(),
  })
  .refine((value) => value.message === AI_ERROR_CONTRACTS[value.code].message)
const reportFailureSchema = z.union([
  summaryFailureSchema,
  configurationFailureSchema,
])
function intervalTimestampKey(value: string) {
  const parts =
    /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(?:Z|\+00:00)$/u.exec(
      value,
    )
  if (!parts || parts[1].startsWith('0000')) return null
  // Python stores microseconds. Date.parse would silently discard the final
  // three digits, weakening both interval order and frozen-intent checks.
  return `${parts[1]}.${(parts[2] ?? '').padEnd(6, '0')}`
}
const intervalDate = utcDate.refine(
  (value) => intervalTimestampKey(value) !== null,
)
const intervalSelection = z
  .strictObject({
    kind: z.literal('first_seen_interval'),
    first_seen_from: intervalDate,
    first_seen_to: intervalDate,
  })
  .refine((value) => {
    const from = intervalTimestampKey(value.first_seen_from)
    const to = intervalTimestampKey(value.first_seen_to)
    return from !== null && to !== null && from < to
  })
const selectionSchema = z.union([
  z.strictObject({ kind: z.literal('initial_job'), job_id: safeId }),
  z.strictObject({ kind: z.literal('workflow_run'), run_id: safeId }),
  intervalSelection,
])
const promptSchema = z
  .strictObject({
    version_id: safeId.nullable(),
    origin: z.enum(['shared', 'override']),
    instructions: promptInstructionsSchema,
    content_hash: z.string().regex(/^[0-9a-f]{64}$/u),
    schema_version: z.literal('topic-report-v1'),
  })
  .refine(
    (value) => (value.origin === 'shared') === (value.version_id !== null),
  )
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
const nodeCountsSchema = z
  .strictObject({
    total: safeCount,
    queued: safeCount,
    running: safeCount,
    completed: safeCount,
    failed: safeCount,
    cancelled: safeCount,
    interrupted: safeCount,
    reused: safeCount,
  })
  .refine(
    (value) =>
      value.total ===
        value.queued +
          value.running +
          value.completed +
          value.failed +
          value.cancelled +
          value.interrupted && value.reused <= value.completed,
  )
const reportUsageSchema = z
  .strictObject({
    judgment: analysisUsageSchema,
    composition: analysisUsageSchema,
    total: analysisUsageSchema,
  })
  .refine(({ judgment, composition, total }) => {
    const parts = [judgment, composition]
    if (
      total.attempted_requests !==
        judgment.attempted_requests + composition.attempted_requests ||
      total.accounted_requests !==
        judgment.accounted_requests + composition.accounted_requests
    )
      return false
    const sum = (
      field: 'prompt_tokens' | 'completion_tokens' | 'total_tokens',
    ) => parts.reduce((value, part) => value + BigInt(part[field] ?? 0), 0n)
    const unknown =
      (total.attempted_requests > 0 && total.accounted_requests === 0) ||
      parts.some(
        (part) => part.total_tokens === null && part.accounted_requests > 0,
      ) ||
      sum('total_tokens') > BigInt(Number.MAX_SAFE_INTEGER)
    if (unknown) return total.total_tokens === null
    return (
      ['prompt_tokens', 'completion_tokens', 'total_tokens'] as const
    ).every((field) => total[field] === Number(sum(field)))
  })
const reportStatusSchema = z.enum([
  'queued',
  'judging',
  'composing',
  'completed',
  'empty',
  'failed',
  'cancelled',
  'interrupted',
  'configuration_blocked',
])
export function isActiveReport(status: z.infer<typeof reportStatusSchema>) {
  return status === 'queued' || status === 'judging' || status === 'composing'
}
export const reportRunSchema = z
  .strictObject({
    id: safeId,
    request_id: uuid.nullable(),
    trigger: z.enum(['automatic', 'interval', 'retry']),
    initial_job_id: safeId.nullable(),
    completion_event_id: safeId.nullable(),
    parent_report_id: safeId.nullable(),
    selection: selectionSchema,
    status: reportStatusSchema,
    revision: safeId,
    configuration_revision: safeId,
    base_url: z.url(),
    model: boundedAnalysisText(200, 1),
    prompt: promptSchema,
    coverage: coverageSchema,
    nodes: z.strictObject({
      judgments: nodeCountsSchema,
      composition: nodeCountsSchema,
    }),
    usage: reportUsageSchema,
    root_section_id: safeId.nullable(),
    empty_reason: z
      .enum(['no_ready_sources', 'no_relevant_sources'])
      .nullable(),
    queue_reason: z.literal('ai_operation_active').nullable(),
    recovery_reason: z.literal('backend_restart').nullable(),
    error: reportFailureSchema.nullable(),
    created_at: utcDate,
    started_at: utcDate.nullable(),
    finished_at: utcDate.nullable(),
  })
  .superRefine((value, ctx) => {
    const automatic = value.trigger === 'automatic'
    const retry = value.trigger === 'retry'
    if (
      isActiveReport(value.status) !== (value.finished_at === null) ||
      (value.status === 'completed') !== (value.root_section_id !== null) ||
      (value.status === 'empty') !== (value.empty_reason !== null) ||
      (value.empty_reason === 'no_ready_sources' &&
        (value.coverage.ready !== 0 ||
          value.usage.total.attempted_requests !== 0)) ||
      (value.empty_reason === 'no_relevant_sources' &&
        (value.coverage.ready === 0 ||
          value.coverage.relevant !== 0 ||
          value.usage.composition.attempted_requests !== 0)) ||
      automatic !== (value.request_id === null) ||
      retry !== (value.parent_report_id !== null) ||
      (value.parent_report_id !== null && value.parent_report_id >= value.id) ||
      (value.selection.kind === 'initial_job'
        ? value.selection.job_id !== value.initial_job_id ||
          (automatic && value.completion_event_id === null)
        : value.selection.kind === 'workflow_run'
          ? !automatic || value.completion_event_id !== null
          : value.initial_job_id !== null) ||
      (automatic &&
        value.selection.kind !== 'initial_job' &&
        value.selection.kind !== 'workflow_run') ||
      (value.trigger === 'interval' &&
        value.selection.kind !== 'first_seen_interval') ||
      (value.recovery_reason !== null && value.status !== 'interrupted') ||
      (value.finished_at !== null &&
        Date.parse(value.finished_at) < Date.parse(value.created_at)) ||
      (!isActiveReport(value.status) &&
        value.coverage.pending +
          value.coverage.judging +
          value.nodes.judgments.queued +
          value.nodes.judgments.running +
          value.nodes.composition.queued +
          value.nodes.composition.running !==
          0)
    )
      ctx.addIssue({ code: 'custom', message: 'invalid report state' })
  })
const judgmentSchema = z.strictObject({
  decision: z.enum(['relevant', 'irrelevant', 'uncertain']),
  reason: prose(600),
})
const sourceStateSchema = z.enum([
  'unavailable',
  'pending',
  'judging',
  'relevant',
  'irrelevant',
  'uncertain',
  'failed',
  'cancelled',
  'interrupted',
])
export const reportSourceSchema = z
  .strictObject({
    position: safeCount,
    source: summarySourceSchema,
    first_seen_at: utcDate,
    initial_attempt_id: safeId.nullable(),
    initial_status: attemptStatusSchema.nullable(),
    unavailable_reason: z
      .enum([
        'not_analysed',
        'legacy_only',
        'in_progress',
        'input_incomplete',
        'unsupported',
        'failed',
        'cancelled',
        'interrupted',
        'stale_evidence',
      ])
      .nullable(),
    state: sourceStateSchema,
    judgment: judgmentSchema.nullable(),
    judgment_node_id: safeId.nullable(),
    error: summaryFailureSchema.nullable(),
  })
  .refine((value) => {
    const semantic =
      value.state === 'relevant' ||
      value.state === 'irrelevant' ||
      value.state === 'uncertain'
    return (
      (value.state === 'unavailable') === (value.unavailable_reason !== null) &&
      (value.state === 'unavailable'
        ? value.judgment_node_id === null
        : value.initial_attempt_id !== null &&
          value.initial_status === 'completed' &&
          value.judgment_node_id !== null) &&
      (value.initial_attempt_id === null) === (value.initial_status === null) &&
      (semantic
        ? value.judgment?.decision === value.state &&
          value.judgment_node_id !== null
        : value.judgment === null)
    )
  })
const paragraphSchema = z.strictObject({
  text: prose(2000),
  source_ids: z.array(safeId).min(1).max(8).refine(uniqueIds),
})
const childParagraphSchema = z.strictObject({
  text: prose(2000),
  section_ids: z.array(safeId).min(1).max(8).refine(uniqueIds),
})
const nodeStatusSchema = z.enum([
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
  'interrupted',
])
export const reportSectionSchema = z
  .strictObject({
    id: safeId,
    report_id: safeId,
    kind: z.enum(['leaf', 'overview']),
    position: safeCount,
    level: safeCount,
    status: nodeStatusSchema,
    source_count: safeId,
    document: z
      .strictObject({
        overview: prose(2000),
        items: z.array(paragraphSchema).min(1).max(16),
      })
      .nullable(),
    overview_document: z
      .strictObject({
        overview: prose(2000),
        items: z.array(childParagraphSchema).min(1).max(16),
      })
      .nullable(),
    sources: z
      .array(
        z.strictObject({ position: safeCount, source: summarySourceSchema }),
      )
      .max(8),
    children: z
      .array(
        z.strictObject({
          id: safeId,
          kind: z.enum(['leaf', 'overview']),
          position: safeCount,
          level: safeCount,
          source_count: safeId,
          overview: prose(2000),
        }),
      )
      .max(8),
    attempted: z.boolean(),
    usage: tokenUsageSchema.nullable(),
    reused_from_node_id: safeId.nullable(),
    error: summaryFailureSchema.nullable(),
  })
  .superRefine((value, ctx) => {
    const completed = value.status === 'completed'
    const reused = value.reused_from_node_id !== null
    const sourceIds = value.sources.map((item) => item.source.result_id)
    const childIds = value.children.map((item) => item.id)
    const citedIds =
      value.document?.items.flatMap((item) => item.source_ids) ?? []
    if (
      (value.kind === 'leaf'
        ? value.level !== 0 ||
          value.children.length !== 0 ||
          value.sources.length < 1 ||
          value.source_count !== value.sources.length ||
          value.overview_document !== null ||
          completed !== (value.document !== null) ||
          !uniqueIds(sourceIds) ||
          value.sources.some(
            (item, index) =>
              index > 0 && item.position <= value.sources[index - 1].position,
          ) ||
          (completed &&
            (citedIds.some((id) => !sourceIds.includes(id)) ||
              new Set(citedIds).size !== sourceIds.length))
        : value.level < 1 ||
          value.sources.length !== 0 ||
          value.children.length < 2 ||
          value.document !== null ||
          completed !== (value.overview_document !== null) ||
          !uniqueIds(childIds) ||
          value.source_count !==
            value.children.reduce(
              (sum, child) => sum + child.source_count,
              0,
            ) ||
          value.children.some(
            (child) =>
              child.id === value.id ||
              child.level >= value.level ||
              (child.kind === 'leaf') !== (child.level === 0),
          ) ||
          value.overview_document?.items.some((item) =>
            item.section_ids.some((id) => !childIds.includes(id)),
          )) ||
      (reused &&
        (!completed ||
          value.attempted ||
          value.usage !== null ||
          (value.reused_from_node_id !== null &&
            value.reused_from_node_id >= value.id))) ||
      (completed && !value.attempted && !reused) ||
      (!value.attempted && value.usage !== null)
    )
      ctx.addIssue({ code: 'custom', message: 'invalid report section' })
  })

const createSchema = z.strictObject({
  request_id: uuid,
  configuration_revision: safeId,
  report_prompt_version_id: safeId,
  instructions_override: promptInstructionsSchema.nullable(),
  selection: intervalSelection,
})
const retrySchema = z.strictObject({
  request_id: uuid,
  expected_revision: safeId,
  configuration_revision: safeId,
  instructions_override: promptInstructionsSchema.nullable(),
})
const cancelSchema = z.strictObject({
  request_id: uuid,
  expected_revision: safeId,
})
export type ReportRun = z.infer<typeof reportRunSchema>
export type ReportSource = z.infer<typeof reportSourceSchema>
export type ReportSection = z.infer<typeof reportSectionSchema>
export type CreateReportRequest = z.infer<typeof createSchema>
export type RetryReportRequest = z.infer<typeof retrySchema>
export type CancelReportRequest = z.infer<typeof cancelSchema>
export type ReportList = { reports: ReportRun[]; next_before_id: number | null }
export type ReportListOptions = {
  beforeId?: number
  initialJobId?: number
  resultId?: number
  limit?: number
}

export const TOPIC_REPORT_ERROR_CONTRACTS = {
  ...AI_ERROR_CONTRACTS,
  invalid_analysis_prompt: ANALYSIS_ERROR_CONTRACTS.invalid_analysis_prompt,
  analysis_prompt_changed: ANALYSIS_ERROR_CONTRACTS.analysis_prompt_changed,
  topic_report_not_found: { status: 404, message: '未找到该文本报告。' },
  topic_report_section_not_found: {
    status: 404,
    message: '未找到该报告章节。',
  },
  topic_report_changed: {
    status: 409,
    message: '报告状态已更新，请刷新后重试。',
  },
  topic_report_request_conflict: {
    status: 409,
    message: '请求标识已用于其他报告操作，请重新确认。',
  },
  topic_report_not_terminal: {
    status: 409,
    message: '报告仍在处理中，请先等待或取消。',
  },
  topic_report_not_active: { status: 409, message: '报告已结束，无需取消。' },
  invalid_report_interval: {
    status: 422,
    message: '请选择有效的首次入库时间范围。',
  },
  topic_report_storage_unavailable: {
    status: 503,
    message: '文本报告数据暂时无法读取或保存，请稍后重试。',
  },
  topic_report_unavailable: {
    status: 503,
    message: '文本报告服务暂时不可用，请稍后重试。',
  },
} as const
type ProductCode = keyof typeof TOPIC_REPORT_ERROR_CONTRACTS
type ErrorCode = ProductCode | 'invalid_response' | 'service_unavailable'
export class TopicReportApiError extends Error {
  override name = 'TopicReportApiError'
  readonly code: ErrorCode
  readonly status?: number
  constructor(code: ErrorCode, status?: number) {
    super(
      code === 'invalid_response'
        ? '文本报告接口返回的数据与当前应用不匹配。'
        : code === 'service_unavailable'
          ? '无法连接本机后端服务，请确认服务已经启动。'
          : TOPIC_REPORT_ERROR_CONTRACTS[code].message,
    )
    this.code = code
    this.status = status
  }
}
export function reportErrorMessage(error: unknown) {
  return error instanceof TopicReportApiError
    ? error.message
    : '文本报告操作未完成，请稍后重试。'
}
export function isAmbiguousReportError(error: unknown) {
  return (
    !(error instanceof TopicReportApiError) ||
    error.code === 'service_unavailable' ||
    error.code === 'invalid_response' ||
    (error.status !== undefined && error.status >= 500)
  )
}
function decode<T>(
  schema: z.ZodType<T>,
  value: unknown,
  code: ErrorCode = 'invalid_response',
): T {
  const parsed = schema.safeParse(value)
  if (!parsed.success) throw new TopicReportApiError(code)
  return parsed.data
}
function isProductCode(value: string): value is ProductCode {
  return Object.hasOwn(TOPIC_REPORT_ERROR_CONTRACTS, value)
}
async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {},
  expectedStatus = 200,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}/topic-reports${path}`, {
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
    throw new TopicReportApiError('service_unavailable')
  }
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new TopicReportApiError('invalid_response', response.status)
  }
  if (!response.ok) {
    const parsed = z
      .strictObject({
        detail: z.strictObject({ code: z.string(), message: z.string() }),
      })
      .safeParse(payload)
    if (parsed.success && isProductCode(parsed.data.detail.code)) {
      const contract = TOPIC_REPORT_ERROR_CONTRACTS[parsed.data.detail.code]
      if (
        response.status === contract.status &&
        parsed.data.detail.message === contract.message
      )
        throw new TopicReportApiError(parsed.data.detail.code, response.status)
    }
    throw new TopicReportApiError('invalid_response', response.status)
  }
  if (response.status !== expectedStatus)
    throw new TopicReportApiError('invalid_response', response.status)
  return decode(schema, payload)
}
function checkId(id: number) {
  decode(safeId, id, 'invalid_request')
}
function pageQuery(offset: number, limit: number) {
  decode(safeCount, offset, 'invalid_request')
  decode(safeId.max(100), limit, 'invalid_request')
  return new URLSearchParams({ offset: String(offset), limit: String(limit) })
}
function checkPage<T extends { total: number; offset: number; limit: number }>(
  page: T,
  count: number,
  offset: number,
  limit: number,
) {
  if (
    page.offset !== offset ||
    page.limit !== limit ||
    count !== Math.min(limit, Math.max(0, page.total - offset))
  )
    throw new TopicReportApiError('invalid_response')
}
export async function fetchTopicReports(
  signal: AbortSignal,
  options: ReportListOptions = {},
): Promise<ReportList> {
  const { limit = REPORT_PAGE_SIZE, beforeId, initialJobId, resultId } = options
  decode(safeId.max(100), limit, 'invalid_request')
  const query = new URLSearchParams({ limit: String(limit) })
  for (const [key, id] of [
    ['before_id', beforeId],
    ['initial_job_id', initialJobId],
    ['result_id', resultId],
  ] as const) {
    if (id !== undefined) {
      checkId(id)
      query.set(key, String(id))
    }
  }
  const page = await request(
    `?${query}`,
    z.strictObject({
      reports: z.array(reportRunSchema).max(100),
      next_before_id: safeId.nullable(),
    }),
    { signal },
  )
  if (
    page.reports.length > limit ||
    page.reports.some(
      (item, index) =>
        (beforeId !== undefined && item.id >= beforeId) ||
        (initialJobId !== undefined && item.initial_job_id !== initialJobId) ||
        (index > 0 && item.id >= page.reports[index - 1].id),
    ) ||
    (page.next_before_id !== null &&
      (page.reports.length !== limit ||
        page.next_before_id !== page.reports.at(-1)?.id))
  )
    throw new TopicReportApiError('invalid_response')
  return page
}
export async function fetchTopicReport(id: number, signal: AbortSignal) {
  checkId(id)
  const report = await request(`/${id}`, reportRunSchema, { signal })
  if (report.id !== id) throw new TopicReportApiError('invalid_response')
  return report
}
export async function fetchReportSources(
  id: number,
  signal: AbortSignal,
  offset = 0,
  limit = REPORT_PAGE_SIZE,
) {
  checkId(id)
  const query = pageQuery(offset, limit)
  const page = await request(
    `/${id}/sources?${query}`,
    z.strictObject({
      items: z.array(reportSourceSchema).max(100),
      total: safeCount,
      limit: safeId.max(100),
      offset: safeCount,
    }),
    { signal },
  )
  checkPage(page, page.items.length, offset, limit)
  if (
    !uniqueIds(page.items.map((item) => item.source.result_id)) ||
    page.items.some((item, index) => item.position !== offset + index)
  )
    throw new TopicReportApiError('invalid_response')
  return page
}
export async function fetchReportSections(
  id: number,
  signal: AbortSignal,
  offset = 0,
  kind?: 'leaf' | 'overview',
  limit = REPORT_SECTION_PAGE_SIZE,
) {
  checkId(id)
  const query = pageQuery(offset, limit)
  if (kind !== undefined)
    query.set(
      'kind',
      decode(z.enum(['leaf', 'overview']), kind, 'invalid_request'),
    )
  const page = await request(
    `/${id}/sections?${query}`,
    z.strictObject({
      sections: z.array(reportSectionSchema).max(100),
      total: safeCount,
      limit: safeId.max(100),
      offset: safeCount,
    }),
    { signal },
  )
  checkPage(page, page.sections.length, offset, limit)
  if (
    !uniqueIds(page.sections.map((item) => item.id)) ||
    page.sections.some(
      (item, index) =>
        item.report_id !== id ||
        (kind !== undefined && item.kind !== kind) ||
        (index > 0 &&
          (item.level < page.sections[index - 1].level ||
            (item.level === page.sections[index - 1].level &&
              item.position <= page.sections[index - 1].position))),
    )
  )
    throw new TopicReportApiError('invalid_response')
  return page
}
export async function fetchReportSection(
  id: number,
  sectionId: number,
  signal: AbortSignal,
) {
  checkId(id)
  checkId(sectionId)
  const section = await request(
    `/${id}/sections/${sectionId}`,
    reportSectionSchema,
    { signal },
  )
  if (section.id !== sectionId || section.report_id !== id)
    throw new TopicReportApiError('invalid_response')
  return section
}
export async function createTopicReport(input: CreateReportRequest) {
  decode(intervalSelection, input.selection, 'invalid_report_interval')
  decode(createSchema, input, 'invalid_request')
  const report = await request(
    '',
    reportRunSchema,
    jsonMutation('POST', input),
    202,
  )
  if (
    report.trigger !== 'interval' ||
    report.request_id !== input.request_id ||
    report.configuration_revision !== input.configuration_revision ||
    report.selection.kind !== 'first_seen_interval' ||
    intervalTimestampKey(report.selection.first_seen_from) !==
      intervalTimestampKey(input.selection.first_seen_from) ||
    intervalTimestampKey(report.selection.first_seen_to) !==
      intervalTimestampKey(input.selection.first_seen_to) ||
    (input.instructions_override === null
      ? report.prompt.origin !== 'shared' ||
        report.prompt.version_id !== input.report_prompt_version_id
      : report.prompt.origin !== 'override' ||
        report.prompt.instructions !== input.instructions_override)
  )
    throw new TopicReportApiError('invalid_response')
  return report
}
export async function retryTopicReport(id: number, input: RetryReportRequest) {
  checkId(id)
  decode(retrySchema, input, 'invalid_request')
  const report = await request(
    `/${id}/retry`,
    reportRunSchema,
    jsonMutation('POST', input),
    202,
  )
  if (
    report.trigger !== 'retry' ||
    report.parent_report_id !== id ||
    report.request_id !== input.request_id ||
    report.configuration_revision !== input.configuration_revision ||
    (input.instructions_override !== null &&
      (report.prompt.origin !== 'override' ||
        report.prompt.instructions !== input.instructions_override))
  )
    throw new TopicReportApiError('invalid_response')
  return report
}
export async function cancelTopicReport(
  id: number,
  input: CancelReportRequest,
) {
  checkId(id)
  decode(cancelSchema, input, 'invalid_request')
  const report = await request(
    `/${id}/cancel`,
    reportRunSchema,
    jsonMutation('POST', input),
  )
  if (
    report.id !== id ||
    isActiveReport(report.status) ||
    report.revision < input.expected_revision
  )
    throw new TopicReportApiError('invalid_response')
  return report
}
