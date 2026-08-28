import { useQuery, type QueryClient } from '@tanstack/react-query'

import {
  COLLECTION_SCHEDULES_QUERY_KEY,
  fetchCollectionOccurrences,
  fetchCollectionSchedule,
  fetchCollectionSchedules,
  type CollectionOccurrence,
  type CollectionSchedule,
  type CollectionSchedulePage,
} from '@/lib/api/collection-schedules'

export const scheduleDetailKey = (id: number | null) =>
  [...COLLECTION_SCHEDULES_QUERY_KEY, 'detail', id] as const
export const scheduleListKey = [
  ...COLLECTION_SCHEDULES_QUERY_KEY,
  'list',
] as const
export const SCHEDULE_PAGE_SIZE = 20

export function scheduleConfigurationChanged(
  observed: CollectionSchedule,
  latest: CollectionSchedule,
) {
  // Rule deletion/disable changes this dependency without incrementing the
  // schedule revision. Timer-only due/history updates do not invalidate drafts.
  return (
    latest.revision > observed.revision ||
    (latest.revision === observed.revision &&
      (latest.monitoring_rule_id !== observed.monitoring_rule_id ||
        latest.rule_state !== observed.rule_state))
  )
}

function activeOccurrence(occurrence: CollectionOccurrence | null) {
  return (
    occurrence?.status === 'claimed' ||
    occurrence?.batch_status === 'queued' ||
    occurrence?.batch_status === 'running'
  )
}
function shouldPoll(schedule: CollectionSchedule) {
  return (
    (schedule.enabled && schedule.available) ||
    activeOccurrence(schedule.latest_occurrence)
  )
}
export function useCollectionSchedules(beforeId?: number) {
  return useQuery({
    queryKey: [...scheduleListKey, beforeId ?? null],
    queryFn: ({ signal }) =>
      fetchCollectionSchedules(signal, { limit: SCHEDULE_PAGE_SIZE, beforeId }),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.schedules.some(shouldPoll) ? 5000 : false,
  })
}
export function useCollectionSchedule(id: number | null) {
  return useQuery({
    queryKey: scheduleDetailKey(id),
    queryFn: ({ signal }) => {
      if (id === null) throw new Error('No schedule selected')
      return fetchCollectionSchedule(id, signal)
    },
    enabled: id !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && shouldPoll(query.state.data) ? 5000 : false,
  })
}
export function useCollectionOccurrences(
  schedule: CollectionSchedule | undefined,
  beforeId?: number,
) {
  return useQuery({
    queryKey: [
      ...COLLECTION_SCHEDULES_QUERY_KEY,
      'occurrences',
      schedule?.id ?? null,
      beforeId ?? null,
    ],
    queryFn: ({ signal }) => {
      if (!schedule) throw new Error('No schedule selected')
      return fetchCollectionOccurrences(schedule.id, signal, {
        limit: SCHEDULE_PAGE_SIZE,
        beforeId,
      })
    },
    enabled: schedule !== undefined,
    retry: false,
    refetchInterval: (query) =>
      (beforeId === undefined && schedule && shouldPoll(schedule)) ||
      query.state.data?.occurrences.some(activeOccurrence)
        ? 5000
        : false,
  })
}

export async function cacheSavedSchedule(
  client: QueryClient,
  saved: CollectionSchedule,
) {
  // Fence reads started before/during a save. A late response must not undo CAS.
  await client.cancelQueries({ queryKey: COLLECTION_SCHEDULES_QUERY_KEY })
  const preferNewer = (current: CollectionSchedule | undefined) =>
    current && current.revision > saved.revision ? current : saved
  client.setQueryData<CollectionSchedule>(
    scheduleDetailKey(saved.id),
    preferNewer,
  )
  client.setQueriesData<CollectionSchedulePage>(
    { queryKey: scheduleListKey },
    (current) =>
      current
        ? {
            ...current,
            schedules: current.schedules.map((schedule) =>
              schedule.id === saved.id ? preferNewer(schedule) : schedule,
            ),
          }
        : current,
  )
  void client.invalidateQueries({ queryKey: COLLECTION_SCHEDULES_QUERY_KEY })
}
