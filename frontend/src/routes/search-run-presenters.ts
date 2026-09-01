import douyinLogo from '@/assets/platforms/douyin.svg'
import kuaishouLogo from '@/assets/platforms/kuaishou.svg'
import toutiaoLogo from '@/assets/platforms/toutiao.svg'
import weiboLogo from '@/assets/platforms/weibo.svg'
import xiaohongshuLogo from '@/assets/platforms/xiaohongshu.svg'
import {
  SEARCH_PLATFORM_ORDER,
  SearchRunApiError,
  type SearchResultOpenOutcome,
  type SearchPlatform,
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
  toutiao: { label: '今日头条', logoSrc: toutiaoLogo },
  wb: { label: '微博', logoSrc: weiboLogo },
  ks: { label: '快手', logoSrc: kuaishouLogo },
  dy: { label: '抖音', logoSrc: douyinLogo },
  xhs: { label: '小红书', logoSrc: xiaohongshuLogo },
} satisfies Record<SearchPlatform, { label: string; logoSrc: string }>

const statusLabels: Record<SearchRunStatus, string> = {
  queued: '等待开始',
  running: '采集中',
  completed_with_results: '采集完成',
  completed_empty: '未发现内容',
  login_required: '需要登录',
  manual_challenge_required: '需要完成安全验证',
  platform_blocked_or_rate_limited: '平台限制访问',
  structure_changed: '页面结构已变化',
  browser_unavailable: '谷歌浏览器不可用',
  timed_out: '采集超时',
  cancelled: '已取消',
  internal_error: '采集失败',
}

const statusGuidance: Partial<
  Record<SearchRunStatus, (platformName: string) => string>
> = {
  completed_empty: () => '本次搜索正常完成，但没有发现符合条件的内容。',
  login_required: (platformName) =>
    `请先到“平台账号”检查${platformName}登录状态，再重新采集。`,
  manual_challenge_required: (platformName) =>
    `请在谷歌浏览器中完成${platformName}显示的安全验证，再重新采集。`,
  platform_blocked_or_rate_limited: (platformName) =>
    `${platformName}暂时限制了本次访问，请稍后手动重试。`,
  structure_changed: (platformName) =>
    `${platformName}页面或搜索协议已发生变化，当前版本无法可靠识别结果。`,
  browser_unavailable: () => '请确认谷歌浏览器已开启远程调试并允许本应用连接。',
  timed_out: () => '本次采集等待时间过长，已安全停止。',
  cancelled: () => '本次采集已取消，取消前发现的内容仍会保留。',
  internal_error: () => '本次采集未能完成，请重新启动服务后再试。',
}

export function searchRunStatusLabel(status: SearchRunStatus) {
  return statusLabels[status]
}

export function searchRunStatusGuidance(
  status: SearchRunStatus,
  platform: SearchPlatform,
) {
  const guidance = statusGuidance[status]
  return guidance?.(searchPlatformPresenters[platform].label) ?? null
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
  completed_with_failures: '部分平台未完成',
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
    return '服务中断，采集已暂停。确认谷歌浏览器可用后，可以继续。'
  }
  switch (item.latest_attempt?.run.status) {
    case 'login_required':
      return '请打开平台，在当前谷歌浏览器中登录后继续采集。'
    case 'manual_challenge_required':
      return '平台要求安全验证。请打开平台完成验证，再继续采集。'
    case 'platform_blocked_or_rate_limited':
      return '平台暂时限制了访问。可以打开平台检查，稍后继续，或先跳过此平台。'
    case 'browser_unavailable':
      return '无法连接谷歌浏览器。请确认浏览器已开启远程调试，并允许本应用连接。'
    case 'structure_changed':
      return '平台页面发生变化，暂时无法可靠读取结果。可以先跳过此平台。'
    case 'timed_out':
      return '采集等待超时。请检查网络和平台页面后继续。'
    default:
      return '本次采集未能完成。可以打开平台检查后继续，或先跳过此平台。'
  }
}

export const manualPageMessages: Record<ManualPageOutcome, string> = {
  opened_existing:
    '已在谷歌浏览器中打开平台页面。处理完成后，请点击“继续采集”。',
  opened_homepage:
    '已在谷歌浏览器中打开平台首页。原页面已不可用，请检查后再继续采集。',
  browser_unavailable: '无法连接谷歌浏览器，请检查远程调试设置后重试。',
  navigation_failed: '平台页面未能打开，请检查网络后重试。',
  internal_error: '打开平台失败，请稍后重试。',
  cancelled: '已取消打开平台。',
}

export const openOutcomeMessages: Record<SearchResultOpenOutcome, string> = {
  opened: '已在谷歌浏览器打开',
  content_not_found: '当前搜索中没有找到这条内容，请重新采集后再试。',
  content_unavailable: '这条内容暂时无法查看，可能已被删除或设为不可见。',
  login_required: '请先在当前谷歌浏览器中登录小红书，然后重试。',
  manual_challenge_required: '请在谷歌浏览器中完成小红书安全验证，然后重试。',
  platform_blocked_or_rate_limited: '小红书暂时限制了访问，请稍后再试。',
  structure_changed: '小红书页面发生变化，暂时无法打开这条内容。',
  browser_unavailable: '无法连接谷歌浏览器，请确认远程调试已开启。',
  internal_error: '打开失败，请稍后重试。',
}

export function openErrorMessage(error: unknown) {
  return error instanceof SearchRunApiError
    ? error.message
    : '打开原文时发生未知错误，请稍后重试。'
}
