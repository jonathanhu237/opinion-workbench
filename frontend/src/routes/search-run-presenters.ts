import weiboLogo from '@/assets/platforms/weibo.svg'
import {
  SEARCH_PLATFORM_ORDER,
  SearchRunApiError,
  type SearchFailureReason,
  type SearchResultOpenOutcome,
  type SearchPlatform,
  type SearchTermDiagnostic,
  type SearchRunSummary,
  type SearchRunStatus,
} from '@/lib/api/search-runs'
import type {
  SearchBatchItemStatus,
  SearchBatchStatus,
  SearchBatchItem,
  ManualPageOutcome,
} from '@/lib/api/search-batches'

export const searchPlatformOrder = SEARCH_PLATFORM_ORDER

export const searchPlatformPresenters = {
  wb: { label: '微博', logoSrc: weiboLogo },
} satisfies Record<SearchPlatform, { label: string; logoSrc: string }>

const statusLabels: Record<SearchRunStatus, string> = {
  queued: '等待开始',
  running: '采集中',
  completed_with_results: '采集完成',
  completed_empty: '未发现内容',
  login_required: '需要登录',
  manual_challenge_required: '需要完成安全验证',
  platform_blocked_or_rate_limited: '平台限制访问',
  structure_changed: '采集内容无法识别',
  browser_unavailable: '应用专用浏览器不可用',
  timed_out: '采集超时',
  cancelled: '已取消',
  internal_error: '采集失败',
}

const failureReasonLabels: Record<SearchFailureReason, string> = {
  page_state_unrecognized: '平台页面状态无法识别',
  search_context_unavailable: '平台搜索会话不可用',
  search_response_incompatible: '搜索响应格式不兼容',
  search_results_incompatible: '搜索结果格式不兼容',
  search_pagination_incompatible: '搜索翻页信息不兼容',
}

export type SearchRunPresentation = Pick<
  SearchRunSummary,
  | 'status'
  | 'platform'
  | 'failure_reason'
  | 'execution_limit'
  | 'incomplete_terms'
>

export function searchFailureReasonLabel(reason: SearchFailureReason) {
  return failureReasonLabels[reason]
}

function failureReasonGuidance(
  platformName: string,
  reason: SearchFailureReason,
) {
  const guidance: Record<SearchFailureReason, string> = {
    page_state_unrecognized: `当前未能识别${platformName}页面的工作状态。请打开平台，确认没有停留在登录或安全验证页面，处理后再重新采集。`,
    search_context_unavailable: `无法确认${platformName}的搜索会话或必要登录信息。请检查应用打开的专用谷歌浏览器中的平台会话，确认后再重新采集。`,
    search_response_incompatible: `收到的${platformName}搜索响应格式与采集器不兼容，需要更新采集器后再试；重新打开平台也无法修复这个问题。`,
    search_results_incompatible: `收到的${platformName}结果条目无法被当前采集器安全识别，需要更新采集器后再试；已经保存的结果仍会保留。`,
    search_pagination_incompatible: `无法确认${platformName}搜索结果的安全翻页信息，已停止以避免重复或漏采。需要更新采集器后再试。`,
  }
  return guidance[reason]
}

function legacyStructureGuidance(platformName: string) {
  return `未能可靠识别${platformName}的采集内容。可以打开平台检查后再试；如果问题持续，请更新采集器。`
}

export function incompleteTermsGuidance(
  diagnostics: readonly SearchTermDiagnostic[] | undefined,
) {
  const items = diagnostics ?? []
  if (items.length === 0) return null
  const terms = items
    .map(
      (diagnostic) =>
        `${diagnostic.term}（已保留 ${diagnostic.result_count} 条）`,
    )
    .join('、')
  const retained = items.reduce((total, item) => total + item.result_count, 0)
  const prefix =
    retained > 0 ? '本次采集已保存可识别内容，但' : '本次采集未能确认完整结果，'
  return `${prefix}以下搜索词未能完整获取：${terms}。已保存内容仍可使用，后续可按需重新发起采集。`
}

const statusGuidance: Partial<
  Record<SearchRunStatus, (platformName: string) => string>
> = {
  completed_empty: () => '本次搜索正常完成，但没有发现符合条件的内容。',
  login_required: (platformName) =>
    `请先到“平台账号”检查${platformName}登录状态，再重新采集。`,
  manual_challenge_required: (platformName) =>
    `请在应用打开的专用谷歌浏览器中完成${platformName}显示的安全验证，再重新采集。`,
  platform_blocked_or_rate_limited: (platformName) =>
    `${platformName}暂时限制了本次访问，请稍后手动重试。`,
  browser_unavailable: () =>
    '应用专用的谷歌浏览器暂时不可用，请重新采集；应用会在需要时自动启动。',
  timed_out: () => '本次采集等待时间过长，已安全停止。',
  cancelled: () => '本次采集已取消，取消前发现的内容仍会保留。',
  internal_error: () => '本次采集未能完成，请重新启动服务后再试。',
}

export function searchRunStatusLabel(
  status: SearchRunStatus,
  failureReason: SearchFailureReason | null = null,
) {
  if (status === 'structure_changed' && failureReason !== null) {
    return searchFailureReasonLabel(failureReason)
  }
  return statusLabels[status]
}

export function searchRunDisplayLabel(run: SearchRunPresentation) {
  if (
    run.incomplete_terms?.length &&
    (run.status === 'completed_with_results' ||
      run.status === 'completed_empty')
  ) {
    return '采集未完整覆盖'
  }
  return searchRunStatusLabel(run.status, run.failure_reason)
}

