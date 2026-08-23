export const HEALTH_SERVICE = 'longtian-public-opinion-api' as const

export type HealthResponse = {
  status: 'ok'
  service: typeof HEALTH_SERVICE
}

export class HealthCheckError extends Error {
  override name = 'HealthCheckError'
}

function isHealthResponse(payload: unknown): payload is HealthResponse {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }

  const candidate = payload as Record<string, unknown>
  return candidate.status === 'ok' && candidate.service === HEALTH_SERVICE
}

function getApiBaseUrl() {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()
  return (configuredBaseUrl || '/api/v1').replace(/\/+$/, '')
}

export async function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${getApiBaseUrl()}/health`, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    throw new HealthCheckError(`健康检查请求失败（HTTP ${response.status}）`)
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new HealthCheckError('健康检查返回的内容不是有效 JSON')
  }

  if (!isHealthResponse(payload)) {
    throw new HealthCheckError('健康检查返回的数据与当前应用不匹配')
  }

  return payload
}
