import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { resultFixture } from '@/lib/api/analysis-fixtures'
import type { AISummarySource } from '@/lib/api/ai-summaries'
import { ResultSourceLink } from '@/routes/results-presenters'

function Citation({
  source,
  number,
}: {
  source: AISummarySource
  number?: number
}) {
  return (
    <p data-testid="paragraph">
      {'保存的文字 <script>alert(1)</script>'}
      <ResultSourceLink source={source} citationNumber={number} />
    </p>
  )
}
function renderCitation(source: AISummarySource, number?: number) {
  return render(<Citation source={source} number={number} />)
}

describe('saved-source citation presentation', () => {
  it('keeps frozen citations inline with stable numbering and escaped prose', () => {
    const source = resultFixture().source
    const { container } = renderCitation(source, 101)
    const citation = screen.getByRole('link', {
      name: `原文 101 · 微博：${source.title}`,
    })
    expect(citation).toHaveAttribute('href', source.content_url)
    expect(citation).toHaveAttribute('rel', 'noopener noreferrer')
    expect(citation).toHaveAttribute('target', '_blank')
    expect(citation).toHaveAttribute('title', source.title)
    expect(screen.getByTestId('paragraph')).toContainElement(citation)
    expect(container.querySelector('script')).toBeNull()
  })
  it('preserves the ordinary saved-result source action when not a citation', () => {
    const source = resultFixture().source
    renderCitation(source)
    expect(
      screen.getByRole('link', { name: `打开原文：${source.title}` }),
    ).toHaveTextContent('打开原文')
  })
  it('keeps the stored Weibo source link safe and stable', () => {
    const source: AISummarySource = {
      ...resultFixture().source,
      platform: 'wb',
      source_run_id: 88,
      result_id: 211,
      platform_content_id: '5012345678901234',
      content_url: 'https://m.weibo.cn/detail/5012345678901234',
    }
    renderCitation(source, 211)
    const citation = screen.getByRole('link', {
      name: `原文 211 · 微博：${source.title}`,
    })
    expect(citation).toHaveAttribute('href', source.content_url)
  })
})
