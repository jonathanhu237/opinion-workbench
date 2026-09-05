import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { searchRunSummarySchema } from '@/lib/api/search-runs'
import {
  cancelSearchBatch,
  continueSearchBatch,
  fetchSearchBatch,
  fetchSearchBatchAttempts,
  fetchSearchBatches,
  fetchSearchBatchResults,
  showSearchBatchManualPage,
  skipSearchBatchPlatform,
  recoverSearchBatchPlatform,
  isActiveSearchBatch,
  SearchBatchApiError,
  startSearchBatch,
  type SearchBatchDetail,
} from '@/lib/api/search-batches'

const run = {
  id: 21,
  monitoring_rule_id: 1,
  platform: 'wb' as const,
  rule_name: '龙田街道及四个社区',
  term_count: 1,
  max_results_per_term: 10,
  status: 'completed_empty' as const,
  failure_reason: null,
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
  control_revision: 7,
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
      completed_term_count: 1,
      remaining_term_count: 0,
      next_term_position: null,
      checkpoint_basis: 'explicit',
      recovery_available: true,
      pause_reason: null,
      completion_basis: 'attempt_success',
      new_count: 0,
      repeated_count: 0,
      total_count: 0,
      position: 0,
      platform: 'wb',
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
    completed_term_count: 0,
    remaining_term_count: 1,
    next_term_position: 0,
    checkpoint_basis: 'unknown',
    completion_basis: null,
    started_at: null,
    finished_at: null,
  })),
  started_at: null,
  finished_at: null,
}

