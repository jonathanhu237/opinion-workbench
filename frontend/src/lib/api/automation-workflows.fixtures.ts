import type {
  AutomationRun,
  AutomationStage,
  AutomationTask,
} from '@/lib/api/automation-workflows'

const timestamp = '2026-08-30T01:00:00Z'

export function automationStage(
  name: AutomationStage['name'],
  values: Partial<AutomationStage> = {},
): AutomationStage {
  return {
    name,
    attempt_number: 1,
    status: 'completed',
    child_kind: name,
    child_id:
      name === 'collection' ? 201 : name === 'initial_analysis' ? 301 : 401,
    input_count: 0,
    success_count: 0,
    failure_count: 0,
    usage_attempted: 0,
    usage_tokens: null,
    error: null,
    created_at: timestamp,
    started_at: '2026-08-30T01:00:01Z',
    finished_at: '2026-08-30T01:00:05Z',
    ...values,
  }
}

export function automationRun(
  values: Partial<AutomationRun> = {},
): AutomationRun {
  return {
    id: 101,
    admission_key: 'manual:7b4f2c23-04d7-4f6b-9b24-3c4c4cf5b900',
    request_id: '7b4f2c23-04d7-4f6b-9b24-3c4c4cf5b900',
    task_id: 7,
    trigger: 'manual',
    task_revision: 2,
    snapshot: {
      task_id: 7,
      task_revision: 2,
      task_name: '街道公共事务值守',
      monitoring_rule_id: 9,
      rule_name: '公共事务',
      terms: ['街道', '社区'],
      platforms: ['wb'],
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
      admitted_at: timestamp,
    },
    status: 'completed',
    active_stage: null,
    stages: [
      automationStage('collection'),
      automationStage('initial_analysis'),
      automationStage('topic_report'),
    ],
    attempts: [
      automationStage('collection'),
      automationStage('initial_analysis'),
      automationStage('topic_report'),
    ],
    cancel_requested: false,
    outcome: 'completed',
    topic_report_id: 401,
    error: null,
    revision: 4,
    created_at: timestamp,
    started_at: '2026-08-30T01:00:01Z',
    finished_at: '2026-08-30T01:00:05Z',
    ...values,
  }
}

export function automationTask(
  values: Partial<AutomationTask> = {},
): AutomationTask {
  return {
    id: 7,
    name: '街道公共事务值守',
    monitoring_rule_id: 9,
    rule_name: '公共事务',
    rule_state: 'enabled',
    platforms: ['wb'],
    max_results_per_term: 10,
    analysis_goal: '识别需要街道回应的公共事务内容。',
    schedule: { kind: 'interval', interval_minutes: 120 },
    enabled: false,
    revision: 2,
    anchor_at: null,
    next_due_at: null,
    created_at: timestamp,
    updated_at: timestamp,
    latest_run: automationRun(),
    available: true,
    ...values,
  }
}
