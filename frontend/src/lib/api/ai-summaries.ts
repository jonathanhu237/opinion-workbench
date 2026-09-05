import { z } from 'zod'

import { AI_ERROR_CONTRACTS } from '@/lib/api/ai-settings'
import { getApiBaseUrl } from '@/lib/api/client'
import {
  isActiveSearchRun,
  isValidSearchContentUrl,
  isoDateSchema,
  searchPlatformSchema,
  searchRunStatusSchema,
} from '@/lib/api/search-runs'
import {
  codePointLength,
  MAX_TERM_LENGTH,
  MAX_TERMS_PER_RULE,
} from '@/lib/monitoring-rule-composition'

export const AI_SUMMARIES_QUERY_KEY = ['ai-summaries'] as const
const nonnegativeInteger = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER)
const positiveInteger = nonnegativeInteger.min(1)
const count = nonnegativeInteger.max(100)
const statusSchema = z.enum([
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
  'interrupted',
])
const decisionSchema = z.enum(['relevant', 'irrelevant', 'uncertain'])

// Match Pydantic's code-point bounds without trimming or truncating saved text.
function boundedText(max: number, min = 0) {
  return z.string().refine((value) => {
    const length = codePointLength(value)
    return length >= min && length <= max
  })
}

const failureMessages = {
  input_incomplete: '正文或媒体不完整，本条未调用模型。',
  source_changed: '原始内容已变化，请重新生成汇总。',
  source_active: '采集任务尚未结束，请结束后再试。',
  browser_operation_active: '谷歌浏览器正在执行其他操作，请结束后再试。',
  browser_unavailable:
    '专用浏览器不可用，本次任务已停止。请在平台账号中检查浏览器后重新生成。',
  acquisition_failed: '未能获取完整内容，请检查平台登录状态后重试。',
  source_access_denied: '平台暂时拒绝访问，未能读取原文；未判定为安全验证。',
  source_content_unavailable: '原帖已删除或不可读取，未使用搜索摘要代替正文。',
  platform_not_supported:
    '该采集结果尚未完成正文和媒体补全；已有内容及成功总结仍可使用。',
  source_structure_changed: '原文返回结构无法识别，未提交模型。',
  acquisition_timed_out: '原文获取超过本次时限，未自动重试。',
  stored_content_unavailable:
    '已保存材料不足以分析，且此获取路径尚未接入；未访问平台账号。',
  invalid_enrichment: '获取的内容格式无法识别，本条未调用模型。',
  unsupported_model: '当前模型配置的媒体输入尚未支持，请检查 AI 配置。',
  request_too_large: '内容超出模型输入限制，未继续调用模型。',
  invalid_json: '模型返回的内容不是有效的 JSON，本步结果未保存。',
  invalid_schema: '模型返回的格式不正确，本步结果未保存。',
  invalid_citations: '模型汇总中的引用无法对应原文，汇总未保存。',
  credential_leakage: '模型返回了不应包含的敏感信息，结果未保存。',
  ai_destination_forbidden: AI_ERROR_CONTRACTS.ai_destination_forbidden.message,
  ai_authentication_failed: AI_ERROR_CONTRACTS.ai_authentication_failed.message,
  ai_model_not_found: AI_ERROR_CONTRACTS.ai_model_not_found.message,
  ai_rate_limited: AI_ERROR_CONTRACTS.ai_rate_limited.message,
  ai_provider_unavailable: AI_ERROR_CONTRACTS.ai_provider_unavailable.message,
  ai_timeout: AI_ERROR_CONTRACTS.ai_timeout.message,
  ai_invalid_response: AI_ERROR_CONTRACTS.ai_invalid_response.message,
  ai_unsupported_input: AI_ERROR_CONTRACTS.ai_unsupported_input.message,
  ai_request_too_large: AI_ERROR_CONTRACTS.ai_request_too_large.message,
  cancelled: '已取消，已完成的内容分析仍然保留。',
  interrupted: '上次分析已中断，已完成的内容分析仍然保留。',
  internal_error: '分析暂时无法完成，请稍后重试。',
  storage_unavailable: '分析结果暂时无法读取或保存，请稍后重试。',
} as const

