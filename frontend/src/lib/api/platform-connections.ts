import { getApiBaseUrl } from '@/lib/api/client'

export const PLATFORM_CONNECTIONS_QUERY_KEY = ['platform-connections'] as const

// Keep this decoder in the same stable order as the backend catalog and the
// search/automation platform descriptors.  The order is part of the response
// contract because it preserves the existing Weibo-first UI position while
// appending the newly supported platforms.
const platformIds = ['wb', 'dy', 'ks', 'xhs', 'toutiao'] as const
const availabilityValues = ['enabled', 'coming_soon'] as const
const statusValues = [
  'not_checked',
  'checking',
  'action_required',
  'connected',
  'disconnected',
  'failed',
  'coming_soon',
] as const
const guidanceValues = [
  'none',
  'starting_browser',
  'retry_browser',
  'enable_remote_debugging',
  'approve_connection',
  'complete_login',
  'retry',
] as const

export type PlatformId = (typeof platformIds)[number]
export type PlatformAvailability = (typeof availabilityValues)[number]
export type PlatformConnectionStatus = (typeof statusValues)[number]
export type PlatformGuidance = (typeof guidanceValues)[number]

export type PlatformConnection = {
  platform: PlatformId
  display_name: string
  availability: PlatformAvailability
  status: PlatformConnectionStatus
  guidance: PlatformGuidance
  last_checked_at: string | null
  active_attempt_id: string | null
}

export type PlatformConnectionsResponse = {
  platforms: PlatformConnection[]
}

export type StartPlatformConnectionAttemptResponse = {
  attempt_id: string
  platform: PlatformConnection
}

export type PlatformConnectionErrorCode =
  | 'platform_not_found'
  | 'platform_not_available'
  | 'connection_attempt_active'
  | 'request_failed'
  | 'invalid_response'
  | 'service_unavailable'

export class PlatformConnectionApiError extends Error {
  override name = 'PlatformConnectionApiError'
  readonly code: PlatformConnectionErrorCode
  readonly status: number | undefined

  constructor(
    message: string,
    code: PlatformConnectionErrorCode,
    status?: number,
  ) {
    super(message)
    this.code = code
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const actualKeys = Object.keys(value)
  return (
    actualKeys.length === keys.length &&
    actualKeys.every((key) => keys.includes(key))
  )
}

function isOneOf<const Value extends readonly string[]>(
  value: unknown,
  values: Value,
): value is Value[number] {
  return typeof value === 'string' && values.includes(value)
}

function isUuid(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  )
}

function isUtcIsoTimestamp(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /(?:Z|\+00:00)$/.test(value) &&
    Number.isFinite(Date.parse(value))
  )
}

function parsePlatformConnection(value: unknown): PlatformConnection | null {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      'platform',
      'display_name',
      'availability',
      'status',
      'guidance',
      'last_checked_at',
      'active_attempt_id',
    ]) ||
    !isOneOf(value.platform, platformIds) ||
    typeof value.display_name !== 'string' ||
    value.display_name.trim().length === 0 ||
    !isOneOf(value.availability, availabilityValues) ||
    !isOneOf(value.status, statusValues) ||
    !isOneOf(value.guidance, guidanceValues) ||
    (value.last_checked_at !== null &&
      !isUtcIsoTimestamp(value.last_checked_at)) ||
    (value.active_attempt_id !== null && !isUuid(value.active_attempt_id))
  ) {
    return null
  }

  if (
    (value.guidance === 'starting_browser' && value.status !== 'checking') ||
    (value.guidance === 'retry_browser' && value.status !== 'failed')
  ) {
    return null
  }

  return {
    platform: value.platform,
    display_name: value.display_name,
    availability: value.availability,
    status: value.status,
    guidance: value.guidance,
    last_checked_at: value.last_checked_at,
    active_attempt_id: value.active_attempt_id,
  }
}

