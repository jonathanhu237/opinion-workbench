import { z } from 'zod'

import {
  boundedAnalysisText,
  evidenceCoverageSchema,
  inputIssueSchema,
  summaryFailureSchema,
  summarySourceSchema,
  tokenUsageSchema,
} from '@/lib/api/ai-summaries'
import {
  promptVersionSchema,
  type PromptChoice,
} from '@/lib/api/analysis-settings'
import {
  AnalysisApiError,
  analysisPageSchema,
  analysisRequest,
  checkPage,
  decodeAnalysis,
  jsonMutation,
  isValidAnalysisProse,
  modelRetryNoticeSchema,
  safeCount,
  safeId,
  uniqueIds,
} from '@/lib/api/analysis-shared'
import { isoDateSchema } from '@/lib/api/search-runs'
import {
  platformAccessDiagnosticSchema,
  platformAccessSnapshotSchema,
} from '@/lib/api/platform-access'
import { codePointLength } from '@/lib/monitoring-rule-composition'

export const CONTENT_ANALYSES_QUERY_KEY = ['content-analyses'] as const
export const CONTENT_ANALYSIS_JOBS_QUERY_KEY = [
  'content-analysis-jobs',
] as const
export const ANALYSIS_PAGE_SIZE = 20
const fingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/u)
const initialFailureSchema = summaryFailureSchema.transform((failure) => ({
  ...failure,
  message:
    failure.code === 'source_changed'
      ? '原始内容已变化，请明确重新获取并分析。'
      : failure.message,
}))
export const attemptStatusSchema = z.enum([
  'queued',
  'acquiring',
  'analysing',
  'completed',
  'input_incomplete',
  'unsupported',
  'failed',
  'cancelled',
  'interrupted',
])
const jobStatusSchema = z.enum([
  'queued',
  'running',
  'completed',
  'cancelled',
  'interrupted',
  'configuration_blocked',
])
export const understandingSchema = z
  .strictObject({
    summary: boundedAnalysisText(1500, 1),
    location_clues: z
      .array(
        z.strictObject({
          excerpt: boundedAnalysisText(200, 1),
          modality: z.enum(['text', 'image', 'video', 'audio']),
        }),
      )
      .max(12),
    time_context: boundedAnalysisText(500, 1),
    media_observations: z.array(boundedAnalysisText(400, 1)).max(12),
    uncertainties: boundedAnalysisText(500, 1),
  })
  .refine(
    (value) =>
      [
        value.summary,
        value.time_context,
        value.uncertainties,
        ...value.location_clues.map((clue) => clue.excerpt),
        ...value.media_observations,
      ].reduce((sum, text) => sum + codePointLength(text), 0) <= 6000 &&
      [
        value.summary,
        value.time_context,
        value.uncertainties,
        ...value.location_clues.map((clue) => clue.excerpt),
        ...value.media_observations,
      ].every(isValidAnalysisProse),
  )

const assetSchema = z
  .strictObject({
    position: safeCount.max(24),
    kind: z.enum(['image', 'video']),
    status: z.enum(['ready', 'unavailable', 'unsupported', 'failed']),
    sha256: fingerprintSchema.nullable(),
    mime_type: z
      .enum(['image/jpeg', 'image/png', 'image/webp', 'video/mp4'])
      .nullable(),
    byte_size: safeId.max(6 * 1024 * 1024).nullable(),
    width: safeId.max(32768).nullable(),
    height: safeId.max(32768).nullable(),
    duration_ms: safeId.nullable(),
    audio_track: z.enum(['present', 'absent', 'unknown', 'not_applicable']),
    coverage: z.enum(['complete', 'partial', 'unknown']),
    issue_code: inputIssueSchema.nullable(),
  })
  .refine((asset) => {
    if (asset.status !== 'ready')
      return (
        asset.sha256 === null &&
        asset.mime_type === null &&
        asset.byte_size === null &&
        asset.width === null &&
        asset.height === null &&
        asset.duration_ms === null &&
        asset.coverage === 'unknown' &&
        asset.issue_code !== null &&
        asset.audio_track ===
          (asset.kind === 'image' ? 'not_applicable' : 'unknown')
      )
    if (
      asset.sha256 === null ||
      asset.mime_type === null ||
      asset.byte_size === null ||
      asset.width === null ||
      asset.height === null ||
      asset.coverage !== 'complete' ||
      asset.issue_code !== null
    )
      return false
    return asset.kind === 'image'
      ? asset.mime_type.startsWith('image/') &&
          asset.duration_ms === null &&
          asset.audio_track === 'not_applicable' &&
          asset.width * asset.height <= 40000000
      : asset.mime_type === 'video/mp4' &&
          asset.duration_ms !== null &&
          asset.audio_track === 'present'
  })