const acquisitionDiagnosticSchema = z.strictObject({
  stage: z.enum(['detail', 'media', 'browser']),
  outcome: z.enum([
    'browser_unavailable',
    'access_denied',
    'asset_blocked',
    'asset_unavailable',
    'content_unavailable',
    'login_required',
    'manual_challenge_required',
    'media_limit',
    'media_redirect',
    'parser_failed',
    'platform_blocked_or_rate_limited',
    'structure_changed',
  ]),
  status_code: z.number().int().min(100).max(599).nullable(),
  basis: z.enum([
    'http_status',
    'explicit_platform_evidence',
    'login_redirect',
    'platform_payload',
    'browser_dom_evidence',
    'upstream_exception',
    'transport',
  ]),
  asset_position: z.number().int().min(0).max(24).nullable(),
  target: z.enum(['selected_post', 'media_asset', 'search_page']),
})

const failureSchema = z
  .strictObject({
    stage: z.enum([
      'acquisition',
      'input',
      'analysis',
      'composition',
      'execution',
    ]),
    code: z.enum(
      Object.keys(failureMessages) as [
        keyof typeof failureMessages,
        ...(keyof typeof failureMessages)[],
      ],
    ),
    message: z.string().max(1000),
    diagnostic: acquisitionDiagnosticSchema.nullable().optional(),
    validation_issues: z
      .array(z.string().max(200))
      .max(8)
      .nullable()
      .optional(),
  })
  .transform((failure): typeof failure => ({
    ...failure,
    message: failureMessages[failure.code],
  }))

const tokenDetailsSchema = z.strictObject({
  text_tokens: nonnegativeInteger.nullable().optional(),
  image_tokens: nonnegativeInteger.nullable().optional(),
  video_tokens: nonnegativeInteger.nullable().optional(),
  audio_tokens: nonnegativeInteger.nullable().optional(),
  cached_tokens: nonnegativeInteger.nullable().optional(),
})
const tokenUsageSchema = z
  .strictObject({
    prompt_tokens: nonnegativeInteger,
    completion_tokens: nonnegativeInteger,
    total_tokens: nonnegativeInteger,
    prompt_tokens_details: tokenDetailsSchema.nullable(),
    completion_tokens_details: tokenDetailsSchema.nullable(),
  })
  .refine(
    (value) =>
      value.prompt_tokens + value.completion_tokens === value.total_tokens,
  )

const summaryUsageSchema = z
  .strictObject({
    attempted_requests: nonnegativeInteger.max(101),
    accounted_requests: nonnegativeInteger.max(101),
    complete: z.boolean(),
    prompt_tokens: nonnegativeInteger.nullable(),
    completion_tokens: nonnegativeInteger.nullable(),
    total_tokens: nonnegativeInteger.nullable(),
  })
  .refine((value) => {
    if (value.accounted_requests > value.attempted_requests) return false
    if (
      value.prompt_tokens === null &&
      value.completion_tokens === null &&
      value.total_tokens === null
    ) {
      // Valid per-attempt counts may have an aggregate outside the JS-safe range.
      return value.attempted_requests > 0 && !value.complete
    }
    if (
      value.prompt_tokens === null ||
      value.completion_tokens === null ||
      value.total_tokens === null
    )
      return false
    return (
      value.complete ===
        (value.accounted_requests === value.attempted_requests) &&
      (value.attempted_requests === 0 || value.accounted_requests > 0) &&
      value.prompt_tokens + value.completion_tokens === value.total_tokens &&
      (value.attempted_requests !== 0 || value.total_tokens === 0)
    )
  })

