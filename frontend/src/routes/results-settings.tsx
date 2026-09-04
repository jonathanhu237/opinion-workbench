import {
  useMutation,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button, buttonVariants } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { AISettings } from '@/lib/api/ai-settings'
import {
  ANALYSIS_SETTINGS_QUERY_KEY,
  saveAnalysisAutomation,
  type AnalysisSettings,
} from '@/lib/api/analysis-settings'
import { analysisErrorMessage } from '@/lib/api/analysis-shared'

async function cacheSavedSettings(
  client: QueryClient,
  saved: AnalysisSettings,
) {
  // A read can start even while a save is pending. Cancel it before publishing
  // the committed snapshot, and merge independent revisions for sibling saves.
  await client.cancelQueries({
    queryKey: ANALYSIS_SETTINGS_QUERY_KEY,
    exact: true,
  })
  client.setQueryData<AnalysisSettings>(
    ANALYSIS_SETTINGS_QUERY_KEY,
    (current) =>
      current
        ? {
            initial_prompt:
              current.initial_prompt.id > saved.initial_prompt.id
                ? current.initial_prompt
                : saved.initial_prompt,
            report_prompt:
              current.report_prompt.id > saved.report_prompt.id
                ? current.report_prompt
                : saved.report_prompt,
            automation:
              current.automation.revision > saved.automation.revision
                ? current.automation
                : saved.automation,
          }
        : saved,
  )
}

export function ResultsSettings({
  settings,
  provider,
}: {
  settings: AnalysisSettings
  provider: AISettings | undefined
}) {
  const client = useQueryClient()
  const [confirmation, setConfirmation] = useState<{
    provider: AISettings
    revision: number
  } | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: saveAnalysisAutomation,
    retry: false,
    onSuccess: async (saved) => {
      await cacheSavedSettings(client, saved)
      setConfirmation(null)
      setFeedback(
        saved.automation.enabled
          ? saved.automation.available
            ? '自动分析已启用。'
            : '自动分析授权已保存；完整流程尚未启用。'
          : '自动分析已停用；已提交任务仍可单独取消。',
      )
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: ANALYSIS_SETTINGS_QUERY_KEY })
    },
  })
  const stale =
    settings.automation.enabled &&
    provider?.revision !== settings.automation.approved_configuration_revision
  return (
    <details className="rounded-xl border bg-card p-4 sm:p-5">
      <summary className="min-h-11 cursor-pointer font-medium">
        自动分析设置
      </summary>
      <section className="mt-4 space-y-3 rounded-lg border bg-muted/20 p-4">
        <h3 className="font-medium">系统提示词（只读）</h3>
        <p className="text-sm leading-6 text-muted-foreground">
          默认模板由系统维护。提交手动分析或创建自动任务时，可以选择默认模板，或只为该次任务填写自定义指令。
        </p>
        <div className="grid gap-3 lg:grid-cols-2">
          {(
            [
              ['内容理解', settings.initial_prompt],
              ['相关性判断与报告', settings.report_prompt],
            ] as const
          ).map(([label, prompt]) => (
            <details key={label} className="rounded-lg border bg-card p-3">
              <summary className="min-h-8 cursor-pointer font-medium">
                {label}
              </summary>
              <p className="mt-2 text-sm leading-6 whitespace-pre-wrap text-muted-foreground">
                {prompt.instructions}
              </p>
            </details>
          ))}
        </div>
      </section>
      <section
        aria-label="自动分析授权"
        className="mt-6 space-y-3 border-t pt-5"
      >
        <h3 className="font-medium">新内容自动分析</h3>
        <p className="text-sm leading-6 text-muted-foreground">
          只自动分析新采集、还没分析过的内容。历史内容、失败重试和重新分析需要手动选择。
        </p>
        <p className="text-sm">
          {!settings.automation.available
            ? '完整流程尚未启用，当前不会自动执行。'
            : settings.automation.enabled && !stale
              ? '已启用新内容自动分析。'
              : '自动分析未启用。'}
          {settings.automation.enabled &&
            ` 已确认使用第 ${settings.automation.approved_configuration_revision} 版模型设置。`}
        </p>
        {stale && (
          <p role="status" className="text-sm text-warning-foreground">
            模型设置已变化，请重新确认；系统不会自动切换模型服务。
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            className="min-h-11"
            disabled={
              !provider?.has_api_key ||
              mutation.isPending ||
              (settings.automation.enabled && !stale)
            }
            onClick={() => {
              if (provider?.has_api_key) {
                mutation.reset()
                setConfirmation({
                  provider: { ...provider },
                  revision: settings.automation.revision,
                })
              }
            }}
          >
            {stale
              ? '重新确认自动分析授权'
              : settings.automation.available
                ? '启用自动分析'
                : '设置自动分析授权'}
          </Button>
          {settings.automation.enabled && (
            <Button
              variant="outline"
              className="min-h-11"
              disabled={mutation.isPending}
              onClick={() =>
                mutation.mutate({
                  enabled: false,
                  expected_revision: settings.automation.revision,
                  configuration_revision: null,
                })
              }
            >
              停用自动分析
            </Button>
          )}
          {!provider?.has_api_key && (
            <Link
              className={buttonVariants({ variant: 'link' })}
              to="/settings/ai"
            >
              先保存 AI 配置
            </Link>
          )}
        </div>
        {feedback && (
          <p role="status" className="text-sm text-muted-foreground">
            {feedback}
          </p>
        )}
        {!confirmation && mutation.isError && (
          <p role="alert" className="text-sm text-destructive">
            {analysisErrorMessage(mutation.error)}
          </p>
        )}
      </section>
      {confirmation && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open && !mutation.isPending) setConfirmation(null)
          }}
        >
          <DialogContent
            className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg"
            showCloseButton={!mutation.isPending}
          >
            <DialogHeader>
              <DialogTitle>确认自动分析授权</DialogTitle>
              <DialogDescription>
                新采集内容的正文、图片和视频会发送到以下模型服务，之后的文字报告也可能消耗
                API 额度。历史内容和失败项不会自动重做。
              </DialogDescription>
            </DialogHeader>
            <dl className="space-y-3 rounded-lg border p-3 text-sm">
              <div>
                <dt>模型服务</dt>
                <dd className="mt-1 [overflow-wrap:anywhere]">
                  {confirmation.provider.base_url}
                </dd>
              </div>
              <div>
                <dt>模型</dt>
                <dd className="mt-1 [overflow-wrap:anywhere]">
                  {confirmation.provider.model}
                </dd>
              </div>
            </dl>
            {!settings.automation.available && (
              <p className="text-sm text-warning-foreground">
                本次只保存授权，自动分析功能还未启用。
              </p>
            )}
            {mutation.isError && (
              <p role="alert" className="text-sm text-destructive">
                {analysisErrorMessage(mutation.error)}
              </p>
            )}
            <DialogFooter>
              <Button
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => setConfirmation(null)}
              >
                取消
              </Button>
              <Button
                disabled={mutation.isPending}
                aria-busy={mutation.isPending}
                onClick={() =>
                  mutation.mutate({
                    enabled: true,
                    expected_revision: confirmation.revision,
                    configuration_revision: confirmation.provider.revision,
                  })
                }
              >
                {mutation.isPending ? '正在保存…' : '确认并保存授权'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </details>
  )
}
