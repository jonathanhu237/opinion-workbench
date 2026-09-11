import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  fetchPlatformAccessSettings,
  PLATFORM_ACCESS_QUERY_KEY,
  savePlatformAccessSettings,
  type PlatformAccessIntervals,
} from '@/lib/api/platform-access'

export function usePlatformAccessSettings() {
  return useQuery({
    queryKey: PLATFORM_ACCESS_QUERY_KEY,
    queryFn: ({ signal }) => fetchPlatformAccessSettings(signal),
    retry: false,
  })
}

export function useSavePlatformAccessSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: savePlatformAccessSettings,
    retry: false,
    onSuccess: (value) => {
      queryClient.setQueryData(PLATFORM_ACCESS_QUERY_KEY, value)
    },
  })
}

export function intervalValues(
  value: PlatformAccessIntervals | undefined,
): PlatformAccessIntervals {
  return (
    value ?? {
      wb: 5,
      dy: 5,
      ks: 5,
      xhs: 5,
      toutiao: 5,
    }
  )
}