export function searchRunStatusGuidance(
  run: SearchRunPresentation,
): string | null
export function searchRunStatusGuidance(
  status: SearchRunStatus,
  platform: SearchPlatform,
  failureReason?: SearchFailureReason | null,
): string | null
export function searchRunStatusGuidance(
  runOrStatus: SearchRunPresentation | SearchRunStatus,
  platform?: SearchPlatform,
  failureReason: SearchFailureReason | null = null,
) {
  const run =
    typeof runOrStatus === 'string'
      ? platform === undefined
        ? null
        : {
            status: runOrStatus,
            platform,
            failure_reason: failureReason,
          }
      : runOrStatus
  if (run === null) return null
  if (
    run.status === 'timed_out' &&
    'execution_limit' in run &&
    run.execution_limit
  ) {
    const limit = {
      requests: '浏览器请求次数',
      pages: '搜索页数',
      time: '执行时间',
    }
    return `已达到本次${limit[run.execution_limit]}预算，采集未全部完成。已入库内容保留，配置条数未被修改；请按需调整配置后手动继续或重试。`
  }
  const platformName = searchPlatformPresenters[run.platform].label
  if (run.status === 'structure_changed') {
    return run.failure_reason === null
      ? legacyStructureGuidance(platformName)
      : failureReasonGuidance(platformName, run.failure_reason)
  }
  if (
    (run.status === 'completed_with_results' ||
      run.status === 'completed_empty') &&
    run.incomplete_terms?.length
  ) {
    return incompleteTermsGuidance(run.incomplete_terms)
  }
  const guidance = statusGuidance[run.status]
  return guidance?.(platformName) ?? null
}

export function formatLocalDate(value: string | null) {
  if (value === null) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

const batchStatusLabels: Record<SearchBatchStatus, string> = {
  queued: '等待开始',
  running: '采集中',
  paused_for_manual_action: '等待你处理',
  completed: '全部完成',
  completed_with_failures: '部分采集未完成',
  cancelled: '已取消',
  internal_error: '采集失败',
}

const batchItemStatusLabels: Record<SearchBatchItemStatus, string> = {
  queued: '等待中',
  running: '采集中',
  paused_for_manual_action: '等待你处理',
  completed: '已完成',
  failed: '未完成',
  skipped: '已跳过',
  cancelled: '已取消',
}

export function searchBatchStatusLabel(status: SearchBatchStatus) {
  return batchStatusLabels[status]
}

export function searchBatchItemStatusLabel(status: SearchBatchItemStatus) {
  return batchItemStatusLabels[status]
}

export function batchPauseGuidance(item: SearchBatchItem) {
  if (item.pause_reason === 'process_interrupted') {
    return '服务中断，采集已暂停。确认应用专用的谷歌浏览器可用后，可以继续。'
  }
  const run = item.latest_attempt?.run
  if (
    run?.status === 'structure_changed' ||
    (run?.status === 'timed_out' && run.execution_limit)
  ) {
    return searchRunStatusGuidance(run)
  }
  switch (item.latest_attempt?.run.status) {
    case 'login_required':
      return '请打开平台，在应用专用的谷歌浏览器中登录后继续采集。'
    case 'manual_challenge_required':
      return '平台要求安全验证。请在应用专用的谷歌浏览器中打开平台完成验证，再继续采集。'
    case 'platform_blocked_or_rate_limited':
      return '微博暂时限制了访问。可以打开微博检查，稍后继续，或先跳过本次采集。'
    case 'browser_unavailable':
      return '应用专用的谷歌浏览器暂时不可用。请重新打开采集或重试；应用会在需要时自动启动。'
    case 'timed_out':
      return '采集等待超时。请检查网络和平台页面后继续。'
    default:
      return '本次采集未能完成。可以打开微博检查后继续，或先跳过本次采集。'
  }
}

export const manualPageMessages: Record<ManualPageOutcome, string> = {
  opened_existing:
    '已在应用专用的谷歌浏览器中打开平台页面。处理完成后，请点击“继续采集”。',
  opened_homepage:
    '已在应用专用的谷歌浏览器中打开平台首页。原页面已不可用，请检查后再继续采集。',
  browser_unavailable:
    '应用专用的谷歌浏览器暂时不可用，请重试；应用会在需要时自动启动。',
  navigation_failed: '平台页面未能打开，请检查网络后重试。',
  internal_error: '打开平台失败，请稍后重试。',
  cancelled: '已取消打开平台。',
}

export const openOutcomeMessages: Record<SearchResultOpenOutcome, string> = {
  opened: '已在应用专用的谷歌浏览器打开',
  content_not_found: '当前搜索中没有找到这条内容，请重新采集后再试。',
  content_unavailable: '这条内容暂时无法查看，可能已被删除或设为不可见。',
  login_required: '请先在应用专用的谷歌浏览器中登录微博，然后重试。',
  manual_challenge_required:
    '请在应用专用的谷歌浏览器中完成微博安全验证，然后重试。',
  platform_blocked_or_rate_limited: '微博暂时限制了访问，请稍后再试。',
  structure_changed: '微博页面发生变化，暂时无法打开这条内容。',
  browser_unavailable:
    '应用专用的谷歌浏览器暂时不可用，请重试；应用会在需要时自动启动。',
  internal_error: '打开失败，请稍后重试。',
}

export function openErrorMessage(error: unknown) {
  return error instanceof SearchRunApiError
    ? error.message
    : '打开原文时发生未知错误，请稍后重试。'
}
