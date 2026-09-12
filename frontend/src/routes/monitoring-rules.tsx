import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useMonitoringRules } from '@/hooks/use-monitoring-rules'
import {
  createMonitoringRule,
  deleteMonitoringRule,
  MONITORING_RULES_QUERY_KEY,
  MonitoringRuleApiError,
  updateMonitoringRule,
  type MonitoringRule,
  type MonitoringRulePayload,
  type MonitoringRulesResponse,
} from '@/lib/api/monitoring-rules'

import {
  codePointLength,
  composeMonitoringTerms,
  MAX_EXECUTABLE_TERMS,
  MAX_RULE_NAME_LENGTH,
  MAX_TERM_LENGTH,
  MAX_TERMS_PER_RULE,
  normalizeForDuplicateCheck,
  termsFromTextarea,
  trimRuleValue,
} from '@/lib/monitoring-rule-composition'

const ruleEditorSchema = z
  .object({
    name: z.string(),
    monitoringObjectsText: z.string(),
    issueKeywordsText: z.string(),
  })
  .superRefine((values, context) => {
    const name = trimRuleValue(values.name)
    if (name.length === 0) {
      context.addIssue({
        code: 'custom',
        path: ['name'],
        message: '请输入规则名称。',
      })
    } else if (codePointLength(name) > MAX_RULE_NAME_LENGTH) {
      context.addIssue({
        code: 'custom',
        path: ['name'],
        message: `规则名称不能超过 ${MAX_RULE_NAME_LENGTH} 个字符。`,
      })
    }

    const objects = termsFromTextarea(values.monitoringObjectsText)
    const issues = termsFromTextarea(values.issueKeywordsText)
    if (objects.length === 0) {
      context.addIssue({
        code: 'custom',
        path: ['monitoringObjectsText'],
        message: '请至少输入一个采集对象。',
      })
      return
    }
    for (const [path, label, terms] of [
      ['monitoringObjectsText', '采集对象', objects],
      ['issueKeywordsText', '舆情词', issues],
    ] as const) {
      if (terms.length > MAX_TERMS_PER_RULE) {
        context.addIssue({
          code: 'custom',
          path: [path],
          message: `${label}最多包含 ${MAX_TERMS_PER_RULE} 项。`,
        })
      }
      if (terms.some((term) => codePointLength(term) > MAX_TERM_LENGTH)) {
        context.addIssue({
          code: 'custom',
          path: [path],
          message: `每个${label}不能超过 ${MAX_TERM_LENGTH} 个字符。`,
        })
      }
      const normalized = terms.map(normalizeForDuplicateCheck)
      if (new Set(normalized).size !== normalized.length) {
        context.addIssue({
          code: 'custom',
          path: [path],
          message: `${label}不能重复，请检查后重试。`,
        })
      }
    }
    const generated = composeMonitoringTerms(objects, issues)
    const combinationPath =
      issues.length > 0 ? 'issueKeywordsText' : 'monitoringObjectsText'
    if (generated.count > MAX_TERMS_PER_RULE) {
      context.addIssue({
        code: 'custom',
        path: [combinationPath],
        message: `每条规则最多生成 ${MAX_TERMS_PER_RULE} 个搜索词，请减少采集对象或舆情词。`,
      })
    }
    if (
      generated.terms.some((term) => codePointLength(term) > MAX_TERM_LENGTH)
    ) {
      context.addIssue({
        code: 'custom',
        path: [combinationPath],
        message: `生成的搜索词不能超过 ${MAX_TERM_LENGTH} 个字符，请缩短采集对象或舆情词。`,
      })
    }
    const normalized = generated.terms.map(normalizeForDuplicateCheck)
    if (new Set(normalized).size !== normalized.length) {
      context.addIssue({
        code: 'custom',
        path: [combinationPath],
        message: '生成的搜索词不能重复，请调整采集对象或舆情词。',
      })
    }
  })

type RuleEditorValues = z.infer<typeof ruleEditorSchema>

type EditorState =
  | { kind: 'closed' }
  | { kind: 'create' }
  | { kind: 'edit'; rule: MonitoringRule }

function errorMessage(error: unknown) {
  if (error instanceof MonitoringRuleApiError) {
    return error.message
  }
  return '监控规则操作未完成，请重新尝试。'
}

