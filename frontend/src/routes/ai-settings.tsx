import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  AI_SETTINGS_QUERY_KEY,
  AISettingsApiError,
  fetchAISettings,
  saveAISettings,
  testAIConnection,
  type AISettings as Settings,
} from '@/lib/api/ai-settings'
import { cn } from '@/lib/utils'

const emptySettings: Settings = {
  base_url: null,
  model: null,
  has_api_key: false,
  revision: 0,
}
const savedKeyMask = '********************'

function canonicalEndpoint(value: string) {
  try {
    return new URL(value).href.replace(/\/+$/u, '')
  } catch {
    return value
  }
}

function formSchema(saved: Settings) {
  return z
    .object({
      api_key: z
        .string()
        .max(4096, 'API Key 过长。')
        .refine(
          (value) => value === '' || /^[!-~]+$/u.test(value),
          'API Key 不能包含空白或控制字符。',
        ),
      base_url: z
        .string()
        .trim()
        .max(2048, '服务地址过长。')
        .refine((value) => {
          try {
            const url = new URL(value)
            return (
              url.protocol === 'https:' &&
              !url.username &&
              !url.password &&
              !url.search &&
              !url.hash
            )
          } catch {
            return false
          }
        }, '请输入有效的 HTTPS 服务地址。'),
      model: z
        .string()
        .trim()
        .min(1, '请输入模型名称。')
        .max(200, '模型名称最多 200 字符。')
        .regex(/^[!-~]+$/u, '模型名称不能包含空白或控制字符。'),
    })
    .superRefine((value, context) => {
      const replacingKey =
        value.api_key !== '' && value.api_key !== savedKeyMask
      if (
        !replacingKey &&
        (!saved.has_api_key ||
          canonicalEndpoint(value.base_url) !== saved.base_url)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['api_key'],
          message: '首次保存或更换服务地址时，请重新输入 API Key。',
        })
      }
    })
}

function productMessage(error: unknown) {
  return error instanceof AISettingsApiError
    ? error.message
    : '操作未完成，请稍后重试。'
}

