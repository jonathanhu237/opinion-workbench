import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AI_ERROR_CONTRACTS } from '@/lib/api/ai-settings'
import { summaryFailureSchema } from '@/lib/api/ai-summaries'
import {
  cancelTopicReport,
  createTopicReport,
  fetchReportSection,
  fetchReportSections,
  fetchReportSources,
  fetchTopicReport,
  fetchTopicReports,
  isAmbiguousReportError,
  reportRunSchema,
  reportSectionSchema,
  reportSourceSchema,
  retryTopicReport,
  TOPIC_REPORT_ERROR_CONTRACTS,
  TopicReportApiError,
} from '@/lib/api/topic-reports'
import {
  reportCreateRequest,
  reportFixture,
  reportNodes,
  reportRequestId,
  reportSectionFixture,
  reportSourceFixture,
  reportUsage,
} from '@/lib/api/topic-reports.fixtures'

const fetchMock = vi.fn<typeof fetch>()
const signal = new AbortController().signal
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
describe('strict saved-text report boundary', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  it('reads a normally settled 8/10 automatic report without admitting anything', async () => {
    const report = reportFixture()
    fetchMock.mockResolvedValueOnce(
      json({ reports: [report], next_before_id: null }),
    )
    expect(await fetchTopicReports(signal, { initialJobId: 7 })).toEqual({
      reports: [report],
      next_before_id: null,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/topic-reports?limit=20&initial_job_id=7',
      expect.objectContaining({ signal, cache: 'no-store', redirect: 'error' }),
    )
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined()
  })
  it.each(['queued', 'judging', 'composing'] as const)(
    'accepts active %s and rejects fabricated terminal progress',
    (status) => {
      const report = reportFixture({
        status,
        finished_at: null,
        root_section_id: null,
        revision: 1,
      })
      expect(reportRunSchema.safeParse(report).success).toBe(true)
      expect(
        reportRunSchema.safeParse({ ...report, finished_at: report.created_at })
          .success,
      ).toBe(false)
      const terminal = reportFixture()
      terminal.coverage.pending = 1
      terminal.coverage.relevant = 7
      expect(reportRunSchema.safeParse(terminal).success).toBe(false)
    },
  )
  it.each([
    'failed',
    'cancelled',
    'interrupted',
    'configuration_blocked',
  ] as const)(
    'retains %s separately from successful or empty output',
    (status) => {
      const report = reportFixture({ status, root_section_id: null })
      expect(reportRunSchema.safeParse(report).success).toBe(true)
      expect(
        reportRunSchema.safeParse({ ...report, root_section_id: 501 }).success,
      ).toBe(false)
    },
  )
  it('requires honest empty reasons and reconciled coverage, nodes and attempted/accounted usage', () => {
    const noRelevant = reportFixture({
      status: 'empty',
      root_section_id: null,
      empty_reason: 'no_relevant_sources',
    })
    noRelevant.coverage.irrelevant = 7
    noRelevant.coverage.uncertain = 1
    noRelevant.coverage.relevant = 0
    noRelevant.nodes.composition = reportNodes()
    noRelevant.usage = {
      judgment: reportUsage(8),
      composition: reportUsage(),
      total: reportUsage(8),
    }
    expect(reportRunSchema.safeParse(noRelevant).success).toBe(true)
    const noReady = {
      ...noRelevant,
      empty_reason: 'no_ready_sources',
      coverage: {
        ...noRelevant.coverage,
        ready: 0,
        unavailable: 10,
        irrelevant: 0,
        uncertain: 0,
      },
      nodes: { judgments: reportNodes(), composition: reportNodes() },
      usage: {
        judgment: reportUsage(),
        composition: reportUsage(),
        total: reportUsage(),
      },
    }
    expect(reportRunSchema.safeParse(noReady).success).toBe(true)
    for (const malformed of [
      { ...noReady, empty_reason: null },
      { ...noReady, coverage: { ...noReady.coverage, total: 11 } },
      {
        ...noReady,
        nodes: { ...noReady.nodes, judgments: { ...reportNodes(), reused: 1 } },
      },
      { ...noReady, usage: { ...noReady.usage, total: reportUsage(1) } },
    ])
      expect(reportRunSchema.safeParse(malformed).success).toBe(false)
  })
  it('accepts uncapped request counts and unknown usage without replacing it with zero', () => {
    const report = reportFixture({
      usage: {
        judgment: reportUsage(1001, 0),
        composition: reportUsage(),
        total: reportUsage(1001, 0),
      },
    })
    expect(reportRunSchema.parse(report).usage.total.total_tokens).toBeNull()
    const reused = reportSectionFixture({
      attempted: false,
      usage: null,
      reused_from_node_id: 499,
    })
    expect(reportSectionSchema.safeParse(reused).success).toBe(true)
    expect(
      reportSectionSchema.safeParse({ ...reused, attempted: true }).success,
    ).toBe(false)
  })
  it('reconciles stage token sums, partial accounting and safe-integer overflow', () => {
    const report = reportFixture()
    expect(
      reportRunSchema.safeParse({
        ...report,
        usage: {
          ...report.usage,
          total: {
            ...report.usage.total,
            prompt_tokens: 0,
            completion_tokens: 270,
          },
        },
      }).success,
    ).toBe(false)
    const partial = {
      judgment: reportUsage(8, 0),
      composition: reportUsage(1),
      total: { ...reportUsage(9, 1) },
    }
    expect(
      reportRunSchema.safeParse({ ...report, usage: partial }).success,
    ).toBe(true)
    const huge = {
      attempted_requests: 1,
      accounted_requests: 1,
      complete: true,
      prompt_tokens: Number.MAX_SAFE_INTEGER,
      completion_tokens: 0,
      total_tokens: Number.MAX_SAFE_INTEGER,
    }
    const overflow = {
      judgment: huge,
      composition: huge,
      total: {
        attempted_requests: 2,
        accounted_requests: 2,
        complete: false,
        prompt_tokens: null,
        completion_tokens: null,
        total_tokens: null,
      },
    }
    expect(
      reportRunSchema.safeParse({ ...report, usage: overflow }).success,
    ).toBe(true)
    expect(
      reportRunSchema.safeParse({
        ...report,
        usage: {
          ...overflow,
          total: { ...huge, attempted_requests: 2, accounted_requests: 2 },
        },
      }).success,
    ).toBe(false)
  })
  it.each([
    'ai_configuration_required',
    'ai_configuration_changed',
    'ai_credentials_unavailable',
    'ai_settings_storage_unavailable',
  ] as const)(
    'accepts report-only fixed %s failure without widening legacy/A',
    (code) => {
      const error = {
        stage: 'execution' as const,
        code,
        message: AI_ERROR_CONTRACTS[code].message,
      }
      expect(
        reportRunSchema.safeParse(
          reportFixture({
            status: 'configuration_blocked',
            root_section_id: null,
            error,
          }),
        ).success,
      ).toBe(true)
      expect(summaryFailureSchema.safeParse(error).success).toBe(false)
      expect(
        reportSourceSchema.safeParse({ ...reportSourceFixture(), error })
          .success,
      ).toBe(false)
      expect(
        reportSectionSchema.safeParse({ ...reportSectionFixture(), error })
          .success,
      ).toBe(false)
      expect(
        reportRunSchema.safeParse({
          ...reportFixture(),
          error: { ...error, message: 'raw secret' },
        }).success,
      ).toBe(false)
      expect(
        reportRunSchema.safeParse({
          ...reportFixture(),
          error: { ...error, stage: 'composition' },
        }).success,
      ).toBe(false)
    },
  )
  it.each([true, 0, -1, 1.2, Number.MAX_SAFE_INTEGER + 1, '31'])(
    'rejects unsafe ID %s before HTTP',
    async (id) => {
      await expect(
        fetchTopicReport(id as number, signal),
      ).rejects.toMatchObject({ code: 'invalid_request' })
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )
  it('rejects mismatched report identity, origin, exact fields and completion times', async () => {
    for (const report of [
      reportFixture({ id: 32 }),
      { ...reportFixture(), private_key: 'hidden' },
      reportFixture({ initial_job_id: 8 }),
      reportFixture({ completion_event_id: null }),
      reportFixture({ request_id: reportRequestId }),
      reportFixture({ finished_at: '2026-08-28T08:00:00Z' }),
    ]) {
      fetchMock.mockResolvedValueOnce(json(report))
      await expect(fetchTopicReport(31, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })
  it.each([31, 32])(
    'rejects a retry parent %s that is not older than the returned report',
    async (parentId) => {
      const report = reportFixture({
        trigger: 'retry',
        parent_report_id: parentId,
        request_id: reportRequestId,
        completion_event_id: null,
      })
      fetchMock.mockResolvedValueOnce(json(report))
      await expect(fetchTopicReport(31, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
      fetchMock.mockResolvedValueOnce(
        json({ reports: [report], next_before_id: null }),
      )
      await expect(fetchTopicReports(signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
      fetchMock.mockResolvedValueOnce(json(report, 202))
      await expect(
        retryTopicReport(parentId, {
          request_id: reportRequestId,
          expected_revision: 2,
          configuration_revision: 3,
        }),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    },
  )
  it.each([501, 502])(
    'rejects a canonical reused node %s that is not older than its section',
    async (nodeId) => {
      const section = reportSectionFixture({
        attempted: false,
        usage: null,
        reused_from_node_id: nodeId,
      })
      fetchMock.mockResolvedValueOnce(json(section))
      await expect(fetchReportSection(31, 501, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
      fetchMock.mockResolvedValueOnce(
        json({ sections: [section], total: 1, offset: 0, limit: 5 }),
      )
      await expect(fetchReportSections(31, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )
  it('accepts strictly older retry parents and canonical reused sections', async () => {
    const report = reportFixture({
      trigger: 'retry',
      parent_report_id: 30,
      request_id: reportRequestId,
      completion_event_id: null,
    })
    fetchMock.mockResolvedValueOnce(json(report))
    expect(await fetchTopicReport(31, signal)).toEqual(report)
    const section = reportSectionFixture({
      attempted: false,
      usage: null,
      reused_from_node_id: 500,
    })
    fetchMock.mockResolvedValueOnce(json(section))
    expect(await fetchReportSection(31, 501, signal)).toEqual(section)
  })
  it('rejects unordered, wrong-job, oversized and impossible history cursors', async () => {
    for (const page of [
      { reports: [reportFixture(), reportFixture()], next_before_id: null },
      {
        reports: [
          reportFixture({
            initial_job_id: 8,
            selection: { kind: 'initial_job', job_id: 8 },
          }),
        ],
        next_before_id: null,
      },
      { reports: [reportFixture()], next_before_id: 31 },
    ]) {
      fetchMock.mockResolvedValueOnce(json(page))
      await expect(
        fetchTopicReports(signal, { initialJobId: 7 }),
      ).rejects.toMatchObject({ code: 'invalid_response' })
    }
    await expect(
      fetchTopicReports(signal, { limit: 101 }),
    ).rejects.toMatchObject({ code: 'invalid_request' })
  })
  it('supports all frozen source pages beyond 100 and requires exact page positions and bounds', async () => {
    const items = [reportSourceFixture(100)]
    fetchMock.mockResolvedValueOnce(
      json({ items, total: 101, limit: 20, offset: 100 }),
    )
    expect((await fetchReportSources(31, signal, 100)).items[0].position).toBe(
      100,
    )
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/topic-reports/31/sources?offset=100&limit=20',
      expect.any(Object),
    )
    for (const page of [
      { items, total: 101, limit: 20, offset: 0 },
      { items, total: 120, limit: 20, offset: 100 },
      { items: [reportSourceFixture(99)], total: 101, limit: 20, offset: 100 },
    ]) {
      fetchMock.mockResolvedValueOnce(json(page))
      await expect(fetchReportSources(31, signal, 100)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
    await expect(fetchReportSources(31, signal, -1)).rejects.toMatchObject({
      code: 'invalid_request',
    })
    await expect(fetchReportSources(31, signal, 0, 101)).rejects.toMatchObject({
      code: 'invalid_request',
    })
  })
  it('keeps unavailable, unrelated, uncertain and technical failures distinct', () => {
    for (const state of ['irrelevant', 'uncertain'] as const)
      expect(
        reportSourceSchema.safeParse(
          reportSourceFixture(0, {
            state,
            judgment: { decision: state, reason: '尚不能确认具体地点。' },
          }),
        ).success,
      ).toBe(true)
    expect(
      reportSourceSchema.safeParse(
        reportSourceFixture(0, { state: 'failed', judgment: null }),
      ).success,
    ).toBe(true)
    const unavailable = reportSourceFixture(0, {
      state: 'unavailable',
      unavailable_reason: 'in_progress',
      initial_status: 'analysing',
      judgment: null,
      judgment_node_id: null,
    })
    expect(reportSourceSchema.safeParse(unavailable).success).toBe(true)
    for (const value of [
      { ...unavailable, judgment: { decision: 'irrelevant', reason: 'no' } },
      { ...unavailable, unavailable_reason: null },
      reportSourceFixture(0, { initial_status: 'failed' }),
      reportSourceFixture(0, { judgment_node_id: null }),
      reportSourceFixture(0, { state: 'uncertain' }),
    ])
      expect(reportSourceSchema.safeParse(value).success).toBe(false)
  })
  it('validates bounded section-owned frozen citations without loading any source page', async () => {
    const source = reportSourceFixture(100).source
    const section = reportSectionFixture({
      position: 12,
      sources: [{ position: 100, source }],
      source_count: 1,
      document: {
        overview: '<script>text only</script>',
        items: [
          {
            text: 'https://untrusted.example is prose',
            source_ids: [source.result_id],
          },
        ],
      },
    })
    fetchMock.mockResolvedValueOnce(json(section))
    expect(await fetchReportSection(31, 501, signal)).toEqual(section)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    for (const bad of [
      { ...section, report_id: 32 },
      {
        ...section,
        document: {
          ...section.document,
          items: [{ text: 'wrong', source_ids: [999] }],
        },
      },
      {
        ...section,
        sources: [...section.sources, ...section.sources],
        source_count: 2,
      },
      {
        ...section,
        document: {
          ...section.document,
          items: [
            { text: 'wrong', source_ids: [source.result_id, source.result_id] },
          ],
        },
      },
      {
        ...section,
        sources: [
          {
            position: 100,
            source: { ...source, content_url: 'https://evil.example/' },
          },
        ],
      },
    ]) {
      fetchMock.mockResolvedValueOnce(json(bad))
      await expect(fetchReportSection(31, 501, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    }
  })
  it('resolves overview references to current-report child IDs and rejects unknown/duplicate children', () => {
    const overview = reportSectionFixture({
      id: 700,
      kind: 'overview',
      level: 2,
      source_count: 9,
      sources: [],
      document: null,
      children: [
        {
          id: 501,
          kind: 'overview',
          level: 1,
          position: 0,
          source_count: 8,
          overview: '子总览',
        },
        {
          id: 502,
          kind: 'leaf',
          level: 0,
          position: 8,
          source_count: 1,
          overview: '末尾章节',
        },
      ],
      overview_document: {
        overview: '已保存总览',
        items: [{ text: '合成文字', section_ids: [501, 502] }],
      },
    })
    expect(reportSectionSchema.safeParse(overview).success).toBe(true)
    for (const value of [
      {
        ...overview,
        overview_document: {
          overview: 'test',
          items: [{ text: 'test', section_ids: [499] }],
        },
      },
      { ...overview, children: [overview.children[0], overview.children[0]] },
      { ...overview, source_count: 8 },
      { ...overview, level: 1 },
    ])
      expect(reportSectionSchema.safeParse(value).success).toBe(false)
  })
  it('paginates leaf sections with original positions, never a first-100 slice or source fetch', async () => {
    const section = reportSectionFixture({ id: 800, position: 12 })
    fetchMock.mockResolvedValueOnce(
      json({ sections: [section], total: 13, limit: 5, offset: 12 }),
    )
    expect(
      (await fetchReportSections(31, signal, 12, 'leaf')).sections[0].position,
    ).toBe(12)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/topic-reports/31/sections?offset=12&limit=5&kind=leaf',
      expect.any(Object),
    )
  })
  it('creates interval and custom reports with the exact frozen intent, and no stage-one fields', async () => {
    const report = reportFixture({
      trigger: 'interval',
      request_id: reportRequestId,
      initial_job_id: null,
      completion_event_id: null,
      selection: reportCreateRequest.selection,
    })
    fetchMock.mockResolvedValueOnce(json(report, 202))
    expect(await createTopicReport(reportCreateRequest)).toEqual(report)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/topic-reports',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(reportCreateRequest),
      }),
    )
    const override = {
      ...reportCreateRequest,
      report_prompt: {
        mode: 'custom' as const,
        instructions: '  本次专用提示词\n',
      },
    }
    fetchMock.mockResolvedValueOnce(
      json(
        {
          ...report,
          prompt: {
            ...report.prompt,
            mode: 'custom',
            origin: 'custom',
            instructions: override.report_prompt.instructions,
          },
        },
        202,
      ),
    )
    expect((await createTopicReport(override)).prompt.instructions).toBe(
      override.report_prompt.instructions,
    )
  })
  it.each([
    ['2026-08-29T00:00:00.123499+00:00', '2026-08-29T00:00:00.123501Z'],
    ['2026-08-29T00:00:00.1Z', '2026-08-29T00:00:00.100001+00:00'],
    ['2026-08-29T00:00:00Z', '2026-08-29T00:00:00.000001+00:00'],
    ['2026-08-29T23:59:59.999999Z', '2026-08-30T00:00:00+00:00'],
  ])(
    'preserves exact valid UTC microsecond interval %s to %s on create and read',
    async (from, to) => {
      const input = {
        ...reportCreateRequest,
        selection: {
          ...reportCreateRequest.selection,
          first_seen_from: from,
          first_seen_to: to,
        },
      }
      const report = reportFixture({
        trigger: 'interval',
        request_id: input.request_id,
        initial_job_id: null,
        completion_event_id: null,
        selection: input.selection,
      })
      fetchMock.mockResolvedValueOnce(json(report, 202))
      expect(await createTopicReport(input)).toEqual(report)
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/v1/topic-reports',
        expect.objectContaining({ body: JSON.stringify(input) }),
      )
      fetchMock.mockResolvedValueOnce(json(report))
      expect(await fetchTopicReport(report.id, signal)).toEqual(report)
      expect(fetchMock.mock.calls[1][1]?.method).toBeUndefined()
    },
  )
  it.each([
    ['2026-08-29T00:00:00.1234Z', '2026-08-29T00:00:00.123400+00:00'],
    ['2026-08-29T00:00:00.123501Z', '2026-08-29T00:00:00.123499+00:00'],
    ['2026-08-29T00:00:00Z', '2026-08-29T00:00:00.000000+00:00'],
    ['2026-08-29T00:00:00.1234999Z', '2026-08-29T00:00:00.123501Z'],
    ['2026-08-29T00:00:00.123499Z', '2026-08-29T00:00:00.1235010Z'],
    ['0000-01-01T00:00:00Z', '2026-08-29T00:00:00Z'],
  ])(
    'rejects equal/reversed or unsupported-precision interval %s to %s',
    async (from, to) => {
      const input = {
        ...reportCreateRequest,
        selection: {
          ...reportCreateRequest.selection,
          first_seen_from: from,
          first_seen_to: to,
        },
      }
      await expect(createTopicReport(input)).rejects.toMatchObject({
        code: 'invalid_report_interval',
      })
      expect(fetchMock).not.toHaveBeenCalled()
      fetchMock.mockResolvedValueOnce(
        json(
          reportFixture({
            trigger: 'interval',
            request_id: input.request_id,
            initial_job_id: null,
            completion_event_id: null,
            selection: input.selection,
          }),
        ),
      )
      await expect(fetchTopicReport(31, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )
  it('accepts equivalent UTC suffix and zero-padding in an interval acknowledgement', async () => {
    const input = {
      ...reportCreateRequest,
      selection: {
        ...reportCreateRequest.selection,
        first_seen_from: '2026-08-29T00:00:00.1Z',
        first_seen_to: '2026-08-29T00:00:00.200001+00:00',
      },
    }
    const report = reportFixture({
      trigger: 'interval',
      request_id: input.request_id,
      initial_job_id: null,
      completion_event_id: null,
      selection: {
        ...input.selection,
        first_seen_from: '2026-08-29T00:00:00.100000+00:00',
        first_seen_to: '2026-08-29T00:00:00.200001Z',
      },
    })
    fetchMock.mockResolvedValueOnce(json(report, 202))
    expect(await createTopicReport(input)).toEqual(report)
  })
  it.each(['first_seen_from', 'first_seen_to'] as const)(
    'rejects a one-microsecond change to acknowledged %s',
    async (field) => {
      const input = {
        ...reportCreateRequest,
        selection: {
          ...reportCreateRequest.selection,
          first_seen_from: '2026-08-29T00:00:00.123400Z',
          first_seen_to: '2026-08-29T00:00:00.123800Z',
        },
      }
      const report = reportFixture({
        trigger: 'interval',
        request_id: input.request_id,
        initial_job_id: null,
        completion_event_id: null,
        selection: {
          ...input.selection,
          [field]:
            field === 'first_seen_from'
              ? '2026-08-29T00:00:00.123401Z'
              : '2026-08-29T00:00:00.123801Z',
        },
      })
      fetchMock.mockResolvedValueOnce(json(report, 202))
      await expect(createTopicReport(input)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )
  it('rejects noncanonical UUID, omitted fields, invalid prompts and non-UTC/reversed intervals before submission', async () => {
    const bad = [
      { ...reportCreateRequest, request_id: reportRequestId.toUpperCase() },
      { ...reportCreateRequest, request_id: 'invalid' },
      {
        ...reportCreateRequest,
        report_prompt: { mode: 'custom' as const, instructions: ' ' },
      },
      {
        ...reportCreateRequest,
        report_prompt: {
          mode: 'custom' as const,
          instructions: 'x'.repeat(8001),
        },
      },
      {
        ...reportCreateRequest,
        report_prompt: { mode: 'custom' as const, instructions: '\u0000' },
      },
      {
        ...reportCreateRequest,
        report_prompt: { mode: 'custom' as const, instructions: '\ud800' },
      },
      { ...reportCreateRequest, configuration_revision: true },
      {
        ...reportCreateRequest,
        selection: {
          ...reportCreateRequest.selection,
          first_seen_to: reportCreateRequest.selection.first_seen_from,
        },
      },
      {
        ...reportCreateRequest,
        selection: {
          ...reportCreateRequest.selection,
          first_seen_to: '2026-08-30T08:00:00+08:00',
        },
      },
      { ...reportCreateRequest, report_prompt: undefined },
    ]
    for (const value of bad)
      await expect(
        createTopicReport(value as typeof reportCreateRequest),
      ).rejects.toBeInstanceOf(TopicReportApiError)
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('sends retry/cancel revisions and UUIDs exactly and validates mutation acknowledgements', async () => {
    const request = {
      request_id: reportRequestId,
      expected_revision: 2,
      configuration_revision: 3,
    }
    const retried = reportFixture({
      id: 32,
      trigger: 'retry',
      parent_report_id: 31,
      request_id: reportRequestId,
      completion_event_id: null,
    })
    fetchMock.mockResolvedValueOnce(json(retried, 202))
    expect(await retryTopicReport(31, request)).toEqual(retried)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/topic-reports/31/retry',
      expect.objectContaining({ body: JSON.stringify(request) }),
    )
    fetchMock.mockResolvedValueOnce(
      json(
        reportFixture({
          status: 'cancelled',
          root_section_id: null,
          revision: 3,
        }),
      ),
    )
    expect(
      (
        await cancelTopicReport(31, {
          request_id: reportRequestId,
          expected_revision: 2,
        })
      ).status,
    ).toBe('cancelled')
    fetchMock.mockResolvedValueOnce(json(retried, 200))
    await expect(retryTopicReport(31, request)).rejects.toMatchObject({
      code: 'invalid_response',
    })
    fetchMock.mockResolvedValueOnce(
      json(
        reportFixture({
          status: 'judging',
          root_section_id: null,
          finished_at: null,
        }),
      ),
    )
    await expect(
      cancelTopicReport(31, {
        request_id: reportRequestId,
        expected_revision: 2,
      }),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })
  it.each(Object.entries(TOPIC_REPORT_ERROR_CONTRACTS))(
    'binds error %s to its exact HTTP status and fixed message',
    async (code, contract) => {
      fetchMock.mockResolvedValueOnce(
        json({ detail: { code, message: contract.message } }, contract.status),
      )
      await expect(fetchTopicReport(31, signal)).rejects.toMatchObject({
        code,
        message: contract.message,
        status: contract.status,
      })
      fetchMock.mockResolvedValueOnce(
        json({ detail: { code, message: contract.message } }, 418),
      )
      await expect(fetchTopicReport(31, signal)).rejects.toMatchObject({
        code: 'invalid_response',
      })
      fetchMock.mockResolvedValueOnce(
        json(
          { detail: { code, message: 'raw private data' } },
          contract.status,
        ),
      )
      await expect(fetchTopicReport(31, signal)).rejects.not.toHaveProperty(
        'message',
        'raw private data',
      )
    },
  )
  it('preserves aborts and treats transport, invalid response and 503 as ambiguous without automatic retry', async () => {
    const aborted = new DOMException('aborted', 'AbortError')
    fetchMock.mockRejectedValueOnce(aborted)
    await expect(fetchTopicReport(31, signal)).rejects.toBe(aborted)
    fetchMock.mockRejectedValueOnce(new TypeError('offline'))
    await expect(createTopicReport(reportCreateRequest)).rejects.toMatchObject({
      code: 'service_unavailable',
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(
      isAmbiguousReportError(new TopicReportApiError('invalid_response', 202)),
    ).toBe(true)
    expect(
      isAmbiguousReportError(
        new TopicReportApiError('topic_report_unavailable', 503),
      ),
    ).toBe(true)
    expect(
      isAmbiguousReportError(
        new TopicReportApiError('topic_report_changed', 409),
      ),
    ).toBe(false)
  })
})
