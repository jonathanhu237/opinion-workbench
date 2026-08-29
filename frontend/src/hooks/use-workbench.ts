import { useQuery } from '@tanstack/react-query'

import { fetchWorkbench, WORKBENCH_QUERY_KEY } from '@/lib/api/workbench'

export function useWorkbench() {
  return useQuery({
    queryKey: WORKBENCH_QUERY_KEY,
    queryFn: ({ signal }) => fetchWorkbench(signal),
    retry: false,
    refetchInterval: (query) => {
      const activity = query.state.data?.activity
      return activity &&
        (activity.collection !== null ||
          activity.initial_analysis !== null ||
          activity.report !== null)
        ? 5000
        : 30_000
    },
  })
}
