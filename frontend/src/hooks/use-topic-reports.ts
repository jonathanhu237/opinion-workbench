import {
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'

import {
  fetchTopicReport,
  fetchTopicReports,
  isActiveReport,
  TOPIC_REPORTS_QUERY_KEY,
  type ReportList,
  type ReportListOptions,
  type ReportRun,
} from '@/lib/api/topic-reports'

export const reportDetailKey = (id: number | null) =>
  [...TOPIC_REPORTS_QUERY_KEY, 'detail', id] as const
export const reportListKey = [...TOPIC_REPORTS_QUERY_KEY, 'list'] as const

function newestKnownReport(client: QueryClient, incoming: ReportRun) {
  const detail = client.getQueryData<ReportRun>(reportDetailKey(incoming.id))
  const listed = client
    .getQueriesData<ReportList>({ queryKey: reportListKey })
    .map(([, page]) =>
      page?.reports.find((report) => report.id === incoming.id),
    )
  // Equal revisions may contain fresher node progress; only fence older controls.
  return [detail, ...listed].reduce<ReportRun>(
    (latest, known) =>
      known && known.revision > latest.revision ? known : latest,
    incoming,
  )
}

export function useTopicReports(
  options: ReportListOptions = {},
  waitForAutomatic = false,
  enabled = true,
) {
  const client = useQueryClient()
  const key = [...reportListKey, options]
  return useQuery({
    queryKey: key,
    queryFn: async ({ signal }) => {
      const incoming = await fetchTopicReports(signal, options)
      return {
        ...incoming,
        reports: incoming.reports.map((report) =>
          newestKnownReport(client, report),
        ),
      }
    },
    enabled,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.reports.some((report) =>
        isActiveReport(report.status),
      ) ||
      (waitForAutomatic && query.state.data?.reports.length === 0)
        ? 1000
        : false,
  })
}
export function useTopicReport(id: number | null) {
  const client = useQueryClient()
  return useQuery({
    queryKey: reportDetailKey(id),
    queryFn: async ({ signal }) => {
      const incoming = await fetchTopicReport(id ?? 0, signal)
      return newestKnownReport(client, incoming)
    },
    enabled: id !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveReport(query.state.data.status)
        ? 1000
        : false,
  })
}
export async function cacheSavedReport(client: QueryClient, saved: ReportRun) {
  // A read already in flight must not undo a settled cancellation/version write.
  await client.cancelQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
  const newest = newestKnownReport(client, saved)
  client.setQueryData<ReportRun>(reportDetailKey(saved.id), newest)
  client.setQueriesData<ReportList>({ queryKey: reportListKey }, (current) =>
    current
      ? {
          ...current,
          reports: current.reports.map((report) =>
            report.id === saved.id ? newest : report,
          ),
        }
      : current,
  )
  void client.invalidateQueries({ queryKey: TOPIC_REPORTS_QUERY_KEY })
}
