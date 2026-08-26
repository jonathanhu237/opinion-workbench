import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelSearchBatch,
  continueSearchBatch,
  fetchSearchBatch,
  fetchSearchBatchAttempts,
  fetchSearchBatches,
  isActiveSearchBatch,
  SearchBatchApiError,
  startSearchBatch,
  type SearchBatchDetail,
} from '@/lib/api/search-batches'

const run = {
  id: 21,
  monitoring_rule_id: 1,
  platform: 'toutiao' as const,
  rule_name: '龙田街道及四个社区',
  term_count: 1,
  max_results_per_term: 10,
  status: 'completed_empty' as const,
  current_term_position: 0,
  new_count: 0,
  repeated_count: 0,
  total_count: 0,
  created_at: '2026-08-26T08:00:00+00:00',
  started_at: '2026-08-26T08:00:01+00:00',
  finished_at: '2026-08-26T08:00:02+00:00',
}

const batch: SearchBatchDetail = {
  id: 4,
  monitoring_rule_id: 1,
  rule_name: '龙田街道及四个社区',
  term_count: 1,
  platform_count: 1,
  terminal_item_count: 1,
  max_results_per_term: 10,
  status: 'completed',
  current_item_position: null,
  terms: ['龙田街道'],
  items: [
    {
      position: 0,
      platform: 'toutiao',
      status: 'completed',
      attempt_count: 1,
      latest_attempt: { attempt_number: 1, run },
      created_at: run.created_at,
      started_at: run.started_at,
      finished_at: run.finished_at,
    },
  ],
  created_at: run.created_at,
  started_at: run.started_at,
  finished_at: run.finished_at,
}

const queuedBatch: SearchBatchDetail = {
  ...batch,
  terminal_item_count: 0,
  status: 'queued',
  current_item_position: null,
  items: batch.items.map((item) => ({
    ...item,
    status: 'queued',
    attempt_count: 0,
    latest_attempt: null,
    started_at: null,
    finished_at: null,
  })),
  started_at: null,
  finished_at: null,
}

const fetchMock = vi.fn<typeof fetch>()

describe('search batch API boundary', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('sends the exact platform array and validates the created batch', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(queuedBatch), { status: 202 }),
    )
    const input = {
      monitoring_rule_id: 1,
      platforms: ['toutiao', 'ks', 'xhs'] as const,
      max_results_per_term: 7,
    }

    await expect(
      startSearchBatch({ ...input, platforms: [...input.platforms] }),
    ).resolves.toMatchObject({ id: 4, status: 'queued' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-batches',
      expect.objectContaining({
        body: JSON.stringify({ ...input, platforms: [...input.platforms] }),
      }),
    )
  })

  it('loads list, detail and immutable attempts with abort signals', async () => {
    const controller = new AbortController()
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            batches: [
              {
                ...batch,
                terms: undefined,
                items: undefined,
              },
            ],
            next_before_id: null,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(batch), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            attempts: [{ attempt_number: 1, run }],
          }),
          { status: 200 },
        ),
      )

    await expect(fetchSearchBatches(controller.signal)).resolves.toMatchObject({
      batches: [{ id: 4 }],
    })
    await expect(fetchSearchBatch(4, controller.signal)).resolves.toEqual(batch)
    await expect(
      fetchSearchBatchAttempts(4, 0, controller.signal),
    ).resolves.toMatchObject({ attempts: [{ attempt_number: 1 }] })
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/search-batches/4/items/0/attempts',
      expect.objectContaining({ signal: controller.signal }),
    )
  })

  it('rejects mismatched item platforms and inconsistent progress counts', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...batch,
          terminal_item_count: 0,
          items: [
            {
              ...batch.items[0],
              platform: 'wb',
            },
          ],
        }),
        { status: 200 },
      ),
    )

    await expect(
      fetchSearchBatch(4, new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('rejects non-catalog platform order and incoherent aggregate states', async () => {
    const weiboRun = { ...run, id: 22, platform: 'wb' as const }
    const twoPlatformBatch = {
      ...batch,
      platform_count: 2,
      terminal_item_count: 2,
      items: [
        {
          ...batch.items[0],
          position: 0,
          platform: 'wb' as const,
          latest_attempt: { attempt_number: 1, run: weiboRun },
        },
        {
          ...batch.items[0],
          position: 1,
          platform: 'toutiao' as const,
        },
      ],
    }
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify(twoPlatformBatch), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ...batch, status: 'paused_for_manual_action' }),
          { status: 200 },
        ),
      )

    await expect(
      fetchSearchBatch(4, new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(
      fetchSearchBatch(4, new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('uses exact status/code contracts for continue and cancel', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: {
            code: 'search_batch_not_paused',
            message: '该批采集任务当前不需要继续操作。',
          },
        }),
        { status: 409 },
      ),
    )
    await expect(continueSearchBatch(4)).rejects.toEqual(
      new SearchBatchApiError(
        '该批采集任务当前不需要继续操作。',
        'search_batch_not_paused',
        409,
      ),
    )

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...batch, status: 'cancelled' }), {
        status: 202,
      }),
    )
    await expect(cancelSearchBatch(4)).resolves.toMatchObject({
      status: 'cancelled',
    })
  })

  it('polls only queued and running batch states', () => {
    expect(isActiveSearchBatch('queued')).toBe(true)
    expect(isActiveSearchBatch('running')).toBe(true)
    expect(isActiveSearchBatch('paused_for_manual_action')).toBe(false)
    expect(isActiveSearchBatch('completed_with_failures')).toBe(false)
  })
})
