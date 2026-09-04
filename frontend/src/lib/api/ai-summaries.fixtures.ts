import type { AISummaryItem, AISummaryRun } from '@/lib/api/ai-summaries'

// Synthetic fixtures only; never imported by product routes or used as saved results.
export const summaryRequestId = 'f3522a81-6e3f-41bd-a403-1ff8be1227b1'
export const summaryTimestamp = '2026-08-28T08:00:00+00:00'

export function summaryFixture(
  values: Partial<AISummaryRun> = {},
): AISummaryRun {
  return {
    id: 4,
    request_id: summaryRequestId,
    source_run_id: 70,
    platform: 'wb',
    source_run_status: 'completed_with_results',
    rule_name: '测试规则',
    terms: ['测试街道 投诉'],
    configuration_revision: 3,
    base_url: 'https://api.example.com/v1',
    model: 'test-summary-model',
    force_refresh: false,
    status: 'completed',
    phase: 'summarising',
    counts: {
      total: 1,
      pending: 0,
      analysing: 0,
      relevant: 1,
      irrelevant: 0,
      uncertain: 0,
      input_incomplete: 0,
      failed: 0,
      cancelled: 0,
      interrupted: 0,
      reused: 0,
    },
    usage: {
      attempted_requests: 2,
      accounted_requests: 2,
      complete: true,
      prompt_tokens: 100,
      completion_tokens: 20,
      total_tokens: 120,
    },
    document: {
      overview: '发布者反映一处道路积水，实际情况尚待核实。',
      items: [
        { text: '视频中可见路面积水，未能确认拍摄日期。', source_ids: [11] },
      ],
    },
    error: null,
    created_at: summaryTimestamp,
    started_at: summaryTimestamp,
    finished_at: summaryTimestamp,
    ...values,
  }
}

export function itemFixture(
  values: Partial<AISummaryItem> = {},
): AISummaryItem {
  return {
    id: 21,
    summary_run_id: 4,
    position: 0,
    source: {
      source_run_id: 70,
      result_id: 11,
      platform: 'wb',
      platform_content_id: '5012345678901234',
      content_type: 'post',
      title: '测试街道道路情况',
      snippet: '一条合成测试内容',
      content_url: 'https://m.weibo.cn/detail/5012345678901234',
      published_at_text: '昨天',
      matched_terms: ['测试街道 投诉'],
    },
    status: 'completed',
    decision: 'relevant',
    reason: '内容反映监控范围内的公共问题。',
    evidence_summary: '画面中可见积水，发布者称位于测试街道；具体情况未核实。',
    reused_from_item_id: null,
    attempted: true,
    usage: {
      prompt_tokens: 80,
      completion_tokens: 10,
      total_tokens: 90,
      prompt_tokens_details: {
        text_tokens: 10,
        image_tokens: null,
        video_tokens: 60,
        audio_tokens: 10,
        cached_tokens: null,
      },
      completion_tokens_details: null,
    },
    input_status: 'ready',
    input_issues: [],
    error: null,
    started_at: summaryTimestamp,
    finished_at: summaryTimestamp,
    ...values,
  }
}

export function pendingSummaryFixture(): AISummaryRun {
  const base = summaryFixture()
  return {
    ...base,
    status: 'queued',
    phase: 'analysing',
    document: null,
    started_at: null,
    finished_at: null,
    counts: { ...base.counts, relevant: 0, pending: 1 },
    usage: {
      attempted_requests: 0,
      accounted_requests: 0,
      complete: true,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
    },
  }
}

export function pendingItemFixture(): AISummaryItem {
  return itemFixture({
    status: 'pending',
    decision: null,
    reason: null,
    evidence_summary: null,
    attempted: false,
    usage: null,
    input_status: null,
    started_at: null,
    finished_at: null,
  })
}
