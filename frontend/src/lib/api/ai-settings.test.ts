import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AI_ERROR_CONTRACTS,
  AISettingsApiError,
  fetchAISettings,
  saveAISettings,
  testAIConnection,
} from '@/lib/api/ai-settings'

const saved = {
  base_url: 'https://api.example.com/v1',
  model: 'test-model',
  has_api_key: true,
  revision: 3,
}
const key = 'fake-only-key-sentinel'

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('AI settings HTTP boundary', () => {
  it('reads only the non-secret projection and sends a key only on explicit save', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(saved))
    vi.stubGlobal('fetch', fetcher)
    const signal = new AbortController().signal
    expect(await fetchAISettings(signal)).toEqual(saved)
    expect(fetcher).toHaveBeenCalledWith('/api/v1/ai-settings', {
      signal,
      cache: 'no-store',
      redirect: 'error',
      headers: { Accept: 'application/json' },
    })
    fetcher.mockResolvedValue(response(saved))
    const payload = {
      base_url: saved.base_url,
      model: saved.model,
      api_key: key,
    }
    const result = await saveAISettings(payload, signal)
    expect(result).toEqual(saved)
    expect(JSON.stringify(result)).not.toContain(key)
    expect(fetcher).toHaveBeenLastCalledWith(
      '/api/v1/ai-settings',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify(payload),
        signal,
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      }),
    )
  })

  it('tests the saved revision without submitting configuration or key', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(response({ status: 'connected', revision: 3 }))
    vi.stubGlobal('fetch', fetcher)
    await testAIConnection(3)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledWith(
      '/api/v1/ai-settings/test',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ revision: 3 }),
      }),
    )
    fetcher.mockResolvedValue(response({ status: 'connected', revision: 2 }))
    await expect(testAIConnection(3)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it.each(Object.entries(AI_ERROR_CONTRACTS))(
    'validates status/code and discards raw messages for %s',
    async (code, contract) => {
      const fetcher = vi
        .fn()
        .mockResolvedValue(
          response({ detail: { code, message: key } }, contract.status),
        )
      vi.stubGlobal('fetch', fetcher)
      await expect(testAIConnection(3)).rejects.toMatchObject({
        code,
        status: contract.status,
        message: contract.message,
      })
      fetcher.mockResolvedValue(
        response({ detail: { code, message: key } }, 418),
      )
      await expect(testAIConnection(3)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )

  it.each([
    { ...saved, api_key: key },
    { ...saved, revision: '3' },
    { ...saved, has_api_key: false },
    { ...saved, base_url: null },
    { ...saved, extra: true },
    null,
  ])(
    'rejects malformed or secret-bearing configuration responses',
    async (payload) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(payload)))
      await expect(
        fetchAISettings(new AbortController().signal),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    },
  )

  it('sanitizes network, JSON and unknown error failures without request retention', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error(key))
    vi.stubGlobal('fetch', fetcher)
    try {
      await saveAISettings({
        base_url: saved.base_url,
        model: saved.model,
        api_key: key,
      })
    } catch (error) {
      expect(error).toBeInstanceOf(AISettingsApiError)
      expect(String(error)).not.toContain(key)
      expect(JSON.stringify(error)).not.toContain(key)
    }
    fetcher.mockResolvedValue(new Response(key))
    await expect(
      fetchAISettings(new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })
    fetcher.mockResolvedValue(
      response({ detail: { code: 'unknown', message: key } }, 500),
    )
    await expect(testAIConnection(3)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
})
