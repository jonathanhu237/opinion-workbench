import { z } from 'zod'

import { getApiBaseUrl } from '@/lib/api/client'

export const SEARCH_RUNS_QUERY_KEY = ['search-runs'] as const
export const SEARCH_PLATFORM_ORDER = ['wb'] as const

const activeStatuses = ['queued', 'running'] as const
const terminalStatuses = [
  'completed_with_results',
  'completed_empty',
  'completed_with_incomplete',
  'login_required',
  'manual_challenge_required',
  'platform_blocked_or_rate_limited',
  'structure_changed',
  'browser_unavailable',
  'timed_out',
  'cancelled',
  'internal_error',
] as const
export const searchRunStatusSchema = z.enum([
  ...activeStatuses,
  ...terminalStatuses,
])
export const searchPlatformSchema = z.enum(['wb'] as const)
export const isoDateSchema = z.string().datetime({ offset: true })
export const searchFailureReasonSchema = z.enum([
  'page_state_unrecognized',
  'search_context_unavailable',
  'search_response_incompatible',
  'search_results_incompatible',
  'search_pagination_incompatible',
])
export const searchTermDiagnosticSchema = z.strictObject({
  position: z.number().int().min(0).max(19),
  term: z.string().min(1).max(200),
  reason: z.enum(['view_all_unresolved']),
  result_count: z.number().int().min(0).max(50),
})
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
const summaryShape = {
  id: positiveSafeIntegerSchema,
  monitoring_rule_id: positiveSafeIntegerSchema.nullable(),
  platform: searchPlatformSchema,
  rule_name: z.string(),
  term_count: z.number().int().positive().max(20),
  max_results_per_term: z.number().int().min(1).max(50),
  status: searchRunStatusSchema,
  failure_reason: searchFailureReasonSchema.nullable(),
  execution_limit: z.enum(['requests', 'pages', 'time']).nullable().optional(),
  current_term_position: z.number().int().min(0).max(19).nullable(),
  new_count: nonnegativeSafeIntegerSchema,
  repeated_count: nonnegativeSafeIntegerSchema,
  total_count: nonnegativeSafeIntegerSchema,
  created_at: isoDateSchema,
  started_at: isoDateSchema.nullable(),
  finished_at: isoDateSchema.nullable(),
  incomplete_terms: z.array(searchTermDiagnosticSchema).max(20).optional(),
} as const
export const searchRunSummarySchema = z
  .strictObject(summaryShape)
  .superRefine((value, context) => {
    if (value.execution_limit != null && value.status !== 'timed_out') {
      context.addIssue({ code: 'custom', message: 'invalid execution limit' })
    }
    if (value.failure_reason !== null && value.status !== 'structure_changed') {
      context.addIssue({ code: 'custom', message: 'invalid failure reason' })
    }
    const diagnostics = value.incomplete_terms ?? []
    if (
      value.status === 'completed_with_incomplete' &&
      diagnostics.length === 0
    ) {
      context.addIssue({
        code: 'custom',
        message: 'incomplete status requires diagnostics',
      })
    }
    if (
      new Set(diagnostics.map((diagnostic) => diagnostic.position)).size !==
        diagnostics.length ||
      diagnostics.some((diagnostic) => diagnostic.position >= value.term_count)
    ) {
      context.addIssue({
        code: 'custom',
        message: 'invalid incomplete term diagnostics',
      })
    }
    if (value.new_count + value.repeated_count !== value.total_count) {
      context.addIssue({ code: 'custom', message: 'invalid result counts' })
    }
  })
const searchRunDetailSchema = z
  .strictObject({ ...summaryShape, terms: z.array(z.string()).min(1).max(20) })
  .superRefine((value, context) => {
    if (value.execution_limit != null && value.status !== 'timed_out') {
      context.addIssue({ code: 'custom', message: 'invalid execution limit' })
    }
    if (value.failure_reason !== null && value.status !== 'structure_changed') {
      context.addIssue({ code: 'custom', message: 'invalid failure reason' })
    }
    if (
      value.terms.length !== value.term_count ||
      value.new_count + value.repeated_count !== value.total_count ||
      (value.incomplete_terms ?? []).some(
        (diagnostic) => value.terms[diagnostic.position] !== diagnostic.term,
      )
    ) {
      context.addIssue({ code: 'custom', message: 'invalid run detail' })
    }
  })