function replaceCachedRule(
  current: MonitoringRulesResponse | undefined,
  savedRule: MonitoringRule,
) {
  if (current === undefined) {
    return current
  }

  const exists = current.rules.some((rule) => rule.id === savedRule.id)
  return {
    rules: exists
      ? current.rules.map((rule) =>
          rule.id === savedRule.id ? savedRule : rule,
        )
      : [...current.rules, savedRule],
  }
}

type RuleEditorDialogProps = {
  editor: Exclude<EditorState, { kind: 'closed' }>
  onClose: () => void
  onSaved: (message: string) => void
}

function RuleEditorDialog({ editor, onClose, onSaved }: RuleEditorDialogProps) {
  const queryClient = useQueryClient()
  const editingRule = editor.kind === 'edit' ? editor.rule : null
  const form = useForm<RuleEditorValues>({
    resolver: zodResolver(ruleEditorSchema),
    mode: 'onBlur',
    defaultValues: {
      name: editingRule?.name ?? '',
      monitoringObjectsText: editingRule?.monitoring_objects.join('\n') ?? '',
      issueKeywordsText: editingRule?.issue_keywords.join('\n') ?? '',
    },
  })
  const [objectsText, issuesText] = useWatch({
    control: form.control,
    name: ['monitoringObjectsText', 'issueKeywordsText'],
  })
  const preview = composeMonitoringTerms(
    termsFromTextarea(objectsText),
    termsFromTextarea(issuesText),
  )
  const saveMutation = useMutation({
    mutationFn: (payload: MonitoringRulePayload) =>
      editingRule === null
        ? createMonitoringRule(payload)
        : updateMonitoringRule(editingRule.id, payload),
  })

  const submit = form.handleSubmit(async (values) => {
    form.clearErrors('root.server')
    const payload: MonitoringRulePayload = {
      name: trimRuleValue(values.name),
      monitoring_objects: termsFromTextarea(values.monitoringObjectsText),
      issue_keywords: termsFromTextarea(values.issueKeywordsText),
      enabled: editingRule?.enabled ?? true,
    }

    try {
      const savedRule = await saveMutation.mutateAsync(payload)
      queryClient.setQueryData<MonitoringRulesResponse>(
        MONITORING_RULES_QUERY_KEY,
        (current) => replaceCachedRule(current, savedRule),
      )
      onSaved(
        editingRule === null
          ? `已新建“${savedRule.name}”。`
          : `已保存“${savedRule.name}”。`,
      )
    } catch (error) {
      if (
        error instanceof MonitoringRuleApiError &&
        error.code === 'monitoring_rule_name_conflict'
      ) {
        form.setError(
          'name',
          { type: 'server', message: error.message },
          { shouldFocus: false },
        )
        queueMicrotask(() => form.setFocus('name'))
        return
      }
      if (
        error instanceof MonitoringRuleApiError &&
        error.code === 'duplicate_monitoring_rule_term'
      ) {
        form.setError(
          'monitoringObjectsText',
          { type: 'server', message: error.message },
          { shouldFocus: false },
        )
        if (payload.issue_keywords.length > 0) {
          form.setError('issueKeywordsText', {
            type: 'server',
            message: error.message,
          })
        }
        queueMicrotask(() => form.setFocus('monitoringObjectsText'))
        return
      }

      form.setError('root.server', {
        type: 'server',
        message: errorMessage(error),
      })
    }
  })
  // Keep inputs focusable during resolver validation so RHF can focus errors.
  const pending = saveMutation.isPending

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) {
          onClose()
        }
      }}
    >
      <DialogContent
        className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-lg"
        aria-describedby="rule-editor-description"
        showCloseButton={!pending}
      >
        <DialogHeader>
          <DialogTitle>
            {editingRule === null ? '新建监控规则' : '编辑监控规则'}
          </DialogTitle>
          <DialogDescription id="rule-editor-description">
            填写后可以预览要搜索的词。
          </DialogDescription>
        </DialogHeader>

        <form id="rule-editor-form" onSubmit={submit} noValidate>
          <FieldGroup>
            <Controller
              name="name"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="rule-name">规则名称</FieldLabel>
                  <Input
                    {...field}
                    id="rule-name"
                    autoComplete="off"
                    aria-invalid={fieldState.invalid}
                    aria-describedby={
                      fieldState.error ? 'rule-name-error' : undefined
                    }
                    disabled={pending}
                  />
                  <FieldError
                    id="rule-name-error"
                    errors={[fieldState.error]}
                  />
                </Field>
              )}
            />

            <Controller
              name="monitoringObjectsText"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="rule-objects">采集对象</FieldLabel>
                  <Textarea
                    {...field}
                    id="rule-objects"
                    rows={4}
                    className="min-h-24 resize-y"
                    placeholder={'对象 1\n对象 2\n对象 3'}
                    aria-invalid={fieldState.invalid}
                    aria-describedby={
                      fieldState.error
                        ? 'rule-objects-description rule-objects-error'
                        : 'rule-objects-description'
                    }
                    disabled={pending}
                  />
                  <FieldDescription id="rule-objects-description">
                    每行填写一个对象，至少填写一项。
                  </FieldDescription>
                  <FieldError
                    id="rule-objects-error"
                    errors={[fieldState.error]}
                  />
                </Field>
              )}
            />

            <Controller
              name="issueKeywordsText"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="rule-issues">舆情词（选填）</FieldLabel>
                  <Textarea
                    {...field}
                    id="rule-issues"
                    rows={3}
                    className="min-h-20 resize-y"
                    placeholder={'关键词 1\n关键词 2\n关键词 3'}
                    aria-invalid={fieldState.invalid}
                    aria-describedby={
                      fieldState.error
                        ? 'rule-issues-description rule-issues-error'
                        : 'rule-issues-description'
                    }
                    disabled={pending}
                  />
                  <FieldDescription id="rule-issues-description">
                    每行填写一个；留空时只搜索采集对象，填写后会逐一组合。
                  </FieldDescription>
                  <FieldError
                    id="rule-issues-error"
                    errors={[fieldState.error]}
                  />
                </Field>
              )}
            />

            <section
              className="min-w-0 space-y-2"
              aria-labelledby="rule-preview-title"
            >
              <h3 id="rule-preview-title" className="text-sm font-medium">
                生成的搜索词 · 共 {preview.count} 个
              </h3>
              <p className="text-xs leading-5 text-muted-foreground">
                系统会按顺序搜索这些词。
              </p>
              {preview.count > MAX_TERMS_PER_RULE ? (
                <p className="text-sm text-destructive">
                  超过 {MAX_TERMS_PER_RULE}{' '}
                  个，无法保存。请减少输入后查看完整预览。
                </p>
              ) : preview.count === 0 ? (
                <p className="text-sm text-muted-foreground">
                  填写采集对象后可查看预览。
                </p>
              ) : (
                <div
                  role="region"
                  aria-label="生成的搜索词预览"
                  tabIndex={0}
                  className="max-h-48 overflow-y-auto rounded-md border border-border bg-muted/30 p-3 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <ol className="list-inside list-decimal space-y-1 text-sm leading-6">
                    {preview.terms.map((term, index) => (
                      <li key={index} className="break-all whitespace-pre-wrap">
                        {term}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {preview.count > MAX_EXECUTABLE_TERMS &&
                preview.count <= MAX_TERMS_PER_RULE && (
                  <p className="rounded-md border border-warning/20 bg-warning/8 p-3 text-sm leading-6 text-foreground">
                    可保存，但每个平台一次最多采集 {MAX_EXECUTABLE_TERMS}{' '}
                    个搜索词。请拆分规则后再采集。
                  </p>
                )}
            </section>

            {form.formState.errors.root?.server?.message && (
              <p role="alert" className="text-sm text-destructive">
                {form.formState.errors.root.server.message}
              </p>
            )}
          </FieldGroup>
        </form>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 sm:min-h-8"
            disabled={pending}
            onClick={onClose}
          >
            取消
          </Button>
          <Button
            type="submit"
            form="rule-editor-form"
            className="min-h-11 sm:min-h-8"
            disabled={pending || form.formState.isSubmitting}
          >
            {pending ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type RuleRowProps = {
  rule: MonitoringRule
  onEdit: (rule: MonitoringRule) => void
  onDelete: (rule: MonitoringRule) => void
  onStatusChanged: (message: string) => void
}

function RuleRow({ rule, onEdit, onDelete, onStatusChanged }: RuleRowProps) {
  const queryClient = useQueryClient()
  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      updateMonitoringRule(rule.id, {
        name: rule.name,
        monitoring_objects: rule.monitoring_objects,
        issue_keywords: rule.issue_keywords,
        enabled,
      }),
    onSuccess: (savedRule) => {
      queryClient.setQueryData<MonitoringRulesResponse>(
        MONITORING_RULES_QUERY_KEY,
        (current) => replaceCachedRule(current, savedRule),
      )
      onStatusChanged(
        savedRule.enabled
          ? `已启用“${savedRule.name}”。`
          : `已停用“${savedRule.name}”。`,
      )
    },
  })
  const pending = toggleMutation.isPending
  const error = toggleMutation.isError
    ? errorMessage(toggleMutation.error)
    : null

  return (
    <li className="border-b border-border/70 last:border-b-0">
      <article className="min-w-0 space-y-4 px-4 py-5 sm:px-6">
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h3 className="text-base leading-6 font-semibold break-words text-foreground">
              {rule.name}
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              共 {rule.terms.length} 个搜索词
            </p>
            {[
              { label: '采集对象', terms: rule.monitoring_objects },
              { label: '舆情词', terms: rule.issue_keywords },
            ].map((group) => (
              <div key={group.label} className="mt-3 space-y-2">
                <p className="text-xs text-muted-foreground">
                  {group.label}
                  {group.terms.length === 0 ? '：未设置，仅搜索采集对象' : ''}
                </p>
                <div className="flex min-w-0 flex-wrap gap-2">
                  {group.terms.map((term) => (
                    <Badge
                      key={term}
                      variant="outline"
                      className="h-auto max-w-full min-w-0 border-border bg-background px-2.5 py-1 leading-5 font-normal break-all whitespace-normal text-foreground"
                    >
                      {term}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
            {rule.terms.length > MAX_EXECUTABLE_TERMS && (
              <p className="mt-3 text-sm text-muted-foreground">
                超过每个平台 {MAX_EXECUTABLE_TERMS}{' '}
                个搜索词的采集上限，请拆分规则后再采集。
              </p>
            )}
          </div>

          <div className="flex min-h-11 shrink-0 items-center gap-3 sm:min-h-8">
            <span className="text-sm text-muted-foreground">
              {pending ? '正在更新…' : rule.enabled ? '已启用' : '已停用'}
            </span>
            <Switch
              checked={rule.enabled}
              disabled={pending}
              aria-label={`${rule.enabled ? '停用' : '启用'}“${rule.name}”`}
              onCheckedChange={(checked) => {
                toggleMutation.reset()
                toggleMutation.mutate(checked)
              }}
            />
          </div>
        </div>

        {error && (
          <p role="alert" className="text-sm leading-6 text-destructive">
            {error}
          </p>
        )}

        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            className="min-h-11 sm:min-h-8"
            aria-label={`编辑“${rule.name}”`}
            disabled={pending}
            onClick={() => onEdit(rule)}
          >
            <Pencil aria-hidden="true" />
            编辑
          </Button>
          <Button
            type="button"
            variant="destructive"
            className="min-h-11 sm:min-h-8"
            aria-label={`删除“${rule.name}”`}
            disabled={pending}
            onClick={() => onDelete(rule)}
          >
            <Trash2 aria-hidden="true" />
            删除
          </Button>
        </div>
      </article>
    </li>
  )
}

function LoadingRules() {
  return (
    <CardContent className="space-y-5 py-6">
      <p
        role="status"
        aria-live="polite"
        className="text-sm text-muted-foreground"
      >
        正在读取监控规则…
      </p>
      {[0, 1, 2].map((item) => (
        <div key={item} className="space-y-3" aria-hidden="true">
          <Skeleton className="h-5 w-48 max-w-2/3" />
          <div className="flex gap-2">
            <Skeleton className="h-6 w-20" />
            <Skeleton className="h-6 w-24" />
          </div>
        </div>
      ))}
    </CardContent>
  )
}

export function MonitoringRules() {
  const queryClient = useQueryClient()
  const rulesQuery = useMonitoringRules()
  const [editor, setEditor] = useState<EditorState>({ kind: 'closed' })
  const [deleteTarget, setDeleteTarget] = useState<MonitoringRule | null>(null)
  const [successMessage, setSuccessMessage] = useState('')
  const rules = rulesQuery.data?.rules ?? []

  const deleteMutation = useMutation({
    mutationFn: (rule: MonitoringRule) => deleteMonitoringRule(rule.id),
    onSuccess: (_result, deletedRule) => {
      queryClient.setQueryData<MonitoringRulesResponse>(
        MONITORING_RULES_QUERY_KEY,
        (current) =>
          current === undefined
            ? current
            : {
                rules: current.rules.filter(
                  (rule) => rule.id !== deletedRule.id,
                ),
              },
      )
      setDeleteTarget(null)
      setSuccessMessage(`已删除“${deletedRule.name}”。`)
    },
  })

  useEffect(() => {
    if (successMessage.length === 0) {
      return
    }

    const timeout = window.setTimeout(() => setSuccessMessage(''), 4000)
    return () => window.clearTimeout(timeout)
  }, [successMessage])

  const openCreate = () => {
    setSuccessMessage('')
    setEditor({ kind: 'create' })
  }

  const queryError = rulesQuery.error ? errorMessage(rulesQuery.error) : null

  return (
    <div className="space-y-5">
      <section className="flex justify-end">
        <Button
          type="button"
          className="min-h-11 w-full sm:min-h-8 sm:w-auto"
          disabled={rulesQuery.data === undefined}
          onClick={openCreate}
        >
          <Plus aria-hidden="true" />
          新建规则
        </Button>
      </section>

      <section aria-labelledby="monitoring-rules-list-title">
        <Card className="gap-0 bg-card/94 py-0">
          <CardHeader className="border-b border-border/75 py-4">
            <CardTitle className="font-display text-xl font-semibold tracking-[-0.03em]">
              <h3 id="monitoring-rules-list-title">规则列表</h3>
            </CardTitle>
          </CardHeader>

          {rulesQuery.isPending && <LoadingRules />}

          {queryError && rulesQuery.data === undefined && (
            <CardContent className="grid min-h-64 place-items-center py-10 text-center">
              <div role="alert" className="max-w-sm">
                <p className="text-sm leading-6 text-foreground">
                  {queryError}
                </p>
                <Button
                  type="button"
                  size="sm"
                  className="mt-5 min-h-11 sm:min-h-8"
                  onClick={() => void rulesQuery.refetch()}
                >
                  重新加载
                </Button>
              </div>
            </CardContent>
          )}

          {queryError && rulesQuery.data !== undefined && (
            <div
              role="alert"
              className="border-b border-warning/20 bg-warning/8 px-4 py-3 text-sm leading-6 text-foreground sm:px-6"
            >
              {queryError} 页面暂时保留之前显示的内容。
            </div>
          )}

          {rulesQuery.data !== undefined && rules.length === 0 && (
            <CardContent className="grid min-h-64 place-items-center py-10 text-center">
              <div>
                <p className="text-base font-medium text-foreground">
                  还没有监控规则
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  新建一条规则，添加需要持续关注的采集对象。
                </p>
                <Button
                  type="button"
                  size="sm"
                  className="mt-5 min-h-11 sm:min-h-8"
                  onClick={openCreate}
                >
                  <Plus aria-hidden="true" />
                  新建规则
                </Button>
              </div>
            </CardContent>
          )}

          {rules.length > 0 && (
            <ul aria-label="监控规则列表">
              {rules.map((rule) => (
                <RuleRow
                  key={rule.id}
                  rule={rule}
                  onStatusChanged={setSuccessMessage}
                  onEdit={(targetRule) => {
                    setSuccessMessage('')
                    setEditor({ kind: 'edit', rule: targetRule })
                  }}
                  onDelete={(targetRule) => {
                    deleteMutation.reset()
                    setSuccessMessage('')
                    setDeleteTarget(targetRule)
                  }}
                />
              ))}
            </ul>
          )}
        </Card>
      </section>

      {successMessage && (
        <p
          className="sr-only"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {successMessage}
        </p>
      )}

      {editor.kind !== 'closed' && (
        <RuleEditorDialog
          key={editor.kind === 'edit' ? `edit-${editor.rule.id}` : 'create'}
          editor={editor}
          onClose={() => setEditor({ kind: 'closed' })}
          onSaved={(message) => {
            setEditor({ kind: 'closed' })
            setSuccessMessage(message)
          }}
        />
      )}

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !deleteMutation.isPending) {
            setDeleteTarget(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {deleteTarget === null
                ? '删除监控规则？'
                : `删除“${deleteTarget.name}”？`}
            </AlertDialogTitle>
            <AlertDialogDescription>删除后无法恢复。</AlertDialogDescription>
          </AlertDialogHeader>

          {deleteMutation.isError && (
            <p role="alert" className="text-sm leading-6 text-destructive">
              {errorMessage(deleteMutation.error)}
            </p>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel
              className="min-h-11 sm:min-h-8"
              disabled={deleteMutation.isPending}
            >
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              type="button"
              variant="destructive"
              className="min-h-11 sm:min-h-8"
              disabled={deleteTarget === null || deleteMutation.isPending}
              onClick={() => {
                if (deleteTarget !== null) {
                  deleteMutation.mutate(deleteTarget)
                }
              }}
            >
              {deleteMutation.isPending ? '删除中…' : '删除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