const countsSchema = z
  .strictObject({
    total: count.min(1),
    pending: count,
    analysing: count,
    relevant: count,
    irrelevant: count,
    uncertain: count,
    input_incomplete: count,
    failed: count,
    cancelled: count,
    interrupted: count,
    reused: count,
  })
  .refine(
    (value) =>
      value.total ===
        value.pending +
          value.analysing +
          value.relevant +
          value.irrelevant +
          value.uncertain +
          value.input_incomplete +
          value.failed +
          value.cancelled +
          value.interrupted &&
      value.reused <= value.relevant + value.irrelevant + value.uncertain,
  )

const documentSchema = z.strictObject({
  overview: boundedText(2000, 1),
  items: z
    .array(
      z.strictObject({
        text: boundedText(2000, 1),
        source_ids: z
          .array(positiveInteger)
          .min(1)
          .max(100)
          .refine((ids) => new Set(ids).size === ids.length),
      }),
    )
    .max(100),
})

const summaryRunSchema = z
  .strictObject({
    id: positiveInteger,
    request_id: z.uuidv4(),
    source_run_id: positiveInteger,
    platform: searchPlatformSchema,
    source_run_status: searchRunStatusSchema.refine(
      (status) => !isActiveSearchRun(status),
    ),
    rule_name: boundedText(100, 1),
    terms: z
      .array(boundedText(MAX_TERM_LENGTH, 1))
      .min(1)
      .max(MAX_TERMS_PER_RULE),
    configuration_revision: positiveInteger,
    base_url: z.string().url().max(2048),
    model: z.string().min(1).max(200),
    force_refresh: z.boolean(),
    status: statusSchema,
    phase: z.enum(['analysing', 'summarising']),
    counts: countsSchema,
    usage: summaryUsageSchema,
    document: documentSchema.nullable(),
    error: failureSchema.nullable(),
    created_at: isoDateSchema,
    started_at: isoDateSchema.nullable(),
    finished_at: isoDateSchema.nullable(),
  })
  .superRefine((value, context) => {
    const active = isActiveAISummary(value.status)
    if (
      active !== (value.finished_at === null) ||
      (value.status === 'queued' && value.started_at !== null) ||
      (!active && value.counts.pending + value.counts.analysing !== 0) ||
      (value.status === 'completed') !== (value.document !== null) ||
      (value.document &&
        (value.counts.relevant === 0) !== (value.document.items.length === 0))
    ) {
      context.addIssue({
        code: 'custom',
        message: 'inconsistent summary state',
      })
    }
  })

const sourceSchema = z
  .strictObject({
    source_run_id: positiveInteger,
    result_id: positiveInteger,
    platform: searchPlatformSchema,
    platform_content_id: z.string().min(1).max(128),
    content_type: z.string().min(1).max(32),
    title: boundedText(300, 1),
    snippet: boundedText(1000),
    content_url: z.string().url(),
    published_at_text: boundedText(100),
    matched_terms: z.array(z.string().min(1)).min(1).max(MAX_TERMS_PER_RULE),
  })
  .refine((value) =>
    isValidSearchContentUrl(
      value.platform,
      value.platform_content_id,
      value.content_url,
    ),
  )

export const inputIssueSchema = z.enum([
  'text_incomplete',
  'text_unavailable',
  'text_limit',
  'inventory_unknown',
  'media_missing',
  'cover_only',
  'asset_unavailable',
  'asset_expired',
  'download_failed',
  'download_timeout',
  'asset_blocked',
  'unsafe_media_url',
  'media_redirect',
  'media_limit',
  'image_limit',
  'video_limit',
  'invalid_media',
  'unsupported_transport',
  'unsupported_media_type',
  'unsupported_codec',
  'audio_missing',
  'audio_unknown',
  'probe_unavailable',
  'probe_failed',
  'structure_changed',
])
const evidenceModalityCoverageSchema = z
  .strictObject({
    expected: count.max(25),
    ready: count.max(25),
    failed: count.max(25),
    unknown: count.max(25),
  })
  .refine((value) => value.ready + value.failed <= value.expected)