const savedInputSchema = z
  .strictObject({
    schema_version: z.literal(1),
    extractor_version: boundedAnalysisText(200, 1),
    acquired_at: safeId.min(1000000000000).max(9999999999999),
    status: z.enum(['ready', 'partial', 'unavailable', 'unsupported']),
    text: z.strictObject({
      title: boundedAnalysisText(1000),
      body: boundedAnalysisText(20000),
      coverage: z.enum(['complete', 'partial', 'unavailable']),
    }),
    detected_modalities: z
      .array(z.enum(['text', 'image', 'video', 'audio', 'unknown']))
      .min(1)
      .max(5),
    media_inventory_complete: z.boolean(),
    assets: z.array(assetSchema).max(25),
    issues: z.array(inputIssueSchema).max(32),
    coverage: evidenceCoverageSchema.nullable().optional(),
  })
  .refine((input) => {
    if (!uniqueIds(input.assets.map((asset) => asset.position))) return false
    if (input.coverage) {
      const textAvailable =
        input.text.title.trim().length > 0 || input.text.body.trim().length > 0
      const preview = input.extractor_version.endsWith('-search-preview-v1')
      if (
        input.coverage.text_available !== textAvailable ||
        input.coverage.text_complete !==
          (textAvailable && input.text.coverage === 'complete') ||
        input.coverage.text.ready !== (textAvailable ? 1 : 0) ||
        input.coverage.text.failed !== (textAvailable ? 0 : 1) ||
        (input.coverage.text_origin === 'search_preview') !== preview ||
        (input.status === 'ready' && textAvailable) !==
          (input.coverage.level === 'full_source') ||
        (preview &&
          (input.status === 'ready' ||
            input.assets.length > 0 ||
            input.media_inventory_complete ||
            input.detected_modalities.join(',') !== 'text,unknown'))
      )
        return false
    }
    if (input.status !== 'ready') return true
    const actualMedia = new Set(input.assets.map((asset) => asset.kind))
    return (
      input.text.coverage === 'complete' &&
      input.media_inventory_complete &&
      input.issues.length === 0 &&
      !input.detected_modalities.includes('unknown') &&
      actualMedia.has('image') ===
        input.detected_modalities.includes('image') &&
      actualMedia.has('video') ===
        input.detected_modalities.includes('video') &&
      actualMedia.has('video') ===
        input.detected_modalities.includes('audio') &&
      input.assets.every((asset) => asset.status === 'ready') &&
      codePointLength(input.text.title + input.text.body) <= 20000 &&
      input.assets.reduce((sum, asset) => sum + (asset.byte_size ?? 0), 0) <=
        6 * 1024 * 1024 &&
      input.assets.filter((asset) => asset.kind === 'video').length <= 1 &&
      input.assets.filter((asset) => asset.kind === 'image').length <= 24
    )
  })

export const analysisAttemptSchema = z
  .strictObject({
    id: safeId,
    job_id: safeId,
    position: safeCount,
    source: summarySourceSchema,
    first_seen_at: isoDateSchema,
    status: attemptStatusSchema,
    output: understandingSchema.nullable(),
    input: savedInputSchema.nullable(),
    input_fingerprint: fingerprintSchema.nullable(),
    reused_from_attempt_id: safeId.nullable(),
    attempted: z.boolean(),
    usage: tokenUsageSchema.nullable(),
    error: initialFailureSchema.nullable(),
    created_at: isoDateSchema,
    started_at: isoDateSchema.nullable(),
    finished_at: isoDateSchema.nullable(),
  })
  .refine((value) => {
    const completed = value.status === 'completed'
    const reused = value.reused_from_attempt_id !== null
    return (
      completed === (value.output !== null) &&
      isActiveAnalysisAttempt(value.status) === (value.finished_at === null) &&
      (!completed ||
        (value.input !== null &&
          (value.input.text.title.trim().length > 0 ||
            value.input.text.body.trim().length > 0 ||
            value.input.assets.some((asset) => asset.status === 'ready')) &&
          value.input_fingerprint !== null &&
          value.error === null &&
          (value.attempted || reused))) &&
      (!reused ||
        (completed &&
          !value.attempted &&
          value.usage === null &&
          value.reused_from_attempt_id !== value.id)) &&
      (value.attempted || value.usage === null)
    )
  })

