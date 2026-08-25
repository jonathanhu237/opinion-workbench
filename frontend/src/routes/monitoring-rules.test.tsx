import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createMonitoringRule,
  deleteMonitoringRule,
  fetchMonitoringRules,
  MONITORING_RULES_QUERY_KEY,
  MonitoringRuleApiError,
  updateMonitoringRule,
  type MonitoringRule,
  type MonitoringRulesResponse,
} from '@/lib/api/monitoring-rules'
import { MonitoringRules } from '@/routes/monitoring-rules'

vi.mock('@/lib/api/monitoring-rules', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/api/monitoring-rules')>()

  return {
    ...actual,
    fetchMonitoringRules: vi.fn(),
    createMonitoringRule: vi.fn(),
    updateMonitoringRule: vi.fn(),
    deleteMonitoringRule: vi.fn(),
  }
})

const defaultRule: MonitoringRule = {
  id: 1,
  name: '龙田街道及四个社区',
  terms: ['龙田街道', '龙田社区', '老坑社区', '竹坑社区', '南布社区'],
  enabled: true,
}
const disabledRule: MonitoringRule = {
  id: 2,
  name: '道路施工',
  terms: ['施工围挡', '道路封闭'],
  enabled: false,
}

const mockedFetchRules = vi.mocked(fetchMonitoringRules)
const mockedCreateRule = vi.mocked(createMonitoringRule)
const mockedUpdateRule = vi.mocked(updateMonitoringRule)
const mockedDeleteRule = vi.mocked(deleteMonitoringRule)

function renderRules(initialData?: MonitoringRulesResponse) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  if (initialData !== undefined) {
    queryClient.setQueryData(MONITORING_RULES_QUERY_KEY, initialData)
  }

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }

  return {
    queryClient,
    ...render(<MonitoringRules />, { wrapper: Wrapper }),
  }
}