function SettingsForm({ saved }: { saved: Settings }) {
  const queryClient = useQueryClient()
  const schema = useMemo(() => formSchema(saved), [saved])
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      api_key: saved.has_api_key ? savedKeyMask : '',
      base_url: saved.base_url ?? '',
      model: saved.model ?? '',
    },
    shouldUnregister: true,
  })
  const { reset, resetField } = form
  const [apiKeyFocused, setApiKeyFocused] = useState(false)
  const [pending, setPending] = useState<'save' | 'test' | null>(null)
  const [feedback, setFeedback] = useState<{
    error: boolean
    message: string
  } | null>(null)
  const request = useRef<AbortController | null>(null)
  const dirty = form.formState.isDirty

  useEffect(() => {
    reset({
      api_key: saved.has_api_key ? savedKeyMask : '',
      base_url: saved.base_url ?? '',
      model: saved.model ?? '',
    })
  }, [saved.base_url, saved.model, saved.revision, reset])
  useEffect(() => () => request.current?.abort(), [])

  async function save(values: z.infer<typeof schema>) {
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setPending('save')
    setFeedback(null)
    try {
      const result = await saveAISettings(
        {
          base_url: values.base_url,
          model: values.model,
          ...(values.api_key && values.api_key !== savedKeyMask
            ? { api_key: values.api_key }
            : {}),
        },
        controller.signal,
      )
      if (controller.signal.aborted) return
      reset({
        api_key: result.has_api_key ? savedKeyMask : '',
        base_url: result.base_url ?? '',
        model: result.model ?? '',
      })
      queryClient.setQueryData(AI_SETTINGS_QUERY_KEY, result)
      void queryClient.invalidateQueries({ queryKey: AI_SETTINGS_QUERY_KEY })
      setFeedback({ error: false, message: '已保存。' })
    } catch (error) {
      if (controller.signal.aborted) return
      if (error instanceof AISettingsApiError) {
        const field =
          error.code === 'invalid_ai_base_url'
            ? 'base_url'
            : error.code === 'invalid_ai_model'
              ? 'model'
              : error.code === 'invalid_ai_api_key' ||
                  error.code === 'ai_api_key_required'
                ? 'api_key'
                : null
        if (field)
          form.setError(
            field,
            { message: error.message },
            { shouldFocus: true },
          )
        else setFeedback({ error: true, message: error.message })
      } else setFeedback({ error: true, message: productMessage(error) })
    } finally {
      values.api_key = ''
      if (!controller.signal.aborted) {
        resetField('api_key', {
          defaultValue: saved.has_api_key ? savedKeyMask : '',
          keepError: true,
        })
        setPending(null)
      }
      request.current = null
    }
  }

  async function test() {
    if (request.current || dirty || !saved.has_api_key) return
    const controller = new AbortController()
    request.current = controller
    setPending('test')
    setFeedback(null)
    try {
      await testAIConnection(saved.revision, controller.signal)
      if (!controller.signal.aborted)
        setFeedback({ error: false, message: '连接成功，仅验证文本响应。' })
    } catch (error) {
      if (!controller.signal.aborted) {
        setFeedback({ error: true, message: productMessage(error) })
        if (
          error instanceof AISettingsApiError &&
          error.code === 'ai_configuration_changed'
        ) {
          void queryClient.invalidateQueries({
            queryKey: AI_SETTINGS_QUERY_KEY,
          })
        }
      }
    } finally {
      if (!controller.signal.aborted) setPending(null)
      request.current = null
    }
  }

  return (
    <form
      aria-label="AI 配置"
      onSubmit={form.handleSubmit(save)}
      onChange={() => setFeedback(null)}
      noValidate
      className="space-y-6"
    >
      <fieldset disabled={pending !== null} className="min-w-0 space-y-6">
        <FieldGroup>
          <Controller
            name="api_key"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="ai-api-key">API Key</FieldLabel>
                <div className="relative">
                  <Input
                    {...field}
                    id="ai-api-key"
                    type={
                      saved.has_api_key &&
                      !apiKeyFocused &&
                      field.value === savedKeyMask
                        ? 'text'
                        : 'password'
                    }
                    autoComplete="off"
                    spellCheck={false}
                    className="min-h-11"
                    aria-invalid={fieldState.invalid}
                    aria-describedby="ai-key-help ai-key-error"
                    onFocus={() => {
                      setApiKeyFocused(true)
                      if (field.value === savedKeyMask)
                        form.setValue('api_key', '', { shouldDirty: false })
                    }}
                    onBlur={() => {
                      field.onBlur()
                      setApiKeyFocused(false)
                      if (saved.has_api_key && form.getValues('api_key') === '')
                        resetField('api_key', {
                          defaultValue: savedKeyMask,
                          keepError: true,
                        })
                    }}
                  />
                </div>
                <FieldDescription id="ai-key-help">
                  {saved.has_api_key
                    ? '已配置，留空即可保留；更换服务地址时请重新输入。'
                    : '密钥只保存在本机，不会显示。'}
                </FieldDescription>
                <FieldError id="ai-key-error" errors={[fieldState.error]} />
              </Field>
            )}
          />
          <Controller
            name="base_url"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="ai-base-url">服务地址</FieldLabel>
                <Input
                  {...field}
                  id="ai-base-url"
                  type="url"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="https://api.example.com/v1"
                  className="min-h-11"
                  aria-invalid={fieldState.invalid}
                  aria-describedby="ai-url-error"
                />
                <FieldError id="ai-url-error" errors={[fieldState.error]} />
              </Field>
            )}
          />
          <Controller
            name="model"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="ai-model">模型名称</FieldLabel>
                <Input
                  {...field}
                  id="ai-model"
                  autoComplete="off"
                  spellCheck={false}
                  className="min-h-11"
                  aria-invalid={fieldState.invalid}
                  aria-describedby="ai-model-error"
                />
                <FieldError id="ai-model-error" errors={[fieldState.error]} />
              </Field>
            )}
          />
        </FieldGroup>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            disabled={pending !== null || (!dirty && saved.has_api_key)}
            className="min-h-11 px-5"
          >
            {pending === 'save' ? '保存中…' : '保存'}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={pending !== null || dirty || !saved.has_api_key}
            onClick={() => void test()}
            className="min-h-11 px-5"
            aria-describedby="ai-test-help"
          >
            {pending === 'test' ? '测试中…' : '测试连接'}
          </Button>
          {dirty && (
            <span className="text-sm text-muted-foreground">请先保存配置</span>
          )}
        </div>
      </fieldset>
      <p
        id="ai-test-help"
        className="text-sm leading-relaxed text-muted-foreground"
      >
        测试仅发送简短文本，可能消耗额度；不验证图片或音视频能力。
      </p>
      {feedback && (
        <p
          role={feedback.error ? 'alert' : 'status'}
          className={feedback.error ? 'text-sm text-destructive' : 'text-sm'}
        >
          {feedback.message}
        </p>
      )}
    </form>
  )
}

export function AISettings({ embedded = false }: { embedded?: boolean }) {
  const query = useQuery({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAISettings(signal),
    retry: false,
    refetchOnWindowFocus: false,
  })
  if (query.isPending)
    return (
      <p role="status" className="text-sm text-muted-foreground">
        正在读取 AI 配置…
      </p>
    )
  const canReplaceMissingKey =
    query.error instanceof AISettingsApiError &&
    query.error.code === 'ai_credentials_unavailable'
  return (
    <section
      aria-label="模型连接配置"
      className={cn(
        'max-w-xl space-y-5',
        !embedded && 'rounded-xl border border-border bg-card p-5 sm:p-6',
      )}
    >
      {query.isError && (
        <div className="space-y-3">
          <p role="alert" className="text-sm text-destructive">
            {productMessage(query.error)}
          </p>
          <Button
            variant="outline"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            重新加载
          </Button>
        </div>
      )}
      {(query.data || canReplaceMissingKey) && (
        <SettingsForm saved={query.data ?? emptySettings} />
      )}
    </section>
  )
}
