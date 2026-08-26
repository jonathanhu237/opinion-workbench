import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelSearchRun,
  fetchSearchRunResults,
  fetchSearchRuns,
  isActiveSearchRun,
  SearchRunApiError,
  startSearchRun,
  type SearchResult,
  type SearchRunDetail,
} from '@/lib/api/search-runs'

const run: SearchRunDetail = {
  id: 7,
  monitoring_rule_id: 1,
  platform: 'toutiao',
  rule_name: '龙田街道及四个社区',
  term_count: 2,
  terms: ['龙田街道', '竹坑社区'],
  max_results_per_term: 10,
  status: 'completed_with_results',
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
  platform: 'toutiao',
  platform_content_id: '100',
  content_type: 'article',
  title: '龙田街道公开信息',
  snippet: '来自公开搜索页面',
  creator_hash: '0123456789abcdef',
  publisher_name: '本***察',
  published_at_text: '刚刚',
  content_url: 'https://www.toutiao.com/article/100/',
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

  it('sends the exact start payload and requires an HTTP 202 detail', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(run), { status: 202 }),
    )
    const input = {
      monitoring_rule_id: 1,
      platform: 'toutiao' as const,
      max_results_per_term: 10,
    }

    await expect(startSearchRun(input)).resolves.toEqual(run)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-runs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(input),
      }),
    )

    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(run), { status: 200 }),
    )
    await expect(startSearchRun(input)).rejects.toMatchObject({
      code: 'invalid_response',
      status: 200,
    })
  })

  it('forwards history pagination and abort signals', async () => {
    fetchMock.mockResolvedValue(
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
  })

  it('accepts only strict, allowlisted result projections', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ results: [result], total: 1, limit: 50, offset: 0 }),
        { status: 200 },
      ),
    )

    await expect(
      fetchSearchRunResults(7, 'new', new AbortController().signal),
    ).resolves.toEqual({ results: [result], total: 1, limit: 50, offset: 0 })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-runs/7/results?kind=new&limit=50&offset=0',
      expect.any(Object),
    )

    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          results: [
            {
              ...result,
              content_url: 'https://evil.example/credential-sentinel',
            },
          ],
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
    await expect(rejected).rejects.not.toThrow(/credential-sentinel/u)

    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          results: [
            {
              ...result,
              content_url: 'https://www.toutiao.com:444/article/100/',
            },
          ],
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

    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          results: [{ ...result, publisher_name: '本地观察' }],
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
  })

  it('rejects count drift and unexpected response fields', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            runs: [
              {
                ...run,
                terms: undefined,
                new_count: 2,
                repeated_count: 0,
                total_count: 1,
              },
            ],
            next_before_id: null,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...run, raw_cookie: 'sentinel' }), {
          status: 202,
        }),
      )

    await expect(
      fetchSearchRuns(new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(
      startSearchRun({
        monitoring_rule_id: 1,
        platform: 'toutiao',
        max_results_per_term: 10,
      }),
    ).rejects.toMatchObject({ code: 'invalid_response' })
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
      message: '谷歌浏览器正在执行其他操作，请稍后重试。',
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
