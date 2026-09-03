import { z } from 'zod'

import {
  analysisRequest,
  decodeAnalysis,
  safeId,
  AnalysisApiError,
} from '@/lib/api/analysis-shared'
import { safeCount, jsonMutation } from '@/lib/api/analysis-shared'
import { getApiBaseUrl } from '@/lib/api/client'

const cachedMedia = z
  .strictObject({
    position: z.number().int().min(0).max(24),
    kind: z.enum(['image', 'video']),
    state: z.enum([
      'cached',
      'not_acquired',
      'not_stored',
      'missing',
      'corrupt',
      'cleared',
      'unavailable',
    ]),
    byte_size: z.number().int().min(1).max(6291456).nullable(),
  })
  .refine((value) => (value.state === 'cached') === (value.byte_size !== null))
export const cachedMediaList = z
  .strictObject({ items: z.array(cachedMedia).max(25) })
  .refine((value) =>
    value.items.every((item, index) => item.position === index),
  )
export type CachedMediaList = z.infer<typeof cachedMediaList>

export const mediaPolicySchema = z
  .strictObject({
    retention_days: z.number().int().min(1).max(3650),
    capacity_mib: z.number().int().min(1).max(20480),
    revision: safeCount,
    reserved_bytes: safeCount,
    files: safeCount.max(10000),
    pending_files: safeCount.max(10000),
  })
  .refine((value) => value.pending_files <= value.files)
export const mediaPolicyUpdateSchema = z.strictObject({
  retention_days: z.number().int().min(1).max(3650),
  capacity_mib: z.number().int().min(1).max(20480),
  expected_revision: safeCount,
})
export const mediaPolicyResultSchema = z.strictObject({
  policy: mediaPolicySchema,
  cleanup: z.strictObject({
    removed_files: safeCount.max(10000),
    removed_bytes: safeCount,
    deferred: z.boolean(),
  }),
})
export type MediaPolicy = z.infer<typeof mediaPolicySchema>
export type MediaPolicyResult = z.infer<typeof mediaPolicyResultSchema>
export const MEDIA_POLICY_KEY = ['media-cache-policy'] as const
export async function fetchMediaPolicy(signal: AbortSignal) {
  return decodeAnalysis(
    mediaPolicySchema,
    await analysisRequest('/media-cache-settings', { signal }),
  )
}
export async function saveMediaPolicy(
  payload: z.infer<typeof mediaPolicyUpdateSchema>,
) {
  const parsed = mediaPolicyUpdateSchema.safeParse(payload)
  if (!parsed.success) throw new AnalysisApiError('invalid_request')
  return decodeAnalysis(
    mediaPolicyResultSchema,
    await analysisRequest(
      '/media-cache-settings',
      jsonMutation('PUT', parsed.data),
    ),
  )
}
export async function cleanMediaCache(expectedRevision: number) {
  if (!safeCount.safeParse(expectedRevision).success)
    throw new AnalysisApiError('invalid_request')
  return decodeAnalysis(
    mediaPolicyResultSchema,
    await analysisRequest(
      '/media-cache-settings/cleanup',
      jsonMutation('POST', { expected_revision: expectedRevision }),
    ),
  )
}

export async function fetchMediaCache(attemptId: number, signal: AbortSignal) {
  if (!safeId.safeParse(attemptId).success)
    throw new AnalysisApiError('invalid_request')
  return decodeAnalysis(
    cachedMediaList,
    await analysisRequest(`/content-analyses/${attemptId}/media-cache`, {
      signal,
    }),
  )
}

export function originalMediaUrl(attemptId: number, position: number) {
  if (
    !safeId.safeParse(attemptId).success ||
    !z.number().int().min(0).max(24).safeParse(position).success
  )
    throw new AnalysisApiError('invalid_request')
  return `${getApiBaseUrl()}/content-analyses/${attemptId}/media/${position}`
}
