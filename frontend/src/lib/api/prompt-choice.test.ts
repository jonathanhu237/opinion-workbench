import { describe, expect, it } from 'vitest'

import {
  promptChoiceSchema,
  promptInstructionsSchema,
  promptSnapshotSchema,
} from '@/lib/api/analysis-settings'

describe('two-stage prompt contracts', () => {
  it('keeps an explicit custom choice distinct even when its text matches a default', () => {
    const defaultChoice = promptChoiceSchema.safeParse({ mode: 'default' })
    const customChoice = promptChoiceSchema.safeParse({
      mode: 'custom',
      instructions: '使用系统默认模板',
    })

    expect(defaultChoice.success).toBe(true)
    expect(customChoice.success).toBe(true)
    if (customChoice.success) expect(customChoice.data.mode).toBe('custom')
  })

  it('enforces the UTF-8-safe 8000-code-point custom boundary', () => {
    expect(promptInstructionsSchema.safeParse('🙂'.repeat(8000)).success).toBe(
      true,
    )
    expect(promptInstructionsSchema.safeParse('🙂'.repeat(8001)).success).toBe(
      false,
    )
    expect(promptInstructionsSchema.safeParse('\ud800').success).toBe(false)
    expect(promptInstructionsSchema.safeParse('a\u0000b').success).toBe(false)
  })

  it('requires a complete immutable snapshot shape', () => {
    const valid = promptSnapshotSchema.safeParse({
      mode: 'custom',
      version_id: 7,
      instructions: '保留证据和不确定性。',
      content_hash: 'a'.repeat(64),
      schema_version: 'topic-report-v1',
    })
    const extra = promptSnapshotSchema.safeParse({
      mode: 'custom',
      version_id: 7,
      instructions: '保留证据和不确定性。',
      content_hash: 'a'.repeat(64),
      schema_version: 'topic-report-v1',
      mutable: true,
    })

    expect(valid.success).toBe(true)
    expect(extra.success).toBe(false)
  })
})
