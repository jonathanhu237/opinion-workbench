import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createMonitoringRule,
  deleteMonitoringRule,
  fetchMonitoringRules,
  MonitoringRuleApiError,
  updateMonitoringRule,
  type MonitoringRule,
} from '@/lib/api/monitoring-rules'

const rule: MonitoringRule = {
  id: 1,
  name: '龙田街道及四个社区',
  terms: ['龙田街道', '龙田社区', '老坑社区', '竹坑社区', '南布社区'],
  enabled: true,
}

describe('monitoring rules API boundary', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('decodes the exact ordered rule response and forwards cancellation', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ rules: [rule] }), { status: 200 }),
    )
    const controller = new AbortController()

    await expect(fetchMonitoringRules(controller.signal)).resolves.toEqual({
      rules: [rule],
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/monitoring-rules', {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
  })

  it('rejects response drift without exposing unexpected stored fields', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          rules: [{ ...rule, normalized_name: 'credential-sentinel' }],
        }),
        { status: 200 },
      ),
    )

    const result = fetchMonitoringRules(new AbortController().signal)

    await expect(result).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(result).rejects.not.toThrow(/credential-sentinel/)
  })

  it('maps known product errors to bounded Chinese guidance', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'monitoring_rule_name_conflict',
            message: 'raw backend text credential-sentinel',
          },
        }),
        { status: 409 },
      ),
    )

    await expect(
      createMonitoringRule({
        name: rule.name,
        terms: rule.terms,
        enabled: true,
      }),
    ).rejects.toMatchObject({
      code: 'monitoring_rule_name_conflict',
      message: '已经存在同名的监控规则。',
      status: 409,
    })
  })

  it('rejects a known product error paired with the wrong HTTP status', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'monitoring_rule_name_conflict',
            message: 'raw backend text credential-sentinel',
          },
        }),
        { status: 503 },
      ),
    )

    await expect(
      createMonitoringRule({
        name: rule.name,
        terms: rule.terms,
        enabled: true,
      }),
    ).rejects.toMatchObject({
      code: 'invalid_response',
      message: '监控规则接口返回的数据与当前应用不匹配。',
      status: 503,
    })
  })

  it('sends exact create and full update payloads', async () => {
    const createdRule = { ...rule, id: 2, name: '道路施工' }
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify(createdRule), { status: 201 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...createdRule, enabled: false }), {
          status: 200,
        }),
      )
    const payload = {
      name: createdRule.name,
      terms: ['施工', '围挡'],
      enabled: true,
    }

    await expect(createMonitoringRule(payload)).resolves.toEqual(createdRule)
    await expect(
      updateMonitoringRule(2, { ...payload, enabled: false }),
    ).resolves.toEqual({ ...createdRule, enabled: false })
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/monitoring-rules',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/monitoring-rules/2',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ ...payload, enabled: false }),
      }),
    )
  })

  it('accepts only an empty 204 delete response', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await expect(deleteMonitoringRule(3)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/monitoring-rules/3',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('bounds malformed and non-JSON failures', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'credential-sentinel' }), {
          status: 500,
        }),
      )
      .mockResolvedValueOnce(new Response('not json', { status: 200 }))

    await expect(deleteMonitoringRule(4)).rejects.toMatchObject({
      code: 'request_failed',
      message: '监控规则请求失败（HTTP 500）',
    })
    await expect(
      fetchMonitoringRules(new AbortController().signal),
    ).rejects.toBeInstanceOf(MonitoringRuleApiError)
  })
})