describe('monitoring rules route', () => {
  beforeEach(() => {
    mockedFetchRules.mockReset()
    mockedCreateRule.mockReset()
    mockedUpdateRule.mockReset()
    mockedDeleteRule.mockReset()
    mockedFetchRules.mockResolvedValue({ rules: [defaultRule, disabledRule] })
  })

  it('shows a stable loading state before persisted rules arrive', () => {
    mockedFetchRules.mockReturnValue(new Promise(() => undefined))

    renderRules()

    expect(screen.getByRole('status')).toHaveTextContent('正在读取监控规则…')
    expect(screen.queryByText(defaultRule.name)).toBeNull()
  })

  it('renders real rules in API order with wrapping terms and explicit states', async () => {
    renderRules()

    const list = await screen.findByRole('list', { name: '监控规则列表' })
    const articles = within(list).getAllByRole('article')
    expect(articles).toHaveLength(2)
    expect(articles[0]).toHaveTextContent(defaultRule.name)
    expect(articles[1]).toHaveTextContent(disabledRule.name)
    expect(articles[0]).toHaveTextContent('龙田街道')
    expect(articles[0]).toHaveTextContent('南布社区')
    expect(articles[0]).toHaveTextContent('已启用')
    expect(articles[1]).toHaveTextContent('已停用')
    expect(
      within(articles[0]).getByRole('button', {
        name: `编辑“${defaultRule.name}”`,
      }),
    ).toBeVisible()
    expect(
      within(articles[0]).getByRole('button', {
        name: `删除“${defaultRule.name}”`,
      }),
    ).toBeVisible()
    expect(screen.queryByText('选择平台')).toBeNull()
    expect(screen.queryByRole('button', { name: /采集|运行/ })).toBeNull()
  })

  it('recovers from an initial read failure and keeps cached rows on refetch failure', async () => {
    const user = userEvent.setup()
    mockedFetchRules
      .mockRejectedValueOnce(
        new MonitoringRuleApiError(
          '监控规则暂时无法读取或保存，请稍后重试。',
          'monitoring_rule_storage_unavailable',
          503,
        ),
      )
      .mockResolvedValueOnce({ rules: [defaultRule] })

    const { queryClient } = renderRules()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '监控规则暂时无法读取或保存，请稍后重试。',
    )
    await user.click(screen.getByRole('button', { name: '重新加载' }))
    expect(await screen.findByText(defaultRule.name)).toBeInTheDocument()

    mockedFetchRules.mockRejectedValueOnce(
      new MonitoringRuleApiError(
        '监控规则暂时无法读取或保存，请稍后重试。',
        'monitoring_rule_storage_unavailable',
        503,
      ),
    )
    await queryClient.refetchQueries({ queryKey: MONITORING_RULES_QUERY_KEY })

    expect(screen.getByText(defaultRule.name)).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '当前仍显示上次读取的内容',
    )
  })

  it('shows an actionable empty state', async () => {
    mockedFetchRules.mockResolvedValue({ rules: [] })

    renderRules()

    expect(await screen.findByText('还没有监控规则')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '新建规则' })).toHaveLength(2)
  })

  it('creates a rule from trimmed multiline terms and updates the visible cache', async () => {
    const user = userEvent.setup()
    const createdRule: MonitoringRule = {
      id: 3,
      name: '重点场所',
      terms: ['龙田学校', '坪山高铁站'],
      enabled: true,
    }
    mockedCreateRule.mockResolvedValue(createdRule)

    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const dialog = screen.getByRole('dialog', { name: '新建监控规则' })

    await user.click(within(dialog).getByRole('button', { name: '保存' }))
    expect(await within(dialog).findByText('请输入规则名称。')).toBeVisible()
    expect(within(dialog).getByText('请至少输入一个搜索词。')).toBeVisible()

    await user.type(within(dialog).getByLabelText('规则名称'), ' 重点场所 ')
    await user.type(
      within(dialog).getByLabelText('搜索词'),
      ' 龙田学校 \n\n坪山高铁站 ',
    )
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(mockedCreateRule).toHaveBeenCalledWith({
        name: '重点场所',
        terms: ['龙田学校', '坪山高铁站'],
        enabled: true,
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByText(createdRule.name)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      `已新建“${createdRule.name}”。`,
    )
  })

  it('rejects duplicate pasted terms before sending a request', async () => {
    const user = userEvent.setup()

    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const dialog = screen.getByRole('dialog', { name: '新建监控规则' })
    await user.type(within(dialog).getByLabelText('规则名称'), '重复词测试')
    await user.type(
      within(dialog).getByLabelText('搜索词'),
      '龙田街道\n  龙田街道  ',
    )
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    expect(
      await within(dialog).findByText('同一条规则中不能包含重复搜索词。'),
    ).toBeVisible()
    expect(mockedCreateRule).not.toHaveBeenCalled()
  })

  it('edits the full rule while preserving its enabled state', async () => {
    const user = userEvent.setup()
    const savedRule = {
      ...disabledRule,
      name: '道路施工与封闭',
      terms: ['道路施工', '道路封闭'],
    }
    mockedUpdateRule.mockResolvedValue(savedRule)

    renderRules()
    const editButton = await screen.findByRole('button', {
      name: `编辑“${disabledRule.name}”`,
    })
    await user.click(editButton)
    const dialog = screen.getByRole('dialog', { name: '编辑监控规则' })
    const nameInput = within(dialog).getByLabelText('规则名称')
    const termsInput = within(dialog).getByLabelText('搜索词')
    expect(nameInput).toHaveValue(disabledRule.name)
    expect(termsInput).toHaveValue(disabledRule.terms.join('\n'))

    await user.clear(nameInput)
    await user.type(nameInput, savedRule.name)
    await user.clear(termsInput)
    await user.type(termsInput, savedRule.terms.join('\n'))
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(mockedUpdateRule).toHaveBeenCalledWith(disabledRule.id, {
        name: savedRule.name,
        terms: savedRule.terms,
        enabled: false,
      }),
    )
    expect(await screen.findByText(savedRule.name)).toBeInTheDocument()
    expect(screen.getByText('已停用')).toBeInTheDocument()
  })

  it('keeps backend name conflicts beside the name field', async () => {
    const user = userEvent.setup()
    mockedCreateRule.mockRejectedValue(
      new MonitoringRuleApiError(
        '已经存在同名的监控规则。',
        'monitoring_rule_name_conflict',
        409,
      ),
    )

    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const dialog = screen.getByRole('dialog', { name: '新建监控规则' })
    await user.type(within(dialog).getByLabelText('规则名称'), defaultRule.name)
    await user.type(within(dialog).getByLabelText('搜索词'), '龙田街道')
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    expect(
      await within(dialog).findByText('已经存在同名的监控规则。'),
    ).toBeVisible()
    await waitFor(() =>
      expect(within(dialog).getByLabelText('规则名称')).toHaveFocus(),
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('keeps backend-normalized duplicate terms beside the terms field', async () => {
    const user = userEvent.setup()
    mockedCreateRule.mockRejectedValue(
      new MonitoringRuleApiError(
        '同一条监控规则中不能包含重复搜索词。',
        'duplicate_monitoring_rule_term',
        422,
      ),
    )

    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const dialog = screen.getByRole('dialog', { name: '新建监控规则' })
    await user.type(within(dialog).getByLabelText('规则名称'), '后端归一化测试')
    await user.type(within(dialog).getByLabelText('搜索词'), 'Straße\nSTRASSE')
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    expect(mockedCreateRule).toHaveBeenCalled()
    expect(
      await within(dialog).findByText('同一条监控规则中不能包含重复搜索词。'),
    ).toBeVisible()
    await waitFor(() =>
      expect(within(dialog).getByLabelText('搜索词')).toHaveFocus(),
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('updates only the toggled row after a successful full replacement', async () => {
    const user = userEvent.setup()
    let resolveUpdate: ((rule: MonitoringRule) => void) | undefined
    mockedUpdateRule.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve
      }),
    )

    renderRules()
    const toggle = await screen.findByRole('switch', {
      name: `停用“${defaultRule.name}”`,
    })
    await user.click(toggle)

    expect(mockedUpdateRule).toHaveBeenCalledWith(defaultRule.id, {
      name: defaultRule.name,
      terms: defaultRule.terms,
      enabled: false,
    })
    const defaultArticle = screen.getByText(defaultRule.name).closest('article')
    if (defaultArticle === null) {
      throw new Error('Default rule row was not rendered')
    }
    expect(within(defaultArticle).getByText('正在更新…')).toBeInTheDocument()
    expect(
      within(defaultArticle).getByRole('button', {
        name: `编辑“${defaultRule.name}”`,
      }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: `编辑“${disabledRule.name}”` }),
    ).toBeEnabled()

    resolveUpdate?.({ ...defaultRule, enabled: false })
    expect(
      await screen.findByRole('switch', {
        name: `启用“${defaultRule.name}”`,
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByText('已停用')).toHaveLength(2)
  })

  it('keeps the server state and shows a row error when toggling fails', async () => {
    const user = userEvent.setup()
    mockedUpdateRule.mockRejectedValue(
      new MonitoringRuleApiError(
        '监控规则暂时无法读取或保存，请稍后重试。',
        'monitoring_rule_storage_unavailable',
        503,
      ),
    )

    renderRules()
    await user.click(
      await screen.findByRole('switch', {
        name: `停用“${defaultRule.name}”`,
      }),
    )

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('监控规则暂时无法读取或保存')
    expect(
      screen.getByText(defaultRule.name).closest('article'),
    ).toHaveTextContent('已启用')
  })

  it('keeps delete confirmation open after failure and removes only after success', async () => {
    const user = userEvent.setup()
    mockedDeleteRule
      .mockRejectedValueOnce(
        new MonitoringRuleApiError(
          '监控规则暂时无法读取或保存，请稍后重试。',
          'monitoring_rule_storage_unavailable',
          503,
        ),
      )
      .mockResolvedValueOnce(undefined)

    renderRules()
    const deleteButton = await screen.findByRole('button', {
      name: `删除“${defaultRule.name}”`,
    })
    await user.click(deleteButton)
    let dialog = screen.getByRole('alertdialog', {
      name: `删除“${defaultRule.name}”？`,
    })
    expect(within(dialog).getByText('删除后无法恢复。')).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: '取消' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())

    await user.click(deleteButton)
    dialog = screen.getByRole('alertdialog', {
      name: `删除“${defaultRule.name}”？`,
    })
    await user.click(within(dialog).getByRole('button', { name: '删除' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      '监控规则暂时无法读取或保存',
    )
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: '删除' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(screen.queryByText(defaultRule.name)).toBeNull()
    expect(screen.getByText(disabledRule.name)).toBeInTheDocument()
  })
})