const searchRunListSchema = z.strictObject({
  runs: z.array(searchRunSummarySchema),
  next_before_id: positiveSafeIntegerSchema.nullable(),
})
export const searchResultSchema = z
  .strictObject({
    id: positiveSafeIntegerSchema,
    platform: searchPlatformSchema,
    platform_content_id: z.string().min(1).max(128),
    content_type: z.string().min(1).max(32),
    title: z.string().min(1).max(300),
    snippet: z.string().max(1000),
    creator_hash: z.string().regex(/^(?:|[0-9a-f]{16})$/u),
    publisher_name: z.string().max(100),
    published_at_text: z.string().max(100),
    content_url: z.string().url(),
    kind: z.enum(['new', 'repeated']),
    matched_terms: z.array(z.string()).min(1).max(20),
    first_seen_at: isoDateSchema,
    last_seen_at: isoDateSchema,
    first_observed_at: isoDateSchema,
    last_observed_at: isoDateSchema,
  })
  .superRefine((value, context) => {
    if (
      !isValidSearchContentUrl(
        value.platform,
        value.platform_content_id,
        value.content_url,
      )
    ) {
      context.addIssue({ code: 'custom', message: 'invalid content URL' })
    }
    const name = value.publisher_name
    const nameCharacters = [...name]
    const masked =
      name === '' ||
      name === '*' ||
      (nameCharacters.length === 2 && nameCharacters[1] === '*') ||
      (nameCharacters.length === 5 &&
        nameCharacters.slice(1, 4).join('') === '***')
    if (Boolean(value.creator_hash) !== Boolean(name) || !masked) {
      context.addIssue({ code: 'custom', message: 'invalid masked publisher' })
    }
  })
const searchResultListSchema = z.strictObject({
  results: z.array(searchResultSchema),
  total: nonnegativeSafeIntegerSchema,
  limit: z.number().int().min(1).max(50),
  offset: nonnegativeSafeIntegerSchema,
})
const searchResultOpenOutcomeSchema = z.enum([
  'opened',
  'content_not_found',
  'content_unavailable',
  'login_required',
  'manual_challenge_required',
  'platform_blocked_or_rate_limited',
  'structure_changed',
  'browser_unavailable',
  'internal_error',
])
const searchResultOpenResponseSchema = z.strictObject({
  outcome: searchResultOpenOutcomeSchema,
})
const errorEnvelopeSchema = z.strictObject({
  detail: z.strictObject({ code: z.string(), message: z.string() }),
})

export type SearchRunStatus = z.infer<typeof searchRunStatusSchema>
export type SearchFailureReason = z.infer<typeof searchFailureReasonSchema>
export type SearchTermDiagnostic = z.infer<typeof searchTermDiagnosticSchema>
export type SearchPlatform = z.infer<typeof searchPlatformSchema>
export type SearchRunSummary = z.infer<typeof searchRunSummarySchema>
export type SearchRunDetail = z.infer<typeof searchRunDetailSchema>
export type SearchRunListResponse = z.infer<typeof searchRunListSchema>
export type SearchResult = z.infer<typeof searchResultSchema>
export type SearchResultListResponse = z.infer<typeof searchResultListSchema>
export type SearchResultOpenOutcome = z.infer<
  typeof searchResultOpenOutcomeSchema
>
export type SearchResultOpenResponse = z.infer<
  typeof searchResultOpenResponseSchema
>
export type SearchResultFilter = 'all' | 'new' | 'repeated'

type ProductErrorCode =
  | 'search_platform_not_available'
  | 'invalid_request'
  | 'monitoring_rule_not_found'
  | 'monitoring_rule_disabled'
  | 'too_many_search_terms'
  | 'browser_operation_active'
  | 'search_run_not_found'
  | 'search_run_not_active'
  | 'search_result_not_found'
  | 'search_result_open_not_supported'
  | 'search_storage_unavailable'

type SearchRunApiErrorCode =
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
  search_run_not_found: { status: 404, message: '未找到该采集任务。' },
  search_run_not_active: {
    status: 409,
    message: '该采集任务已经结束，无法取消。',
  },
  search_result_not_found: {
    status: 404,
    message: '未在该采集任务中找到这条结果。',
  },
  search_result_open_not_supported: {
    status: 409,
    message: '该采集结果当前无法通过浏览器打开。',
  },
  search_storage_unavailable: {
    status: 503,
    message: '采集任务暂时无法读取或保存，请稍后重试。',
  },
}

export class SearchRunApiError extends Error {
  readonly code: SearchRunApiErrorCode
  readonly status?: number

  constructor(message: string, code: SearchRunApiErrorCode, status?: number) {
    super(message)
    this.name = 'SearchRunApiError'
    this.code = code
    this.status = status
  }
}

export function isActiveSearchRun(status: SearchRunStatus) {
  return activeStatuses.includes(status as (typeof activeStatuses)[number])
}