export const analysisUsageSchema = z
  .strictObject({
    attempted_requests: safeCount,
    accounted_requests: safeCount,
    complete: z.boolean(),
    prompt_tokens: safeCount.nullable(),
    completion_tokens: safeCount.nullable(),
    total_tokens: safeCount.nullable(),
  })
  .refine((usage) => {
    if (usage.accounted_requests > usage.attempted_requests) return false
    if (
      usage.prompt_tokens === null &&
      usage.completion_tokens === null &&
      usage.total_tokens === null
    )
      return usage.attempted_requests > 0 && !usage.complete
    if (
      usage.prompt_tokens === null ||
      usage.completion_tokens === null ||
      usage.total_tokens === null
    )
      return false
    return (
      usage.prompt_tokens + usage.completion_tokens === usage.total_tokens &&
      usage.complete ===
        (usage.attempted_requests === usage.accounted_requests) &&
      (usage.attempted_requests === 0
        ? usage.total_tokens === 0
        : usage.accounted_requests > 0)
    )
  })
const countsSchema = z
  .strictObject({
    total: safeId,
    queued: safeCount,
    acquiring: safeCount,
    analysing: safeCount,
    completed: safeCount,
    input_incomplete: safeCount,
    unsupported: safeCount,
    failed: safeCount,
    cancelled: safeCount,
    interrupted: safeCount,
    reused: safeCount,
  })
  .refine(
    (value) =>
      value.total ===
        value.queued +
          value.acquiring +
          value.analysing +
          value.completed +
          value.input_incomplete +
          value.unsupported +
          value.failed +
          value.cancelled +
          value.interrupted && value.reused <= value.completed,
  )
export const analysisJobSchema = z
  .strictObject({
    id: safeId,
    request_id: z
      .uuidv4()
      .refine((value) => value === value.toLowerCase())
      .nullable(),
    trigger: z.enum(['manual', 'automatic']),
    status: jobStatusSchema,
    configuration_revision: safeId,
    base_url: z.url(),
    model: boundedAnalysisText(200, 1),
    initial_prompt: promptVersionSchema.refine(
      (value) => value.stage === 'initial',
    ),
    report_prompt: promptVersionSchema.refine(
      (value) => value.stage === 'report',
    ),
    force_refresh: z.boolean(),
    summary_concurrency: z
      .union([
        z.literal(1),
        z.literal(2),
        z.literal(4),
        z.literal(8),
        z.literal(16),
      ])
      .optional()
      .default(1),
    platform_access_snapshot: platformAccessSnapshotSchema
      .nullable()
      .optional()
      .default(null),
    access_waiting: z.boolean().optional().default(false),
    access_notice: platformAccessDiagnosticSchema
      .nullable()
      .optional()
      .default(null),
    model_retry_notice: modelRetryNoticeSchema
      .nullable()
      .optional()
      .default(null),
    counts: countsSchema,
    usage: analysisUsageSchema,
    queue_reason: z
      .enum(['ai_operation_active', 'browser_operation_active'])
      .nullable(),
    completion_event_id: safeId.nullable(),
    created_at: isoDateSchema,
    started_at: isoDateSchema.nullable(),
    finished_at: isoDateSchema.nullable(),
  })
  .refine(
    (job) =>
      isActiveAnalysisJob(job.status) === (job.finished_at === null) &&
      (isActiveAnalysisJob(job.status) ||
        job.counts.queued + job.counts.acquiring + job.counts.analysing ===
          0) &&
      (job.status === 'completed') === (job.completion_event_id !== null) &&
      (job.trigger === 'manual' ? job.request_id !== null : true),
  )

const admissionSchema = z
  .strictObject({
    job: analysisJobSchema.nullable(),
    admitted_count: safeCount,
    already_active_count: safeCount,
  })
  .refine((value) =>
    value.job === null
      ? value.admitted_count === 0
      : value.admitted_count === value.job.counts.total,
  )
const jobsSchema = z.strictObject({
  jobs: z.array(analysisJobSchema).max(100),
  next_before_id: safeId.nullable(),
})
const attemptsSchema = analysisPageSchema(analysisAttemptSchema)

export type AnalysisAttempt = z.infer<typeof analysisAttemptSchema>
export type AnalysisJob = z.infer<typeof analysisJobSchema>
export type AnalysisUsage = z.infer<typeof analysisUsageSchema>
export type AnalysisAdmission = z.infer<typeof admissionSchema>
export type AnalysisSelection =
  | { kind: 'all_never_started' }
  | { kind: 'explicit' | 'retry' | 'reanalysis'; result_ids: number[] }
export type AnalysisRequest = {
  request_id: string
  configuration_revision: number
  initial_prompt: PromptChoice
  force_refresh: boolean
  selection: AnalysisSelection
}

