import { z } from 'zod'

import { AI_ERROR_CONTRACTS } from '@/lib/api/ai-settings'
import { getApiBaseUrl } from '@/lib/api/client'

export const safeCount = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER)
export const safeId = safeCount.min(1)
export function isValidAnalysisProse(value: string) {
  return (
    value.trim().length > 0 &&
    !value.includes('\0') &&
    !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(
      value,
    )
  )
}
export const ANALYSIS_ERROR_CONTRACTS = {
  media_cache_policy_conflict: {
    status: 409,
    message: '媒体策略已改变，请刷新后重新确认。',
  },
  ...AI_ERROR_CONTRACTS,
  result_not_found: { status: 404, message: '未找到采集内容。' },
  content_analysis_not_found: { status: 404, message: '未找到初步分析记录。' },
  report_generation_not_found: { status: 404, message: '未找到报告生成任务。' },
  report_generation_active: {
    status: 409,
    message: '已有报告正在生成，请等待当前任务结束后再提交。',
  },
  no_eligible_contents: {
    status: 409,
    message: '当前没有符合所选规则的待分析内容，请刷新后重新选择。',
  },
  analysis_prompt_changed: {
    status: 409,
    message: '提示词已更新，请刷新后重试。',
  },
  analysis_policy_changed: {
    status: 409,
    message: '自动分析设置已更新，请刷新后重试。',
  },
  content_analysis_request_conflict: {
    status: 409,
    message: '此请求标识已用于其他分析操作。',
  },
  content_analysis_selection_conflict: {
    status: 409,
    message: '所选内容状态已变化，请刷新并使用对应的重试或重新分析操作。',
  },
  invalid_analysis_prompt: {
    status: 422,
    message: '提示词须为 1 至 8000 字的有效非空文本。',
  },
  invalid_result_interval: { status: 422, message: '首次采集时间范围不正确。' },
  analysis_storage_unavailable: {
    status: 503,
    message: '暂时无法读取或保存分析数据，请稍后重试。',
  },
  content_analysis_unavailable: {
    status: 503,
    message: '初步分析服务暂时不可用，请稍后重试。',
  },
} as const
type ProductCode = keyof typeof ANALYSIS_ERROR_CONTRACTS
type ErrorCode = ProductCode | 'invalid_response' | 'service_unavailable'

export class AnalysisApiError extends Error {
  override name = 'AnalysisApiError'
  readonly code: ErrorCode
  readonly status?: number
  constructor(code: ErrorCode, status?: number) {
    super(
      code === 'invalid_response'
        ? '分析接口返回的数据与当前应用不匹配。'
        : code === 'service_unavailable'
          ? '无法连接本机后端服务，请确认服务已经启动。'
          : ANALYSIS_ERROR_CONTRACTS[code].message,
    )
    this.code = code
    this.status = status
  }
}

function isProductCode(value: string): value is ProductCode {
  return Object.hasOwn(ANALYSIS_ERROR_CONTRACTS, value)
}

export async function analysisRequest(
  path: string,
  init: RequestInit = {},
  expectedStatus = 200,
): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      cache: 'no-store',
      redirect: 'error',
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch (error) {
    if (
      (error instanceof Error || error instanceof DOMException) &&
      error.name === 'AbortError'
    )
      throw error
    throw new AnalysisApiError('service_unavailable')
  }
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new AnalysisApiError('invalid_response', response.status)
  }
  if (!response.ok) {
    const parsed = z
      .strictObject({
        detail: z.strictObject({ code: z.string(), message: z.string() }),
      })
      .safeParse(payload)
    if (
      parsed.success &&
      isProductCode(parsed.data.detail.code) &&
      ANALYSIS_ERROR_CONTRACTS[parsed.data.detail.code].status ===
        response.status
    )
      throw new AnalysisApiError(parsed.data.detail.code, response.status)
    throw new AnalysisApiError('invalid_response', response.status)
  }
  if (response.status !== expectedStatus)
    throw new AnalysisApiError('invalid_response', response.status)
  return payload
}

export function decodeAnalysis<T>(schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value)
  if (!result.success) throw new AnalysisApiError('invalid_response')
  return result.data
}

export function jsonMutation(
  method: 'POST' | 'PUT',
  value: unknown,
): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  }
}

export function analysisPageSchema<T>(item: z.ZodType<T>) {
  return z
    .strictObject({
      items: z.array(item).max(100),
      total: safeCount,
      limit: safeId.max(100),
      offset: safeCount,
    })
    .refine(
      (page) =>
        page.items.length ===
        Math.min(page.limit, Math.max(0, page.total - page.offset)),
    )
}

export function checkPage<T extends { offset: number; limit: number }>(
  page: T,
  offset: number,
  limit: number,
): T {
  if (page.offset !== offset || page.limit !== limit)
    throw new AnalysisApiError('invalid_response')
  return page
}

export function uniqueIds(ids: number[]) {
  return new Set(ids).size === ids.length
}

export function analysisErrorMessage(error: unknown) {
  return error instanceof AnalysisApiError
    ? error.message
    : '暂时无法读取或保存分析数据，请稍后重试。'
}

export function isAmbiguousAnalysisError(error: unknown) {
  return (
    !(error instanceof AnalysisApiError) ||
    error.code === 'service_unavailable' ||
    error.code === 'invalid_response'
  )
}
