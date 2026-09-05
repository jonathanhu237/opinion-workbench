import { z } from 'zod'

import {
  boundedAnalysisText,
  summarySourceSchema,
} from '@/lib/api/ai-summaries'
import {
  AnalysisApiError,
  analysisPageSchema,
  analysisRequest,
  checkPage,
  decodeAnalysis,
  safeCount,
  safeId,
  uniqueIds,
} from '@/lib/api/analysis-shared'
import {
  ANALYSIS_PAGE_SIZE,
  attemptStatusSchema,
} from '@/lib/api/content-analyses'
import {
  isoDateSchema,
  searchPlatformSchema,
  searchRunStatusSchema,
  type SearchPlatform,
} from '@/lib/api/search-runs'
import { MAX_TERMS_PER_RULE } from '@/lib/monitoring-rule-composition'

export const RESULTS_QUERY_KEY = ['results'] as const
export const RESULT_PAGE_SIZE = 20
export const resultStateSchema = z.enum([
  'never_started',
  'pending_new',
  ...attemptStatusSchema.options,
  'legacy_completed',
  'legacy_attempted',
])
const materialSchema = z.strictObject({
  text_available: z.boolean(),
  image_count: safeCount,
  video_count: safeCount,
  inventory_complete: z.boolean(),
  missing: z.boolean(),
})
const resultSchema = z
  .strictObject({
    id: safeId,
    source: summarySourceSchema,
    first_seen_at: isoDateSchema,
    last_seen_at: isoDateSchema,
    origin_count: safeId,
    analysis_state: resultStateSchema,
    latest_attempt_id: safeId.nullable(),
    active_job_id: safeId.nullable(),
    legacy_count: safeCount,
    material: materialSchema.nullable().optional(),
  })
  .refine(
    (value) =>
      value.id === value.source.result_id &&
      Date.parse(value.first_seen_at) <= Date.parse(value.last_seen_at),
  )
const resultListSchema = z
  .strictObject({
    items: z.array(resultSchema).max(100),
    total: safeCount,
    limit: safeId.max(100),
    offset: safeCount,
    eligible_count: safeCount,
    active_count: safeCount,
  })
  .refine(
    (value) =>
      value.items.length <= value.limit &&
      value.items.length <= Math.max(0, value.total - value.offset) &&
      uniqueIds(value.items.map((item) => item.id)),
  )
const originSchema = z.strictObject({
  source_run_id: safeId,
  rule_name: boundedAnalysisText(100, 1),
  status: searchRunStatusSchema,
  discovery_kind: z.enum(['new', 'repeated']),
  matched_terms: z.array(z.string().min(1)).min(1).max(MAX_TERMS_PER_RULE),
  first_observed_at: isoDateSchema,
  last_observed_at: isoDateSchema,
})
const originsSchema = analysisPageSchema(originSchema)
const legacySchema = analysisPageSchema(
  z.strictObject({
    source_run_id: safeId,
    summary_id: safeId,
    item_id: safeId,
    status: z.enum([
      'pending',
      'analysing',
      'completed',
      'input_incomplete',
      'failed',
      'cancelled',
      'interrupted',
    ]),
    decision: z.enum(['relevant', 'irrelevant', 'uncertain']).nullable(),
    reused_from_item_id: safeId.nullable(),
  }),
)
export type SharedResult = z.infer<typeof resultSchema>
export function isActiveResult(result: SharedResult) {
  return (
    result.active_job_id !== null ||
    result.analysis_state === 'queued' ||
    result.analysis_state === 'acquiring' ||
    result.analysis_state === 'analysing'
  )
}
export type ResultState = SharedResult['analysis_state']
export type ResultFilters = {
  platform?: SearchPlatform
  state?: ResultState
  first_seen_from?: string
  first_seen_to?: string
  offset: number
}

export async function fetchResults(
  filters: ResultFilters,
  signal: AbortSignal,
  limit = RESULT_PAGE_SIZE,
) {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(filters.offset),
  })
  for (const key of [
    'platform',
    'state',
    'first_seen_from',
    'first_seen_to',
  ] as const)
    if (filters[key]) query.set(key, filters[key])
  const data = checkPage(
    decodeAnalysis(
      resultListSchema,
      await analysisRequest(`/results?${query}`, { signal }),
    ),
    filters.offset,
    limit,
  )
  if (
    data.items.some(
      (item) =>
        (filters.platform !== undefined &&
          item.source.platform !== filters.platform) ||
        (filters.state !== undefined &&
          item.analysis_state !== filters.state) ||
        (filters.first_seen_from !== undefined &&
          Date.parse(item.first_seen_at) <
            Date.parse(filters.first_seen_from)) ||
        (filters.first_seen_to !== undefined &&
          Date.parse(item.first_seen_at) >= Date.parse(filters.first_seen_to)),
    )
  )
    throw new AnalysisApiError('invalid_response')
  return data
}
export async function fetchResult(id: number, signal: AbortSignal) {
  const result = decodeAnalysis(
    resultSchema,
    await analysisRequest(`/results/${id}`, { signal }),
  )
  if (result.id !== id) throw new AnalysisApiError('invalid_response')
  return result
}
export async function fetchResultOrigins(
  id: number,
  signal: AbortSignal,
  offset = 0,
) {
  const page = checkPage(
    decodeAnalysis(
      originsSchema,
      await analysisRequest(
        `/results/${id}/origins?limit=${ANALYSIS_PAGE_SIZE}&offset=${offset}`,
        { signal },
      ),
    ),
    offset,
    ANALYSIS_PAGE_SIZE,
  )
  if (!uniqueIds(page.items.map((item) => item.source_run_id)))
    throw new AnalysisApiError('invalid_response')
  return page
}
export async function fetchResultLegacyAnalyses(
  id: number,
  signal: AbortSignal,
  offset = 0,
) {
  const page = checkPage(
    decodeAnalysis(
      legacySchema,
      await analysisRequest(
        `/results/${id}/legacy-analyses?limit=${ANALYSIS_PAGE_SIZE}&offset=${offset}`,
        { signal },
      ),
    ),
    offset,
    ANALYSIS_PAGE_SIZE,
  )
  if (!uniqueIds(page.items.map((item) => item.item_id)))
    throw new AnalysisApiError('invalid_response')
  return page
}

export function parseResultFilters(params: URLSearchParams): ResultFilters {
  const platform = searchPlatformSchema.safeParse(params.get('platform'))
  const state = resultStateSchema.safeParse(params.get('state'))
  const from = shanghaiDateBoundary(params.get('from'))
  const to = shanghaiDateBoundary(params.get('to'), true)
  return {
    offset: readOffset(params.get('offset')),
    ...(platform.success && { platform: platform.data }),
    ...(state.success && { state: state.data }),
    ...(from && { first_seen_from: from }),
    ...(to && { first_seen_to: to }),
  }
}
export function readId(value: string | null) {
  if (value === null || !/^[1-9]\d*$/u.test(value)) return null
  const id = Number(value)
  return Number.isSafeInteger(id) ? id : null
}
export function readOffset(value: string | null) {
  return readId(value) ?? 0
}
export function shanghaiDateBoundary(
  value: string | null,
  end = false,
): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/u.test(value)) return null
  const utc = Date.parse(`${value}T00:00:00.000Z`)
  if (
    !Number.isFinite(utc) ||
    new Date(utc).toISOString().slice(0, 10) !== value
  )
    return null
  return new Date(
    utc - 8 * 60 * 60 * 1000 + (end ? 24 * 60 * 60 * 1000 : 0),
  ).toISOString()
}
