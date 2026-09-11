import { z } from 'zod'

import {
  AnalysisApiError,
  analysisRequest,
  decodeAnalysis,
  jsonMutation,
  safeId,
} from '@/lib/api/analysis-shared'
import { isoDateSchema } from '@/lib/api/search-runs'

export const PLATFORM_ACCESS_QUERY_KEY = ['platform-access-pacing'] as const
export const PLATFORM_ACCESS_PLATFORMS = [
  'wb',
  'dy',
  'ks',
  'xhs',
  'toutiao',
] as const

export const platformIntervalsSchema = z.strictObject({
  wb: z.number().int().min(1).max(300),
  dy: z.number().int().min(1).max(300),
  ks: z.number().int().min(1).max(300),
  xhs: z.number().int().min(1).max(300),
  toutiao: z.number().int().min(1).max(300),
})
export const platformAccessSnapshotSchema = z.strictObject({
  interval_seconds: platformIntervalsSchema,
  basis: z.enum(['explicit', 'upgrade_safe_default', 'legacy_unavailable']),
})
export const platformAccessDiagnosticSchema = z.strictObject({
  platform: z.enum(PLATFORM_ACCESS_PLATFORMS),
  stage: z.enum(['search', 'detail', 'media']),
  outcome: z.literal('platform_blocked_or_rate_limited'),
  basis: z.enum([
    'http_status',
    'explicit_platform_evidence',
    'browser_dom_evidence',
  ]),
  status_code: z.number().int().min(100).max(599).nullable(),
  platform_code: z.string().min(1).max(100).nullable(),
  retry_after_at: z.string().datetime({ offset: true }).nullable(),
  manual_challenge_required: z.boolean(),
  observed_at: z.string().datetime({ offset: true }),
})
const platformAccessSettingsSchema = z.strictObject({
  revision: safeId,
  interval_seconds: platformIntervalsSchema,
  updated_at: isoDateSchema,
})
export type PlatformAccessIntervals = z.infer<typeof platformIntervalsSchema>
export type PlatformAccessSnapshot = z.infer<
  typeof platformAccessSnapshotSchema
>
export type PlatformAccessSettings = z.infer<
  typeof platformAccessSettingsSchema
>
export type PlatformAccessUpdate = {
  expected_revision: number
  interval_seconds: PlatformAccessIntervals
}

export async function fetchPlatformAccessSettings(signal: AbortSignal) {
  return decodeAnalysis(
    platformAccessSettingsSchema,
    await analysisRequest('/platform-access-pacing', { signal }),
  )
}

export async function savePlatformAccessSettings(value: PlatformAccessUpdate) {
  const valid = platformAccessSettingsSchema
    .pick({ revision: true })
    .safeParse({ revision: value.expected_revision })
  if (
    !valid.success ||
    !platformIntervalsSchema.safeParse(value.interval_seconds).success
  )
    throw new AnalysisApiError('invalid_request')
  return decodeAnalysis(
    platformAccessSettingsSchema,
    await analysisRequest(
      '/platform-access-pacing',
      jsonMutation('PUT', value),
    ),
  )
}

export function platformAccessErrorMessage(error: unknown) {
  if (error instanceof AnalysisApiError) {
    if (error.code === 'platform_access_settings_conflict')
      return '平台访问间隔已被其他窗口更新，请刷新后重试。'
    if (error.code === 'platform_access_settings_unavailable')
      return '平台访问间隔暂时无法读取或保存，请稍后重试。'
  }
  return '平台访问间隔暂时无法读取或保存，请稍后重试。'
}
