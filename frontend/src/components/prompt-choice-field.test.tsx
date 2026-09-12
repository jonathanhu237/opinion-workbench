import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import { PromptChoiceField } from '@/components/prompt-choice-field'
import type { PromptChoice } from '@/lib/api/analysis-settings'

function PromptChoiceHarness() {
  const [value, setValue] = useState<PromptChoice>({ mode: 'default' })
  return (
    <PromptChoiceField
      id="prompt"
      label="总结提示词"
      description="每条来源的初步理解。"
      value={value}
      onChange={setValue}
      defaultInstructions="系统默认的完整模板。"
    />
  )
}

describe('PromptChoiceField', () => {
  it('previews the real default and copies it when custom mode is selected', async () => {
    const user = userEvent.setup()
    render(<PromptChoiceHarness />)

    const customChoice = screen.getByRole('checkbox', {
      name: '使用本任务自定义指令',
    })
    expect(customChoice).not.toBeChecked()
    expect(screen.getByRole('note')).toHaveTextContent('系统默认的完整模板。')
    await user.click(customChoice)

    expect(customChoice).toBeChecked()
    expect(screen.getByRole('textbox')).toHaveValue('系统默认的完整模板。')
    await user.clear(screen.getByRole('textbox'))
    await user.type(screen.getByRole('textbox'), '保留我在本次表单中的草稿。')
    await user.click(customChoice)
    expect(screen.queryByRole('textbox')).toBeNull()
    await user.click(customChoice)
    expect(screen.getByRole('textbox')).toHaveValue(
      '保留我在本次表单中的草稿。',
    )
  })
})
