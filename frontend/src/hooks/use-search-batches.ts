import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import {
  fetchSearchBatch,
  fetchSearchBatchAttempts,
  fetchSearchBatchResults,
  fetchSearchBatches,
  isActiveSearchBatch,
  SEARCH_BATCHES_QUERY_KEY,
} from '@/lib/api/search-batches'
import type { SearchResultFilter } from '@/lib/api/search-runs'

export function useSearchBatchResults(
  batchId: number | null,
  position: number | null,
  kind: SearchResultFilter,
  offset: number,
  active: boolean,
) {
  return useQuery({
    queryKey: [
      ...SEARCH_BATCHES_QUERY_KEY,
      batchId,
      'items',
      position,
      'results',
      kind,
      offset,
    ],
    queryFn: ({ signal }) =>
      fetchSearchBatchResults(
        batchId ?? 0,
        position ?? 0,
        kind,
        offset,
        signal,
      ),
    enabled: batchId !== null && position !== null,
    retry: false,
    refetchInterval: active ? 1000 : false,
  })
}

export function useSearchBatches() {
  const query = useInfiniteQuery({
    queryKey: SEARCH_BATCHES_QUERY_KEY,
    queryFn: ({ signal, pageParam }) =>
      fetchSearchBatches(
        signal,
        pageParam === null ? {} : { beforeId: pageParam },
      ),
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) => lastPage.next_before_id ?? undefined,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) =>
        page.batches.some((batch) => isActiveSearchBatch(batch.status)),
      )
        ? 1000
        : false,
  })

  return {
    ...query,
    data: query.data
      ? {
          batches: query.data.pages.flatMap((page) => page.batches),
          next_before_id: query.data.pages.at(-1)?.next_before_id ?? null,
        }
      : undefined,
  }
}

export function useSearchBatch(batchId: number | null) {
  return useQuery({
    queryKey: [...SEARCH_BATCHES_QUERY_KEY, batchId],
    queryFn: ({ signal }) => fetchSearchBatch(batchId ?? 0, signal),
    enabled: batchId !== null,
    retry: false,
    refetchInterval: (query) =>
      query.state.data && isActiveSearchBatch(query.state.data.status)
        ? 1000
        : false,
  })
}

export function useSearchBatchAttempts(
  batchId: number | null,
  position: number | null,
) {
  return useQuery({
    queryKey: [
      ...SEARCH_BATCHES_QUERY_KEY,
      batchId,
      'items',
      position,
      'attempts',
    ],
    queryFn: ({ signal }) =>
      fetchSearchBatchAttempts(batchId ?? 0, position ?? 0, signal),
    enabled: batchId !== null && position !== null,
    retry: false,
  })
}
