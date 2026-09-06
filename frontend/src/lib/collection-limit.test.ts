import { describe, expect, it } from 'vitest'

import { collectionLimitLabel } from '@/lib/collection-limit'
import { automationTaskUpdatePayload } from '@/lib/api/automation-workflows'
import { automationTask } from '@/lib/api/automation-workflows.fixtures'

describe('collection total limit', () => {
  it('distinguishes latest total limits from legacy per-term limits', () => {
    expect(
      collectionLimitLabel({ max_results_per_term: 10, max_total_results: 25 }),
    ).toBe('最新优先 · 合计最多 25 条')
    expect(collectionLimitLabel({ max_results_per_term: 10 })).toBe(
      '每词最多 10 条（旧配置）',
    )
  })

  it('preserves the total when toggling a task without editing its configuration', () => {
    const task = automationTask({ max_total_results: 25 })
    expect(automationTaskUpdatePayload(task, false).max_total_results).toBe(25)
    expect(
      automationTaskUpdatePayload(automationTask(), false).max_total_results,
    ).toBeUndefined()
  })
})
