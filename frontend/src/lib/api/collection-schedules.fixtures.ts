import type {
  CollectionOccurrence,
  CollectionSchedule,
} from '@/lib/api/collection-schedules'

export const scheduleCreatedAt = '2026-08-29T00:00:00Z'
export function scheduleFixture(
  overrides: Partial<CollectionSchedule> = {},
): CollectionSchedule {
  return {
    id: 4,
    monitoring_rule_id: 7,
    rule_name: '社区公共事务',
    rule_state: 'enabled',
    platforms: ['toutiao', 'wb', 'ks', 'dy', 'xhs'],
    max_results_per_term: 10,
    interval_minutes: 60,
    enabled: false,
    revision: 1,
    anchor_at: null,
    next_due_at: null,
    created_at: scheduleCreatedAt,
    updated_at: scheduleCreatedAt,
    latest_occurrence: null,
    available: false,
    ...overrides,
  }
}
export function occurrenceFixture(
  overrides: Partial<CollectionOccurrence> = {},
): CollectionOccurrence {
  return {
    id: 30,
    schedule_id: 4,
    schedule_revision: 1,
    due_at: '2026-08-29T01:00:00Z',
    status: 'skipped',
    reason: 'browser_operation_active',
    batch_id: null,
    batch_status: null,
    missed_count: 0,
    missed_until: null,
    created_at: '2026-08-29T01:00:00Z',
    dispatched_at: null,
    ...overrides,
  }
}