export function isActiveAnalysisAttempt(
  status: z.infer<typeof attemptStatusSchema>,
) {
  return status === 'queued' || status === 'acquiring' || status === 'analysing'
}
export function isActiveAnalysisJob(status: z.infer<typeof jobStatusSchema>) {
  return status === 'queued' || status === 'running'
}

export async function startContentAnalysis(
  request: AnalysisRequest,
): Promise<AnalysisAdmission> {
  const data = decodeAnalysis(
    admissionSchema,
    await analysisRequest(
      '/content-analysis-jobs',
      jsonMutation('POST', request),
      202,
    ),
  )
  if (
    data.job &&
    (data.job.request_id !== request.request_id ||
      data.job.trigger !== 'manual' ||
      data.job.configuration_revision !== request.configuration_revision ||
      !promptChoiceMatchesVersion(
        request.initial_prompt,
        data.job.initial_prompt,
      ) ||
      data.job.force_refresh !== request.force_refresh)
  )
    throw new AnalysisApiError('invalid_response')
  return data
}

function promptChoiceMatchesVersion(
  choice: PromptChoice,
  version: AnalysisJob['initial_prompt'],
) {
  return choice.mode === 'default'
    ? version.mode === 'default'
    : version.mode === 'custom' && version.instructions === choice.instructions
}
export async function fetchAnalysisJobs(
  signal: AbortSignal,
  beforeId: number | null = null,
) {
  const query = new URLSearchParams({ limit: '20' })
  if (beforeId !== null) query.set('before_id', String(beforeId))
  const data = decodeAnalysis(
    jobsSchema,
    await analysisRequest(`/content-analysis-jobs?${query}`, { signal }),
  )
  if (
    data.jobs.some(
      (job, index) =>
        (beforeId !== null && job.id >= beforeId) ||
        (index > 0 && job.id >= data.jobs[index - 1].id),
    ) ||
    (data.next_before_id !== null &&
      data.next_before_id !== data.jobs.at(-1)?.id)
  )
    throw new AnalysisApiError('invalid_response')
  return data
}
export async function fetchAnalysisJob(id: number, signal: AbortSignal) {
  const job = decodeAnalysis(
    analysisJobSchema,
    await analysisRequest(`/content-analysis-jobs/${id}`, { signal }),
  )
  if (job.id !== id) throw new AnalysisApiError('invalid_response')
  return job
}
export async function fetchAnalysisJobItems(
  id: number,
  signal: AbortSignal,
  offset = 0,
) {
  const page = checkPage(
    decodeAnalysis(
      attemptsSchema,
      await analysisRequest(
        `/content-analysis-jobs/${id}/items?limit=${ANALYSIS_PAGE_SIZE}&offset=${offset}`,
        { signal },
      ),
    ),
    offset,
    ANALYSIS_PAGE_SIZE,
  )
  if (
    !uniqueIds(page.items.map((item) => item.id)) ||
    !uniqueIds(page.items.map((item) => item.source.result_id)) ||
    page.items.some(
      (item, index) => item.job_id !== id || item.position !== offset + index,
    )
  )
    throw new AnalysisApiError('invalid_response')
  return page
}
export async function fetchResultAnalyses(
  id: number,
  signal: AbortSignal,
  offset = 0,
) {
  const page = checkPage(
    decodeAnalysis(
      attemptsSchema,
      await analysisRequest(
        `/results/${id}/analyses?limit=${ANALYSIS_PAGE_SIZE}&offset=${offset}`,
        { signal },
      ),
    ),
    offset,
    ANALYSIS_PAGE_SIZE,
  )
  if (
    !uniqueIds(page.items.map((item) => item.id)) ||
    page.items.some((item) => item.source.result_id !== id)
  )
    throw new AnalysisApiError('invalid_response')
  return page
}
export async function fetchAnalysisAttempt(id: number, signal: AbortSignal) {
  const attempt = decodeAnalysis(
    analysisAttemptSchema,
    await analysisRequest(`/content-analyses/${id}`, { signal }),
  )
  if (attempt.id !== id) throw new AnalysisApiError('invalid_response')
  return attempt
}
export async function cancelAnalysisJob(id: number) {
  const job = decodeAnalysis(
    analysisJobSchema,
    await analysisRequest(
      `/content-analysis-jobs/${id}/cancel`,
      jsonMutation('POST', {}),
    ),
  )
  if (job.id !== id || isActiveAnalysisJob(job.status))
    throw new AnalysisApiError('invalid_response')
  return job
}
