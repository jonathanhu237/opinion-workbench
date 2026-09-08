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
  it.each([{}, { likes: 83 }, { comments: null, shares: 0 }])(
    'accepts partial platform statistics without inventing missing counts: %j',
    async (stats) => {
      const result = resultFixture()
      result.source.interaction_stats = stats
      fetchMock.mockResolvedValue(
        json({
          items: [result],
          total: 1,
          offset: 0,
          limit: 5,
          eligible_count: 1,
          active_count: 0,
        }),
      )
      const page = await fetchResults({ offset: 0 }, signal, 5)
      expect(page.items[0].source.interaction_stats).toEqual(stats)
    },
  )
  it.each([{ likes: -1 }, { likes: '83' }, { unknown: 1 }])(
    'still rejects invalid platform statistics: %j',
    async (stats) => {
      const result = resultFixture()
      fetchMock.mockResolvedValue(
        json({
          ...result,
          source: { ...result.source, interaction_stats: stats },
        }),
      )
      await expect(fetchResult(result.id, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )
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
          { platform: 'wb', state: 'never_started', offset: 0 },
          signal,
        )
      ).eligible_count,
    ).toBe(1001)
    expect(fetchMock.mock.calls[0][0]).toContain(
      'platform=wb&state=never_started',
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
  it('does not accept unsafe URLs in global source projections', async () => {
    const result = resultFixture()
    result.source = {
      ...result.source,
      platform: 'wb',
      platform_content_id: '5012345678901234',
      content_url: 'https://m.weibo.cn/detail/5012345678901234?token=sentinel',
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
          'from=2026-08-29&to=2026-08-29&offset=20&platform=wb',
        ),
      ),
    ).toEqual({
      offset: 20,
      platform: 'wb',
      first_seen_from: '2026-08-28T16:00:00.000Z',
      first_seen_to: '2026-08-29T16:00:00.000Z',
    })
    expect(shanghaiDateBoundary('2026-02-30')).toBeNull()
    expect(
      parseResultFilters(new URLSearchParams('offset=9007199254740992')),
    ).toEqual({ offset: 0 })
  })
})
