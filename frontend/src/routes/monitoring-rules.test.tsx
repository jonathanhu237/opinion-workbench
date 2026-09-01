import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
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
  monitoring_objects: [
    '龙田街道',
    '龙田社区',
    '老坑社区',
    '竹坑社区',
    '南布社区',
  ],
  issue_keywords: [],
  terms: ['龙田街道', '龙田社区', '老坑社区', '竹坑社区', '南布社区'],
  enabled: true,
}
const disabledRule: MonitoringRule = {
  id: 2,
  name: '道路施工',
  monitoring_objects: ['施工围挡', '道路封闭'],
  issue_keywords: [],
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
      '页面暂时保留之前显示的内容',
    )
  })

  it('shows an actionable empty state', async () => {
    mockedFetchRules.mockResolvedValue({ rules: [] })

    renderRules()

    expect(await screen.findByText('还没有监控规则')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '新建规则' })).toHaveLength(2)
  })

  it('shows numbered three-line placeholders without filling or saving the inputs', async () => {
    const user = userEvent.setup()

    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const dialog = screen.getByRole('dialog', { name: '新建监控规则' })
    const objects = within(dialog).getByLabelText('监控对象')
    const issues = within(dialog).getByLabelText('舆情关键词（选填）')

    expect(objects).toHaveAttribute('placeholder', '对象 1\n对象 2\n对象 3')
    expect(issues).toHaveAttribute(
      'placeholder',
      '关键词 1\n关键词 2\n关键词 3',
    )
    expect(objects).toHaveValue('')
    expect(issues).toHaveValue('')
    expect(within(dialog).getByText('生成的搜索词 · 共 0 个')).toBeVisible()
    expect(mockedCreateRule).not.toHaveBeenCalled()
    expect(mockedUpdateRule).not.toHaveBeenCalled()
  })

  it('creates a rule from trimmed multiline terms and updates the visible cache', async () => {
    const user = userEvent.setup()
    const createdRule: MonitoringRule = {
      id: 3,
      name: '重点场所',
      monitoring_objects: ['龙田学校', '坪山高铁站'],
      issue_keywords: [],
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
    expect(within(dialog).getByText('请至少输入一个监控对象。')).toBeVisible()

    await user.type(within(dialog).getByLabelText('规则名称'), ' 重点场所 ')
    await user.type(
      within(dialog).getByLabelText('监控对象'),
      ' 龙田学校 \n\n坪山高铁站 ',
    )
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(mockedCreateRule).toHaveBeenCalledWith({
        name: '重点场所',
        monitoring_objects: ['龙田学校', '坪山高铁站'],
        issue_keywords: [],
        enabled: true,
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByText(createdRule.name)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      `已新建“${createdRule.name}”。`,
    )
  })

  it('uses the backend whitespace contract for names, inputs, preview and saved payloads', async () => {
    const user = userEvent.setup()
    mockedCreateRule.mockReturnValue(new Promise(() => undefined))
    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    fireEvent.change(screen.getByLabelText('规则名称'), {
      target: { value: '\u0085\ufeff旧名称\ufeff\u001c' },
    })
    fireEvent.change(screen.getByLabelText('监控对象'), {
      target: { value: '\u0085A B\u001f\n\ufeff完整短语' },
    })
    fireEvent.change(screen.getByLabelText('舆情关键词（选填）'), {
      target: { value: '\u0085问题\u001c' },
    })
    expect(
      within(screen.getByRole('region', { name: '生成的搜索词预览' }))
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['A B 问题', '\ufeff完整短语 问题'])
    await user.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() =>
      expect(mockedCreateRule).toHaveBeenCalledWith({
        name: '\ufeff旧名称\ufeff',
        monitoring_objects: ['A B', '\ufeff完整短语'],
        issue_keywords: ['问题'],
        enabled: true,
      }),
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
      within(dialog).getByLabelText('监控对象'),
      '龙田街道\n  龙田街道  ',
    )
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    expect(
      await within(dialog).findByText('监控对象不能重复，请检查后重试。'),
    ).toBeVisible()
    expect(mockedCreateRule).not.toHaveBeenCalled()
  })

  it('previews combinations without requests, saves both groups, and reloads them for editing and toggling', async () => {
    const user = userEvent.setup()
    const composed: MonitoringRule = {
      id: 3,
      name: '组合规则',
      monitoring_objects: ['甲  社区', '乙社区'],
      issue_keywords: ['噪音', '积水'],
      terms: ['甲  社区 噪音', '甲  社区 积水', '乙社区 噪音', '乙社区 积水'],
      enabled: true,
    }
    mockedCreateRule.mockResolvedValue(composed)
    mockedUpdateRule.mockResolvedValue({ ...composed, enabled: false })
    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const dialog = screen.getByRole('dialog')
    await user.type(within(dialog).getByLabelText('规则名称'), composed.name)
    await user.type(
      within(dialog).getByLabelText('监控对象'),
      ' 甲  社区 \n乙社区',
    )
    await user.type(
      within(dialog).getByLabelText('舆情关键词（选填）'),
      '噪音\n积水',
    )
    const preview = within(dialog).getByRole('region', {
      name: '生成的搜索词预览',
    })
    expect(
      within(preview)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(composed.terms)
    expect(within(dialog).getByText('生成的搜索词 · 共 4 个')).toBeVisible()
    await user.tab()
    expect(preview).toHaveFocus()
    expect(mockedFetchRules).toHaveBeenCalledTimes(1)
    expect(mockedCreateRule).not.toHaveBeenCalled()
    expect(mockedUpdateRule).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: '保存' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(mockedCreateRule).toHaveBeenCalledWith({
      name: composed.name,
      monitoring_objects: composed.monitoring_objects,
      issue_keywords: composed.issue_keywords,
      enabled: true,
    })
    await user.click(
      screen.getByRole('button', { name: `编辑“${composed.name}”` }),
    )
    expect(screen.getByLabelText('监控对象')).toHaveValue(
      composed.monitoring_objects.join('\n'),
    )
    expect(screen.getByLabelText('舆情关键词（选填）')).toHaveValue(
      composed.issue_keywords.join('\n'),
    )
    await user.click(screen.getByRole('button', { name: '取消' }))
    await user.click(
      screen.getByRole('switch', { name: `停用“${composed.name}”` }),
    )
    await waitFor(() =>
      expect(mockedUpdateRule).toHaveBeenCalledWith(composed.id, {
        name: composed.name,
        monitoring_objects: composed.monitoring_objects,
        issue_keywords: composed.issue_keywords,
        enabled: false,
      }),
    )
  })

  it('treats a blank optional textarea as object-only search, preserving spaces and pending fields', async () => {
    const user = userEvent.setup()
    mockedCreateRule.mockReturnValue(new Promise(() => undefined))
    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    await user.type(screen.getByLabelText('规则名称'), '完整短语')
    await user.type(screen.getByLabelText('监控对象'), ' A  B \n旧 完整查询 ')
    await user.type(screen.getByLabelText('舆情关键词（选填）'), ' \n\n ')
    expect(
      within(screen.getByRole('region', { name: '生成的搜索词预览' }))
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['A  B', '旧 完整查询'])
    await user.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() =>
      expect(mockedCreateRule).toHaveBeenCalledWith({
        name: '完整短语',
        monitoring_objects: ['A  B', '旧 完整查询'],
        issue_keywords: [],
        enabled: true,
      }),
    )
    expect(screen.getByLabelText('监控对象')).toBeDisabled()
    expect(screen.getByLabelText('舆情关键词（选填）')).toBeDisabled()
    expect(screen.getByRole('button', { name: '保存中…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled()
  })

  it.each([20, 21, 100, 101])(
    'previews the %i-query boundary and preserves separate save/execution limits',
    async (count) => {
      const user = userEvent.setup()
      mockedCreateRule.mockReturnValue(new Promise(() => undefined))
      renderRules()
      await screen.findByText(defaultRule.name)
      await user.click(screen.getByRole('button', { name: '新建规则' }))
      fireEvent.change(screen.getByLabelText('规则名称'), {
        target: { value: '数量边界' },
      })
      fireEvent.change(screen.getByLabelText('监控对象'), {
        target: { value: '对象' },
      })
      fireEvent.change(screen.getByLabelText('舆情关键词（选填）'), {
        target: {
          value: Array.from(
            { length: count },
            (_, index) => `问题${index}`,
          ).join('\n'),
        },
      })
      expect(screen.getByText(`生成的搜索词 · 共 ${count} 个`)).toBeVisible()
      if (count <= 100) {
        expect(
          within(
            screen.getByRole('region', { name: '生成的搜索词预览' }),
          ).getAllByRole('listitem'),
        ).toHaveLength(count)
      }
      expect(screen.queryByText(/可保存，但每个平台一次最多采集/)).toBe(
        count > 20 && count <= 100
          ? screen.getByText(/可保存，但每个平台一次最多采集/)
          : null,
      )
      await user.click(screen.getByRole('button', { name: '保存' }))
      if (count > 100) {
        expect(mockedCreateRule).not.toHaveBeenCalled()
        expect(screen.getByLabelText('舆情关键词（选填）')).toHaveAttribute(
          'aria-invalid',
          'true',
        )
        await waitFor(() =>
          expect(screen.getByLabelText('舆情关键词（选填）')).toHaveFocus(),
        )
        expect(
          screen.queryByRole('region', { name: '生成的搜索词预览' }),
        ).toBeNull()
      } else {
        await waitFor(() => expect(mockedCreateRule).toHaveBeenCalledTimes(1))
      }
    },
  )

  it.each([
    ['A\nA B', 'B C\nC', '生成的搜索词不能重复，请调整监控对象或舆情关键词。'],
    ['A', 'Ｂ\nb', '舆情关键词不能重复，请检查后重试。'],
    [
      'A'.repeat(99),
      'B',
      '生成的搜索词不能超过 100 个字符，请缩短监控对象或舆情关键词。',
    ],
  ])(
    'rejects invalid combinations beside the issue field',
    async (objects, issues, message) => {
      const user = userEvent.setup()
      renderRules()
      await screen.findByText(defaultRule.name)
      await user.click(screen.getByRole('button', { name: '新建规则' }))
      fireEvent.change(screen.getByLabelText('规则名称'), {
        target: { value: '组合校验' },
      })
      fireEvent.change(screen.getByLabelText('监控对象'), {
        target: { value: objects },
      })
      fireEvent.change(screen.getByLabelText('舆情关键词（选填）'), {
        target: { value: issues },
      })
      await user.click(screen.getByRole('button', { name: '保存' }))
      expect(await screen.findByText(message)).toBeVisible()
      expect(screen.getByLabelText('舆情关键词（选填）')).toHaveAttribute(
        'aria-describedby',
        'rule-issues-description rule-issues-error',
      )
      await waitFor(() =>
        expect(screen.getByLabelText('舆情关键词（选填）')).toHaveFocus(),
      )
      expect(mockedCreateRule).not.toHaveBeenCalled()
    },
  )

  it('edits the full rule while preserving its enabled state', async () => {
    const user = userEvent.setup()
    const savedRule = {
      ...disabledRule,
      name: '道路施工与封闭',
      monitoring_objects: ['道路施工', '道路封闭'],
      issue_keywords: [],
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
    const termsInput = within(dialog).getByLabelText('监控对象')
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
        monitoring_objects: savedRule.monitoring_objects,
        issue_keywords: savedRule.issue_keywords,
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
    await user.type(within(dialog).getByLabelText('监控对象'), '龙田街道')
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
        '监控对象、舆情关键词或生成的搜索词存在重复，请检查。',
        'duplicate_monitoring_rule_term',
        422,
      ),
    )

    renderRules()
    await screen.findByText(defaultRule.name)
    await user.click(screen.getByRole('button', { name: '新建规则' }))
    const dialog = screen.getByRole('dialog', { name: '新建监控规则' })
    await user.type(within(dialog).getByLabelText('规则名称'), '后端归一化测试')
    await user.type(
      within(dialog).getByLabelText('监控对象'),
      'Straße\nSTRASSE',
    )
    await user.click(within(dialog).getByRole('button', { name: '保存' }))

    expect(mockedCreateRule).toHaveBeenCalled()
    expect(
      await within(dialog).findByText(
        '监控对象、舆情关键词或生成的搜索词存在重复，请检查。',
      ),
    ).toBeVisible()
    await waitFor(() =>
      expect(within(dialog).getByLabelText('监控对象')).toHaveFocus(),
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
      monitoring_objects: defaultRule.monitoring_objects,
      issue_keywords: defaultRule.issue_keywords,
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
