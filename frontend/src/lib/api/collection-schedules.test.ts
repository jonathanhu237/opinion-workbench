import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CollectionScheduleApiError,
  createCollectionSchedule,
  fetchCollectionOccurrences,
  fetchCollectionSchedule,
  fetchCollectionSchedules,
  scheduleUpdatePayload,
  SCHEDULE_ERROR_CONTRACTS,
  updateCollectionSchedule,
} from '@/lib/api/collection-schedules'
import {
  occurrenceFixture,
  scheduleFixture,
} from '@/lib/api/collection-schedules.fixtures'

const fetchMock = vi.fn<typeof fetch>()
const signal = new AbortController().signal
const createInput = {
  monitoring_rule_id: 7,
  platforms: ['wb', 'xhs'] as ('wb' | 'xhs')[],
  max_results_per_term: 10,
  interval: { value: 2, unit: 'hours' as const },
}
function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify(body), { status }),
  )
}
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})
afterEach(() => vi.unstubAllGlobals())

describe('collection schedule HTTP boundary', () => {
  it('reads schedules without mutation and uses the bounded cursor contract', async () => {
    const schedules = [scheduleFixture({ id: 8 }), scheduleFixture({ id: 4 })]
    respond({ schedules, next_before_id: 4 })
    expect(
      await fetchCollectionSchedules(signal, { limit: 2, beforeId: 10 }),
    ).toEqual({ schedules, next_before_id: 4 })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/collection-schedules?limit=2&before_id=10',
      expect.objectContaining({ signal, cache: 'no-store', redirect: 'error' }),
    )
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined()
  })
  it('creates disabled configurations and preserves full settings on guarded toggles', async () => {
    const created = scheduleFixture({
      platforms: ['wb', 'xhs'],
      interval_minutes: 120,
    })
    respond(created, 201)
    expect(await createCollectionSchedule(createInput)).toEqual(created)
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify(createInput),
      headers: { 'Content-Type': 'application/json' },
    })
    const enabled = {
      ...created,
      revision: 2,
      enabled: true,
      anchor_at: '2026-08-29T01:00:00Z',
      next_due_at: '2026-08-29T03:00:00Z',
    }
    respond(enabled)
    const input = scheduleUpdatePayload(created, true)
    expect(await updateCollectionSchedule(4, input)).toEqual(enabled)
    expect(input).toEqual({
      monitoring_rule_id: 7,
      platforms: ['wb', 'xhs'],
      max_results_per_term: 10,
      interval: { value: 120, unit: 'minutes' },
      enabled: true,
      expected_revision: 1,
    })
    expect(fetchMock.mock.calls[1][1]?.method).toBe('PUT')
  })
  it('allows disabled deleted references without changing old batch linkage', async () => {
    const previous = scheduleFixture({
      monitoring_rule_id: null,
      rule_state: 'deleted',
      latest_occurrence: occurrenceFixture({
        status: 'dispatched',
        reason: null,
        batch_id: 21,
        batch_status: 'paused_for_manual_action',
        dispatched_at: '2026-08-29T01:00:01Z',
      }),
    })
    respond({ ...previous, revision: 2 })
    expect(
      (
        await updateCollectionSchedule(
          4,
          scheduleUpdatePayload(previous, false),
        )
      ).latest_occurrence?.batch_id,
    ).toBe(21)
  })
  it.each(Object.entries(SCHEDULE_ERROR_CONTRACTS))(
    'validates the exact %s status/code/message without raw errors',
    async (code, contract) => {
      respond({ detail: { code, message: contract.message } }, contract.status)
      await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
        code,
        status: contract.status,
        message: contract.message,
      })
      respond({ detail: { code, message: contract.message } }, 400)
      await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
      respond(
        { detail: { code, message: '/private/secret/raw failure' } },
        contract.status,
      )
      await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )
  it('keeps cancellation separate from bounded network and protocol failures', async () => {
    const abort = new DOMException('Aborted', 'AbortError')
    fetchMock.mockRejectedValueOnce(abort)
    await expect(fetchCollectionSchedule(4, signal)).rejects.toBe(abort)
    fetchMock.mockRejectedValueOnce(new Error('private transport'))
    await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
      code: 'service_unavailable',
    })
    fetchMock.mockResolvedValueOnce(new Response('not json'))
    await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    respond(scheduleFixture(), 202)
    await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
  it.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, Number.NaN])(
    'rejects unsafe ID %s before network',
    async (id) => {
      await expect(fetchCollectionSchedule(id, signal)).rejects.toBeInstanceOf(
        CollectionScheduleApiError,
      )
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )
  it.each([
    { limit: 0 },
    { limit: 101 },
    { limit: 1.5 },
    { beforeId: 0 },
    { beforeId: Number.MAX_SAFE_INTEGER + 1 },
  ])('rejects bad page bounds %o before network', async (options) => {
    await expect(
      fetchCollectionSchedules(signal, options),
    ).rejects.toMatchObject({ code: 'invalid_request' })
    await expect(
      fetchCollectionOccurrences(4, signal, options),
    ).rejects.toMatchObject({ code: 'invalid_request' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it.each([
    { value: 0, unit: 'minutes' },
    { value: 1.5, unit: 'hours' },
    { value: 721, unit: 'hours' },
    { value: 43201, unit: 'minutes' },
  ] as const)('rejects invalid normalized intervals %o', async (interval) => {
    await expect(
      createCollectionSchedule({ ...createInput, interval }),
    ).rejects.toMatchObject({ code: 'invalid_collection_interval' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it.each([1, 43200])(
    'accepts normalized minute boundary %s',
    async (value) => {
      respond(scheduleFixture({ interval_minutes: value }), 201)
      expect(
        (
          await createCollectionSchedule({
            ...createInput,
            interval: { value, unit: 'minutes' },
          })
        ).interval_minutes,
      ).toBe(value)
    },
  )
  it.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER + 1])(
    'rejects revision %s that cannot produce a safe next revision',
    async (expected_revision) => {
      await expect(
        updateCollectionSchedule(4, {
          ...scheduleUpdatePayload(scheduleFixture()),
          expected_revision,
        }),
      ).rejects.toMatchObject({ code: 'invalid_collection_schedule' })
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )
  it('accepts the last writable safe revision', async () => {
    respond(scheduleFixture({ revision: Number.MAX_SAFE_INTEGER }))
    expect(
      (
        await updateCollectionSchedule(4, {
          ...scheduleUpdatePayload(scheduleFixture()),
          expected_revision: Number.MAX_SAFE_INTEGER - 1,
        })
      ).revision,
    ).toBe(Number.MAX_SAFE_INTEGER)
  })
  it.each([
    { platforms: ['wb', 'wb'] },
    { platforms: ['xhs', 'wb'] },
    { revision: 0 },
    { id: Number.MAX_SAFE_INTEGER + 1 },
    { enabled: true },
    { rule_state: 'deleted' },
    { rule_name: '' },
    { rule_name: '😀'.repeat(81) },
    { next_due_at: '2026-08-29T01:00:00Z' },
    { created_at: '2026-08-29T08:00:00+08:00' },
    { latest_occurrence: occurrenceFixture({ schedule_id: 6 }) },
    { latest_occurrence: occurrenceFixture({ schedule_revision: 2 }) },
    { prompt: 'not a schedule field' },
  ])('rejects drifted schedule shape %o', async (change) => {
    respond({ ...scheduleFixture(), ...change })
    await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
  it('rejects mismatched route IDs, create activation and stale update revisions', async () => {
    respond(scheduleFixture({ id: 8 }))
    await expect(fetchCollectionSchedule(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    respond(
      scheduleFixture({
        enabled: true,
        anchor_at: '2026-08-29T00:00:00Z',
        next_due_at: '2026-08-29T01:00:00Z',
      }),
      201,
    )
    await expect(createCollectionSchedule(createInput)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    respond(scheduleFixture({ revision: 1 }))
    await expect(
      updateCollectionSchedule(4, scheduleUpdatePayload(scheduleFixture())),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })
  it.each([
    { schedules: [scheduleFixture(), scheduleFixture()], next_before_id: 4 },
    {
      schedules: [scheduleFixture({ id: 2 }), scheduleFixture({ id: 4 })],
      next_before_id: 4,
    },
    { schedules: [scheduleFixture()], next_before_id: 4 },
    {
      schedules: [scheduleFixture({ id: 8 }), scheduleFixture()],
      next_before_id: 3,
    },
  ])(
    'rejects duplicate, unordered, truncated or mismatched cursors',
    async (page) => {
      respond(page)
      await expect(
        fetchCollectionSchedules(signal, { limit: 2 }),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    },
  )
  it('rejects items outside the requested cursor', async () => {
    respond({ schedules: [scheduleFixture()], next_before_id: null })
    await expect(
      fetchCollectionSchedules(signal, { beforeId: 4 }),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })
})

describe('occurrence truth and provenance', () => {
  it.each([
    occurrenceFixture({ status: 'claimed', reason: null }),
    occurrenceFixture(),
    occurrenceFixture({ reason: 'browser_unavailable' }),
    occurrenceFixture({
      status: 'dispatched',
      reason: null,
      batch_id: 50,
      batch_status: 'paused_for_manual_action',
      dispatched_at: '2026-08-29T01:00:01Z',
    }),
    occurrenceFixture({
      status: 'missed',
      reason: 'offline',
      missed_count: 100,
      missed_until: '2026-08-30T01:00:00Z',
    }),
    occurrenceFixture({
      status: 'interrupted',
      reason: 'dispatch_interrupted',
    }),
    occurrenceFixture({
      status: 'interrupted',
      reason: 'dispatch_interrupted',
      batch_id: 50,
      batch_status: 'paused_for_manual_action',
      dispatched_at: '2026-08-29T01:00:01Z',
    }),
  ])(
    'accepts truthful %s states including linked interruptions',
    async (occurrence) => {
      respond({ occurrences: [occurrence], next_before_id: null })
      expect((await fetchCollectionOccurrences(4, signal)).occurrences).toEqual(
        [occurrence],
      )
    },
  )
  it.each([
    { status: 'dispatched' },
    { status: 'completed' },
    { status: 'claimed' },
    { reason: 'offline' },
    { reason: 'dispatch_interrupted' },
    { reason: null },
    { missed_count: 1 },
    { batch_id: 30 },
    { batch_status: 'completed' },
    { schedule_id: 5 },
    { schedule_revision: 0 },
    { source_url: 'https://untrusted.invalid' },
    {
      status: 'missed',
      reason: 'clock_jump',
      missed_count: 2,
      missed_until: '2026-08-28T00:00:00Z',
    },
  ])('rejects impossible or unsafe occurrence %o', async (change) => {
    respond({
      occurrences: [{ ...occurrenceFixture(), ...change }],
      next_before_id: null,
    })
    await expect(fetchCollectionOccurrences(4, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
})
