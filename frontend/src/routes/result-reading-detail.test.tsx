import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

import {
  analysisAttemptFixture,
  resultFixture,
} from '@/lib/api/analysis-fixtures'
import { fetchResultAnalyses } from '@/lib/api/content-analyses'
import { fetchResult } from '@/lib/api/results'
import { ResultReadingDetail } from '@/routes/result-reading-detail'

vi.mock('@/lib/api/results', async (original) => ({
  ...(await original<typeof import('@/lib/api/results')>()),
  fetchResult: vi.fn(),
}))
vi.mock('@/lib/api/content-analyses', async (original) => ({
  ...(await original<typeof import('@/lib/api/content-analyses')>()),
  fetchResultAnalyses: vi.fn(),
}))

function show() {
  const close = vi.fn()
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ResultReadingDetail resultId={11} onClose={close} />
    </QueryClientProvider>,
  )
  return close
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchResult).mockResolvedValue(resultFixture())
})

it('shows only saved original and latest successful summary, paging past failures', async () => {
  vi.mocked(fetchResultAnalyses)
    .mockResolvedValueOnce({
      items: Array.from({ length: 20 }, (_, index) =>
        analysisAttemptFixture({
          id: 100 - index,
          status: 'failed',
          output: null,
        }),
      ),
      total: 21,
      limit: 20,
      offset: 0,
    })
    .mockResolvedValueOnce({
      items: [analysisAttemptFixture()],
      total: 21,
      limit: 20,
      offset: 20,
    })
  const close = show()
  expect(
    await screen.findByText('发布者称一处道路积水，实际地点未确认。'),
  ).toBeVisible()
  expect(
    screen.getByText('完整保存的合成正文，未把来源陈述当成事实。'),
  ).toBeVisible()
  expect(fetchResultAnalyses).toHaveBeenLastCalledWith(
    11,
    expect.any(AbortSignal),
    20,
  )
  expect(
    screen.queryByText(/提示词|处理历史|第 21 次分析|来源与单条总结/),
  ).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: /打开原文/ })).toHaveAttribute(
    'target',
    '_blank',
  )
  await userEvent.click(screen.getByRole('button', { name: '返回选材' }))
  expect(close).toHaveBeenCalledOnce()
})

it('shows a clear empty summary and labels snippet-only original', async () => {
  vi.mocked(fetchResultAnalyses).mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  })
  show()
  expect(await screen.findByText('暂无总结')).toBeVisible()
  expect(
    screen.getByText('仅保存了部分正文，完整内容请查看原文。'),
  ).toBeVisible()
})

it('does not turn a request failure into an empty summary and supports retry', async () => {
  vi.mocked(fetchResultAnalyses)
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({
      items: [analysisAttemptFixture()],
      total: 1,
      limit: 20,
      offset: 0,
    })
  show()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('总结读取失败')
  expect(screen.queryByText('暂无总结')).not.toBeInTheDocument()
  await userEvent.click(within(alert).getByRole('button', { name: '重试' }))
  expect(
    await screen.findByText('发布者称一处道路积水，实际地点未确认。'),
  ).toBeVisible()
})
