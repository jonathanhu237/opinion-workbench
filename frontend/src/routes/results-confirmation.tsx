import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { AISettings } from '@/lib/api/ai-settings'
import type { AnalysisSettings } from '@/lib/api/analysis-settings'
import type { AnalysisRequest } from '@/lib/api/content-analyses'

export type AnalysisConfirmation = {
  provider: AISettings
  settings: AnalysisSettings
  request: AnalysisRequest
  count: number
  label: string
}

export function ResultsConfirmation({
  confirmation,
  pending,
  ambiguous,
  error,
  blocked,
  onClose,
  onConfirm,
  onReconfirm,
}: {
  confirmation: AnalysisConfirmation
  pending: boolean
  ambiguous: boolean
  error: string | null
  blocked: boolean
  onClose: () => void
  onConfirm: () => void
  onReconfirm: () => void
}) {
  const all = confirmation.request.selection.kind === 'all_never_started'
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose()
      }}
    >
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl"
        showCloseButton={!pending}
      >
        <DialogHeader>
          <DialogTitle>{confirmation.label}</DialogTitle>
          <DialogDescription>
            {all
              ? `当前有 ${confirmation.count} 条内容还没做初步分析，包括历史内容。提交后按这批内容处理，已在其他任务中的内容不会重复处理。`
              : `将${confirmation.request.selection.kind === 'retry' ? '重试' : confirmation.request.selection.kind === 'reanalysis' ? '重新分析' : '分析'}所选内容；已有结果和历史版本会保留。`}
          </DialogDescription>
        </DialogHeader>
        <dl className="grid gap-3 rounded-lg border p-3 text-sm">
          <div>
            <dt className="text-muted-foreground">模型服务</dt>
            <dd className="mt-1 [overflow-wrap:anywhere]">
              {confirmation.provider.base_url}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">模型</dt>
            <dd className="mt-1 [overflow-wrap:anywhere]">
              {confirmation.provider.model}
            </dd>
          </div>
        </dl>
        <p className="text-sm leading-6 text-muted-foreground">
          正文、图片和视频将发送到上述模型服务，可能消耗 API
          额度。每条分析结果都会单独保存，与报告是否生成无关。
          手动分析不会自动判断相关性或生成报告。失败项不会自动重做，新采集内容不加入本次任务。
          {confirmation.request.force_refresh
            ? '本次将重新获取内容并分析，不复用旧版理解。'
            : '仅复用兼容的已保存理解，不会把未读媒体当成完整内容。'}
        </p>
        <div className="space-y-3">
          {[
            confirmation.settings.initial_prompt,
            confirmation.settings.report_prompt,
          ].map((prompt) => (
            <details key={prompt.stage} className="rounded-lg border p-3">
              <summary className="min-h-8 cursor-pointer font-medium">
                {prompt.stage === 'initial' ? '初步分析' : '报告'}提示词
              </summary>
              <p className="mt-2 text-sm leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap">
                {prompt.instructions}
              </p>
            </details>
          ))}
        </div>
        {!confirmation.settings.automation.available && (
          <p className="text-sm text-muted-foreground">
            自动任务目前不可用；不影响本次明确提交的手动初步分析。
          </p>
        )}
        {ambiguous && (
          <p role="status" className="text-sm text-warning-foreground">
            上次提交结果不确定。再次确认可以继续上次操作，不会重复创建任务。
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={onClose}>
            {ambiguous ? '暂时关闭' : '取消'}
          </Button>
          {blocked ? (
            <Button disabled={pending} onClick={onReconfirm}>
              刷新后重新确认
            </Button>
          ) : (
            <Button disabled={pending} aria-busy={pending} onClick={onConfirm}>
              {pending
                ? '正在提交…'
                : ambiguous
                  ? '确认上次提交'
                  : '确认初步分析'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
