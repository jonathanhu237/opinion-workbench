import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelAISummary,
  fetchAISummaries,
  fetchAISummary,
  fetchAISummaryItems,
  startAISummary,
  SUMMARY_ERROR_CONTRACTS,
  validateAISummarySources,
} from '@/lib/api/ai-summaries'
import {
  itemFixture,
  pendingSummaryFixture,
  summaryFixture,
  summaryRequestId,
} from '@/lib/api/ai-summaries.fixtures'

const signal = new AbortController().signal

describe('summary API boundary', () => {
  const fetchMock = vi.fn<typeof fetch>()
  function respond(payload: unknown, status = 200) {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify(payload), { status }),
    )
  }
  function itemsPayload(items = [itemFixture()]) {
    return { items, total: items.length, limit: 100, offset: 0 }
  }
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('starts one exact revision-bound intent and validates the echoed identity', async () => {
    const intent = {
      request_id: summaryRequestId,
      force_refresh: false,
      configuration_revision: 3,
    }
    respond(pendingSummaryFixture(), 202)
    await expect(startAISummary(70, intent)).resolves.toEqual(
      pendingSummaryFixture(),
    )
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/v1/search-runs/70/ai-summaries',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(intent),
        cache: 'no-store',
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      }),
    )
    for (const changed of [
      { source_run_id: 71 },
      { request_id: '49fd5744-0135-4880-8bfc-1f3f2d60190a' },
      { force_refresh: true },
      { configuration_revision: 4 },
    ]) {
      respond({ ...pendingSummaryFixture(), ...changed }, 202)
      await expect(startAISummary(70, intent)).rejects.toMatchObject({
        code: 'invalid_response',
        status: 202,
      })
    }
    respond(summaryFixture(), 200)
    await expect(startAISummary(70, intent)).rejects.toMatchObject({
      code: 'invalid_response',
      status: 200,
    })
  })

  it('reads ordered history and all frozen items independently of result pagination', async () => {
    respond({ summaries: [summaryFixture()], next_before_id: 4 })
    await expect(fetchAISummaries(70, signal, 8)).resolves.toMatchObject({
      next_before_id: 4,
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/search-runs/70/ai-summaries?limit=20&before_id=8',
      expect.objectContaining({ signal }),
    )
    respond(itemsPayload())
    await expect(fetchAISummaryItems(4, signal)).resolves.toEqual(
      itemsPayload(),
    )
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/ai-summaries/4/items?limit=100&offset=0',
      expect.objectContaining({ signal }),
    )
  })

  it('preserves all 100 historical rule terms without clipping', async () => {
    const terms = Array.from(
      { length: 100 },
      (_, position) => `对象 ${position} 投诉`,
    )
    respond(summaryFixture({ terms }))
    await expect(fetchAISummary(4, signal)).resolves.toMatchObject({ terms })
  })

  it.each([21, 100])(
    'preserves all %i matched historical terms per source',
    async (length) => {
      const matched_terms = Array.from(
        { length },
        (_, position) => `对象 ${position}`,
      )
      const item = itemFixture()
      respond(
        itemsPayload([{ ...item, source: { ...item.source, matched_terms } }]),
      )
      await expect(fetchAISummaryItems(4, signal)).resolves.toMatchObject({
        items: [{ source: { matched_terms } }],
      })
    },
  )

  it('rejects more than 100 matched historical terms', async () => {
    const item = itemFixture()
    respond(
      itemsPayload([
        {
          ...item,
          source: {
            ...item.source,
            matched_terms: Array.from(
              { length: 101 },
              (_, index) => `对象 ${index}`,
            ),
          },
        },
      ]),
    )
    await expect(fetchAISummaryItems(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('uses code-point bounds for historical context and summary prose without clipping', async () => {
    const summary = summaryFixture({
      rule_name: '𠮷'.repeat(80),
      terms: ['𠮷'.repeat(100)],
      document: {
        overview: '𠮷'.repeat(2000),
        items: [{ text: '𠮷'.repeat(2000), source_ids: [11] }],
      },
    })
    respond(summary)
    await expect(fetchAISummary(4, signal)).resolves.toEqual(summary)
    for (const patch of [
      { rule_name: '界'.repeat(101) },
      { terms: ['界'.repeat(101)] },
      { document: { ...summary.document, overview: '𠮷'.repeat(2001) } },
      {
        document: {
          ...summary.document,
          items: [{ text: '𠮷'.repeat(2001), source_ids: [11] }],
        },
      },
    ]) {
      respond({ ...summary, ...patch })
      await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })

  it('uses code-point bounds for source and analysis text without clipping', async () => {
    const base = itemFixture()
    const item = itemFixture({
      source: {
        ...base.source,
        title: '𠮷'.repeat(300),
        snippet: '𠮷'.repeat(1000),
        published_at_text: '𠮷'.repeat(100),
      },
      reason: '𠮷'.repeat(300),
      evidence_summary: '𠮷'.repeat(1000),
    })
    respond(itemsPayload([item]))
    await expect(fetchAISummaryItems(4, signal)).resolves.toEqual(
      itemsPayload([item]),
    )
    for (const patch of [
      { source: { ...item.source, title: '𠮷'.repeat(301) } },
      { source: { ...item.source, snippet: '𠮷'.repeat(1001) } },
      { source: { ...item.source, published_at_text: '𠮷'.repeat(101) } },
      { reason: '𠮷'.repeat(301) },
      { evidence_summary: '𠮷'.repeat(1001) },
    ]) {
      respond(itemsPayload([{ ...item, ...patch }]))
      await expect(fetchAISummaryItems(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })

  it('validates detail and sends exact idempotent cancel without source data', async () => {
    respond(summaryFixture())
    await expect(fetchAISummary(4, signal)).resolves.toEqual(summaryFixture())
    await expect(cancelAISummary(4)).resolves.toEqual(summaryFixture())
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/ai-summaries/4/cancel',
      expect.objectContaining({ method: 'POST', body: '{}' }),
    )
    respond(summaryFixture({ id: 5 }))
    await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    await expect(cancelAISummary(4)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it.each(Object.entries(SUMMARY_ERROR_CONTRACTS))(
    'maps %s only at its documented HTTP status',
    async (code, contract) => {
      respond(
        { detail: { code, message: 'untrusted-provider-secret-sentinel' } },
        contract.status,
      )
      await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
        code,
        message: contract.message,
      })
      respond(
        { detail: { code, message: 'untrusted-provider-secret-sentinel' } },
        418,
      )
      await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
        status: 418,
      })
    },
  )

  it('does not retry network or invalid JSON responses and preserves aborts', async () => {
    fetchMock.mockRejectedValue(new Error('path-secret-sentinel'))
    await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
      code: 'service_unavailable',
    })
    expect(fetchMock).toHaveBeenCalledOnce()
    fetchMock.mockResolvedValue(new Response('not json'))
    await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    const abort = new DOMException('aborted', 'AbortError')
    fetchMock.mockRejectedValue(abort)
    await expect(fetchAISummary(4, signal)).rejects.toBe(abort)
  })

  it('rejects mismatched history, extra fields, conflicting counts and invalid lifecycle', async () => {
    const base = summaryFixture()
    for (const change of [
      { extra: 'secret' },
      { id: Number.MAX_SAFE_INTEGER + 1 },
      { source_run_status: 'running' },
      { counts: { ...base.counts, total: 2 } },
      { counts: { ...base.counts, reused: 2 } },
      { status: 'running' },
      { finished_at: null },
      { document: null },
      { counts: { ...base.counts, pending: 1, relevant: 0 } },
    ]) {
      respond({ ...base, ...change })
      await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
    for (const history of [
      {
        summaries: [summaryFixture({ source_run_id: 71 })],
        next_before_id: null,
      },
      { summaries: [base, base], next_before_id: null },
      { summaries: [base], next_before_id: 3 },
    ]) {
      respond(history)
      await expect(fetchAISummaries(70, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })

  it('keeps unknown and partial accounting distinct, including nullable modality fields', async () => {
    const unknown = {
      attempted_requests: 2,
      accounted_requests: 0,
      complete: false,
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
    }
    respond(summaryFixture({ usage: unknown }))
    await expect(fetchAISummary(4, signal)).resolves.toMatchObject({
      usage: unknown,
    })
    const overflow = { ...unknown, accounted_requests: 2 }
    respond(summaryFixture({ usage: overflow }))
    await expect(fetchAISummary(4, signal)).resolves.toMatchObject({
      usage: overflow,
    })
    const partial = {
      attempted_requests: 2,
      accounted_requests: 1,
      complete: false,
      prompt_tokens: 80,
      completion_tokens: 10,
      total_tokens: 90,
    }
    respond(summaryFixture({ usage: partial }))
    await expect(fetchAISummary(4, signal)).resolves.toMatchObject({
      usage: partial,
    })
    for (const usage of [
      { ...unknown, total_tokens: 0 },
      { ...partial, complete: true },
      { ...partial, total_tokens: 91 },
      { ...partial, accounted_requests: 3 },
      { ...partial, prompt_tokens: true },
    ]) {
      respond({ ...summaryFixture(), usage })
      await expect(fetchAISummary(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
    respond(itemsPayload())
    await expect(fetchAISummaryItems(4, signal)).resolves.toMatchObject({
      items: [
        {
          usage: {
            prompt_tokens_details: { image_tokens: null, video_tokens: 60 },
          },
        },
      ],
    })
  })

  it('rejects incomplete analysis as a verdict, copied reuse usage and unknown acquisition issues', async () => {
    const item = itemFixture()
    for (const patch of [
      { status: 'input_incomplete' },
      { attempted: false },
      { input_status: 'partial' },
      { input_issues: ['unknown-raw-message'] },
      { reused_from_item_id: 10 },
      { source: { ...item.source, content_url: 'javascript:alert(1)' } },
      { source: { ...item.source, content_url: 'https://evil.example/post' } },
      { summary_run_id: 5 },
      { position: 1 },
      { decision: 'related' },
    ]) {
      respond({ ...itemsPayload(), items: [{ ...item, ...patch }] })
      await expect(fetchAISummaryItems(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
    respond(
      itemsPayload([
        itemFixture({ reused_from_item_id: 5, attempted: false, usage: null }),
      ]),
    )
    await expect(fetchAISummaryItems(4, signal)).resolves.toMatchObject({
      items: [{ reused_from_item_id: 5, attempted: false, usage: null }],
    })
  })

  it('does not retain raw operational error messages', async () => {
    const item = itemFixture({
      status: 'failed',
      decision: null,
      reason: null,
      evidence_summary: null,
      error: {
        stage: 'analysis',
        code: 'invalid_json',
        message: 'provider-secret-sentinel',
      },
    })
    respond(itemsPayload([item]))
    const parsed = await fetchAISummaryItems(4, signal)
    expect(JSON.stringify(parsed)).not.toContain('provider-secret-sentinel')
    expect(parsed.items[0].error?.code).toBe('invalid_json')
    expect(parsed.items[0].usage?.total_tokens).toBe(90)
  })

  it('checks citations by original result identity and refuses foreign or non-relevant sources', () => {
    const summary = summaryFixture()
    const item = itemFixture()
    expect(validateAISummarySources(summary, [item])).toBe(true)
    expect(
      validateAISummarySources(summary, [{ ...item, decision: 'irrelevant' }]),
    ).toBe(false)
    expect(
      validateAISummarySources(summary, [
        { ...item, source: { ...item.source, source_run_id: 999 } },
      ]),
    ).toBe(false)
    expect(
      validateAISummarySources(
        {
          ...summary,
          document: {
            overview: 'test',
            items: [{ text: 'invented', source_ids: [item.id] }],
          },
        },
        [item],
      ),
    ).toBe(false)
    expect(validateAISummarySources(summary, [])).toBe(false)
  })
})