export function isValidSearchContentUrl(
  platform: SearchPlatform,
  platformContentId: string,
  value: string,
) {
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return false
  }
  const hostname = url.hostname.toLowerCase().replace(/\.$/u, '')
  if (
    url.username !== '' ||
    url.password !== '' ||
    url.port !== '' ||
    url.hash !== ''
  ) {
    return false
  }
  if (platform === 'wb') {
    return (
      value === `https://m.weibo.cn/detail/${platformContentId}` &&
      url.protocol === 'https:' &&
      hostname === 'm.weibo.cn' &&
      url.search === ''
    )
  }
  return false
}

async function request(path: string, init: RequestInit) {
  try {
    return await fetch(`${getApiBaseUrl()}${path}`, init)
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw error
    }
    throw new SearchRunApiError(
      '无法连接本机后端服务，请确认服务已经启动。',
      'service_unavailable',
    )
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw invalidResponse(response.status)
  }
}

function invalidResponse(status: number) {
  return new SearchRunApiError(
    '后端返回了无法识别的数据，请重新启动服务后再试。',
    'invalid_response',
    status,
  )
}

function errorFromResponse(status: number, payload: unknown) {
  const parsed = errorEnvelopeSchema.safeParse(payload)
  if (parsed.success && parsed.data.detail.code in productErrorContracts) {
    const code = parsed.data.detail.code as ProductErrorCode
    const contract = productErrorContracts[code]
    if (
      contract.status !== status ||
      contract.message !== parsed.data.detail.message
    ) {
      return invalidResponse(status)
    }
    return new SearchRunApiError(contract.message, code, status)
  }
  return new SearchRunApiError(
    `采集任务请求失败（HTTP ${status}）`,
    'request_failed',
    status,
  )
}

async function parseResponse<T>(
  response: Response,
  expectedStatus: number,
  schema: z.ZodType<T>,
) {
  const payload = await readJson(response)
  if (!response.ok) {
    throw errorFromResponse(response.status, payload)
  }
  if (response.status !== expectedStatus) {
    throw invalidResponse(response.status)
  }
  const parsed = schema.safeParse(payload)
  if (!parsed.success) {
    throw invalidResponse(response.status)
  }
  return parsed.data
}

export async function startSearchRun(
  input: {
    monitoring_rule_id: number
    platform?: SearchPlatform
    max_results_per_term: number
  },
  signal?: AbortSignal,
) {
  if (input.platform !== undefined && input.platform !== 'wb') {
    throw new SearchRunApiError('当前版本仅支持微博采集。', 'invalid_request')
  }
  const response = await request('/search-runs', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  })
  return parseResponse(response, 202, searchRunDetailSchema)
}

export async function fetchSearchRuns(
  signal: AbortSignal,
  options: {
    limit?: number
    beforeId?: number
    scope?: 'all' | 'standalone'
  } = {},
) {
  const query = new URLSearchParams({ limit: String(options.limit ?? 20) })
  if (options.scope !== undefined) {
    query.set('scope', options.scope)
  }
  if (options.beforeId !== undefined) {
    query.set('before_id', String(options.beforeId))
  }
  const response = await request(`/search-runs?${query}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  return parseResponse(response, 200, searchRunListSchema)
}

export async function fetchSearchRun(runId: number, signal: AbortSignal) {
  const response = await request(
    `/search-runs/${encodeURIComponent(String(runId))}`,
    { headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 200, searchRunDetailSchema)
}

export async function fetchSearchRunResults(
  runId: number,
  filter: SearchResultFilter,
  signal: AbortSignal,
  options: { limit?: number; offset?: number } = {},
) {
  const query = new URLSearchParams({
    kind: filter,
    limit: String(options.limit ?? 50),
    offset: String(options.offset ?? 0),
  })
  const response = await request(
    `/search-runs/${encodeURIComponent(String(runId))}/results?${query}`,
    { headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 200, searchResultListSchema)
}

export async function cancelSearchRun(runId: number, signal?: AbortSignal) {
  const response = await request(
    `/search-runs/${encodeURIComponent(String(runId))}/cancel`,
    { method: 'POST', headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 202, searchRunDetailSchema)
}

export async function openSearchRunResult(
  runId: number,
  resultId: number,
  signal?: AbortSignal,
) {
  const response = await request(
    `/search-runs/${encodeURIComponent(String(runId))}/results/${encodeURIComponent(String(resultId))}/open`,
    { method: 'POST', headers: { Accept: 'application/json' }, signal },
  )
  return parseResponse(response, 200, searchResultOpenResponseSchema)
}
