import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelSearchRun,
  fetchSearchRunResults,
  fetchSearchRuns,
  isActiveSearchRun,
  openSearchRunResult,
  searchFailureReasonSchema,
  searchRunSummarySchema,
  SearchRunApiError,
  startSearchRun,
  type SearchResult,
  type SearchRunDetail,
} from '@/lib/api/search-runs'

const run: SearchRunDetail = {
  id: 7,
  monitoring_rule_id: 1,
  platform: 'wb',
  rule_name: '龙田街道及四个社区',
  term_count: 2,
  terms: ['龙田街道', '竹坑社区'],
  max_results_per_term: 10,
  status: 'completed_with_results',
  failure_reason: null,
  current_term_position: 1,
  new_count: 1,
  repeated_count: 0,
  total_count: 1,
  created_at: '2026-08-26T08:00:00+00:00',
  started_at: '2026-08-26T08:00:01+00:00',
  finished_at: '2026-08-26T08:00:05+00:00',
}

const result: SearchResult = {
  id: 11,
  platform: 'wb',
  platform_content_id: '5012345678901234',
  content_type: 'post',
  title: '微博公开信息',
  snippet: '来自公开搜索页面',
  creator_hash: '0123456789abcdef',
  publisher_name: '本***察',
  published_at_text: '刚刚',
  content_url: 'https://m.weibo.cn/detail/5012345678901234',
  kind: 'new',
  matched_terms: ['龙田街道'],
  first_seen_at: '2026-08-26T08:00:02+00:00',
  last_seen_at: '2026-08-26T08:00:02+00:00',
  first_observed_at: '2026-08-26T08:00:02+00:00',
  last_observed_at: '2026-08-26T08:00:02+00:00',
}

describe('search runs API boundary', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('accepts an explicit execution budget stop but never on a successful run', () => {
    const { terms: _terms, ...summary } = run
    expect(
      searchRunSummarySchema.safeParse({
        ...summary,
        status: 'timed_out',
        execution_limit: 'requests',
      }).success,
    ).toBe(true)
    expect(
      searchRunSummarySchema.safeParse({
        ...summary,
        execution_limit: 'requests',
      }).success,
    ).toBe(false)
  })

  it('keeps incomplete coverage terminal and requires its diagnostics', () => {
    const { terms: _terms, ...summary } = run
    const incomplete = {
      ...summary,
      status: 'completed_with_incomplete' as const,
      incomplete_terms: [
        {
          position: 0,
          term: '龙田街道',
          reason: 'view_all_unresolved' as const,
          result_count: 1,
        },
      ],
    }
    expect(searchRunSummarySchema.safeParse(incomplete).success).toBe(true)
    expect(
      searchRunSummarySchema.safeParse({
        ...summary,
        status: 'completed_with_incomplete',
      }).success,
    ).toBe(false)
    expect(isActiveSearchRun(incomplete.status)).toBe(false)
  })

  it('validates structured failure reasons and contradictory pairs', () => {
    const { terms: _terms, ...summary } = run
    const reason = 'search_results_incompatible' as const
    expect(searchFailureReasonSchema.safeParse(reason).success).toBe(true)
    expect(
      searchRunSummarySchema.safeParse({
        ...summary,
        status: 'structure_changed',
        failure_reason: reason,
      }).success,
    ).toBe(true)
    expect(
      searchRunSummarySchema.safeParse({
        ...summary,
        failure_reason: reason,
      }).success,
    ).toBe(false)
  })

  it('sends the exact Weibo start payload and requires an HTTP 202 detail', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(run), { status: 202 }),
    )
    const input = {
      monitoring_rule_id: 1,
      platform: 'wb' as const,
      max_results_per_term: 10,
    }

    await expect(startSearchRun(input)).resolves.toEqual(run)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-runs',
      expect.objectContaining({ method: 'POST', body: JSON.stringify(input) }),
    )

    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(run), { status: 200 }),
    )
    await expect(startSearchRun(input)).rejects.toMatchObject({
      code: 'invalid_response',
      status: 200,
    })
  })

  it('allows the fixed Weibo platform to be omitted from a start payload', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(run), { status: 202 }),
    )

    await expect(
      startSearchRun({ monitoring_rule_id: 1, max_results_per_term: 10 }),
    ).resolves.toEqual(run)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-runs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          monitoring_rule_id: 1,
          max_results_per_term: 10,
        }),
      }),
    )
  })

  it('forwards history pagination and validates the Weibo result URL', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          runs: [{ ...run, terms: undefined }],
          next_before_id: 4,
        }),
        { status: 200 },
      ),
    )
    const controller = new AbortController()
    await expect(
      fetchSearchRuns(controller.signal, { limit: 5, beforeId: 8 }),
    ).resolves.toMatchObject({ next_before_id: 4 })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-runs?limit=5&before_id=8',
      expect.objectContaining({ signal: controller.signal }),
    )

    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ results: [result], total: 1, limit: 50, offset: 0 }),
        {
          status: 200,
        },
      ),
    )
    await expect(
      fetchSearchRunResults(7, 'new', new AbortController().signal),
    ).resolves.toEqual({ results: [result], total: 1, limit: 50, offset: 0 })

    for (const content_url of [
      'https://m.weibo.cn/detail/other-id',
      'https://m.weibo.cn/detail/5012345678901234?q=1',
      'https://evil.example/detail/5012345678901234',
    ]) {
      fetchMock.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            results: [{ ...result, content_url }],
            total: 1,
            limit: 50,
            offset: 0,
          }),
          { status: 200 },
        ),
      )
      await expect(
        fetchSearchRunResults(7, 'all', new AbortController().signal),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    }
  })

  it('rejects secret-bearing or unknown response fields', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          results: [{ ...result, raw_cookie: 'sentinel' }],
          total: 1,
          limit: 50,
          offset: 0,
        }),
        { status: 200 },
      ),
    )
    const rejected = fetchSearchRunResults(
      7,
      'all',
      new AbortController().signal,
    )
    await expect(rejected).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(rejected).rejects.not.toThrow(/sentinel/u)
  })

  it('decodes Weibo open outcomes without accepting a request body', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ outcome: 'opened' }), { status: 200 }),
    )

    await expect(openSearchRunResult(7, 11)).resolves.toEqual({
      outcome: 'opened',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-runs/7/results/11/open',
      {
        method: 'POST',
        headers: { Accept: 'application/json' },
        signal: undefined,
      },
    )
    expect(fetchMock.mock.calls[0]?.[1]).not.toHaveProperty('body')
  })

  it('maps only exact product errors and bounds other failures', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: 'browser_operation_active',
              message: '谷歌浏览器正在执行其他操作，请稍后重试。',
            },
          }),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: 'browser_operation_active',
              message: 'credential-sentinel',
            },
          }),
          { status: 409 },
        ),
      )

    await expect(cancelSearchRun(7)).rejects.toMatchObject({
      code: 'browser_operation_active',
      status: 409,
    })
    const mismatched = cancelSearchRun(7)
    await expect(mismatched).rejects.toBeInstanceOf(SearchRunApiError)
    await expect(mismatched).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(mismatched).rejects.not.toThrow(/credential-sentinel/u)
  })

  it('polls only statuses explicitly marked active', () => {
    expect(isActiveSearchRun('queued')).toBe(true)
    expect(isActiveSearchRun('running')).toBe(true)
    expect(isActiveSearchRun('completed_empty')).toBe(false)
    expect(isActiveSearchRun('manual_challenge_required')).toBe(false)
    expect(isActiveSearchRun('internal_error')).toBe(false)
  })
})