export const evidenceCoverageSchema = z
  .strictObject({
    schema_version: z.literal('evidence-coverage-v1'),
    input_contract_version: z.literal('analysis-evidence-v2'),
    level: z.enum([
      'search_preview',
      'detail_text',
      'validated_media',
      'full_source',
    ]),
    text_origin: z.enum(['search_preview', 'detail']),
    text_available: z.boolean(),
    text_complete: z.boolean(),
    text: evidenceModalityCoverageSchema,
    image: evidenceModalityCoverageSchema,
    video: evidenceModalityCoverageSchema,
    audio: evidenceModalityCoverageSchema,
    issues: z.array(inputIssueSchema).max(32),
  })
  .superRefine((coverage, context) => {
    const textReady = coverage.text_available ? 1 : 0
    const textFailed = coverage.text_available ? 0 : 1
    if (
      coverage.text.expected !== 1 ||
      coverage.text.ready !== textReady ||
      coverage.text.failed !== textFailed ||
      coverage.text.unknown !== 0 ||
      (!coverage.text_available && coverage.text_complete) ||
      (coverage.text_origin === 'search_preview' &&
        (coverage.level !== 'search_preview' || coverage.text_complete)) ||
      (coverage.level === 'full_source' &&
        (coverage.text_origin !== 'detail' ||
          !coverage.text_available ||
          !coverage.text_complete ||
          coverage.issues.length > 0 ||
          [coverage.image, coverage.video, coverage.audio].some(
            (modality) =>
              modality.unknown > 0 ||
              modality.failed > 0 ||
              modality.ready !== modality.expected,
          ))) ||
      (coverage.level === 'validated_media' &&
        coverage.image.ready + coverage.video.ready + coverage.audio.ready ===
          0) ||
      new Set(coverage.issues).size !== coverage.issues.length
    ) {
      context.addIssue({
        code: 'custom',
        message: 'inconsistent evidence coverage',
      })
    }
    if (coverage.text_origin === 'search_preview') {
      for (const modality of [coverage.image, coverage.video, coverage.audio]) {
        if (
          modality.expected !== 0 ||
          modality.ready !== 0 ||
          modality.failed !== 0 ||
          modality.unknown !== 1
        ) {
          context.addIssue({
            code: 'custom',
            message: 'preview coverage contains unseen media',
          })
          break
        }
      }
    }
  })
const summaryItemSchema = z
  .strictObject({
    id: positiveInteger,
    summary_run_id: positiveInteger,
    position: count.max(99),
    source: sourceSchema,
    status: z.enum([
      'pending',
      'analysing',
      'completed',
      'input_incomplete',
      'failed',
      'cancelled',
      'interrupted',
    ]),
    decision: decisionSchema.nullable(),
    reason: boundedText(300, 1).nullable(),
    evidence_summary: boundedText(1000, 1).nullable(),
    reused_from_item_id: positiveInteger.nullable(),
    attempted: z.boolean(),
    usage: tokenUsageSchema.nullable(),
    input_status: z
      .enum(['ready', 'partial', 'unavailable', 'unsupported'])
      .nullable(),
    input_issues: z.array(inputIssueSchema).max(32),
    error: failureSchema.nullable(),
    started_at: isoDateSchema.nullable(),
    finished_at: isoDateSchema.nullable(),
  })
  .superRefine((value, context) => {
    const complete = value.status === 'completed'
    const hasAnalysis =
      value.decision !== null &&
      value.reason !== null &&
      value.evidence_summary !== null
    const noAnalysis =
      value.decision === null &&
      value.reason === null &&
      value.evidence_summary === null
    const reused = value.reused_from_item_id !== null
    if (
      (complete ? !hasAnalysis : !noAnalysis) ||
      (reused && (!complete || value.attempted || value.usage !== null)) ||
      (!reused && complete && !value.attempted) ||
      (!value.attempted && value.usage !== null) ||
      (complete &&
        (value.input_status !== 'ready' ||
          value.error !== null ||
          value.input_issues.length > 0)) ||
      (value.status === 'pending' || value.status === 'analysing') !==
        (value.finished_at === null)
    ) {
      context.addIssue({
        code: 'custom',
        message: 'inconsistent analysis state',
      })
    }
  })

