import {
  analysisProvider,
  analysisSettingsFixture,
  analysisTimestamp,
  resultFixture,
} from '@/lib/api/analysis-fixtures'
import type { AnalysisUsage } from '@/lib/api/content-analyses'
import type {
  CreateReportRequest,
  ReportRun,
  ReportSection,
  ReportSource,
} from '@/lib/api/topic-reports'

// Synthetic HTTP-boundary fixtures. Never import into product components.
export const reportRequestId = 'd70f7c78-f3a7-4179-9a3d-371fa8d3ebc2'
export const reportCreateRequest: CreateReportRequest = {
  request_id: reportRequestId,
  configuration_revision: 3,
  report_prompt: { mode: 'default' },
  selection: {
    kind: 'first_seen_interval',
    first_seen_from: '2026-08-28T16:00:00.000Z',
    first_seen_to: '2026-08-29T16:00:00.000Z',
  },
}
export function reportUsage(
  attempted = 0,
  accounted = attempted,
): AnalysisUsage {
  return {
    attempted_requests: attempted,
    accounted_requests: accounted,
    complete: attempted === accounted,
    prompt_tokens: attempted > 0 && accounted === 0 ? null : 10 * accounted,
    completion_tokens: attempted > 0 && accounted === 0 ? null : 20 * accounted,
    total_tokens: attempted > 0 && accounted === 0 ? null : 30 * accounted,
  }
}
export function reportNodes(completed = 0): ReportRun['nodes']['judgments'] {
  return {
    total: completed,
    queued: 0,
    running: 0,
    completed,
    failed: 0,
    cancelled: 0,
    interrupted: 0,
    reused: 0,
  }
}
export function reportFixture(values: Partial<ReportRun> = {}): ReportRun {
  const prompt = analysisSettingsFixture().report_prompt
  return {
    id: 31,
    request_id: null,
    trigger: 'automatic',
    initial_job_id: 7,
    completion_event_id: 3,
    parent_report_id: null,
    selection: { kind: 'initial_job', job_id: 7 },
    status: 'completed',
    revision: 2,
    configuration_revision: 3,
    base_url: analysisProvider.base_url,
    model: analysisProvider.model,
    prompt: {
      version_id: prompt.id,
      origin: 'shared',
      instructions: prompt.instructions,
      content_hash: prompt.content_hash,
      schema_version: 'topic-report-v1',
    },
    coverage: {
      total: 10,
      ready: 8,
      unavailable: 2,
      pending: 0,
      judging: 0,
      relevant: 8,
      irrelevant: 0,
      uncertain: 0,
      failed: 0,
      cancelled: 0,
      interrupted: 0,
    },
    nodes: { judgments: reportNodes(8), composition: reportNodes(1) },
    usage: {
      judgment: reportUsage(8),
      composition: reportUsage(1),
      total: reportUsage(9),
    },
    collection_gaps: [],
    root_section_id: 501,
    empty_reason: null,
    queue_reason: null,
    recovery_reason: null,
    model_retry_notice: null,
    error: null,
    created_at: analysisTimestamp,
    started_at: analysisTimestamp,
    finished_at: analysisTimestamp,
    ...values,
  }
}
export function reportSourceFixture(
  position = 0,
  values: Partial<ReportSource> = {},
): ReportSource {
  return {
    position,
    source: resultFixture({ id: position + 11 }).source,
    first_seen_at: analysisTimestamp,
    initial_attempt_id: position + 21,
    initial_status: 'completed',
    unavailable_reason: null,
    state: 'relevant',
    judgment: {
      decision: 'relevant',
      reason: `文字线索 ${position + 1} 可能涉及龙田，尚需人工核实。`,
    },
    judgment_node_id: position + 101,
    error: null,
    ...values,
  }
}
export function reportSectionFixture(
  values: Partial<ReportSection> = {},
): ReportSection {
  const sources = Array.from({ length: 8 }, (_, position) => ({
    position,
    source: reportSourceFixture(position).source,
  }))
  return {
    id: 501,
    report_id: 31,
    kind: 'leaf',
    position: 0,
    level: 0,
    status: 'completed',
    source_count: sources.length,
    document: {
      overview: '多条来源提及道路积水，具体地点仍待核实。',
      items: [
        {
          text: '这是保存的文字报告，并不把来源陈述视为已核实事实。',
          source_ids: sources.map((item) => item.source.result_id),
        },
      ],
    },
    overview_document: null,
    sources,
    children: [],
    attempted: true,
    usage: {
      prompt_tokens: 10,
      completion_tokens: 20,
      total_tokens: 30,
      prompt_tokens_details: null,
      completion_tokens_details: null,
    },
    reused_from_node_id: null,
    error: null,
    ...values,
  }
}
