import type { AnalysisSettings } from '@/lib/api/analysis-settings'
import type {
  AnalysisAttempt,
  AnalysisJob,
  AnalysisRequest,
} from '@/lib/api/content-analyses'
import type { SharedResult } from '@/lib/api/results'

// Synthetic boundary fixtures only. Never import these into product components.
export const analysisTimestamp = '2026-08-29T08:00:00+00:00'
export const analysisProvider = {
  base_url: 'https://api.example.com/v1',
  model: 'test-understanding-model',
  has_api_key: true,
  revision: 3,
}
export const analysisRequest: AnalysisRequest = {
  request_id: 'f3522a81-6e3f-41bd-a403-1ff8be1227b1',
  configuration_revision: 3,
  initial_prompt: { mode: 'default' },
  force_refresh: false,
  selection: { kind: 'all_never_started' },
}
export function analysisSettingsFixture(): AnalysisSettings {
  return {
    initial_prompt: {
      id: 1,
      version_id: 1,
      mode: 'default',
      stage: 'initial',
      instructions: '理解全部来源并保留地点线索，不先判断主题。',
      content_hash: 'a'.repeat(64),
      schema_version: 'initial-understanding-v1',
      created_at: analysisTimestamp,
    },
    report_prompt: {
      id: 2,
      version_id: 2,
      mode: 'default',
      stage: 'report',
      instructions: '只依据保存文字判断地点；证据不足则保留不确定性。',
      content_hash: 'b'.repeat(64),
      schema_version: 'topic-report-v1',
      created_at: analysisTimestamp,
    },
    automation: {
      enabled: false,
      revision: 1,
      approved_configuration_revision: null,
      activation_content_id: 10,
      available: false,
    },
  }
}
export function resultFixture(
  values: Partial<SharedResult> = {},
): SharedResult {
  const id = values.id ?? 11
  return {
    id,
    source: {
      source_run_id: 70,
      result_id: id,
      platform: 'dy',
      platform_content_id: String(7512340000000000 + id),
      content_type: 'video',
      title: `合成采集内容 ${id}`,
      snippet: '合成测试：发布者提及龙田，具体地点仍不确定。',
      content_url: `https://www.douyin.com/video/${7512340000000000 + id}`,
      published_at_text: '昨天',
      matched_terms: ['龙田'],
    },
    first_seen_at: analysisTimestamp,
    last_seen_at: analysisTimestamp,
    origin_count: 1,
    analysis_state: 'never_started',
    latest_attempt_id: null,
    active_job_id: null,
    legacy_count: 0,
    ...values,
  }
}
export function analysisAttemptFixture(
  values: Partial<AnalysisAttempt> = {},
): AnalysisAttempt {
  return {
    id: 21,
    job_id: 7,
    position: 0,
    source: resultFixture().source,
    first_seen_at: analysisTimestamp,
    status: 'completed',
    output: {
      summary: '发布者称一处道路积水，实际地点未确认。',
      location_clues: [
        {
          excerpt: '画面路牌只显示“龙田”，不能确定行政区。',
          modality: 'video',
        },
      ],
      time_context: '平台显示昨天；拍摄时间未知。',
      media_observations: ['画面中可见积水。'],
      uncertainties: '无法确认是否位于深圳龙田，也未核实来源陈述。',
    },
    input: {
      schema_version: 1,
      extractor_version: 'test-extractor-v1',
      acquired_at: 1787990400000,
      status: 'ready',
      text: {
        title: '合成原文标题',
        body: '完整保存的合成正文，未把来源陈述当成事实。',
        coverage: 'complete',
      },
      detected_modalities: ['text'],
      media_inventory_complete: true,
      assets: [],
      issues: [],
    },
    input_fingerprint: 'c'.repeat(64),
    reused_from_attempt_id: null,
    attempted: true,
    usage: {
      prompt_tokens: 10,
      completion_tokens: 20,
      total_tokens: 30,
      prompt_tokens_details: null,
      completion_tokens_details: null,
    },
    error: null,
    created_at: analysisTimestamp,
    started_at: analysisTimestamp,
    finished_at: analysisTimestamp,
    ...values,
  }
}
export function analysisJobFixture(
  values: Partial<AnalysisJob> = {},
): AnalysisJob {
  const settings = analysisSettingsFixture()
  return {
    id: 7,
    request_id: analysisRequest.request_id,
    trigger: 'manual',
    status: 'queued',
    configuration_revision: 3,
    base_url: analysisProvider.base_url,
    model: analysisProvider.model,
    initial_prompt: settings.initial_prompt,
    report_prompt: settings.report_prompt,
    force_refresh: false,
    counts: {
      total: 101,
      queued: 101,
      acquiring: 0,
      analysing: 0,
      completed: 0,
      input_incomplete: 0,
      unsupported: 0,
      failed: 0,
      cancelled: 0,
      interrupted: 0,
      reused: 0,
    },
    usage: {
      attempted_requests: 0,
      accounted_requests: 0,
      complete: true,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
    },
    queue_reason: null,
    completion_event_id: null,
    created_at: analysisTimestamp,
    started_at: null,
    finished_at: null,
    ...values,
  }
}
