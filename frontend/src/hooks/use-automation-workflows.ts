import { useQuery, type QueryClient } from '@tanstack/react-query'

import {
  AUTOMATION_RUNS_QUERY_KEY,
  AUTOMATION_TASKS_QUERY_KEY,
  fetchAutomationOccurrences,
  fetchAutomationRun,
  fetchAutomationRuns,
  fetchAutomationTask,
  fetchAutomationTasks,
  isAutomationRunActive,
  type AutomationRun,
  type AutomationRunPage,
  type AutomationTask,
  type AutomationTaskPage,
} from '@/lib/api/automation-workflows'

export const AUTOMATION_PAGE_SIZE = 20

export const automationTaskDetailKey = (id: number | null) =>
  [...AUTOMATION_TASKS_QUERY_KEY, 'detail', id] as const
export const automationTaskListKey = [
  ...AUTOMATION_TASKS_QUERY_KEY,
  'list',
] as const
export const automationOccurrencesKey = (
  taskId: number | null,
  beforeId?: number,
) =>
  [
    ...AUTOMATION_TASKS_QUERY_KEY,
    'occurrences',
    taskId,
    beforeId ?? null,
  ] as const
export const automationRunsKey = (taskId: number | null, beforeId?: number) =>
  [...AUTOMATION_RUNS_QUERY_KEY, 'task', taskId, beforeId ?? null] as const
export const automationRunDetailKey = (id: number | null) =>
  [...AUTOMATION_RUNS_QUERY_KEY, 'detail', id] as const

function activeRunFromTask(task: AutomationTask) {
  return task.latest_run !== null && isAutomationRunActive(task.latest_run)
}

export function useAutomationTasks(beforeId?: number) {
  return useQuery({
    queryKey: [...automationTaskListKey, beforeId ?? null],
    queryFn: ({ signal }) =>
      fetchAutomationTasks(signal, {
        limit: AUTOMATION_PAGE_SIZE,
        beforeId,
      }),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.tasks.some(activeRunFromTask) ? 5_000 : false,
  })
}

export function useAutomationTask(id: number | null) {
  return useQuery({
    queryKey: automationTaskDetailKey(id),
    queryFn: ({ signal }) => {
      if (id === null) throw new Error('No automation task selected')
      return fetchAutomationTask(id, signal)
    },
    enabled: id !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && activeRunFromTask(query.state.data) ? 5_000 : false,
  })
}

export function useAutomationOccurrences(
  taskId: number | null,
  beforeId?: number,
) {
  return useQuery({
    queryKey: automationOccurrencesKey(taskId, beforeId),
    queryFn: ({ signal }) => {
      if (taskId === null) throw new Error('No automation task selected')
      return fetchAutomationOccurrences(taskId, signal, {
        limit: AUTOMATION_PAGE_SIZE,
        beforeId,
      })
    },
    enabled: taskId !== null,
    retry: false,
  })
}

export function useAutomationRuns(taskId: number | null, beforeId?: number) {
  return useQuery({
    queryKey: automationRunsKey(taskId, beforeId),
    queryFn: ({ signal }) => {
      if (taskId === null) throw new Error('No automation task selected')
      return fetchAutomationRuns(taskId, signal, {
        limit: AUTOMATION_PAGE_SIZE,
        beforeId,
      })
    },
    enabled: taskId !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.runs.some(isAutomationRunActive) ? 5_000 : false,
  })
}

export function useAutomationRun(id: number | null) {
  return useQuery({
    queryKey: automationRunDetailKey(id),
    queryFn: ({ signal }) => {
      if (id === null) throw new Error('No automation run selected')
      return fetchAutomationRun(id, signal)
    },
    enabled: id !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isAutomationRunActive(query.state.data)
        ? 2_000
        : false,
  })
}

export async function cacheSavedAutomationTask(
  client: QueryClient,
  saved: AutomationTask,
) {
  await client.cancelQueries({ queryKey: AUTOMATION_TASKS_QUERY_KEY })
  const preferNewer = (current: AutomationTask | undefined) =>
    current && current.revision > saved.revision ? current : saved
  client.setQueryData<AutomationTask>(
    automationTaskDetailKey(saved.id),
    preferNewer,
  )
  client.setQueriesData<AutomationTaskPage>(
    { queryKey: automationTaskListKey },
    (current) =>
      current
        ? {
            ...current,
            tasks: current.tasks.map((task) =>
              task.id === saved.id ? preferNewer(task) : task,
            ),
          }
        : current,
  )
  void client.invalidateQueries({ queryKey: AUTOMATION_TASKS_QUERY_KEY })
}

export async function cacheSavedAutomationRun(
  client: QueryClient,
  saved: AutomationRun,
) {
  await client.cancelQueries({ queryKey: AUTOMATION_RUNS_QUERY_KEY })
  const preferNewer = (current: AutomationRun | undefined) =>
    current && current.revision > saved.revision ? current : saved
  client.setQueryData<AutomationRun>(
    automationRunDetailKey(saved.id),
    preferNewer,
  )
  client.setQueriesData<AutomationRunPage>(
    { queryKey: [...AUTOMATION_RUNS_QUERY_KEY, 'task', saved.task_id] },
    (current) =>
      current
        ? {
            ...current,
            runs: current.runs.some((run) => run.id === saved.id)
              ? current.runs.map((run) =>
                  run.id === saved.id ? preferNewer(run) : run,
                )
              : current.runs,
          }
        : current,
  )
  void client.invalidateQueries({ queryKey: AUTOMATION_RUNS_QUERY_KEY })
  void client.invalidateQueries({ queryKey: AUTOMATION_TASKS_QUERY_KEY })
}

export function firstFailedStage(run: AutomationRun) {
  return (
    run.stages.find((stage) =>
      ['failed', 'interrupted', 'configuration_blocked'].includes(stage.status),
    ) ?? null
  )
}

export function isAutomationRunRetryable(run: AutomationRun) {
  return (
    ['failed', 'interrupted', 'configuration_blocked'].includes(run.status) &&
    firstFailedStage(run) !== null
  )
}
