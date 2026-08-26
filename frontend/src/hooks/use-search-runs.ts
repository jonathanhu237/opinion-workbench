import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import {
  fetchSearchRun,
  fetchSearchRunResults,
  fetchSearchRuns,
  isActiveSearchRun,
  SEARCH_RUNS_QUERY_KEY,
  type SearchResultFilter,
} from '@/lib/api/search-runs'

export function useSearchRuns() {
  const query = useInfiniteQuery({
    queryKey: [...SEARCH_RUNS_QUERY_KEY, 'standalone'],
    queryFn: ({ signal, pageParam }) =>
      fetchSearchRuns(
        signal,
        pageParam === null
          ? { scope: 'standalone' }
          : { beforeId: pageParam, scope: 'standalone' },
      ),
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) => lastPage.next_before_id ?? undefined,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.runs.some((run) => isActiveSearchRun(run.status)),
      )
        ? 1000
        : false,
  })

  return {
    ...query,
    data: query.data
      ? {
          runs: query.data.pages.flatMap((page) => page.runs),
          next_before_id: query.data.pages.at(-1)?.next_before_id ?? null,
        }
      : undefined,
  }
}

export function useSearchRun(runId: number | null) {
  return useQuery({
    queryKey: [...SEARCH_RUNS_QUERY_KEY, runId],
    queryFn: ({ signal }) => fetchSearchRun(runId ?? 0, signal),
    enabled: runId !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveSearchRun(query.state.data.status)
        ? 1000
        : false,
  })
}

export function useSearchRunResults(
  runId: number | null,
  filter: SearchResultFilter,
  active: boolean,
  offset = 0,
) {
  return useQuery({
    queryKey: [...SEARCH_RUNS_QUERY_KEY, runId, 'results', filter, offset],
    queryFn: ({ signal }) =>
      fetchSearchRunResults(runId ?? 0, filter, signal, { offset }),
    enabled: runId !== null,
    retry: false,
    refetchInterval: active ? 1000 : false,
  })
}
