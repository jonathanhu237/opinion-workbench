import toutiaoLogo from '@/assets/platforms/toutiao.svg'
import weiboLogo from '@/assets/platforms/weibo.svg'
import type { SearchPlatform, SearchRunStatus } from '@/lib/api/search-runs'

export const searchPlatformOrder = [
  'toutiao',
  'wb',
] as const satisfies readonly SearchPlatform[]

export const searchPlatformPresenters = {
  toutiao: { label: '今日头条', logoSrc: toutiaoLogo },
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
