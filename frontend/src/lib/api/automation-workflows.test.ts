import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AUTOMATION_ERROR_CONTRACTS,
  AutomationApiError,
  createAutomationTask,
  deleteAutomationTask,
  fetchAutomationRun,
  fetchAutomationTasks,
  retryAutomationRun,
  runAutomationTaskNow,
} from '@/lib/api/automation-workflows'

const fetchMock = vi.fn<typeof fetch>()
const signal = new AbortController().signal
const requestId = '7b4f2c23-04d7-4f6b-9b24-3c4c4cf5b900'

function stage(
  name: 'collection' | 'initial_analysis' | 'topic_report',
  values: Record<string, unknown> = {},
) {
  return {
    name,
    attempt_number: 1,
    status: 'completed' as const,
    child_kind: name,
    child_id:
      name === 'collection' ? 201 : name === 'initial_analysis' ? 301 : 401,
    input_count: 0,
    success_count: 0,
    failure_count: 0,
    usage_attempted: 0,
    usage_tokens: null,
    error: null,
    created_at: '2026-08-30T01:00:00Z',
    started_at: '2026-08-30T01:00:01Z',
    finished_at: '2026-08-30T01:00:05Z',
    ...values,
  }
}

function run(values: Record<string, unknown> = {}) {
  return {
    id: 101,
    admission_key: `manual:${requestId}`,
    request_id: requestId,
    task_id: 7,
    trigger: 'manual' as const,
    task_revision: 2,
    snapshot: {
      task_id: 7,
      task_revision: 2,
      task_name: '街道公共事务值守',
      monitoring_rule_id: 9,
      rule_name: '公共事务',
      terms: ['街道', '社区'],
      platforms: ['toutiao', 'wb'] as const,
      max_results_per_term: 10,
      analysis_goal: '识别需要街道回应的公共事务内容。',
      analysis_goal_hash: 'a'.repeat(64),
      ai_configuration_revision: 3,
      ai_base_url: 'https://api.example.com/v1',
      ai_model: 'model-a',
      initial_prompt_version_id: 4,
      report_prompt_version_id: 5,
      initial_template_version: 'initial-v1',
      report_template_version: 'report-v1',
      admitted_at: '2026-08-30T01:00:00Z',
    },
    status: 'completed' as const,
    active_stage: null,
    stages: [
      stage('collection'),
      stage('initial_analysis'),
      stage('topic_report'),
    ],
    attempts: [
      stage('collection'),
      stage('initial_analysis'),
      stage('topic_report'),
    ],
    cancel_requested: false,
    outcome: 'completed' as const,
    topic_report_id: 401,
    error: null,
    revision: 4,
    created_at: '2026-08-30T01:00:00Z',
    started_at: '2026-08-30T01:00:01Z',
    finished_at: '2026-08-30T01:00:05Z',
    ...values,
  }
}

function task(values: Record<string, unknown> = {}) {
  return {
    id: 7,
    name: '街道公共事务值守',
    monitoring_rule_id: 9,
    rule_name: '公共事务',
    rule_state: 'enabled' as const,
    platforms: ['toutiao', 'wb'] as const,
    max_results_per_term: 10,
    analysis_goal: '识别需要街道回应的公共事务内容。',
    schedule: { kind: 'interval' as const, interval_minutes: 120 },
    enabled: false,
    revision: 2,
    anchor_at: null,
    next_due_at: null,
    created_at: '2026-08-29T01:00:00Z',
    updated_at: '2026-08-29T01:00:00Z',
    latest_run: run(),
    available: true,
    ...values,
  }
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

describe('automation workflow HTTP boundary', () => {
  it('decodes the task page and keeps the cursor contract', async () => {
    respond({ tasks: [task()], next_before_id: null })
    await expect(fetchAutomationTasks(signal, { limit: 20 })).resolves.toEqual({
      tasks: [task()],
      next_before_id: null,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/automation-tasks?limit=20',
      expect.objectContaining({ signal, cache: 'no-store', redirect: 'error' }),
    )
  })

  it('creates a disabled task with a daily IANA schedule', async () => {
    const input = {
      name: '每日街道值守',
      monitoring_rule_id: 9,
      platforms: ['toutiao', 'wb'] as ('toutiao' | 'wb')[],
      max_results_per_term: 12,
      initial_prompt: { mode: 'default' as const },
      report_prompt: {
        mode: 'custom' as const,
        instructions: '筛选需要回应的公共事务内容。',
      },
      schedule: {
        kind: 'daily' as const,
        daily_time: '09:30',
        timezone: 'Asia/Shanghai',
      },
    }
    const saved = task({
      name: input.name,
      max_results_per_term: input.max_results_per_term,
      analysis_goal: input.report_prompt.instructions,
      schedule: input.schedule,
    })
    respond(saved, 201)
    await expect(createAutomationTask(input)).resolves.toEqual(saved)
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify(input),
    })
  })

  it('rejects an invalid task name before making the create request', async () => {
    await expect(
      createAutomationTask({
        name: ' \t',
        monitoring_rule_id: 9,
        platforms: ['toutiao'],
        max_results_per_term: 12,
        initial_prompt: { mode: 'default' },
        report_prompt: { mode: 'default' },
        schedule: { kind: 'interval', interval_minutes: 30 },
      }),
    ).rejects.toMatchObject({ code: 'invalid_response' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('keeps request intent while admitting and retrying a run', async () => {
    respond(run(), 202)
    await expect(runAutomationTaskNow(7, requestId)).resolves.toEqual(run())
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/automation-tasks/7/run-now',
    )
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ request_id: requestId }),
    })

    respond(run({ revision: 5 }), 202)
    await expect(
      retryAutomationRun(101, { requestId, expectedRevision: 4 }),
    ).resolves.toMatchObject({ revision: 5 })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/automation-runs/101/retry')
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      body: JSON.stringify({ request_id: requestId, expected_revision: 4 }),
    })
  })

  it('sends the expected task revision and accepts only an empty 204 delete', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))

    await expect(
      deleteAutomationTask(7, { expectedRevision: 2 }, signal),
    ).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/automation-tasks/7',
      expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({ expected_revision: 2 }),
      }),
    )
  })

  it('rejects impossible stage order and exact product error contracts', async () => {
    respond({
      ...run(),
      stages: [
        stage('initial_analysis'),
        stage('collection'),
        stage('topic_report'),
      ],
    })
    await expect(fetchAutomationRun(101, signal)).rejects.toMatchObject({
      code: 'invalid_response',
    })

    const code = 'invalid_request' as const
    const contract = AUTOMATION_ERROR_CONTRACTS[code]
    respond({ detail: { code, message: contract.message } }, contract.status)
    await expect(fetchAutomationRun(101, signal)).rejects.toEqual(
      new AutomationApiError(code, contract.status),
    )
  })
})
