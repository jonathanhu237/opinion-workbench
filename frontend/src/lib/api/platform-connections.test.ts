import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchPlatformConnections,
  PlatformConnectionApiError,
  startPlatformConnectionAttempt,
  type PlatformConnection,
} from '@/lib/api/platform-connections'

const attemptId = '2efb05b0-b1f7-4bbb-8b9f-9effa11cd355'

const platforms: PlatformConnection[] = [
  {
    platform: 'wb',
    display_name: '微博',
    availability: 'enabled',
    status: 'not_checked',
    guidance: 'none',
    last_checked_at: null,
    active_attempt_id: null,
  },
  ...[
    ['dy', '抖音'],
    ['ks', '快手'],
  ].map(
    ([platform, display_name]) =>
      ({
        platform,
        display_name,
        availability: 'enabled',
        status: 'not_checked',
        guidance: 'none',
        last_checked_at: null,
        active_attempt_id: null,
      }) as PlatformConnection,
  ),
  {
    platform: 'xhs',
    display_name: '小红书',
    availability: 'coming_soon',
    status: 'coming_soon',
    guidance: 'none',
    last_checked_at: null,
    active_attempt_id: null,
  },
  {
    platform: 'toutiao',
    display_name: '今日头条',
    availability: 'enabled',
    status: 'not_checked',
    guidance: 'none',
    last_checked_at: null,
    active_attempt_id: null,
  },
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

  it('validates and projects the ordered platform catalog', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ platforms }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const controller = new AbortController()

    await expect(fetchPlatformConnections(controller.signal)).resolves.toEqual({
      platforms,
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/platform-connections', {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
  })

  it('rejects contract drift without retaining unexpected credential fields', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          platforms: [
            { ...platforms[0], cookie: 'credential-sentinel' },
            ...platforms.slice(1),
          ],
        }),
        { status: 200 },
      ),
    )

    const result = fetchPlatformConnections(new AbortController().signal)

    await expect(result).rejects.toMatchObject({
      code: 'invalid_response',
    })
    await expect(result).rejects.not.toThrow(/credential-sentinel/)
  })

  it('maps a known conflict to safe product guidance', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'connection_attempt_active',
            message: 'raw backend text credential-sentinel',
          },
        }),
        { status: 409 },
      ),
    )

    await expect(startPlatformConnectionAttempt('wb')).rejects.toMatchObject({
      code: 'connection_attempt_active',
      message: '已有平台连接任务正在运行，请完成后再试。',
      status: 409,
    })
  })

  it('accepts only a matching 202 attempt projection', async () => {
    const checkingPlatform: PlatformConnection = {
      ...platforms[0],
      status: 'checking',
      active_attempt_id: attemptId,
    }
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          attempt_id: attemptId,
          platform: checkingPlatform,
        }),
        { status: 202 },
      ),
    )

    await expect(startPlatformConnectionAttempt('wb')).resolves.toEqual({
      attempt_id: attemptId,
      platform: checkingPlatform,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/platform-connections/wb/attempts',
      expect.objectContaining({ method: 'POST' }),
    )
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
