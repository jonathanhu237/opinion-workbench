import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resultFixture } from '@/lib/api/analysis-fixtures'
import type { AISummarySource } from '@/lib/api/ai-summaries'
import { openSearchRunResult } from '@/lib/api/search-runs'
import {
  ResultSourceLink,
  useResultSourceControls,
} from '@/routes/results-presenters'

vi.mock('@/lib/api/search-runs', async (original) => ({
  ...(await original<typeof import('@/lib/api/search-runs')>()),
  openSearchRunResult: vi.fn(),
}))

function Citation({
  source,
  number,
}: {
  source: AISummarySource
  number?: number
}) {
  const controls = useResultSourceControls()
  return (
    <p data-testid="paragraph">
      {'保存的文字 <script>alert(1)</script>'}
      <ResultSourceLink
        source={source}
        controls={controls}
        citationNumber={number}
      />
    </p>
  )
}
function renderCitation(source: AISummarySource, number?: number) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <Citation source={source} number={number} />
    </QueryClientProvider>,
  )
}

describe('saved-source citation presentation', () => {
  beforeEach(() => vi.clearAllMocks())
  it('keeps frozen citations inline with stable numbering and escaped prose', () => {
    const source = resultFixture().source
    const { container } = renderCitation(source, 101)
    const citation = screen.getByRole('link', {
      name: `原文 101 · 抖音：${source.title}`,
    })
    expect(citation).toHaveAttribute('href', source.content_url)
    expect(citation).toHaveAttribute('rel', 'noopener noreferrer')
    expect(citation).toHaveAttribute('target', '_blank')
    expect(citation).toHaveAttribute('title', source.title)
    expect(screen.getByTestId('paragraph')).toContainElement(citation)
    expect(container.querySelector('script')).toBeNull()
    expect(openSearchRunResult).not.toHaveBeenCalled()
  })
  it('preserves the ordinary saved-result source action when not a citation', () => {
    const source = resultFixture().source
    renderCitation(source)
    expect(
      screen.getByRole('link', { name: `打开原文：${source.title}` }),
    ).toHaveTextContent('打开原文')
  })
  it('opens XHS only with its frozen origin tuple and retains pending/error feedback', async () => {
    const user = userEvent.setup()
    const source: AISummarySource = {
      ...resultFixture().source,
      platform: 'xhs',
      source_run_id: 88,
      result_id: 211,
      platform_content_id: 'a'.repeat(24),
      content_url: `https://www.xiaohongshu.com/explore/${'a'.repeat(24)}`,
    }
    let reject: (error: Error) => void = () => undefined
    vi.mocked(openSearchRunResult).mockImplementationOnce(
      () =>
        new Promise((_resolve, rejectPromise) => {
          reject = rejectPromise
        }),
    )
    renderCitation(source, 211)
    const citation = screen.getByRole('button', {
      name: `原文 211 · 小红书：${source.title}`,
    })
    expect(screen.queryByRole('link')).toBeNull()
    citation.focus()
    await user.keyboard('{Enter}')
    expect(openSearchRunResult).toHaveBeenCalledWith(88, 211)
    await waitFor(() => expect(citation).toBeDisabled())
    expect(citation).toHaveAttribute('aria-busy', 'true')
    await act(async () => reject(new Error('synthetic transport failure')))
    expect(await screen.findByRole('status')).not.toHaveTextContent(
      'synthetic transport failure',
    )
    expect(citation).toBeEnabled()
  })
})
