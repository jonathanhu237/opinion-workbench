import type { WorkbenchSnapshot } from '@/lib/api/workbench'

export const workbenchTimestamp = '2026-08-29T08:00:00+00:00'

export function coverage() {
  return {
    total: 10,
    ready: 8,
    unavailable: 2,
    pending: 0,
    judging: 0,
    relevant: 6,
    irrelevant: 1,
    uncertain: 1,
    failed: 0,
    cancelled: 0,
    interrupted: 0,
  }
}

export function workbenchFixture(
  values: Partial<WorkbenchSnapshot> = {},
): WorkbenchSnapshot {
  return {
    observed_at: workbenchTimestamp,
    attention: [],
    activity: {
      automation: null,
      collection: null,
      initial_analysis: null,
      report: null,
    },
    next_automation: null,
    latest_report: null,
    ...values,
  }
}

export function completedReport(): NonNullable<
  WorkbenchSnapshot['latest_report']
> {
  return {
    id: 31,
    status: 'completed',
    created_at: workbenchTimestamp,
    finished_at: '2026-08-29T08:10:00+00:00',
    overview: '多条来源提及社区道路积水，具体地点和发生时间仍需核实。',
    empty_reason: null,
    coverage: coverage(),
  }
}
