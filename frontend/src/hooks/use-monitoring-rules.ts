import { useQuery } from '@tanstack/react-query'

import {
  fetchMonitoringRules,
  MONITORING_RULES_QUERY_KEY,
} from '@/lib/api/monitoring-rules'

export function useMonitoringRules() {
  return useQuery({
    queryKey: MONITORING_RULES_QUERY_KEY,
    queryFn: ({ signal }) => fetchMonitoringRules(signal),
    retry: false,
  })
}
