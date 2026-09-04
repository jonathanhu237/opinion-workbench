import { beforeEach, expect, it, vi } from 'vitest'

import {
  analysisJobFixture,
  analysisRequest,
  analysisTimestamp,
} from '@/lib/api/analysis-fixtures'
import {
  createReportGeneration,
  controlReportGeneration,
  fetchReportGeneration,
  generationSchema,
  previewReportSelection,
} from '@/lib/api/report-generations'

const fetchMock = vi.fn<typeof fetch>()
const intent = {
  request_id: analysisRequest.request_id,
  configuration_revision: 3,
  initial_prompt: { mode: 'default' as const },
  report_prompt: { mode: 'default' as const },
  selection: { kind: 'explicit' as const, result_ids: [11] },
}
const generation = () => ({
  id: 1,
  request_id: intent.request_id,
  selection: intent.selection,
  selection_policy: intent.selection,
  status: 'summarising',
  analysis: analysisJobFixture(),
  report: null,
  created_at: analysisTimestamp,
  finished_at: null,
  pause_reason: null,
  pause_attempt_id: null,
  control_revision: 0,
})

it('accepts a truthful manual pause and sends its exact revision only on explicit control', async () => {
  const value = {
    ...generation(),
    status: 'paused_for_manual_action',
    pause_reason: 'login_required',
    pause_attempt_id: 91,
    control_revision: 1,
  }
  value.analysis.counts = { ...value.analysis.counts, total: 1, queued: 1 }
  expect(generationSchema.safeParse(value).success).toBe(true)
  expect(
    generationSchema.safeParse({ ...value, status: 'summarising' }).success,
  ).toBe(false)
  expect(
    generationSchema.safeParse({ ...value, pause_attempt_id: null }).success,
  ).toBe(false)
  fetchMock.mockResolvedValueOnce(Response.json(value))
  await fetchReportGeneration(1, new AbortController().signal)
  expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined()
  fetchMock.mockResolvedValueOnce(Response.json(value))
  await controlReportGeneration(1, 1, 'manual-page')
  expect(fetchMock.mock.calls[1][0]).toContain(
    '/report-generations/1/manual-page',
  )
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
    expected_revision: 1,
  })
})
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})
it('starts once with the exact selection and only reads on reload', async () => {
  const value = generation()
  value.analysis.counts = { ...value.analysis.counts, total: 1, queued: 1 }
  fetchMock.mockResolvedValueOnce(Response.json(value, { status: 202 }))
  expect(await createReportGeneration(intent)).toEqual(value)
  expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual(intent)
  fetchMock.mockResolvedValueOnce(Response.json(value))
  expect(await fetchReportGeneration(1, new AbortController().signal)).toEqual(
    value,
  )
  expect(fetchMock.mock.calls[1][1]?.method).toBeUndefined()
  fetchMock.mockResolvedValueOnce(
    Response.json(
      { ...value, request_id: crypto.randomUUID() },
      { status: 202 },
    ),
  )
  await expect(createReportGeneration(intent)).rejects.toThrow()
})
it('rejects dishonest progress and a fabricated completed report', () => {
  expect(
    generationSchema.safeParse({
      ...generation(),
      status: 'completed',
      finished_at: analysisTimestamp,
    }).success,
  ).toBe(false)
  expect(
    generationSchema.safeParse({
      ...generation(),
      selection: { kind: 'explicit', result_ids: [11, 12, 13] },
    }).success,
  ).toBe(false)
})

it('keeps a library policy separate from its uncapped frozen membership', async () => {
  const policy = { kind: 'library_pending' as const }
  const value = {
    ...generation(),
    selection_policy: policy,
    selection: {
      kind: 'explicit',
      result_ids: Array.from({ length: 1001 }, (_, index) => index + 1),
    },
  }
  value.analysis.counts = {
    ...value.analysis.counts,
    total: 1001,
    queued: 1001,
  }
  fetchMock.mockResolvedValueOnce(Response.json(value, { status: 202 }))
  expect(
    (await createReportGeneration({ ...intent, selection: policy })).selection
      .result_ids,
  ).toHaveLength(1001)
  fetchMock.mockResolvedValueOnce(
    Response.json(
      { ...value, selection_policy: { kind: 'library_pending' } },
      { status: 202 },
    ),
  )
  await expect(
    createReportGeneration({ ...intent, selection: policy }),
  ).resolves.toMatchObject({ selection_policy: policy })
})

it('resolves a library selection into a concrete snapshot without creating a task', async () => {
  fetchMock.mockResolvedValueOnce(
    Response.json({
      selection: { kind: 'explicit', result_ids: [3, 2] },
      counts: {
        total: 2,
        pending: 1,
        already_summarized: 1,
        failed: 0,
        active: 0,
      },
    }),
  )
  await expect(
    previewReportSelection({ kind: 'library' }),
  ).resolves.toMatchObject({
    selection: { result_ids: [3, 2] },
    counts: { total: 2, pending: 1 },
  })
  expect(fetchMock.mock.calls[0][0]).toContain(
    '/report-generations/selection-preview',
  )
  expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
    kind: 'library',
  })
})
