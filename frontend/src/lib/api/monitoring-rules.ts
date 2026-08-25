import { z } from 'zod'

import { getApiBaseUrl } from '@/lib/api/client'

export const MONITORING_RULES_QUERY_KEY = ['monitoring-rules'] as const

function codePointLength(value: string) {
  return Array.from(value).length
}

const ruleNameSchema = z
  .string()
  .refine(
    (value) => codePointLength(value) >= 1 && codePointLength(value) <= 80,
  )
const ruleTermSchema = z
  .string()
  .refine(
    (value) => codePointLength(value) >= 1 && codePointLength(value) <= 100,
  )

const monitoringRuleSchema = z
  .object({
    id: z.number().int().positive(),
    name: ruleNameSchema,
    terms: z.array(ruleTermSchema).min(1).max(100),
    enabled: z.boolean(),
  })
  .strict()

const monitoringRulesResponseSchema = z
  .object({
    rules: z.array(monitoringRuleSchema),
  })
  .strict()

const errorEnvelopeSchema = z
  .object({
    detail: z
      .object({
        code: z.string(),
        message: z.string(),
      })
      .strict(),
  })
  .strict()

export type MonitoringRule = z.infer<typeof monitoringRuleSchema>
export type MonitoringRulesResponse = z.infer<
  typeof monitoringRulesResponseSchema
>

export type MonitoringRulePayload = {
  name: string
  terms: string[]
  enabled: boolean
}

export type MonitoringRuleApiErrorCode =
  | 'invalid_request'
  | 'invalid_monitoring_rule'
  | 'duplicate_monitoring_rule_term'
  | 'monitoring_rule_name_conflict'
  | 'monitoring_rule_not_found'
  | 'monitoring_rule_storage_unavailable'
  | 'request_failed'
  | 'invalid_response'
  | 'service_unavailable'

export class MonitoringRuleApiError extends Error {
  override name = 'MonitoringRuleApiError'
  readonly code: MonitoringRuleApiErrorCode
  readonly status: number | undefined

  constructor(
    message: string,
    code: MonitoringRuleApiErrorCode,
    status?: number,
  ) {
    super(message)
    this.code = code
    this.status = status
  }
}

const productErrorContracts = {
  invalid_request: {
    status: 422,
    message: '提交的监控规则格式不正确，请检查后重试。',
  },
  invalid_monitoring_rule: {
    status: 422,
    message: '监控规则内容不符合要求，请检查后重试。',
  },
  duplicate_monitoring_rule_term: {
    status: 422,
    message: '同一条监控规则中不能包含重复搜索词。',
  },
  monitoring_rule_name_conflict: {
    status: 409,
    message: '已经存在同名的监控规则。',
  },
  monitoring_rule_not_found: {
    status: 404,
    message: '未找到该监控规则，可能已被删除。',
  },
  monitoring_rule_storage_unavailable: {
    status: 503,
    message: '监控规则暂时无法读取或保存，请稍后重试。',
  },
} as const

function isKnownProductErrorCode(
  code: string,
): code is keyof typeof productErrorContracts {
  return code in productErrorContracts
}

function invalidResponse(status?: number) {
  return new MonitoringRuleApiError(
    '监控规则接口返回的数据与当前应用不匹配。',
    'invalid_response',
    status,
  )
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw invalidResponse(response.status)
  }
}

function errorFromResponse(status: number, payload: unknown) {
  const parsed = errorEnvelopeSchema.safeParse(payload)

  if (parsed.success && isKnownProductErrorCode(parsed.data.detail.code)) {
    const code = parsed.data.detail.code
    const contract = productErrorContracts[code]
    if (status !== contract.status) {
      return invalidResponse(status)
    }
    return new MonitoringRuleApiError(contract.message, code, status)
  }

  return new MonitoringRuleApiError(
    `监控规则请求失败（HTTP ${status}）`,
    'request_failed',
    status,
  )
}

async function request(path: string, init: RequestInit) {
  try {
    return await fetch(`${getApiBaseUrl()}${path}`, init)
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw error
    }

    throw new MonitoringRuleApiError(
      '无法连接本机后端服务，请确认服务已经启动。',
      'service_unavailable',
    )
  }
}

function jsonRequest(payload: MonitoringRulePayload): RequestInit {
  return {
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  }
}

function parseRule(payload: unknown, status: number) {
  const parsed = monitoringRuleSchema.safeParse(payload)
  if (!parsed.success) {
    throw invalidResponse(status)
  }
  return parsed.data
}

export async function fetchMonitoringRules(
  signal: AbortSignal,
): Promise<MonitoringRulesResponse> {
  const response = await request('/monitoring-rules', {
    headers: { Accept: 'application/json' },
    signal,
  })
  const payload = await readJson(response)

  if (!response.ok) {
    throw errorFromResponse(response.status, payload)
  }
  if (response.status !== 200) {
    throw invalidResponse(response.status)
  }

  const parsed = monitoringRulesResponseSchema.safeParse(payload)
  if (!parsed.success) {
    throw invalidResponse(response.status)
  }

  return parsed.data
}

export async function createMonitoringRule(
  payload: MonitoringRulePayload,
  signal?: AbortSignal,
): Promise<MonitoringRule> {
  const response = await request('/monitoring-rules', {
    ...jsonRequest(payload),
    method: 'POST',
    signal,
  })
  const responsePayload = await readJson(response)

  if (!response.ok) {
    throw errorFromResponse(response.status, responsePayload)
  }
  if (response.status !== 201) {
    throw invalidResponse(response.status)
  }

  return parseRule(responsePayload, response.status)
}

export async function updateMonitoringRule(
  ruleId: number,
  payload: MonitoringRulePayload,
  signal?: AbortSignal,
): Promise<MonitoringRule> {
  const response = await request(
    `/monitoring-rules/${encodeURIComponent(ruleId)}`,
    {
      ...jsonRequest(payload),
      method: 'PUT',
      signal,
    },
  )
  const responsePayload = await readJson(response)

  if (!response.ok) {
    throw errorFromResponse(response.status, responsePayload)
  }
  if (response.status !== 200) {
    throw invalidResponse(response.status)
  }

  return parseRule(responsePayload, response.status)
}

export async function deleteMonitoringRule(
  ruleId: number,
  signal?: AbortSignal,
): Promise<void> {
  const response = await request(
    `/monitoring-rules/${encodeURIComponent(ruleId)}`,
    {
      method: 'DELETE',
      headers: { Accept: 'application/json' },
      signal,
    },
  )

  if (!response.ok) {
    const responsePayload = await readJson(response)
    throw errorFromResponse(response.status, responsePayload)
  }
  if (response.status !== 204) {
    throw invalidResponse(response.status)
  }
}
