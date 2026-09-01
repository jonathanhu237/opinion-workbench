import { beforeEach, describe, expect, it, vi } from 'vitest'

import { analysisSettingsFixture } from '@/lib/api/analysis-fixtures'
import {
  fetchAnalysisSettings,
  promptInstructionsSchema,
  saveAnalysisAutomation,
} from '@/lib/api/analysis-settings'
import { ANALYSIS_ERROR_CONTRACTS } from '@/lib/api/analysis-shared'

const fetchMock = vi.fn<typeof fetch>()
const signal = new AbortController().signal
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

describe('analysis prompt and authorization boundary', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  it('reads both defaults without a mutation and preserves exact text', async () => {
    const data = analysisSettingsFixture()
    data.initial_prompt.instructions = '  原文指令\n🙂  '
    fetchMock.mockResolvedValue(json(data))
    expect(await fetchAnalysisSettings(signal)).toEqual(data)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/analysis-settings',
      expect.objectContaining({ signal, cache: 'no-store', redirect: 'error' }),
    )
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined()
  })
  it('authorizes only the displayed provider revision', async () => {
    fetchMock.mockImplementation(async () => json(analysisSettingsFixture()))
    await saveAnalysisAutomation({
      expected_revision: 1,
      enabled: true,
      configuration_revision: 3,
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/analysis-settings/automation',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({
          expected_revision: 1,
          enabled: true,
          configuration_revision: 3,
        }),
      }),
    )
  })
  it.each(['', '  \n ', 'a\0b', '\ud800', 'a'.repeat(8001)])(
    'rejects invalid instructions locally',
    (value) => {
      expect(promptInstructionsSchema.safeParse(value).success).toBe(false)
    },
  )
  it('counts Unicode code points, not UTF-16 units', () => {
    expect(promptInstructionsSchema.safeParse('🙂'.repeat(8000)).success).toBe(
      true,
    )
    expect(promptInstructionsSchema.safeParse('🙂'.repeat(8001)).success).toBe(
      false,
    )
  })
  it.each(Object.entries(ANALYSIS_ERROR_CONTRACTS))(
    'maps only the exact status/code for %s and discards server messages',
    async (code, contract) => {
      fetchMock.mockResolvedValueOnce(
        json(
          { detail: { code, message: 'secret-path-sentinel' } },
          contract.status,
        ),
      )
      await expect(fetchAnalysisSettings(signal)).rejects.toMatchObject({
        code,
        message: contract.message,
      })
      fetchMock.mockResolvedValueOnce(
        json(
          { detail: { code, message: 'secret-path-sentinel' } },
          contract.status === 409 ? 400 : 409,
        ),
      )
      await expect(fetchAnalysisSettings(signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )
  it('rejects extra fields, swapped stage versions and unsafe integers', async () => {
    for (const invalid of [
      { ...analysisSettingsFixture(), api_key: 'sentinel' },
      {
        ...analysisSettingsFixture(),
        initial_prompt: analysisSettingsFixture().report_prompt,
      },
      {
        ...analysisSettingsFixture(),
        automation: {
          ...analysisSettingsFixture().automation,
          revision: Number.MAX_SAFE_INTEGER + 1,
        },
      },
    ]) {
      fetchMock.mockResolvedValueOnce(json(invalid))
      await expect(fetchAnalysisSettings(signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })
  it('does not retry transport failures or swallow aborts', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('network sentinel'))
    await expect(fetchAnalysisSettings(signal)).rejects.toMatchObject({
      code: 'service_unavailable',
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const abort = new DOMException('aborted', 'AbortError')
    fetchMock.mockRejectedValueOnce(abort)
    await expect(fetchAnalysisSettings(signal)).rejects.toBe(abort)
  })
})
