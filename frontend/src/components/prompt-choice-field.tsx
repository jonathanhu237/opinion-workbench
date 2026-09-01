import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from '@/components/ui/field'
import { useEffect, useState } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { codePointLength } from '@/lib/monitoring-rule-composition'
import type { PromptChoice } from '@/lib/api/analysis-settings'

type PromptChoiceFieldProps = {
  id: string
  label: string
  description: string
  value: PromptChoice
  onChange: (value: PromptChoice) => void
  onBlur?: () => void
  defaultInstructions?: string
  error?: string
  disabled?: boolean
}

export function PromptChoiceField({
  id,
  label,
  description,
  value,
  onChange,
  onBlur,
  defaultInstructions,
  error,
  disabled = false,
}: PromptChoiceFieldProps) {
  const custom = value.mode === 'custom'
  const customInstructions = value.mode === 'custom' ? value.instructions : null
  const [draft, setDraft] = useState<string | null>(
    value.mode === 'custom' ? value.instructions : null,
  )
  useEffect(() => {
    if (customInstructions !== null) setDraft(customInstructions)
  }, [customInstructions])
  const modeDescription = custom
    ? '本任务会保存这段自定义指令；之后修改不会影响已提交的运行。'
    : '使用系统维护的固定模板；模板不能在这里或全局设置中编辑。'

  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel id={`${id}-label`} htmlFor={`${id}-mode`}>
        {label}
      </FieldLabel>
      <FieldDescription id={`${id}-description`}>
        {description}
      </FieldDescription>
      <Select
        items={[
          { value: 'default', label: '使用系统默认模板' },
          { value: 'custom', label: '使用本任务自定义指令' },
        ]}
        value={value.mode}
        onValueChange={(mode) => {
          if (mode === 'default') onChange({ mode: 'default' })
          if (mode === 'custom')
            onChange({
              mode: 'custom',
              instructions: custom
                ? value.instructions
                : (draft ?? defaultInstructions ?? ''),
            })
        }}
        disabled={disabled}
      >
        <SelectTrigger
          id={`${id}-mode`}
          className="min-h-11 w-full"
          aria-invalid={Boolean(error)}
          aria-describedby={`${id}-description ${id}-error`}
          onBlur={onBlur}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="default">使用系统默认模板</SelectItem>
          <SelectItem value="custom">使用本任务自定义指令</SelectItem>
        </SelectContent>
      </Select>
      <p className="text-sm leading-6 text-muted-foreground">
        {modeDescription}
      </p>
      {custom ? (
        <>
          <Textarea
            id={`${id}-instructions`}
            value={value.instructions}
            onChange={(event) => {
              setDraft(event.target.value)
              onChange({ mode: 'custom', instructions: event.target.value })
            }}
            onBlur={onBlur}
            rows={6}
            className="min-h-36 text-base sm:text-sm"
            disabled={disabled}
            aria-invalid={Boolean(error)}
            aria-labelledby={`${id}-label`}
            aria-describedby={`${id}-error`}
            placeholder="输入本任务专用的分析指令"
          />
          <p className="text-xs text-muted-foreground">
            {codePointLength(value.instructions)} / 8000 字
          </p>
        </>
      ) : (
        <div
          className="max-h-36 overflow-y-auto rounded-lg border bg-muted/30 px-3 py-2 text-sm leading-6 text-muted-foreground"
          role="note"
          aria-label={`${label}默认模板预览`}
        >
          {defaultInstructions ?? '系统默认模板将在提交时固定保存。'}
        </div>
      )}
      <FieldError
        id={`${id}-error`}
        errors={error ? [{ message: error }] : []}
      />
    </Field>
  )
}