const listSchema = z.strictObject({
  summaries: z.array(summaryRunSchema).max(50),
  next_before_id: positiveInteger.nullable(),
})
const itemsSchema = z.strictObject({
  items: z.array(summaryItemSchema).max(100),
  total: count.min(1),
  limit: positiveInteger.max(100),
  offset: nonnegativeInteger,
})

export type AISummaryRun = z.infer<typeof summaryRunSchema>
export type AISummaryItem = z.infer<typeof summaryItemSchema>
export type AISummarySource = AISummaryItem['source']
export type AISummaryUsage = AISummaryRun['usage']
export type AISummaryList = z.infer<typeof listSchema>
export type AISummaryItems = z.infer<typeof itemsSchema>
export type AISummaryRequest = {
  request_id: string
  force_refresh: boolean
  configuration_revision: number
}

// Shared evidence contracts are also consumed by independent initial analysis.
// Keep the legacy bounds/validation unchanged when reusing these primitives.
export {
  boundedText as boundedAnalysisText,
  failureSchema as summaryFailureSchema,
  sourceSchema as summarySourceSchema,
  tokenUsageSchema,
}

export const SUMMARY_ERROR_CONTRACTS = {
  ...AI_ERROR_CONTRACTS,
  search_run_not_found: { status: 404, message: '采集任务不存在。' },
  ai_summary_not_found: { status: 404, message: '汇总记录不存在。' },
  ai_summary_source_active: {
    status: 409,
    message: '采集任务尚未结束，请结束后再生成汇总。',
  },
  ai_summary_request_conflict: {
    status: 409,
    message: '此请求已用于其他汇总，请刷新后重试。',
  },
  browser_operation_active: {
    status: 409,
    message: '浏览器正在执行其他操作，请结束后再试。',
  },
  ai_summary_empty_source: {
    status: 422,
    message: '采集任务没有结果，暂时无法生成汇总。',
  },
  ai_summary_source_limit: {
    status: 422,
    message: '一次最多汇总 100 条内容，请缩小采集范围。',
  },
  ai_summary_storage_unavailable: {
    status: 503,
    message: '汇总记录暂时无法读取或保存，请稍后重试。',
  },
  ai_summary_unavailable: {
    status: 503,
    message: '汇总服务暂时不可用，请稍后重试。',
  },
} as const
type ProductCode = keyof typeof SUMMARY_ERROR_CONTRACTS
type ErrorCode = ProductCode | 'invalid_response' | 'service_unavailable'

export class AISummaryApiError extends Error {
  override name = 'AISummaryApiError'
  readonly code: ErrorCode
  readonly status?: number
  constructor(code: ErrorCode, status?: number) {
    super(
      code === 'invalid_response'
        ? '汇总接口返回的数据与当前应用不匹配。'
        : code === 'service_unavailable'
          ? '无法连接本机后端服务，请确认服务已经启动。'
          : SUMMARY_ERROR_CONTRACTS[code].message,
    )
    this.code = code
    this.status = status
  }
}

function isProductCode(code: string): code is ProductCode {
  return Object.hasOwn(SUMMARY_ERROR_CONTRACTS, code)
}

export function isActiveAISummary(status: z.infer<typeof statusSchema>) {
  return status === 'queued' || status === 'running'
}

async function request(
  path: string,
  init: RequestInit,
  status: number,
): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
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
    throw new AISummaryApiError('service_unavailable')
  }
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new AISummaryApiError('invalid_response', response.status)
  }
  if (!response.ok) {
    const parsed = z
      .strictObject({
        detail: z.strictObject({ code: z.string(), message: z.string() }),
      })
      .safeParse(payload)
    if (
      parsed.success &&
      isProductCode(parsed.data.detail.code) &&
      SUMMARY_ERROR_CONTRACTS[parsed.data.detail.code].status ===
        response.status
    ) {
      throw new AISummaryApiError(parsed.data.detail.code, response.status)
    }
    throw new AISummaryApiError('invalid_response', response.status)
  }
  if (response.status !== status)
    throw new AISummaryApiError('invalid_response', response.status)
  return payload
}

