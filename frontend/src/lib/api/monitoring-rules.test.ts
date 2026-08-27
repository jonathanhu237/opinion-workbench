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
  monitoring_objects: [
    '龙田街道',
    '龙田社区',
    '老坑社区',
    '竹坑社区',
    '南布社区',
  ],
  issue_keywords: [],
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

  it.each([
    { ...rule, monitoring_objects: undefined },
    { ...rule, issue_keywords: undefined },
    { ...rule, issue_keywords: null },
    {
      ...rule,
      monitoring_objects: ['甲', '乙'],
      issue_keywords: ['噪音', '积水'],
      terms: ['甲 噪音', '乙 噪音', '甲 积水', '乙 积水'],
    },
    { ...rule, issue_keywords: ['噪音'] },
    { ...rule, monitoring_objects: [] },
    { ...rule, monitoring_objects: [' '.repeat(3)], terms: [' '.repeat(3)] },
  ])(
    'rejects missing groups and inconsistent derived-query projections',
    async (invalidRule) => {
      fetchMock.mockResolvedValue(
        new Response(JSON.stringify({ rules: [invalidRule] }), { status: 200 }),
      )
      await expect(
        fetchMonitoringRules(new AbortController().signal),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    },
  )

  it('decodes composed Unicode phrases with codepoint length limits', async () => {
    const object = '𠮷'.repeat(98)
    const composed = {
      ...rule,
      monitoring_objects: [object],
      issue_keywords: ['水'],
      terms: [`${object} 水`],
    }
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ rules: [composed] }), { status: 200 }),
    )
    await expect(
      fetchMonitoringRules(new AbortController().signal),
    ).resolves.toEqual({ rules: [composed] })
  })

  it('preserves legacy BOM names and complete phrases accepted by Python strip', async () => {
    const legacy = {
      ...rule,
      name: '\ufeff名称\ufeff',
      monitoring_objects: ['\ufeff完整短语'],
      issue_keywords: [],
      terms: ['\ufeff完整短语'],
    }
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ rules: [legacy] }), { status: 200 }),
    )
    await expect(
      fetchMonitoringRules(new AbortController().signal),
    ).resolves.toEqual({ rules: [legacy] })
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
        monitoring_objects: rule.monitoring_objects,
        issue_keywords: rule.issue_keywords,
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
        monitoring_objects: rule.monitoring_objects,
        issue_keywords: rule.issue_keywords,
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
      monitoring_objects: ['施工', '围挡'],
      issue_keywords: [],
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