function parsePlatformConnectionsResponse(
  value: unknown,
): PlatformConnectionsResponse | null {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ['platforms']) ||
    !Array.isArray(value.platforms) ||
    value.platforms.length !== platformIds.length
  ) {
    return null
  }

  const platforms = value.platforms.map(parsePlatformConnection)
  if (
    platforms.some((platform) => platform === null) ||
    platforms.some(
      (platform, index) => platform?.platform !== platformIds[index],
    )
  ) {
    return null
  }

  return { platforms: platforms as PlatformConnection[] }
}

function parseStartAttemptResponse(
  value: unknown,
): StartPlatformConnectionAttemptResponse | null {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ['attempt_id', 'platform']) ||
    !isUuid(value.attempt_id)
  ) {
    return null
  }

  const platform = parsePlatformConnection(value.platform)
  if (platform === null || platform.active_attempt_id !== value.attempt_id) {
    return null
  }

  return { attempt_id: value.attempt_id, platform }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw new PlatformConnectionApiError(
      '平台连接接口返回的内容不是有效 JSON',
      'invalid_response',
      response.status,
    )
  }
}

function errorFromResponse(status: number, payload: unknown) {
  const detail = isRecord(payload) ? payload.detail : null
  const code = isRecord(detail) ? detail.code : null
  const message = isRecord(detail) ? detail.message : null
  const hasExpectedShape =
    isRecord(payload) &&
    hasExactKeys(payload, ['detail']) &&
    isRecord(detail) &&
    hasExactKeys(detail, ['code', 'message']) &&
    typeof message === 'string'

  if (hasExpectedShape && code === 'platform_not_found') {
    return new PlatformConnectionApiError('未找到这个平台配置。', code, status)
  }
  if (hasExpectedShape && code === 'platform_not_available') {
    return new PlatformConnectionApiError('该平台暂未接入。', code, status)
  }
  if (hasExpectedShape && code === 'connection_attempt_active') {
    return new PlatformConnectionApiError(
      '已有平台连接任务正在运行，请完成后再试。',
      code,
      status,
    )
  }

  return new PlatformConnectionApiError(
    `平台连接请求失败（HTTP ${status}）`,
    'request_failed',
    status,
  )
}

async function request(path: string, init: RequestInit) {
  try {
    return await fetch(`${getApiBaseUrl()}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new PlatformConnectionApiError(
      '无法连接本机后端服务，请确认服务已经启动。',
      'service_unavailable',
    )
  }
}

export async function fetchPlatformConnections(
  signal: AbortSignal,
): Promise<PlatformConnectionsResponse> {
  const response = await request('/platform-connections', {
    headers: { Accept: 'application/json' },
    signal,
  })
  const payload = await readJson(response)

  if (!response.ok) {
    throw errorFromResponse(response.status, payload)
  }

  const parsed = parsePlatformConnectionsResponse(payload)
  if (parsed === null) {
    throw new PlatformConnectionApiError(
      '平台连接接口返回的数据与当前应用不匹配。',
      'invalid_response',
      response.status,
    )
  }

  return parsed
}

export async function startPlatformConnectionAttempt(
  platform: PlatformId,
  signal?: AbortSignal,
): Promise<StartPlatformConnectionAttemptResponse> {
  const response = await request(
    `/platform-connections/${encodeURIComponent(platform)}/attempts`,
    {
      method: 'POST',
      headers: { Accept: 'application/json' },
      signal,
    },
  )
  const payload = await readJson(response)

  if (!response.ok) {
    throw errorFromResponse(response.status, payload)
  }
  if (response.status !== 202) {
    throw new PlatformConnectionApiError(
      `平台连接请求返回了意外状态（HTTP ${response.status}）`,
      'invalid_response',
      response.status,
    )
  }

  const parsed = parseStartAttemptResponse(payload)
  if (parsed === null || parsed.platform.platform !== platform) {
    throw new PlatformConnectionApiError(
      '平台连接接口返回的数据与当前应用不匹配。',
      'invalid_response',
      response.status,
    )
  }

  return parsed
}
