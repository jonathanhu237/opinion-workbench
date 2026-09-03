import type { AnalysisAttempt } from '@/lib/api/content-analyses'

type InputIssue = NonNullable<AnalysisAttempt['input']>['issues'][number]

export const mediaIssueLabels: Record<InputIssue, string> = {
  text_incomplete: '正文不完整',
  text_unavailable: '没有可用正文',
  text_limit: '正文超过长度限制',
  inventory_unknown: '媒体清单尚未确认',
  media_missing: '尚未取得媒体文件',
  cover_only: '只有封面，不能替代原视频',
  asset_unavailable: '源文件不可用',
  asset_expired: '原文件已过期',
  download_failed: '文件下载失败',
  download_timeout: '文件获取超时',
  asset_blocked: '平台拒绝文件访问',
  unsafe_media_url: '地址不在允许的来源范围内',
  media_redirect: '文件要求跳转，未跟随访问',
  media_limit: '超过单条媒体下载预算',
  image_limit: '图片数量超过本次限制',
  video_limit: '视频数量超过本次限制',
  invalid_media: '文件未通过完整性校验',
  unsupported_transport: '暂不支持这种媒体传输方式',
  unsupported_media_type: '暂不支持这种文件格式',
  unsupported_codec: '暂不支持这种视频编码',
  audio_missing: '视频没有音轨',
  audio_unknown: '视频音轨尚未确认',
  probe_unavailable: '媒体检查工具不可用',
  probe_failed: '媒体检查失败',
  structure_changed: '媒体结构无法识别',
}
