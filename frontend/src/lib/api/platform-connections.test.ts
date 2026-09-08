import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchPlatformConnections,
  PlatformConnectionApiError,
  openManagedBrowser,
  startPlatformConnectionAttempt,
  type PlatformConnection,
} from '@/lib/api/platform-connections'

const attemptId = '2efb05b0-b1f7-4bbb-8b9f-9effa11cd355'
const weibo: PlatformConnection = {
  platform: 'wb',
  display_name: '微博',
  availability: 'enabled',
  status: 'not_checked',
  guidance: 'none',
  last_checked_at: null,
  active_attempt_id: null,
}
const catalogPlatforms: PlatformConnection[] = [
  weibo,
  { ...weibo, platform: 'dy', display_name: '抖音' },
  { ...weibo, platform: 'ks', display_name: '快手' },
  { ...weibo, platform: 'xhs', display_name: '小红书' },
  { ...weibo, platform: 'toutiao', display_name: '今日头条' },
]

describe('platform connections API boundary', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('validates the ordered five-platform catalog', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ platforms: catalogPlatforms }), {
        status: 200,
      }),
    )

    await expect(
      fetchPlatformConnections(new AbortController().signal),
    ).resolves.toEqual({ platforms: catalogPlatforms })
  })

  it('rejects an unsupported platform row instead of exposing a future option', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ platforms: [{ ...weibo, platform: 'xhs' }] }),
        { status: 200 },
      ),
    )

    await expect(
      fetchPlatformConnections(new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('rejects contract drift without retaining unexpected credential fields', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          platforms: [
            { ...weibo, cookie: 'credential-sentinel' },
            ...catalogPlatforms.slice(1),
          ],
        }),
        { status: 200 },
      ),
    )

    const result = fetchPlatformConnections(new AbortController().signal)
    await expect(result).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(result).rejects.not.toThrow(/credential-sentinel/)
  })

  it('accepts a matching 202 attempt projection', async () => {
    const checking: PlatformConnection = {
      ...weibo,
      status: 'checking',
      active_attempt_id: attemptId,
    }
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ attempt_id: attemptId, platform: checking }),
        { status: 202 },
      ),
    )

    await expect(startPlatformConnectionAttempt('wb')).resolves.toEqual({
      attempt_id: attemptId,
      platform: checking,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/platform-connections/wb/attempts',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('opens a selected platform in the dedicated browser', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ outcome: 'opened_existing' }), {
        status: 200,
      }),
    )

    await expect(openManagedBrowser('dy')).resolves.toEqual({
      outcome: 'opened_existing',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/platform-connections/dy/browser',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('accepts managed-browser progress and retry guidance', async () => {
    const checking = {
      platforms: [
        { ...weibo, status: 'checking', guidance: 'starting_browser' },
        ...catalogPlatforms.slice(1),
      ],
    }
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(checking), { status: 200 }),
    )
    await expect(
      fetchPlatformConnections(new AbortController().signal),
    ).resolves.toEqual(checking)

    const failed = {
      platforms: [
        { ...weibo, status: 'failed', guidance: 'retry_browser' },
        ...catalogPlatforms.slice(1),
      ],
    }
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(failed), { status: 200 }),
    )
    await expect(
      fetchPlatformConnections(new AbortController().signal),
    ).resolves.toEqual(failed)
  })

  it('accepts an explicit dedicated-browser open response', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ outcome: 'opened_existing' }), {
        status: 200,
      }),
    )

    await expect(openManagedBrowser()).resolves.toEqual({
      outcome: 'opened_existing',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/platform-connections/browser',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('preserves the actionable message when the browser is not open', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'browser_not_open',
            message: '请先打开专用浏览器，再检查登录状态。',
          },
        }),
        { status: 409 },
      ),
    )

    await expect(startPlatformConnectionAttempt('wb')).rejects.toMatchObject({
      code: 'browser_not_open',
      message: '请先打开专用浏览器，再检查登录状态。',
    })
  })

  it('turns malformed error payloads into a bounded error', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'credential-sentinel' }), {
        status: 500,
      }),
    )

    const result = startPlatformConnectionAttempt('wb')
    await expect(result).rejects.toBeInstanceOf(PlatformConnectionApiError)
    await expect(result).rejects.toMatchObject({
      code: 'request_failed',
      message: '平台连接请求失败（HTTP 500）',
    })
  })
})