function decode<T>(schema: z.ZodType<T>, payload: unknown, status = 200): T {
  const parsed = schema.safeParse(payload)
  if (!parsed.success) throw new AISummaryApiError('invalid_response', status)
  return parsed.data
}

export async function fetchAISummaries(
  sourceRunId: number,
  signal: AbortSignal,
  beforeId: number | null = null,
): Promise<AISummaryList> {
  const query = new URLSearchParams({ limit: '20' })
  if (beforeId !== null) query.set('before_id', String(beforeId))
  const data = decode(
    listSchema,
    await request(
      `/search-runs/${sourceRunId}/ai-summaries?${query}`,
      { signal },
      200,
    ),
  )
  if (
    data.summaries.some(
      (run, index) =>
        run.source_run_id !== sourceRunId ||
        (beforeId !== null && run.id >= beforeId) ||
        (index > 0 && run.id >= data.summaries[index - 1].id),
    ) ||
    (data.next_before_id !== null &&
      data.next_before_id !== data.summaries.at(-1)?.id)
  )
    throw new AISummaryApiError('invalid_response', 200)
  return data
}

export async function fetchAISummary(
  summaryId: number,
  signal: AbortSignal,
): Promise<AISummaryRun> {
  const data = decode(
    summaryRunSchema,
    await request(`/ai-summaries/${summaryId}`, { signal }, 200),
  )
  if (data.id !== summaryId)
    throw new AISummaryApiError('invalid_response', 200)
  return data
}

export async function fetchAISummaryItems(
  summaryId: number,
  signal: AbortSignal,
): Promise<AISummaryItems> {
  const data = decode(
    itemsSchema,
    await request(
      `/ai-summaries/${summaryId}/items?limit=100&offset=0`,
      { signal },
      200,
    ),
  )
  if (
    data.limit !== 100 ||
    data.offset !== 0 ||
    data.items.length !== data.total ||
    new Set(data.items.map((item) => item.id)).size !== data.items.length ||
    new Set(data.items.map((item) => item.source.result_id)).size !==
      data.items.length ||
    data.items.some(
      (item, position) =>
        item.summary_run_id !== summaryId || item.position !== position,
    )
  )
    throw new AISummaryApiError('invalid_response', 200)
  return data
}

export async function startAISummary(
  sourceRunId: number,
  intent: AISummaryRequest,
): Promise<AISummaryRun> {
  const data = decode(
    summaryRunSchema,
    await request(
      `/search-runs/${sourceRunId}/ai-summaries`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(intent),
      },
      202,
    ),
    202,
  )
  if (
    data.source_run_id !== sourceRunId ||
    data.request_id !== intent.request_id ||
    data.configuration_revision !== intent.configuration_revision ||
    data.force_refresh !== intent.force_refresh
  )
    throw new AISummaryApiError('invalid_response', 202)
  return data
}

export async function cancelAISummary(
  summaryId: number,
): Promise<AISummaryRun> {
  const data = decode(
    summaryRunSchema,
    await request(
      `/ai-summaries/${summaryId}/cancel`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      },
      200,
    ),
  )
  if (data.id !== summaryId || isActiveAISummary(data.status))
    throw new AISummaryApiError('invalid_response', 200)
  return data
}

// Validate citations against all frozen items, never against the current display page.
export function validateAISummarySources(
  summary: AISummaryRun,
  items: AISummaryItem[],
) {
  if (
    items.length !== summary.counts.total ||
    items.some(
      (item) =>
        item.summary_run_id !== summary.id ||
        item.source.source_run_id !== summary.source_run_id ||
        item.source.platform !== summary.platform,
    )
  )
    return false
  const relevantIds = new Set(
    items
      .filter(
        (item) => item.status === 'completed' && item.decision === 'relevant',
      )
      .map((item) => item.source.result_id),
  )
  return (
    summary.document === null ||
    summary.document.items.every((entry) =>
      entry.source_ids.every((id) => relevantIds.has(id)),
    )
  )
}
