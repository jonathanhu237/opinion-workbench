import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CollectionSummaryConfirmation } from '@/routes/collection-summary-confirmation'

const settings = {
  base_url: 'https://api.example.com/v1',
  model: 'test-summary-model',
  has_api_key: true,
  revision: 3,
}

describe('summary confirmation', () => {
  it('discloses the full scope and saved destination without starting on mount', async () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <CollectionSummaryConfirmation
        sourceCount={67}
        settings={settings}
        pending={false}
        error={null}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    )

    expect(screen.getByRole('dialog')).toHaveAccessibleName('生成汇总')
    expect(screen.getByRole('dialog')).toHaveAccessibleDescription(/全部 67 条/)
    expect(screen.getByText(settings.base_url)).toBeVisible()
    expect(screen.getByText(settings.model)).toBeVisible()
    expect(screen.getByText(/可能消耗 API 额度/)).toBeVisible()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(onConfirm).not.toHaveBeenCalled()

    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '开始生成' }))
    expect(onConfirm).toHaveBeenCalledExactlyOnceWith(true)
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('locks controls while submission is pending and keeps an inline error', async () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <CollectionSummaryConfirmation
        sourceCount={1}
        settings={settings}
        pending
        error="提交结果尚未确认。"
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    )

    expect(screen.getByRole('checkbox')).toHaveAttribute(
      'aria-disabled',
      'true',
    )
    expect(screen.getByRole('button', { name: '正在提交…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: '关闭' })).toBeNull()
    expect(screen.getByRole('alert')).toHaveTextContent('提交结果尚未确认。')
    await user.keyboard('{Escape}')
    expect(onConfirm).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })
})
