import { z } from 'zod'
import {
  analysisRequest,
  jsonMutation,
  decodeAnalysis,
} from './analysis-shared'

export const summaryPreferenceSchema = z.object({
  summary_concurrency: z.union([
    z.literal(1),
    z.literal(2),
    z.literal(4),
    z.literal(8),
    z.literal(16),
  ]),
})
export type SummaryConcurrency = z.infer<
  typeof summaryPreferenceSchema
>['summary_concurrency']
export async function fetchSummaryPreference(signal?: AbortSignal) {
  return decodeAnalysis(
    summaryPreferenceSchema,
    await analysisRequest('/summary-preferences', { signal }),
  )
}
export async function saveSummaryPreference(
  summary_concurrency: SummaryConcurrency,
) {
  return decodeAnalysis(
    summaryPreferenceSchema,
    await analysisRequest(
      '/summary-preferences',
      jsonMutation('PUT', { summary_concurrency }),
    ),
  )
}
