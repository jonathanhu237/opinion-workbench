import { z } from 'zod'

import { boundedAnalysisText } from '@/lib/api/ai-summaries'
import {
  analysisRequest,
  decodeAnalysis,
  jsonMutation,
  isValidAnalysisProse,
  safeCount,
  safeId,
} from '@/lib/api/analysis-shared'
import { isoDateSchema } from '@/lib/api/search-runs'

export const ANALYSIS_SETTINGS_QUERY_KEY = ['analysis-settings'] as const
export const promptInstructionsSchema = boundedAnalysisText(8000, 1).refine(
  isValidAnalysisProse,
  '提示词须为 1 至 8000 字的有效非空文本。',
)
export const promptVersionSchema = z
  .strictObject({
    id: safeId,
    stage: z.enum(['initial', 'report']),
    instructions: promptInstructionsSchema,
    content_hash: z.string().regex(/^[0-9a-f]{64}$/u),
    schema_version: z.enum(['initial-understanding-v1', 'topic-report-v1']),
    created_at: isoDateSchema,
  })
  .refine(
    (prompt) =>
      prompt.schema_version ===
      (prompt.stage === 'initial'
        ? 'initial-understanding-v1'
        : 'topic-report-v1'),
  )

const settingsSchema = z.strictObject({
  initial_prompt: promptVersionSchema.refine(
    (value) => value.stage === 'initial',
  ),
  report_prompt: promptVersionSchema.refine(
    (value) => value.stage === 'report',
  ),
  automation: z
    .strictObject({
      enabled: z.boolean(),
      revision: safeId,
      approved_configuration_revision: safeId.nullable(),
      activation_content_id: safeCount,
      available: z.boolean(),
    })
    .refine(
      (value) =>
        !value.enabled || value.approved_configuration_revision !== null,
    ),
})
export type AnalysisSettings = z.infer<typeof settingsSchema>
export type PromptVersion = z.infer<typeof promptVersionSchema>
export type PromptStage = PromptVersion['stage']
export type AutomationUpdate = {
  expected_revision: number
  enabled: boolean
  configuration_revision: number | null
}

export async function fetchAnalysisSettings(
  signal: AbortSignal,
): Promise<AnalysisSettings> {
  return decodeAnalysis(
    settingsSchema,
    await analysisRequest('/analysis-settings', { signal }),
  )
}
export async function saveAnalysisPrompt(
  stage: PromptStage,
  value: { expected_version_id: number; instructions: string },
): Promise<AnalysisSettings> {
  return decodeAnalysis(
    settingsSchema,
    await analysisRequest(
      `/analysis-settings/prompts/${stage}`,
      jsonMutation('PUT', value),
    ),
  )
}
export async function saveAnalysisAutomation(
  value: AutomationUpdate,
): Promise<AnalysisSettings> {
  return decodeAnalysis(
    settingsSchema,
    await analysisRequest(
      '/analysis-settings/automation',
      jsonMutation('PUT', value),
    ),
  )
}
