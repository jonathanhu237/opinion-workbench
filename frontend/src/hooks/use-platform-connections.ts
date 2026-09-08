import { useQuery } from '@tanstack/react-query'

import {
  fetchPlatformConnections,
  PLATFORM_CONNECTIONS_QUERY_KEY,
  type PlatformConnection,
} from '@/lib/api/platform-connections'

export function isPlatformConnectionActive(connection: PlatformConnection) {
  return connection.status === 'checking'
}

export function usePlatformConnections(
  idleRefetchInterval: number | false = false,
) {
  return useQuery({
    queryKey: PLATFORM_CONNECTIONS_QUERY_KEY,
    queryFn: ({ signal }) => fetchPlatformConnections(signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.platforms.some(isPlatformConnectionActive)
        ? 1000
        : idleRefetchInterval,
  })
}
