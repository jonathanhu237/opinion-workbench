import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AI_SETTINGS_QUERY_KEY,
  AISettingsApiError,
  fetchAISettings,
  saveAISettings,
  testAIConnection,
  type AISettings as Settings,
} from '@/lib/api/ai-settings'
import { AISettings } from '@/routes/ai-settings'

vi.mock('@/lib/api/ai-settings', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/ai-settings')>()
  return {
    ...actual,
    fetchAISettings: vi.fn(),
    saveAISettings: vi.fn(),
    testAIConnection: vi.fn(),
  }
})

const saved: Settings = {
  base_url: 'https://api.example.com/v1',
  model: 'test-model',
  has_api_key: true,
  revision: 1,
}
const empty: Settings = {
  base_url: null,
  model: null,
  has_api_key: false,
  revision: 0,
}
const key = 'fake-form-key-sentinel'
const savedKeyMask = '********************'
const fetchSettings = vi.mocked(fetchAISettings)
const saveSettings = vi.mocked(saveAISettings)
const testConnection = vi.mocked(testAIConnection)

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <AISettings />
      </QueryClientProvider>,
    ),
  }
}

describe('AI settings form', () => {
  beforeEach(() => {
    fetchSettings.mockReset().mockResolvedValue(saved)
    saveSettings.mockReset().mockResolvedValue(saved)
    testConnection.mockReset().mockResolvedValue(undefined)
  })

  it('shows loading then three labeled fields without revealing a saved key or calling the model', async () => {
    renderSettings()
    expect(screen.getByRole('status')).toHaveTextContent('正在读取 AI 配置')
    const password = await screen.findByLabelText('API Key')
    expect(password).toHaveAttribute('type', 'password')
    expect(password).toHaveAttribute('autocomplete', 'off')
    expect(password).not.toHaveAttribute('placeholder')
    expect(password).toHaveValue('')
    const mask = screen.getByText(savedKeyMask)
    expect(mask).toBeVisible()
    expect(mask).toHaveAttribute('aria-hidden', 'true')
    expect(mask).toHaveClass('text-foreground', 'pointer-events-none')
    expect(screen.getByLabelText('服务地址')).toHaveValue(saved.base_url)
    expect(screen.getByLabelText('模型名称')).toHaveValue(saved.model)
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeEnabled()
    expect(screen.getByText(/已配置，留空即可保留/)).toBeVisible()
    expect(screen.queryByText('请先保存配置')).toBeNull()
    expect(testConnection).not.toHaveBeenCalled()
    expect(saveSettings).not.toHaveBeenCalled()
  })

  it('validates initial required fields with nearby accessible errors', async () => {
    fetchSettings.mockResolvedValue(empty)
    const user = userEvent.setup()
    renderSettings()
    expect(await screen.findByLabelText('API Key')).not.toHaveAttribute(
      'placeholder',
    )
    expect(screen.queryByText(savedKeyMask)).toBeNull()
    await user.click(await screen.findByRole('button', { name: '保存' }))
    expect(
      await screen.findByText('请输入有效的 HTTPS 服务地址。'),
    ).toBeVisible()
    expect(screen.getByLabelText('API Key')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    expect(screen.getByLabelText('API Key')).toHaveAccessibleDescription(
      /首次保存或更换服务地址/,
    )
    expect(screen.getByLabelText('模型名称')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled()
    expect(saveSettings).not.toHaveBeenCalled()
  })

  it('hides saved-key text on focus or typing and restores it only on empty blur', async () => {
    const user = userEvent.setup()
    renderSettings()
    const password = await screen.findByLabelText('API Key')
    await user.click(password)
    expect(password).toHaveFocus()
    expect(password).toHaveValue('')
    expect(screen.queryByText(savedKeyMask)).toBeNull()
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeEnabled()
    await user.tab()
    expect(password).not.toHaveFocus()
    expect(screen.getByText(savedKeyMask)).toBeVisible()
    await user.type(password, key)
    expect(password).toHaveValue(key)
    expect(password).toHaveAttribute('type', 'password')
    expect(screen.queryByText(savedKeyMask)).toBeNull()
    expect(screen.getByRole('button', { name: '保存' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled()
    await user.tab()
    expect(password).not.toHaveFocus()
    expect(screen.queryByText(savedKeyMask)).toBeNull()
    await user.clear(password)
    expect(password).toHaveValue('')
    expect(password).toHaveFocus()
    expect(screen.queryByText(savedKeyMask)).toBeNull()
    await user.tab()
    expect(screen.getByText(savedKeyMask)).toBeVisible()
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeEnabled()
    expect(screen.queryByText('请先保存配置')).toBeNull()
    expect(saveSettings).not.toHaveBeenCalled()
    expect(testConnection).not.toHaveBeenCalled()
  })

  it('requires a newly entered key for an endpoint change and prevents testing dirty values', async () => {
    const user = userEvent.setup()
    renderSettings()
    const endpoint = await screen.findByLabelText('服务地址')
    await user.clear(endpoint)
    await user.type(endpoint, 'https://other.example.com/v1')
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByText(savedKeyMask)).toBeVisible()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled()
    expect(screen.getByText('请先保存配置')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(
      await screen.findByText('首次保存或更换服务地址时，请重新输入 API Key。'),
    ).toBeVisible()
    expect(saveSettings).not.toHaveBeenCalled()
    expect(testConnection).not.toHaveBeenCalled()
  })

  it('saves directly, restores the mask on reopen, and retains only non-secret query data', async () => {
    fetchSettings.mockResolvedValue(empty)
    let finish: ((value: Settings) => void) | undefined
    saveSettings.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const localWrite = vi.spyOn(Storage.prototype, 'setItem')
    const user = userEvent.setup()
    const { queryClient, unmount } = renderSettings()
    await user.type(await screen.findByLabelText('API Key'), key)
    await user.type(screen.getByLabelText('服务地址'), saved.base_url ?? '')
    await user.type(screen.getByLabelText('模型名称'), saved.model ?? '')
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(
      await screen.findByRole('button', { name: '保存中…' }),
    ).toBeDisabled()
    expect(screen.getByLabelText('API Key')).toBeDisabled()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled()
    expect(saveSettings).toHaveBeenCalledTimes(1)
    expect(saveSettings).toHaveBeenCalledWith(
      { base_url: saved.base_url, model: saved.model, api_key: key },
      expect.any(AbortSignal),
    )
    expect(queryClient.getMutationCache().getAll()).toEqual([])
    expect(JSON.stringify(queryClient.getQueryCache().getAll())).not.toContain(
      key,
    )
    fetchSettings.mockResolvedValue(saved)
    await act(async () => finish?.(saved))
    expect(await screen.findByRole('status')).toHaveTextContent('已保存。')
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByText(savedKeyMask)).toBeVisible()
    expect(queryClient.getQueryData(AI_SETTINGS_QUERY_KEY)).toEqual(saved)
    expect(queryClient.getMutationCache().getAll()).toEqual([])
    expect(localWrite).not.toHaveBeenCalled()
    expect(testConnection).not.toHaveBeenCalled()
    unmount()
    renderSettings()
    const reopenedPassword = await screen.findByLabelText('API Key')
    expect(reopenedPassword).toHaveValue('')
    expect(reopenedPassword).not.toHaveAttribute('placeholder')
    expect(screen.getByText(savedKeyMask)).toBeVisible()
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeEnabled()
    localWrite.mockRestore()
  })

  it('retains a same-endpoint key by omitting it when only model changes', async () => {
    const user = userEvent.setup()
    renderSettings()
    const model = await screen.findByLabelText('模型名称')
    expect(screen.getByText(savedKeyMask)).toBeVisible()
    await user.clear(model)
    await user.type(model, 'other-model')
    const result = { ...saved, model: 'other-model', revision: 2 }
    saveSettings.mockResolvedValue(result)
    fetchSettings.mockResolvedValue(result)
    await user.click(screen.getByRole('button', { name: '保存' }))
    await screen.findByText('已保存。')
    expect(saveSettings).toHaveBeenCalledWith(
      { base_url: saved.base_url, model: 'other-model' },
      expect.any(AbortSignal),
    )
    expect(saveSettings.mock.calls[0]?.[0]).not.toHaveProperty('api_key')
    expect(JSON.stringify(saveSettings.mock.calls[0]?.[0])).not.toContain(
      savedKeyMask,
    )
  })

  it('clears a submitted key even on failure and preserves non-secret edits', async () => {
    const user = userEvent.setup()
    saveSettings.mockRejectedValue(
      new AISettingsApiError('ai_settings_storage_unavailable', 503),
    )
    const { queryClient } = renderSettings()
    await user.type(await screen.findByLabelText('API Key'), key)
    await user.type(screen.getByLabelText('模型名称'), '-edited')
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'AI 配置暂时无法读取或保存',
    )
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByText(savedKeyMask)).toBeVisible()
    expect(screen.getByLabelText('模型名称')).toHaveValue('test-model-edited')
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled()
    expect(queryClient.getQueryData(AI_SETTINGS_QUERY_KEY)).toEqual(saved)
    expect(queryClient.getMutationCache().getAll()).toEqual([])
    expect(document.body.textContent).not.toContain(key)
  })

  it('tests only a saved revision, shows pending and truthful text-only success', async () => {
    let finish: (() => void) | undefined
    testConnection.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const user = userEvent.setup()
    renderSettings()
    await user.click(await screen.findByRole('button', { name: '测试连接' }))
    expect(
      await screen.findByRole('button', { name: '测试中…' }),
    ).toBeDisabled()
    expect(screen.getByLabelText('服务地址')).toBeDisabled()
    expect(screen.getByText(savedKeyMask)).toHaveAttribute(
      'data-disabled',
      'true',
    )
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
    expect(testConnection).toHaveBeenCalledExactlyOnceWith(
      1,
      expect.any(AbortSignal),
    )
    await act(async () => finish?.())
    expect(await screen.findByRole('status')).toHaveTextContent(
      '连接成功，仅验证文本响应。',
    )
    expect(screen.getByText(savedKeyMask)).toHaveAttribute(
      'data-disabled',
      'false',
    )
    expect(screen.getByText(/不验证图片或音视频能力/)).toBeVisible()
    expect(saveSettings).not.toHaveBeenCalled()
  })

  it('displays a sanitized failure and refreshes a stale saved revision', async () => {
    testConnection.mockRejectedValue(
      new AISettingsApiError('ai_configuration_changed', 409),
    )
    const user = userEvent.setup()
    renderSettings()
    const button = await screen.findByRole('button', { name: '测试连接' })
    fetchSettings.mockResolvedValue({ ...saved, revision: 2 })
    await user.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '配置已更新，请重新加载后再测试。',
    )
    await waitFor(() => expect(fetchSettings).toHaveBeenCalledTimes(2))
    testConnection.mockResolvedValue(undefined)
    await user.click(screen.getByRole('button', { name: '测试连接' }))
    await screen.findByText('连接成功，仅验证文本响应。')
    expect(testConnection).toHaveBeenLastCalledWith(2, expect.any(AbortSignal))
  })

  it('clears a previous connection result when editing before an invalid save', async () => {
    const user = userEvent.setup()
    renderSettings()
    await user.click(await screen.findByRole('button', { name: '测试连接' }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      '连接成功，仅验证文本响应。',
    )
    const endpoint = screen.getByLabelText('服务地址')
    await user.clear(endpoint)
    await user.type(endpoint, 'https://other.example.com/v1')
    expect(screen.queryByText('连接成功，仅验证文本响应。')).toBeNull()
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(
      await screen.findByText('首次保存或更换服务地址时，请重新输入 API Key。'),
    ).toBeVisible()
    expect(screen.queryByText('连接成功，仅验证文本响应。')).toBeNull()
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled()
    expect(saveSettings).not.toHaveBeenCalled()
    expect(testConnection).toHaveBeenCalledTimes(1)
  })

  it('offers read retry after a storage failure', async () => {
    fetchSettings.mockRejectedValueOnce(
      new AISettingsApiError('ai_settings_storage_unavailable', 503),
    )
    const user = userEvent.setup()
    renderSettings()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'AI 配置暂时无法读取或保存',
    )
    await user.click(screen.getByRole('button', { name: '重新加载' }))
    expect(await screen.findByLabelText('API Key')).toHaveValue('')
  })

  it('allows replacing a missing saved key without a successful initial read', async () => {
    fetchSettings.mockRejectedValue(
      new AISettingsApiError('ai_credentials_unavailable', 503),
    )
    const user = userEvent.setup()
    const { queryClient } = renderSettings()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'API Key 无法安全读取或保存',
    )
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled()
    await user.type(screen.getByLabelText('API Key'), key)
    await user.type(screen.getByLabelText('服务地址'), saved.base_url ?? '')
    await user.type(screen.getByLabelText('模型名称'), saved.model ?? '')
    fetchSettings.mockResolvedValue(saved)
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByRole('status')).toHaveTextContent('已保存。')
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByText(/已配置，留空即可保留/)).toBeVisible()
    expect(queryClient.getQueryData(AI_SETTINGS_QUERY_KEY)).toEqual(saved)
    expect(queryClient.getMutationCache().getAll()).toEqual([])
    expect(testConnection).not.toHaveBeenCalled()
  })

  it('aborts an in-flight submission on unmount without caching the secret', async () => {
    let finish: ((value: Settings) => void) | undefined
    saveSettings.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const user = userEvent.setup()
    const { unmount, queryClient } = renderSettings()
    await user.type(await screen.findByLabelText('API Key'), key)
    await user.click(screen.getByRole('button', { name: '保存' }))
    await screen.findByRole('button', { name: '保存中…' })
    const signal = saveSettings.mock.calls[0]?.[1]
    unmount()
    expect(signal?.aborted).toBe(true)
    await act(async () => finish?.({ ...saved, revision: 2 }))
    expect(queryClient.getQueryData(AI_SETTINGS_QUERY_KEY)).toEqual(saved)
    expect(queryClient.getMutationCache().getAll()).toEqual([])
  })
})
