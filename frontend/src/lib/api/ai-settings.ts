import { z } from 'zod'

import { getApiBaseUrl } from '@/lib/api/client'

export const AI_SETTINGS_QUERY_KEY = ['ai-settings'] as const

const settingsSchema = z
  .object({
    base_url: z.string().min(1).max(2048).nullable(),
    model: z.string().min(1).max(200).nullable(),
    has_api_key: z.boolean(),
    revision: z.number().int().nonnegative(),
  })
  .strict()
  .refine((value) =>
    value.has_api_key
      ? value.base_url !== null && value.model !== null && value.revision > 0
      : value.base_url === null && value.model === null && value.revision === 0,
  )

const testResultSchema = z
  .object({
    status: z.literal('connected'),
    revision: z.number().int().positive(),
  })
  .strict()

const errorSchema = z
  .object({
    detail: z.object({ code: z.string(), message: z.string() }).strict(),
  })
  .strict()

export type AISettings = z.infer<typeof settingsSchema>
export type AISettingsPayload = {
  base_url: string
  model: string
  api_key?: string
}

export const AI_ERROR_CONTRACTS = {
  invalid_request: { status: 422, message: '请求内容不正确。' },
  invalid_ai_base_url: {
    status: 422,
    message: '请输入有效的公网 HTTPS Base URL，不含认证信息或查询参数。',
  },
  invalid_ai_model: {
    status: 422,
    message: '请输入有效的模型名称（最多 200 字符）。',
  },
  invalid_ai_api_key: {
    status: 422,
    message: 'API Key 不能为空，也不能包含空白或控制字符。',
  },
  ai_api_key_required: {
    status: 422,
    message: '首次保存或更改 Base URL 时，请重新输入 API Key。',
  },
  ai_configuration_required: { status: 409, message: '请先保存 AI 配置。' },
  ai_configuration_changed: {
    status: 409,
    message: '配置已更新，请重新加载后再测试。',
  },
  ai_operation_active: {
    status: 409,
    message: 'AI 操作正在进行，请结束后再试。',
  },
  ai_credentials_unavailable: {
    status: 503,
    message: 'API Key 无法安全读取或保存，请检查本机存储后重新输入。',
  },
  ai_settings_storage_unavailable: {
    status: 503,
    message: 'AI 配置暂时无法读取或保存，请稍后重试。',
  },
  ai_request_forbidden: {
    status: 403,
    message: '请从本机应用页面操作 AI 配置。',
  },
  ai_json_required: { status: 415, message: '请使用 JSON 提交 AI 配置。' },
  ai_destination_forbidden: {
    status: 422,
    message: '模型地址必须指向公网 HTTPS 服务。',
  },
  ai_authentication_failed: {
    status: 502,
    message: '模型服务未接受 API Key，请检查密钥和服务区域。',
  },
  ai_model_not_found: {
    status: 502,
    message: '模型或接口不存在，请检查 Base URL 和模型名称。',
  },
  ai_rate_limited: {
    status: 429,
    message: '模型服务限流或额度不足，请检查后稍后重试。',
  },
  ai_provider_unavailable: {
    status: 503,
    message: '模型服务暂时无法连接，请稍后重试。',
  },
  ai_timeout: { status: 504, message: '模型请求超时，请稍后重试。' },
  ai_invalid_response: {
    status: 502,
    message: '模型未返回完整有效的文本响应，请检查接口兼容性。',
  },
  ai_unsupported_input: {
    status: 502,
    message: '模型服务不支持当前请求格式，请检查接口兼容性。',
  },
  ai_request_too_large: { status: 413, message: '模型请求超出服务限制。' },
} as const

type ProductErrorCode = keyof typeof AI_ERROR_CONTRACTS
type AISettingsErrorCode =
  ProductErrorCode | 'invalid_response' | 'service_unavailable'

export class AISettingsApiError extends Error {
  override name = 'AISettingsApiError'
  readonly code: AISettingsErrorCode
  readonly status: number | undefined

  constructor(code: AISettingsErrorCode, status?: number) {
    super(
      code === 'invalid_response'
        ? 'AI 配置接口返回的数据与当前应用不匹配。'
        : code === 'service_unavailable'
          ? '无法连接本机后端服务，请确认服务已经启动。'
          : AI_ERROR_CONTRACTS[code].message,
    )
    this.code = code
    this.status = status
  }
}

function isProductCode(code: string): code is ProductErrorCode {
  return Object.hasOwn(AI_ERROR_CONTRACTS, code)
}

async function request(path: string, init: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}/ai-settings${path}`, {
      ...init,
      cache: 'no-store',
      redirect: 'error',
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new AISettingsApiError('service_unavailable')
  }
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new AISettingsApiError('invalid_response', response.status)
  }
  if (!response.ok) {
    const parsed = errorSchema.safeParse(payload)
    if (parsed.success && isProductCode(parsed.data.detail.code)) {
      const code = parsed.data.detail.code
      if (AI_ERROR_CONTRACTS[code].status === response.status) {
        // Never render or retain an upstream error message or request body.
        throw new AISettingsApiError(code, response.status)
      }
    }
    throw new AISettingsApiError('invalid_response', response.status)
  }
  if (response.status !== 200)
    throw new AISettingsApiError('invalid_response', response.status)
  return payload
}

function readSettings(payload: unknown) {
  const parsed = settingsSchema.safeParse(payload)
  if (!parsed.success) throw new AISettingsApiError('invalid_response', 200)
  return parsed.data
}

export async function fetchAISettings(
  signal: AbortSignal,
): Promise<AISettings> {
  return readSettings(await request('', { signal }))
}

// Call directly from transient form state, never through useMutation variables.
export async function saveAISettings(
  payload: AISettingsPayload,
  signal?: AbortSignal,
): Promise<AISettings> {
  return readSettings(
    await request('', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    }),
  )
}

export async function testAIConnection(
  revision: number,
  signal?: AbortSignal,
): Promise<void> {
  const payload = await request('/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ revision }),
    signal,
  })
  const parsed = testResultSchema.safeParse(payload)
  if (!parsed.success || parsed.data.revision !== revision) {
    throw new AISettingsApiError('invalid_response', 200)
  }
}
