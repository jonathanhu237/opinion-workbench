import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resultFixture } from '@/lib/api/analysis-fixtures'
import {
  fetchResult,
  fetchResultLegacyAnalyses,
  fetchResults,
  parseResultFilters,
  shanghaiDateBoundary,
} from '@/lib/api/results'

const fetchMock = vi.fn<typeof fetch>()
const signal = new AbortController().signal
const json = (value: unknown) =>
  new Response(JSON.stringify(value), { status: 200 })
describe('global result boundary', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  it('keeps library eligibility counts independent from the filtered page', async () => {
    fetchMock.mockResolvedValue(
      json({
        items: [resultFixture()],
        total: 1,
        offset: 0,
        limit: 20,
        eligible_count: 1001,
        active_count: 3,
      }),
    )
    expect(
      (
        await fetchResults(
          { platform: 'dy', state: 'never_started', offset: 0 },
          signal,
        )
      ).eligible_count,
    ).toBe(1001)
    expect(fetchMock.mock.calls[0][0]).toContain(
      'platform=dy&state=never_started',
    )
  })
  it('rejects wrong result/source IDs and filtered-state drift', async () => {
    fetchMock.mockResolvedValueOnce(json({ ...resultFixture(), id: 12 }))
    await expect(fetchResult(12, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    fetchMock.mockResolvedValueOnce(
      json({
        items: [resultFixture()],
        total: 1,
        offset: 0,
        limit: 20,
        eligible_count: 1001,
        active_count: 0,
      }),
    )
    await expect(
      fetchResults({ state: 'completed', offset: 0 }, signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })
  it('does not accept signed XHS URLs in global source projections', async () => {
    const result = resultFixture()
    result.source = {
      ...result.source,
      platform: 'xhs',
      platform_content_id: 'a'.repeat(24),
      content_url: `https://www.xiaohongshu.com/explore/${'a'.repeat(24)}?xsec_token=sentinel`,
    }
    fetchMock.mockResolvedValue(json(result))
    await expect(fetchResult(11, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
  it('retains the actual legacy report origin instead of substituting the current result origin', async () => {
    fetchMock.mockResolvedValue(
      json({
        items: [
          {
            source_run_id: 91,
            summary_id: 5,
            item_id: 30,
            status: 'completed',
            decision: 'uncertain',
            reused_from_item_id: 29,
          },
        ],
        total: 1,
        offset: 0,
        limit: 20,
      }),
    )
    expect(
      (await fetchResultLegacyAnalyses(11, signal)).items[0].source_run_id,
    ).toBe(91)
  })
  it('converts inclusive Shanghai dates to half-open UTC boundaries independently of browser timezone', () => {
    expect(
      parseResultFilters(
        new URLSearchParams(
          'from=2026-08-29&to=2026-08-29&offset=20&platform=dy',
        ),
      ),
    ).toEqual({
      offset: 20,
      platform: 'dy',
      first_seen_from: '2026-08-28T16:00:00.000Z',
      first_seen_to: '2026-08-29T16:00:00.000Z',
    })
    expect(shanghaiDateBoundary('2026-02-30')).toBeNull()
    expect(
      parseResultFilters(new URLSearchParams('offset=9007199254740992')),
    ).toEqual({ offset: 0 })
  })
})
