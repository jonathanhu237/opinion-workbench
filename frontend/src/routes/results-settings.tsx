import { zodResolver } from '@hookform/resolvers/zod'
import {
  useMutation,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'

import { Button, buttonVariants } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import type { AISettings } from '@/lib/api/ai-settings'
import {
  ANALYSIS_SETTINGS_QUERY_KEY,
  promptInstructionsSchema,
  saveAnalysisAutomation,
  saveAnalysisPrompt,
  type AnalysisSettings,
  type PromptVersion,
} from '@/lib/api/analysis-settings'
import { analysisErrorMessage } from '@/lib/api/analysis-shared'
import { codePointLength } from '@/lib/monitoring-rule-composition'

const promptFormSchema = z.object({ instructions: promptInstructionsSchema })

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

function PromptEditor({ prompt }: { prompt: PromptVersion }) {
  const client = useQueryClient()
  const [editingVersion, setEditingVersion] = useState(prompt)
  const [feedback, setFeedback] = useState<string | null>(null)
  const form = useForm({
    resolver: zodResolver(promptFormSchema),
    defaultValues: { instructions: prompt.instructions },
  })
  const { isDirty, isSubmitting, errors } = form.formState
  const title = prompt.stage === 'initial' ? '初步分析提示词' : '报告提示词'
  const id = `prompt-${prompt.stage}`
  const mutation = useMutation({
    mutationFn: (instructions: string) =>
      saveAnalysisPrompt(prompt.stage, {
        expected_version_id: editingVersion.id,
        instructions,
      }),
    retry: false,
    onSuccess: async (settings) => {
      const saved =
        prompt.stage === 'initial'
          ? settings.initial_prompt
          : settings.report_prompt
      await cacheSavedSettings(client, settings)
      form.reset({ instructions: saved.instructions })
      setEditingVersion(saved)
      setFeedback(`${title}已保存；仅用于之后提交的任务。`)
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: ANALYSIS_SETTINGS_QUERY_KEY })
    },
  })
  useEffect(() => {
    if (!isDirty && !mutation.isPending && prompt.id !== editingVersion.id) {
      form.reset({ instructions: prompt.instructions })
      setEditingVersion(prompt)
    }
  }, [prompt, editingVersion.id, form, isDirty, mutation.isPending])
  return (
    <form
      className="min-w-0 space-y-3"
      onSubmit={form.handleSubmit(({ instructions }) =>
        mutation.mutate(instructions),
      )}
    >
      <Field data-invalid={Boolean(errors.instructions)}>
        <FieldLabel htmlFor={id}>{title}</FieldLabel>
        <FieldDescription id={`${id}-help`}>
          {prompt.stage === 'initial'
            ? '理解每条内容，保留地点、时间、媒体观察和不确定性；不先按主题剔除内容。'
            : '根据已有内容判断是否相关，并生成报告。'}
        </FieldDescription>
        <Textarea
          id={id}
          rows={7}
          className="min-h-44 text-base sm:text-sm"
          disabled={mutation.isPending}
          aria-invalid={Boolean(errors.instructions)}
          aria-describedby={`${id}-help ${id}-error`}
          {...form.register('instructions', {
            onChange: () => {
              setFeedback(null)
              mutation.reset()
            },
          })}
        />
        <FieldError id={`${id}-error`}>
          {errors.instructions
            ? '提示词须为 1 至 8000 字的有效非空文本。'
            : null}
        </FieldError>
      </Field>
      <p className="text-xs text-muted-foreground">
        第 {editingVersion.id} 版 ·{' '}
        {codePointLength(form.watch('instructions'))} / 8000 字
      </p>
      {prompt.id !== editingVersion.id && isDirty && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-warning-foreground">
            默认提示词已被更新。当前草稿仍保留，保存前请重新确认。
          </p>
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            disabled={mutation.isPending}
            onClick={() => {
              setEditingVersion(prompt)
              mutation.reset()
              setFeedback('草稿已保留，请确认最新内容后再次保存。')
            }}
          >
            保留草稿并采用最新版本
          </Button>
        </div>
      )}
      {mutation.isError && (
        <p role="alert" className="text-sm text-destructive">
          {analysisErrorMessage(mutation.error)}
        </p>
      )}
      {feedback && (
        <p role="status" className="text-sm text-muted-foreground">
          {feedback}
        </p>
      )}
      <Button
        variant="outline"
        className="min-h-11"
        type="submit"
        disabled={!isDirty || isSubmitting || mutation.isPending}
        aria-busy={mutation.isPending}
      >
        {mutation.isPending ? '正在保存…' : `保存${title}`}
      </Button>
    </form>
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
        提示词与自动分析设置
      </summary>
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <PromptEditor prompt={settings.initial_prompt} />
        <PromptEditor prompt={settings.report_prompt} />
      </div>
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
              to="/ai-settings"
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
