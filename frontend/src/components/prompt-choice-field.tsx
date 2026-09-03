import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldTitle,
} from '@/components/ui/field'
import { useEffect, useState } from 'react'
import { Checkbox } from '@/components/ui/checkbox'
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

  return (
    <Field data-invalid={Boolean(error)}>
      <FieldTitle id={`${id}-label`}>{label}</FieldTitle>
      <FieldDescription id={`${id}-description`}>
        {description}
      </FieldDescription>
      <Field
        orientation="horizontal"
        data-disabled={disabled}
        data-invalid={Boolean(error)}
      >
        <Checkbox
          id={`${id}-custom`}
          checked={custom}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={`${id}-custom-description ${id}-error`}
          onBlur={onBlur}
          onCheckedChange={(checked) => {
            if (checked) {
              onChange({
                mode: 'custom',
                instructions: custom
                  ? value.instructions
                  : (draft ?? defaultInstructions ?? ''),
              })
            } else {
              onChange({ mode: 'default' })
            }
          }}
        />
        <FieldContent>
          <FieldLabel htmlFor={`${id}-custom`}>使用本任务自定义指令</FieldLabel>
          <FieldDescription id={`${id}-custom-description`}>
            {custom
              ? '将保存下面的自定义指令；之后修改不会影响已提交的运行。'
              : '不勾选时使用系统维护的固定模板。'}
          </FieldDescription>
        </FieldContent>
      </Field>
      {custom ? (
        <>
          <button
            type="button"
            className="min-h-8 self-start text-sm text-primary underline underline-offset-4"
            disabled={disabled}
            onClick={() => onChange({ mode: 'default' })}
          >
            恢复默认
          </button>
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
