import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  analysisAttemptFixture,
  analysisJobFixture,
  analysisRequest,
  analysisTimestamp,
} from '@/lib/api/analysis-fixtures'
import {
  cancelAnalysisJob,
  fetchAnalysisAttempt,
  fetchAnalysisJob,
  fetchAnalysisJobItems,
  fetchResultAnalyses,
  startContentAnalysis,
  understandingSchema,
} from '@/lib/api/content-analyses'

const fetchMock = vi.fn<typeof fetch>()
const signal = new AbortController().signal
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
describe('initial analysis HTTP contract', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  it.each([101, 1001])(
    'admits all %i records with one set intent and no page IDs',
    async (total) => {
      const job = analysisJobFixture()
      job.counts.total = total
      job.counts.queued = total
      fetchMock.mockResolvedValue(
        json({ job, admitted_count: total, already_active_count: 5 }, 202),
      )
      const admitted = await startContentAnalysis(analysisRequest)
      expect(admitted.admitted_count).toBe(total)
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/content-analysis-jobs',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(analysisRequest),
          cache: 'no-store',
        }),
      )
      expect(analysisRequest.selection).toEqual({ kind: 'all_never_started' })
    },
  )
  it('accepts a durable zero-admission no-op, not an empty task', async () => {
    fetchMock.mockResolvedValue(
      json({ job: null, admitted_count: 0, already_active_count: 8 }, 202),
    )
    expect((await startContentAnalysis(analysisRequest)).job).toBeNull()
  })
  it('rejects a mismatched admission intent or total instead of accepting another task', async () => {
    for (const job of [
      analysisJobFixture({ configuration_revision: 4 }),
      analysisJobFixture({ force_refresh: true }),
      analysisJobFixture({
        report_prompt: { ...analysisJobFixture().report_prompt, id: 6 },
      }),
    ]) {
      fetchMock.mockResolvedValueOnce(
        json({ job, admitted_count: 101, already_active_count: 0 }, 202),
      )
      await expect(startContentAnalysis(analysisRequest)).rejects.toMatchObject(
        { code: 'invalid_response' },
      )
    }
  })
  it('accepts saved uncertain evidence, full text and 100 matched terms without a relevance verdict', async () => {
    const item = analysisAttemptFixture()
    item.source.matched_terms = Array.from(
      { length: 100 },
      (_, index) => `线索 ${index}`,
    )
    fetchMock.mockResolvedValue(json(item))
    const decoded = await fetchAnalysisAttempt(21, signal)
    expect(decoded.output?.uncertainties).toContain('无法确认')
    expect(decoded.input?.text.body).toContain('完整保存')
  })
  it('rejects unknown output fields, forged navigation and false complete input', async () => {
    const item = analysisAttemptFixture()
    for (const value of [
      { ...item, output: { ...item.output, decision: 'irrelevant' } },
      {
        ...item,
        source: { ...item.source, content_url: 'https://evil.example/source' },
      },
      {
        ...item,
        input: {
          ...item.input,
          text: { title: '', body: 'partial', coverage: 'partial' },
        },
      },
      { ...item, input: { ...item.input, blob_ref: 'private-path-sentinel' } },
      {
        ...item,
        source: { ...item.source, result_id: Number.MAX_SAFE_INTEGER + 1 },
      },
    ]) {
      fetchMock.mockResolvedValueOnce(json(value))
      await expect(fetchAnalysisAttempt(21, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })
  it('validates ready media inventory against declared image, video and audio modalities', async () => {
    const item = analysisAttemptFixture()
    const image = {
      position: 0,
      kind: 'image',
      status: 'ready',
      sha256: 'a'.repeat(64),
      mime_type: 'image/png',
      byte_size: 100,
      width: 1,
      height: 1,
      duration_ms: null,
      audio_track: 'not_applicable',
      coverage: 'complete',
      issue_code: null,
    }
    const video = {
      ...image,
      kind: 'video',
      mime_type: 'video/mp4',
      duration_ms: 1000,
      audio_track: 'present',
    }
    for (const inventory of [
      { detected_modalities: ['text', 'image'], assets: [image] },
      { detected_modalities: ['text', 'video', 'audio'], assets: [video] },
    ]) {
      fetchMock.mockResolvedValueOnce(
        json({ ...item, input: { ...item.input, ...inventory } }),
      )
      expect((await fetchAnalysisAttempt(21, signal)).input?.status).toBe(
        'ready',
      )
    }
    for (const inventory of [
      { detected_modalities: ['text', 'image'], assets: [] },
      { detected_modalities: ['text', 'video', 'audio'], assets: [] },
      { detected_modalities: ['text', 'audio'], assets: [] },
      { detected_modalities: ['text'], assets: [image] },
      { detected_modalities: ['text', 'video'], assets: [video] },
      { detected_modalities: ['text', 'image', 'audio'], assets: [image] },
    ]) {
      fetchMock.mockResolvedValueOnce(
        json({ ...item, input: { ...item.input, ...inventory } }),
      )
      await expect(fetchAnalysisAttempt(21, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })
  it('preserves incomplete media inventory as saved unsuccessful evidence', async () => {
    const item = analysisAttemptFixture({
      status: 'input_incomplete',
      output: null,
      attempted: false,
      usage: null,
    })
    fetchMock.mockResolvedValueOnce(
      json({
        ...item,
        input: {
          ...item.input,
          status: 'partial',
          detected_modalities: ['text', 'image', 'unknown'],
          media_inventory_complete: false,
          assets: [],
          issues: ['inventory_unknown'],
        },
      }),
    )
    const decoded = await fetchAnalysisAttempt(21, signal)
    expect(decoded.status).toBe('input_incomplete')
    expect(decoded.input?.media_inventory_complete).toBe(false)
    expect(decoded.input?.issues).toEqual(['inventory_unknown'])
    expect(decoded.output).toBeNull()
  })
  it('keeps failures and unknown usage separate from completed understanding', async () => {
    const item = analysisAttemptFixture({
      status: 'failed',
      output: null,
      usage: null,
      error: {
        stage: 'analysis',
        code: 'invalid_schema',
        message: 'untrusted detail',
      },
    })
    fetchMock.mockResolvedValue(json(item))
    const decoded = await fetchAnalysisAttempt(21, signal)
    expect(decoded.output).toBeNull()
    expect(decoded.usage).toBeNull()
    expect(decoded.error?.message).not.toContain('untrusted')
  })
  it('accepts 8 successes and 2 failures only with a terminal completion event', async () => {
    const job = analysisJobFixture({
      status: 'completed',
      completion_event_id: 3,
      finished_at: analysisTimestamp,
    })
    job.counts = {
      ...job.counts,
      total: 10,
      queued: 0,
      completed: 8,
      failed: 2,
    }
    fetchMock.mockResolvedValueOnce(json(job))
    expect((await fetchAnalysisJob(7, signal)).counts.failed).toBe(2)
    fetchMock.mockResolvedValueOnce(json({ ...job, completion_event_id: null }))
    await expect(fetchAnalysisJob(7, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
  it('retains unknown and overflow usage without a legacy request cap', async () => {
    const job = analysisJobFixture()
    job.counts.total = 1001
    job.counts.queued = 1001
    job.usage = {
      attempted_requests: 1001,
      accounted_requests: 1001,
      complete: false,
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
    }
    fetchMock.mockResolvedValue(json(job))
    expect((await fetchAnalysisJob(7, signal)).usage.total_tokens).toBeNull()
  })
  it('validates paginated job membership/positions and result history independently', async () => {
    const item = analysisAttemptFixture({ position: 20 })
    fetchMock.mockResolvedValueOnce(
      json({ items: [item], total: 21, offset: 20, limit: 20 }),
    )
    expect((await fetchAnalysisJobItems(7, signal, 20)).items[0].position).toBe(
      20,
    )
    fetchMock.mockResolvedValueOnce(
      json({
        items: [{ ...item, job_id: 8 }],
        total: 21,
        offset: 20,
        limit: 20,
      }),
    )
    await expect(fetchAnalysisJobItems(7, signal, 20)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    fetchMock.mockResolvedValueOnce(
      json({ items: [item], total: 1, offset: 0, limit: 20 }),
    )
    await expect(fetchResultAnalyses(12, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
  it('validates cancellation and sends only an explicit empty JSON mutation', async () => {
    const job = analysisJobFixture({
      status: 'cancelled',
      finished_at: analysisTimestamp,
    })
    job.counts.cancelled = 101
    job.counts.queued = 0
    fetchMock.mockResolvedValue(json(job))
    expect((await cancelAnalysisJob(7)).status).toBe('cancelled')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/content-analysis-jobs/7/cancel',
      expect.objectContaining({ method: 'POST', body: '{}' }),
    )
  })
  it('checks code-point bounds and combined prose without silent clipping', () => {
    const output = analysisAttemptFixture().output
    expect(
      understandingSchema.safeParse({ ...output, summary: '🙂'.repeat(1500) })
        .success,
    ).toBe(true)
    expect(
      understandingSchema.safeParse({ ...output, summary: '🙂'.repeat(1501) })
        .success,
    ).toBe(false)
    expect(
      understandingSchema.safeParse({
        ...output,
        summary: 'x'.repeat(1500),
        time_context: 'x'.repeat(500),
        uncertainties: 'x'.repeat(500),
        media_observations: Array.from({ length: 12 }, () => 'x'.repeat(400)),
      }).success,
    ).toBe(false)
  })
})
