import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { MediaSettings } from '@/routes/media-settings'
import {
  cleanMediaCache,
  fetchMediaPolicy,
  saveMediaPolicy,
} from '@/lib/api/media-cache'

vi.mock('@/lib/api/media-cache', async (original) => ({
  ...(await original<typeof import('@/lib/api/media-cache')>()),
  fetchMediaPolicy: vi.fn(),
  saveMediaPolicy: vi.fn(),
  cleanMediaCache: vi.fn(),
}))
const policy = {
  retention_days: 30,
  capacity_mib: 1024,
  revision: 0,
  reserved_bytes: 4096,
  files: 2,
  pending_files: 0,
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchMediaPolicy).mockResolvedValue(policy)
})
function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MediaSettings />
    </QueryClientProvider>,
  )
}
it('reads without cleanup, saves explicit units and explains deferred deletion', async () => {
  vi.mocked(saveMediaPolicy).mockResolvedValue({
    policy: { ...policy, retention_days: 7, capacity_mib: 512, revision: 1 },
    cleanup: { removed_files: 0, removed_bytes: 0, deferred: true },
  })
  show()
  const user = userEvent.setup()
  const retention = await screen.findByLabelText('保留期限（天）')
  expect(cleanMediaCache).not.toHaveBeenCalled()
  await user.clear(retention)
  await user.type(retention, '7')
  const capacity = screen.getByLabelText('容量上限（MiB）')
  await user.clear(capacity)
  await user.type(capacity, '512')
  await user.click(
    screen.getByRole('button', { name: '保存策略并执行安全清理' }),
  )
  expect(vi.mocked(saveMediaPolicy).mock.calls[0][0]).toEqual({
    retention_days: 7,
    capacity_mib: 512,
    expected_revision: 0,
  })
  expect(await screen.findByText(/清理暂缓/)).toBeInTheDocument()
  expect(screen.getByText(/不会删除正文、总结或报告/)).toBeInTheDocument()
})
it('runs cleanup only when explicitly requested with the displayed revision', async () => {
  vi.mocked(cleanMediaCache).mockResolvedValue({
    policy,
    cleanup: { removed_files: 0, removed_bytes: 0, deferred: false },
  })
  show()
  await userEvent.click(
    await screen.findByRole('button', { name: '按当前策略清理' }),
  )
  expect(vi.mocked(cleanMediaCache).mock.calls[0][0]).toBe(0)
  expect(saveMediaPolicy).not.toHaveBeenCalled()
})
