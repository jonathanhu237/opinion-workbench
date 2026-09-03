import { z } from 'zod'

import { promptChoiceSchema } from '@/lib/api/analysis-settings'
import {
  AnalysisApiError,
  analysisRequest,
  decodeAnalysis,
  jsonMutation,
  safeId,
  safeCount,
  uniqueIds,
} from '@/lib/api/analysis-shared'
import { analysisJobSchema } from '@/lib/api/content-analyses'
import { isoDateSchema } from '@/lib/api/search-runs'
import { reportRunSchema } from '@/lib/api/topic-reports'

export const GENERATIONS_QUERY_KEY = ['report-generations'] as const
const selection = z.strictObject({
  kind: z.literal('explicit'),
  result_ids: z.array(safeId).min(1).refine(uniqueIds),
})
const selectionPreviewRequest = z.discriminatedUnion('kind', [
  z.strictObject({
    kind: z.literal('explicit'),
    result_ids: z.array(safeId).min(1).refine(uniqueIds),
  }),
  z.strictObject({
    kind: z.literal('library'),
    include_failed: z.boolean().default(false),
  }),
])
const selectionPolicy = z.discriminatedUnion('kind', [
  selection,
  z.strictObject({
    kind: z.literal('library_pending'),
    include_failed: z.boolean(),
  }),
])
const selectionPreviewSchema = z.strictObject({
  selection,
  counts: z.strictObject({
    total: safeCount,
    pending: safeCount,
    already_summarized: safeCount,
    failed: safeCount,
    active: safeCount,
  }),
})
export const generationCreateSchema = z.strictObject({
  request_id: z.uuidv4(),
  name: z.string().trim().min(1).max(200).optional(),
  configuration_revision: safeId,
  initial_prompt: promptChoiceSchema,
  report_prompt: promptChoiceSchema,
  selection: selectionPolicy,
})
export const generationStatusSchema = z.enum([
  'summarising',
  'paused_for_manual_action',
  'reporting',
  'completed',
  'empty',
  'failed',
  'configuration_blocked',
  'cancelled',
  'interrupted',
])
export function isActiveGeneration(
  status: z.infer<typeof generationStatusSchema>,
) {
  return ['summarising', 'reporting', 'paused_for_manual_action'].includes(
    status,
  )
}
export const generationSchema = z
  .strictObject({
    id: safeId,
    request_id: z.uuidv4(),
    name: z.string().min(1).max(200).optional(),
    selection,
    selection_policy: selectionPolicy,
    status: generationStatusSchema,
    analysis: analysisJobSchema,
    report: reportRunSchema.nullable(),
    created_at: isoDateSchema,
    finished_at: isoDateSchema.nullable(),
    pause_reason: z
      .enum([
        'login_required',
        'manual_challenge_required',
        'platform_blocked_or_rate_limited',
      ])
      .nullable(),
    pause_attempt_id: safeId.nullable(),
    control_revision: safeCount,
  })
  .refine(
    (value) =>
      value.analysis.request_id === value.request_id &&
      (value.selection_policy.kind !== 'explicit' ||
        JSON.stringify(value.selection_policy) ===
          JSON.stringify(value.selection)) &&
      value.analysis.counts.total === value.selection.result_ids.length &&
      isActiveGeneration(value.status) === (value.finished_at === null) &&
      (value.status === 'paused_for_manual_action') ===
        (value.pause_reason !== null) &&
      (value.pause_reason === null) === (value.pause_attempt_id === null) &&
      (value.status !== 'paused_for_manual_action' ||
        (value.report === null &&
          ['queued', 'running'].includes(value.analysis.status))) &&
      (value.status !== 'summarising' || value.report === null) &&
      (!['reporting', 'completed', 'empty'].includes(value.status) ||
        value.report !== null) &&
      (!['completed', 'empty'].includes(value.status) ||
        value.report?.status === value.status) &&
      (value.report === null ||
        (value.report.trigger === 'manual' &&
          JSON.stringify(value.report.selection) ===
            JSON.stringify(value.selection) &&
          value.report.configuration_revision ===
            value.analysis.configuration_revision)),
  )
export type GenerationCreate = z.infer<typeof generationCreateSchema>
export type ReportGeneration = z.infer<typeof generationSchema>
export type SelectionPreviewRequest = z.infer<typeof selectionPreviewRequest>
export type SelectionPreview = z.infer<typeof selectionPreviewSchema>
export async function createReportGeneration(input: GenerationCreate) {
  const valid = generationCreateSchema.safeParse(input)
  if (!valid.success) throw new AnalysisApiError('invalid_request')
  const value = decodeAnalysis(
    generationSchema,
    await analysisRequest(
      '/report-generations',
      jsonMutation('POST', valid.data),
      202,
    ),
  )
  if (
    value.request_id !== input.request_id ||
    value.analysis.configuration_revision !== input.configuration_revision ||
    JSON.stringify(value.selection_policy) !== JSON.stringify(input.selection)
  )
    throw new AnalysisApiError('invalid_response')
  return value
}

export async function previewReportSelection(
  input: SelectionPreviewRequest,
): Promise<SelectionPreview> {
  const valid = selectionPreviewRequest.safeParse(input)
  if (!valid.success) throw new AnalysisApiError('invalid_request')
  return decodeAnalysis(
    selectionPreviewSchema,
    await analysisRequest(
      '/report-generations/selection-preview',
      jsonMutation('POST', valid.data),
    ),
  )
}
export async function fetchReportGeneration(id: number, signal: AbortSignal) {
  if (!safeId.safeParse(id).success)
    throw new AnalysisApiError('invalid_request')
  const value = decodeAnalysis(
    generationSchema,
    await analysisRequest(`/report-generations/${id}`, { signal }),
  )
  if (value.id !== id) throw new AnalysisApiError('invalid_response')
  return value
}
export async function fetchReportGenerations(
  signal: AbortSignal,
  beforeId?: number,
) {
  if (beforeId !== undefined && !safeId.safeParse(beforeId).success)
    throw new AnalysisApiError('invalid_request')
  const page = decodeAnalysis(
    z.strictObject({
      items: z.array(generationSchema).max(20),
      next_before_id: safeId.nullable(),
    }),
    await analysisRequest(
      `/report-generations?limit=20${beforeId ? `&before_id=${beforeId}` : ''}`,
      { signal },
    ),
  )
  if (
    page.items.some(
      (item, index) =>
        (beforeId !== undefined && item.id >= beforeId) ||
        (index > 0 && item.id >= page.items[index - 1].id),
    ) ||
    (page.next_before_id !== null &&
      (page.items.length !== 20 || page.items[19].id !== page.next_before_id))
  )
    throw new AnalysisApiError('invalid_response')
  return page
}

export async function fetchGenerationEligibility(signal: AbortSignal) {
  return decodeAnalysis(
    z.strictObject({
      pending: safeCount,
      failed: safeCount,
      active: safeCount,
    }),
    await analysisRequest('/report-generations/eligibility', { signal }),
  )
}

export async function controlReportGeneration(
  id: number,
  revision: number,
  action: 'continue' | 'manual-page' | 'cancel',
) {
  if (!safeId.safeParse(id).success || !safeCount.safeParse(revision).success)
    throw new AnalysisApiError('invalid_request')
  const value = decodeAnalysis(
    generationSchema,
    await analysisRequest(
      `/report-generations/${id}/${action}`,
      jsonMutation('POST', { expected_revision: revision }),
    ),
  )
  if (value.id !== id || value.control_revision < revision)
    throw new AnalysisApiError('invalid_response')
  return value
}