const fetchMock = vi.fn<typeof fetch>()
const control = { item_position: 0, expected_run_id: 21, expected_revision: 7 }

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
      platforms: ['wb'] as const,
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

  it.each([
    'page_state_unrecognized',
    'search_context_unavailable',
    'search_response_incompatible',
    'search_results_incompatible',
    'search_pagination_incompatible',
  ] as const)(
    'preserves %s on a paused child attempt',
    async (failure_reason) => {
      const payload = {
        ...batch,
        status: 'paused_for_manual_action' as const,
        terminal_item_count: 0,
        current_item_position: 0,
        finished_at: null,
        items: [
          {
            ...batch.items[0],
            status: 'paused_for_manual_action' as const,
            pause_reason: 'attempt_failed' as const,
            completion_basis: null,
            finished_at: null,
            latest_attempt: {
              attempt_number: 1,
              run: {
                ...run,
                status: 'structure_changed' as const,
                failure_reason,
              },
            },
          },
        ],
      }
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), { status: 200 }),
      )
      await expect(
        fetchSearchBatch(4, new AbortController().signal),
      ).resolves.toEqual(payload)
    },
  )

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
          platform: 'wb' as const,
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
    await expect(continueSearchBatch(4, control)).rejects.toEqual(
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
    await expect(
      cancelSearchBatch(4, { expected_revision: 7 }),
    ).resolves.toMatchObject({
      status: 'cancelled',
    })
  })

  it('polls only queued and running batch states', () => {
    expect(isActiveSearchBatch('queued')).toBe(true)
    expect(isActiveSearchBatch('running')).toBe(true)
    expect(isActiveSearchBatch('paused_for_manual_action')).toBe(false)
    expect(isActiveSearchBatch('completed_with_failures')).toBe(false)
  })

  it('sends versioned control bodies and preserves the abort signal', async () => {
    const signal = new AbortController().signal
    for (let index = 0; index < 4; index += 1)
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(batch), { status: 202 }),
      )
    await continueSearchBatch(4, control, signal)
    await skipSearchBatchPlatform(4, control, signal)
    await recoverSearchBatchPlatform(
      4,
      0,
      { expected_run_id: 21, expected_revision: 7 },
      signal,
    )
    await cancelSearchBatch(4, { expected_revision: 7 }, signal)
    const routes = ['continue', 'skip', 'items/0/recover', 'cancel']
    const bodies = [
      control,
      control,
      { expected_run_id: 21, expected_revision: 7 },
      { expected_revision: 7 },
    ]
    routes.forEach((route, index) =>
      expect(fetchMock).toHaveBeenNthCalledWith(
        index + 1,
        `/api/v1/search-batches/4/${route}`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(bodies[index]),
          signal,
        }),
      ),
    )
  })

  it.each([
    'opened_existing',
    'opened_homepage',
    'browser_unavailable',
    'navigation_failed',
    'internal_error',
    'cancelled',
  ])('accepts only fixed manual-page outcome %s', async (outcome) => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ outcome }), { status: 200 }),
    )
    await expect(showSearchBatchManualPage(4, control)).resolves.toEqual({
      outcome,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search-batches/4/manual-page',
      expect.objectContaining({ body: JSON.stringify(control) }),
    )
  })

  it.each([
    ['search_batch_state_changed', '采集任务状态已变化，请刷新后重试。'],
    [
      'search_batch_recovery_unavailable',
      '无法确认可靠的续采位置，请跳过本次采集或取消批次。',
    ],
    ['search_batch_item_not_recoverable', '本次采集当前不能重新处理。'],
  ])(
    'uses exact conflict %s and rejects changed messages',
    async (code, message) => {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: { code, message } }), {
          status: 409,
        }),
      )
      await expect(continueSearchBatch(4, control)).rejects.toMatchObject({
        code,
        message,
        status: 409,
      })
      fetchMock.mockResolvedValueOnce(
        new Response(
          JSON.stringify({ detail: { code, message: `${message}extra` } }),
          { status: 409 },
        ),
      )
      await expect(continueSearchBatch(4, control)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )

  it('accepts queued-with-old-attempt and confirmed-terms completion without relabeling the failed run', async () => {
    const failed = { ...run, status: 'internal_error' }
    const queued = {
      ...batch,
      status: 'running',
      terminal_item_count: 0,
      finished_at: null,
      items: [
        {
          ...batch.items[0],
          status: 'queued',
          completion_basis: null,
          finished_at: null,
          latest_attempt: { attempt_number: 1, run: failed },
        },
      ],
    }
    const confirmed = {
      ...batch,
      items: [
        {
          ...batch.items[0],
          completion_basis: 'confirmed_terms',
          latest_attempt: { attempt_number: 1, run: failed },
        },
      ],
    }
    for (const payload of [queued, confirmed]) {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), { status: 200 }),
      )
      await expect(
        fetchSearchBatch(4, new AbortController().signal),
      ).resolves.toEqual(payload)
    }
  })

  it('distinguishes reliable empty progress from unavailable corrupt progress', async () => {
    for (const available of [true, false]) {
      const payload = {
        ...queuedBatch,
        status: 'paused_for_manual_action',
        current_item_position: 0,
        items: [
          {
            ...queuedBatch.items[0],
            status: 'paused_for_manual_action',
            pause_reason: 'process_interrupted',
            recovery_available: available,
            next_term_position: available ? 0 : null,
          },
        ],
      }
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), { status: 200 }),
      )
      await expect(
        fetchSearchBatch(4, new AbortController().signal),
      ).resolves.toEqual(payload)
    }
  })

  it.each([0, 1])(
    'keeps a corrupt child snapshot with %s rows readable without trusting it',
    async (termCount) => {
      const payload = {
        ...batch,
        term_count: 2,
        terms: ['词一', '词二'],
        status: 'paused_for_manual_action',
        terminal_item_count: 0,
        current_item_position: 0,
        finished_at: null,
        items: [
          {
            ...batch.items[0],
            status: 'paused_for_manual_action',
            pause_reason: 'attempt_failed',
            completion_basis: null,
            finished_at: null,
            completed_term_count: 0,
            remaining_term_count: 2,
            next_term_position: null,
            checkpoint_basis: 'unknown',
            recovery_available: false,
            latest_attempt: {
              attempt_number: 1,
              run: {
                ...run,
                status: 'structure_changed',
                current_term_position: null,
                term_count: termCount,
              },
            },
          },
        ],
      }
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), { status: 200 }),
      )
      await expect(
        fetchSearchBatch(4, new AbortController().signal),
      ).resolves.toEqual(payload)
      fetchMock.mockResolvedValueOnce(
        new Response(
          JSON.stringify({ attempts: [payload.items[0].latest_attempt] }),
          { status: 200 },
        ),
      )
      await expect(
        fetchSearchBatchAttempts(4, 0, new AbortController().signal),
      ).resolves.toEqual({ attempts: [payload.items[0].latest_attempt] })
      if (termCount === 0)
        expect(
          searchRunSummarySchema.safeParse(payload.items[0].latest_attempt.run)
            .success,
        ).toBe(false)
      fetchMock.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...payload,
            items: [
              {
                ...payload.items[0],
                recovery_available: true,
                next_term_position: 0,
              },
            ],
          }),
          { status: 200 },
        ),
      )
      await expect(
        fetchSearchBatch(4, new AbortController().signal),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    },
  )

  it.each(['completed_empty', 'structure_changed', 'cancelled'])(
    'accepts the persisted %s attempt before the running item is finalized',
    async (status) => {
      const payload = {
        ...batch,
        status: 'running',
        terminal_item_count: 0,
        current_item_position: 0,
        finished_at: null,
        items: [
          {
            ...batch.items[0],
            status: 'running',
            completion_basis: null,
            finished_at: null,
            latest_attempt: { attempt_number: 1, run: { ...run, status } },
          },
        ],
      }
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), { status: 200 }),
      )
      await expect(
        fetchSearchBatch(4, new AbortController().signal),
      ).resolves.toEqual(payload)
    },
  )

  it('accepts incomplete coverage when the platform item itself finished', async () => {
    const diagnostic = {
      position: 0,
      term: '龙田街道',
      reason: 'view_all_unresolved' as const,
      result_count: 0,
    }
    const payload: SearchBatchDetail = {
      ...batch,
      status: 'completed_with_failures',
      items: [
        {
          ...batch.items[0],
          incomplete_terms: [diagnostic],
          latest_attempt: {
            attempt_number: 1,
            run: { ...run, incomplete_terms: [diagnostic] },
          },
        },
      ],
    }
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(payload), { status: 200 }),
    )
    await expect(
      fetchSearchBatch(4, new AbortController().signal),
    ).resolves.toEqual(payload)
  })

  it('keeps an out-of-range historical position readable only as unavailable recovery', async () => {
    const payload = {
      ...batch,
      status: 'paused_for_manual_action',
      terminal_item_count: 0,
      current_item_position: 0,
      finished_at: null,
      items: [
        {
          ...batch.items[0],
          status: 'paused_for_manual_action',
          pause_reason: 'attempt_failed',
          completion_basis: null,
          finished_at: null,
          completed_term_count: 0,
          remaining_term_count: 1,
          next_term_position: null,
          checkpoint_basis: 'unknown',
          recovery_available: false,
          latest_attempt: {
            attempt_number: 1,
            run: {
              ...run,
              status: 'internal_error',
              current_term_position: 20,
            },
          },
        },
      ],
    }
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(payload), { status: 200 }),
    )
    await expect(
      fetchSearchBatch(4, new AbortController().signal),
    ).resolves.toEqual(payload)
    expect(
      searchRunSummarySchema.safeParse(payload.items[0].latest_attempt.run)
        .success,
    ).toBe(false)
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...payload,
          items: [
            {
              ...payload.items[0],
              recovery_available: true,
              next_term_position: 0,
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

  it.each([
    { completed_term_count: 0 },
    { next_term_position: 0 },
    { recovery_available: false },
    { completion_basis: null },
    { checkpoint_basis: 'unknown' },
    { total_count: 1 },
    { pause_reason: 'attempt_failed' },
  ])('rejects inconsistent recovery fields %j', async (fields) => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ ...batch, items: [{ ...batch.items[0], ...fields }] }),
        { status: 200 },
      ),
    )
    await expect(
      fetchSearchBatch(4, new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('rejects unknown manual outcomes and unexpected fields', async () => {
    for (const payload of [
      { outcome: 'logged_in' },
      { outcome: 'opened_existing', url: 'https://example.test' },
    ]) {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), { status: 200 }),
      )
      await expect(showSearchBatchManualPage(4, control)).rejects.toMatchObject(
        { code: 'invalid_response' },
      )
    }
  })

  it('loads an aggregate page using source-run provenance and rejects missing or unsafe fields', async () => {
    const result = {
      id: 3,
      source_run_id: 21,
      platform: 'wb',
      platform_content_id: '5012345678901234',
      content_type: 'post',
      title: '结果',
      snippet: '',
      creator_hash: '',
      publisher_name: '',
      published_at_text: '',
      content_url: 'https://m.weibo.cn/detail/5012345678901234',
      kind: 'new',
      matched_terms: ['龙田街道'],
      first_seen_at: run.created_at,
      last_seen_at: run.created_at,
      first_observed_at: run.created_at,
      last_observed_at: run.created_at,
    }
    const payload = { results: [result], total: 51, limit: 50, offset: 50 }
    const signal = new AbortController().signal
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(payload), { status: 200 }),
    )
    await expect(
      fetchSearchBatchResults(4, 0, 'new', 50, signal),
    ).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/search-batches/4/items/0/results?kind=new&limit=50&offset=50',
      expect.objectContaining({ signal }),
    )
    for (const invalid of [
      { ...result, source_run_id: undefined },
      { ...result, source_run_id: 0 },
      { ...result, content_url: 'https://evil.test/' },
      { ...result, publisher_name: 'unmasked' },
    ]) {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ ...payload, results: [invalid] }), {
          status: 200,
        }),
      )
      await expect(
        fetchSearchBatchResults(4, 0, 'all', 0, signal),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    }
  })
})
