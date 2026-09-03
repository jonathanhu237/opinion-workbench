import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { OriginalMediaCache } from '@/routes/original-media-cache'
import { cachedMediaList } from '@/lib/api/media-cache'

afterEach(() => vi.unstubAllGlobals())

it('checks originals only on request and distinguishes historical acquisition from local retention', async () => {
  const items = [
    { position: 0, kind: 'image', state: 'cached', byte_size: 68 },
    { position: 1, kind: 'video', state: 'cleared', byte_size: null },
  ]
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ items }), { status: 200 }))
  vi.stubGlobal('fetch', fetch)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <OriginalMediaCache attemptId={42} />
    </QueryClientProvider>,
  )
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '检查本地原媒体' }))
  expect(await screen.findByText(/原文件仍在本地/)).toBeInTheDocument()
  expect(screen.getByText(/原文件已按策略清理/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '打开本地图片' })).toHaveAttribute(
    'href',
    '/api/v1/content-analyses/42/media/0',
  )
  expect(
    screen.queryByRole('link', { name: '打开本地视频' }),
  ).not.toBeInTheDocument()
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/content-analyses/42/media-cache')
})

it('rejects a cached flag without actual size and duplicated media positions', () => {
  const asset = { position: 0, kind: 'image', state: 'cached', byte_size: null }
  expect(cachedMediaList.safeParse({ items: [asset] }).success).toBe(false)
  const ready = { ...asset, byte_size: 68 }
  expect(cachedMediaList.safeParse({ items: [ready, ready] }).success).toBe(
    false,
  )
})
