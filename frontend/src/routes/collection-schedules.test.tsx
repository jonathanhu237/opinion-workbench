import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cacheSavedSchedule,
  scheduleConfigurationChanged,
  scheduleDetailKey,
  scheduleListKey,
} from '@/hooks/use-collection-schedules'
import {
  COLLECTION_SCHEDULES_QUERY_KEY,
  CollectionScheduleApiError,
  createCollectionSchedule,
  fetchCollectionOccurrences,
  fetchCollectionSchedule,
  fetchCollectionSchedules,
  updateCollectionSchedule,
  type CollectionSchedule,
  type CollectionSchedulePage,
} from '@/lib/api/collection-schedules'
import {
  occurrenceFixture,
  scheduleFixture,
} from '@/lib/api/collection-schedules.fixtures'
import {
  fetchMonitoringRules,
  type MonitoringRule,
} from '@/lib/api/monitoring-rules'
import { CollectionSchedules } from '@/routes/collection-schedules'
import { scheduleFormSchema } from '@/routes/collection-schedule-editor'

vi.mock('@/lib/api/collection-schedules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/collection-schedules')>()),
  createCollectionSchedule: vi.fn(),
  fetchCollectionOccurrences: vi.fn(),
  fetchCollectionSchedule: vi.fn(),
  fetchCollectionSchedules: vi.fn(),
  updateCollectionSchedule: vi.fn(),
}))
vi.mock('@/lib/api/monitoring-rules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/monitoring-rules')>()),
  fetchMonitoringRules: vi.fn(),
}))

const rule: MonitoringRule = {
  id: 7,
  name: '社区公共事务',
  monitoring_objects: ['社区'],
  issue_keywords: [],
  terms: ['社区'],
  enabled: true,
}
const otherRule: MonitoringRule = { ...rule, id: 8, name: '其他社区' }
const listMock = vi.mocked(fetchCollectionSchedules)
const detailMock = vi.mocked(fetchCollectionSchedule)
const historyMock = vi.mocked(fetchCollectionOccurrences)
const createMock = vi.mocked(createCollectionSchedule)
const updateMock = vi.mocked(updateCollectionSchedule)
let current: CollectionSchedule
function page() {
  return { schedules: [current], next_before_id: null }
}
function deferred<T>() {
  let resolve: (value: T) => void = () => {
    throw new Error('not initialized')
  }
  const promise = new Promise<T>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}
function renderSchedules(entry = '/collection-runs') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [{ path: '/collection-runs', element: <CollectionSchedules /> }],
    { initialEntries: [entry] },
  )
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { client, router }
}
async function openCreate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '新建定时采集' }))
  const dialog = screen.getByRole('dialog', { name: '新建定时采集' })
  return within(dialog)
}
async function chooseRule(user: ReturnType<typeof userEvent.setup>) {
  screen.getByRole('combobox', { name: '定时采集的监控规则' }).focus()
  await user.keyboard('{ArrowDown}')
  await user.click(
    await screen.findByRole('option', { name: '社区公共事务（1 个词）' }),
  )
}
beforeEach(() => {
  vi.clearAllMocks()
  current = scheduleFixture()
  listMock.mockReset().mockImplementation(async () => page())
  detailMock.mockReset().mockImplementation(async () => current)
  historyMock
    .mockReset()
    .mockResolvedValue({ occurrences: [], next_before_id: null })
  vi.mocked(fetchMonitoringRules)
    .mockReset()
    .mockResolvedValue({ rules: [rule, otherRule] })
  createMock.mockReset().mockImplementation(async (input) => {
    current = scheduleFixture({
      monitoring_rule_id: input.monitoring_rule_id,
      platforms: input.platforms,
      max_results_per_term: input.max_results_per_term,
      interval_minutes:
        input.interval.value * (input.interval.unit === 'hours' ? 60 : 1),
    })
    return current
  })
  updateMock.mockReset().mockImplementation(async (_id, input) => {
    if (input.expected_revision !== current.revision)
      throw new CollectionScheduleApiError('collection_schedule_changed', 409)
    current = {
      ...current,
      monitoring_rule_id: input.monitoring_rule_id,
      platforms: input.platforms,
      max_results_per_term: input.max_results_per_term,
      interval_minutes:
        input.interval.value * (input.interval.unit === 'hours' ? 60 : 1),
      enabled: input.enabled,
      revision: current.revision + 1,
      anchor_at: input.enabled ? '2026-08-29T01:00:00Z' : null,
      next_due_at: input.enabled ? '2026-08-29T03:00:00Z' : null,
    }
    return current
  })
})

describe('schedule forms and separate controls', () => {
  it('creates a disabled configuration with labelled fields, canonical platforms and whole hours', async () => {
    const user = userEvent.setup()
    renderSchedules()
    const dialog = await openCreate(user)
    expect(
      dialog.getByRole('combobox', { name: '间隔单位' }),
    ).toHaveTextContent('小时')
    expect(dialog.getAllByRole('checkbox')).toHaveLength(5)
    await chooseRule(user)
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '2')
    for (const platform of ['今日头条', '快手', '抖音'])
      await user.click(dialog.getByRole('checkbox', { name: platform }))
    await user.click(dialog.getByRole('button', { name: '创建停用的定时任务' }))
    await screen.findByText(
      '定时任务已创建，当前为停用状态。核对后可单独启用。',
    )
    expect(createMock).toHaveBeenCalledExactlyOnceWith({
      monitoring_rule_id: 7,
      platforms: ['wb', 'xhs'],
      max_results_per_term: 10,
      interval: { value: 2, unit: 'hours' },
    })
    expect(current.enabled).toBe(false)
    expect(updateMock).not.toHaveBeenCalled()
    expect(screen.getByText('每 2 小时 · 每词最多 10 条')).toBeVisible()
  })
  it('validates required rule, normalized interval and empty platform selection without disabling error focus', async () => {
    const user = userEvent.setup()
    renderSchedules()
    const dialog = await openCreate(user)
    await user.click(dialog.getByRole('button', { name: '创建停用的定时任务' }))
    expect(await dialog.findByText('请选择仍然存在的监控规则。')).toBeVisible()
    expect(
      dialog.getByRole('combobox', { name: '定时采集的监控规则' }),
    ).toHaveFocus()
    await chooseRule(user)
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '721')
    await user.click(dialog.getByRole('button', { name: '创建停用的定时任务' }))
    expect(
      await dialog.findByText(
        '采集间隔须为 1 至 43200 个整分钟（最多 720 小时）。',
      ),
    ).toBeVisible()
    expect(dialog.getByRole('spinbutton', { name: '采集间隔' })).toHaveFocus()
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '1')
    for (const checkbox of dialog.getAllByRole('checkbox'))
      await user.click(checkbox)
    await user.click(dialog.getByRole('button', { name: '创建停用的定时任务' }))
    expect(await dialog.findByText('请至少选择一个采集平台。')).toBeVisible()
    expect(createMock).not.toHaveBeenCalled()
  })
  it('retains dirty drafts on Escape and offers an explicit discard', async () => {
    const user = userEvent.setup()
    renderSchedules()
    const dialog = await openCreate(user)
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '3')
    await user.keyboard('{Escape}')
    expect(dialog.getByText('有未保存的更改，是否放弃草稿？')).toBeVisible()
    await user.click(dialog.getByRole('button', { name: '继续编辑' }))
    expect(dialog.getByRole('spinbutton', { name: '采集间隔' })).toHaveValue(3)
    await user.click(dialog.getByRole('button', { name: '取消' }))
    await user.click(dialog.getByRole('button', { name: '放弃更改' }))
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(createMock).not.toHaveBeenCalled()
  })
  it('locks pending saves, prevents duplicate requests and does not dismiss on Escape', async () => {
    const pending = deferred<CollectionSchedule>()
    createMock.mockReturnValueOnce(pending.promise)
    const user = userEvent.setup()
    renderSchedules()
    const dialog = await openCreate(user)
    await chooseRule(user)
    await user.dblClick(
      dialog.getByRole('button', { name: '创建停用的定时任务' }),
    )
    expect(dialog.getByRole('button', { name: '正在保存…' })).toBeDisabled()
    expect(dialog.getByRole('spinbutton', { name: '采集间隔' })).toBeDisabled()
    expect(
      dialog.getByRole('combobox', { name: '定时采集的监控规则' }),
    ).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('dialog')).toBeVisible()
    expect(createMock).toHaveBeenCalledTimes(1)
    await act(async () => pending.resolve(current))
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })
  it('normalizes minutes when editing and saves only dirty forms with observed revision', async () => {
    current = scheduleFixture({ interval_minutes: 90, revision: 3 })
    const user = userEvent.setup()
    renderSchedules()
    await user.click(
      await screen.findByRole('button', { name: '编辑定时任务' }),
    )
    const dialog = within(screen.getByRole('dialog'))
    expect(
      dialog.getByRole('combobox', { name: '间隔单位' }),
    ).toHaveTextContent('分钟')
    expect(dialog.getByRole('spinbutton', { name: '采集间隔' })).toHaveValue(90)
    expect(dialog.getByRole('button', { name: '保存定时采集' })).toBeDisabled()
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '120')
    await user.click(dialog.getByRole('button', { name: '保存定时采集' }))
    await screen.findByText('定时配置已保存；已提交的采集批次不受影响。')
    expect(updateMock).toHaveBeenCalledExactlyOnceWith(
      4,
      expect.objectContaining({
        expected_revision: 3,
        enabled: false,
        interval: { value: 120, unit: 'minutes' },
      }),
    )
  })
  it('preserves dirty values through a CAS conflict and requires explicit adoption before resave', async () => {
    const user = userEvent.setup()
    const { client } = renderSchedules()
    await user.click(
      await screen.findByRole('button', { name: '编辑定时任务' }),
    )
    const dialog = within(screen.getByRole('dialog'))
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '3')
    current = { ...current, revision: 2, interval_minutes: 240 }
    await user.click(dialog.getByRole('button', { name: '保存定时采集' }))
    expect(
      await dialog.findByText('定时采集计划已更新，请刷新后重试。'),
    ).toBeVisible()
    await act(async () => {
      await client.invalidateQueries({
        queryKey: COLLECTION_SCHEDULES_QUERY_KEY,
      })
    })
    expect(dialog.getByRole('spinbutton', { name: '采集间隔' })).toHaveValue(3)
    expect(dialog.getByRole('button', { name: '保存定时采集' })).toBeDisabled()
    await user.click(
      dialog.getByRole('button', { name: '保留草稿并采用最新版本' }),
    )
    expect(updateMock).toHaveBeenCalledTimes(1)
    await user.click(dialog.getByRole('button', { name: '保存定时采集' }))
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(2))
    expect(updateMock.mock.calls[1][1]).toMatchObject({
      expected_revision: 2,
      interval: { value: 3, unit: 'hours' },
    })
  })
  it('separates saved enablement from rollout and displays the server next due', async () => {
    const user = userEvent.setup()
    renderSchedules()
    await user.click(
      await screen.findByRole('button', { name: '启用定时任务' }),
    )
    expect(
      screen.getByText('完整流程尚未开放，本次只保存设置，不会启动自动采集。'),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: '确认启用' }))
    expect(
      await screen.findByText(
        '启用设置已保存；完整流程尚未开放，当前不会自动执行。',
      ),
    ).toBeVisible()
    expect(screen.getByText('2026/08/29 11:00')).toBeVisible()
    expect(updateMock.mock.calls[0][1]).toMatchObject({
      expected_revision: 1,
      enabled: true,
    })
  })
  it('disables future work while retaining active batch links and existing settings', async () => {
    current = scheduleFixture({
      enabled: true,
      anchor_at: '2026-08-29T00:00:00Z',
      next_due_at: '2026-08-29T01:00:00Z',
      latest_occurrence: occurrenceFixture({
        status: 'dispatched',
        reason: null,
        batch_id: 80,
        batch_status: 'paused_for_manual_action',
        dispatched_at: '2026-08-29T01:00:01Z',
      }),
    })
    const user = userEvent.setup()
    renderSchedules()
    await user.click(
      await screen.findByRole('button', { name: '停用定时任务' }),
    )
    expect(screen.getByText(/仅停止未来的定时执行/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: '确认停用' }))
    expect(
      await screen.findByText(
        '定时任务已停用，仅停止后续执行；已提交的采集批次继续保留。',
      ),
    ).toBeVisible()
    expect(
      screen.getByRole('link', { name: '查看采集批次 #80' }),
    ).toHaveAttribute('href', '/collection-batches/80')
    expect(screen.getByText('采集状态：等待人工处理')).toBeVisible()
    expect(updateMock.mock.calls[0][1]).toMatchObject({
      platforms: current.platforms,
      max_results_per_term: 10,
      enabled: false,
      expected_revision: 1,
    })
  })
  it('does not apply stale enable controls without re-reading and explicit confirmation', async () => {
    const user = userEvent.setup()
    renderSchedules()
    await screen.findByRole('button', { name: '启用定时任务' })
    current = { ...current, revision: 2, interval_minutes: 300 }
    await user.click(screen.getByRole('button', { name: '启用定时任务' }))
    expect(
      await screen.findByText('定时配置已更新，请核对后重新确认操作。'),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: '确认启用' })).toBeDisabled()
    expect(updateMock).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '核对最新设置' }))
    expect(screen.getByText(/每 5 小时采集/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: '确认启用' }))
    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledExactlyOnceWith(
        4,
        expect.objectContaining({ expected_revision: 2, enabled: true }),
      ),
    )
  })
  it('allows retaining a deleted rule while disabled, but never enables it', async () => {
    current = scheduleFixture({
      monitoring_rule_id: null,
      rule_state: 'deleted',
    })
    const user = userEvent.setup()
    renderSchedules()
    expect(
      await screen.findByRole('button', { name: '启用定时任务' }),
    ).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '编辑定时任务' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(
      dialog.getByRole('combobox', { name: '定时采集的监控规则' }),
    ).toHaveTextContent('规则已删除')
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '2')
    await user.click(dialog.getByRole('button', { name: '保存定时采集' }))
    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledExactlyOnceWith(
        4,
        expect.objectContaining({ monitoring_rule_id: null, enabled: false }),
      ),
    )
  })
  it.each(['deleted', 'disabled'] as const)(
    'requires explicit adoption when a rule is %s during disable confirmation at the same revision',
    async (state) => {
      current = scheduleFixture({
        enabled: true,
        anchor_at: '2026-08-29T00:00:00Z',
        next_due_at: '2026-08-29T01:00:00Z',
      })
      const user = userEvent.setup()
      const { client } = renderSchedules()
      await user.click(
        await screen.findByRole('button', { name: '停用定时任务' }),
      )
      await waitFor(() =>
        expect(screen.getByRole('button', { name: '确认停用' })).toBeEnabled(),
      )
      const ruleId = state === 'deleted' ? null : current.monitoring_rule_id
      current = { ...current, monitoring_rule_id: ruleId, rule_state: state }
      await act(async () => {
        await client.invalidateQueries({
          queryKey: COLLECTION_SCHEDULES_QUERY_KEY,
        })
      })
      const adopt = await screen.findByRole('button', { name: '核对最新设置' })
      expect(screen.getByRole('button', { name: '确认停用' })).toBeDisabled()
      await user.click(adopt)
      expect(updateMock).not.toHaveBeenCalled()
      await user.click(screen.getByRole('button', { name: '确认停用' }))
      await waitFor(() =>
        expect(updateMock).toHaveBeenCalledExactlyOnceWith(
          4,
          expect.objectContaining({
            monitoring_rule_id: ruleId,
            expected_revision: 1,
            enabled: false,
          }),
        ),
      )
    },
  )
  it('retains dirty interval values and offers the deleted-rule option after same-revision recovery', async () => {
    const user = userEvent.setup()
    const { client } = renderSchedules()
    await user.click(
      await screen.findByRole('button', { name: '编辑定时任务' }),
    )
    const dialog = within(screen.getByRole('dialog'))
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '3')
    current = { ...current, monitoring_rule_id: null, rule_state: 'deleted' }
    vi.mocked(fetchMonitoringRules).mockResolvedValue({ rules: [otherRule] })
    await act(async () => {
      await client.invalidateQueries()
    })
    const adopt = await dialog.findByRole('button', {
      name: '保留草稿并采用最新版本',
    })
    expect(dialog.getByRole('button', { name: '保存定时采集' })).toBeDisabled()
    await user.click(adopt)
    expect(dialog.getByRole('spinbutton', { name: '采集间隔' })).toHaveValue(3)
    expect(updateMock).not.toHaveBeenCalled()
    dialog.getByRole('combobox', { name: '定时采集的监控规则' }).focus()
    await user.keyboard('{ArrowDown}')
    await user.click(
      await screen.findByRole('option', { name: '社区公共事务（规则已删除）' }),
    )
    await user.click(dialog.getByRole('button', { name: '保存定时采集' }))
    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledExactlyOnceWith(
        4,
        expect.objectContaining({
          monitoring_rule_id: null,
          expected_revision: 1,
          enabled: false,
          interval: { value: 3, unit: 'hours' },
        }),
      ),
    )
  })
  it('does not invalidate dirty configuration for an occurrence-only update at the same revision', async () => {
    const user = userEvent.setup()
    const { client } = renderSchedules()
    await user.click(
      await screen.findByRole('button', { name: '编辑定时任务' }),
    )
    const dialog = within(screen.getByRole('dialog'))
    await user.clear(dialog.getByRole('spinbutton', { name: '采集间隔' }))
    await user.type(dialog.getByRole('spinbutton', { name: '采集间隔' }), '3')
    current = { ...current, latest_occurrence: occurrenceFixture() }
    await act(async () => {
      await client.invalidateQueries({
        queryKey: COLLECTION_SCHEDULES_QUERY_KEY,
      })
    })
    expect(dialog.getByRole('spinbutton', { name: '采集间隔' })).toHaveValue(3)
    expect(
      dialog.queryByRole('button', { name: '保留草稿并采用最新版本' }),
    ).not.toBeInTheDocument()
    expect(dialog.getByRole('button', { name: '保存定时采集' })).toBeEnabled()
    await user.click(dialog.getByRole('button', { name: '保存定时采集' }))
    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledExactlyOnceWith(
        4,
        expect.objectContaining({
          expected_revision: 1,
          interval: { value: 3, unit: 'hours' },
        }),
      ),
    )
  })
})

describe('history, read-only entry and paging', () => {
  it('loads selected occurrence pages from the URL with safe batch links and truthful outcomes', async () => {
    historyMock.mockResolvedValueOnce({
      occurrences: [
        occurrenceFixture({ id: 30 }),
        occurrenceFixture({ id: 29, reason: 'browser_unavailable' }),
        occurrenceFixture({
          id: 28,
          status: 'missed',
          reason: 'offline',
          missed_count: 40,
          missed_until: '2026-08-30T01:00:00Z',
        }),
        occurrenceFixture({
          id: 27,
          status: 'interrupted',
          reason: 'dispatch_interrupted',
          batch_id: 99,
          batch_status: 'paused_for_manual_action',
          dispatched_at: '2026-08-29T01:00:01Z',
        }),
        ...Array.from({ length: 16 }, (_, index) =>
          occurrenceFixture({
            id: 26 - index,
            status: 'claimed',
            reason: null,
          }),
        ),
      ],
      next_before_id: 11,
    })
    const user = userEvent.setup()
    const { router } = renderSchedules('/collection-runs?schedule=4&keep=1')
    expect(await screen.findByText(/共错过 40 轮/)).toBeVisible()
    expect(screen.getByText(/浏览器会话不可用/)).toBeVisible()
    expect(screen.getByText(/浏览器正在执行其他操作/)).toBeVisible()
    expect(screen.getByText('调度中断')).toBeVisible()
    expect(
      screen.getByRole('link', { name: '查看采集批次 #99' }),
    ).toHaveAttribute('href', '/collection-batches/99')
    expect(screen.queryByText('未发现内容')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '更早执行记录' }))
    await waitFor(() =>
      expect(historyMock).toHaveBeenLastCalledWith(4, expect.any(AbortSignal), {
        limit: 20,
        beforeId: 11,
      }),
    )
    expect(router.state.location.search).toContain('occurrencesBefore=11')
    expect(router.state.location.search).toContain('keep=1')
    expect(createMock).not.toHaveBeenCalled()
    expect(updateMock).not.toHaveBeenCalled()
  })
  it('keeps schedule pagination addressable and provides latest-page recovery', async () => {
    listMock.mockResolvedValueOnce({
      schedules: Array.from({ length: 20 }, (_, index) =>
        scheduleFixture({ id: 30 - index }),
      ),
      next_before_id: 11,
    })
    const user = userEvent.setup()
    const { router } = renderSchedules()
    await user.click(
      await screen.findByRole('button', { name: '更早定时任务' }),
    )
    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith(expect.any(AbortSignal), {
        limit: 20,
        beforeId: 11,
      }),
    )
    expect(router.state.location.search).toContain('schedulesBefore=11')
    await user.click(screen.getByRole('button', { name: '最新定时任务' }))
    await waitFor(() =>
      expect(router.state.location.search).not.toContain('schedulesBefore'),
    )
  })
  it('opens and closes history with keyboard focus without scheduling work', async () => {
    const user = userEvent.setup()
    renderSchedules()
    const button = await screen.findByRole('button', {
      name: '查看定时执行记录',
    })
    button.focus()
    await user.keyboard('{Enter}')
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: '定时执行记录 · #4' }),
      ).toHaveFocus(),
    )
    await user.click(screen.getByRole('button', { name: '收起记录' }))
    expect(button).toHaveFocus()
    await user.click(screen.getByRole('button', { name: '刷新定时任务' }))
    expect(createMock).not.toHaveBeenCalled()
    expect(updateMock).not.toHaveBeenCalled()
  })
  it('recovers failed selected history through page refresh, retaining the URL selection', async () => {
    historyMock.mockRejectedValueOnce(
      new CollectionScheduleApiError(
        'collection_schedule_storage_unavailable',
        503,
      ),
    )
    const user = userEvent.setup()
    const { router } = renderSchedules('/collection-runs?schedule=4')
    await screen.findByText('定时采集数据暂时无法读取或保存，请稍后重试。')
    await user.click(screen.getByRole('button', { name: '刷新定时任务' }))
    await screen.findByText('还没有这一页的执行记录；保存配置不代表已经采集。')
    expect(router.state.location.search).toBe('?schedule=4')
    expect(historyMock).toHaveBeenCalledTimes(2)
    expect(updateMock).not.toHaveBeenCalled()
  })
  it('shows invalid IDs and safe recovery rather than sending an unsafe detail request', async () => {
    const user = userEvent.setup()
    const { router } = renderSchedules(
      '/collection-runs?schedule=9007199254740992&occurrencesBefore=-1',
    )
    expect(
      screen.getByText('定时任务链接中的编号或分页位置无效。'),
    ).toBeVisible()
    expect(detailMock).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '重置定时任务视图' }))
    expect(router.state.location.search).toBe('')
  })
})

describe('revision and in-flight read fences', () => {
  it('does not adopt an older dependency projection over a newer configuration', () => {
    const observed = scheduleFixture({ revision: 3 })
    const older = scheduleFixture({
      revision: 2,
      monitoring_rule_id: null,
      rule_state: 'deleted',
    })
    expect(scheduleConfigurationChanged(observed, older)).toBe(false)
    expect(
      scheduleConfigurationChanged(observed, { ...older, revision: 3 }),
    ).toBe(true)
  })
  it('never lets an older save replace newer detail or list revisions', async () => {
    const client = new QueryClient()
    const latest = scheduleFixture({ revision: 3, interval_minutes: 300 })
    client.setQueryData<CollectionSchedulePage>([...scheduleListKey, null], {
      schedules: [current],
      next_before_id: null,
    })
    await cacheSavedSchedule(client, latest)
    await cacheSavedSchedule(
      client,
      scheduleFixture({ revision: 2, interval_minutes: 120 }),
    )
    expect(client.getQueryData(scheduleDetailKey(4))).toEqual(latest)
    expect(client.getQueryData([...scheduleListKey, null])).toEqual({
      schedules: [latest],
      next_before_id: null,
    })
    client.clear()
  })
  it('fences a stale GET from rolling back the saved projection', async () => {
    const client = new QueryClient()
    const pending = deferred<CollectionSchedule>()
    client.setQueryData(scheduleDetailKey(4), current)
    const request = client
      .fetchQuery({
        queryKey: scheduleDetailKey(4),
        queryFn: ({ signal }) => {
          expect(signal.aborted).toBe(false)
          return pending.promise
        },
      })
      .catch(() => undefined)
    const saved = scheduleFixture({ revision: 2, interval_minutes: 120 })
    await cacheSavedSchedule(client, saved)
    pending.resolve(current)
    await request
    await Promise.resolve()
    expect(client.getQueryData(scheduleDetailKey(4))).toEqual(saved)
    client.clear()
  })
  it.each(['before', 'during'])(
    'keeps saved state visible when a GET begun %s a pending write returns late',
    async (timing) => {
      const user = userEvent.setup()
      const { client } = renderSchedules('/collection-runs?schedule=4')
      await screen.findByText(
        '还没有这一页的执行记录；保存配置不代表已经采集。',
      )
      await user.click(screen.getByRole('button', { name: '启用定时任务' }))
      await waitFor(() =>
        expect(screen.getByRole('button', { name: '确认启用' })).toBeEnabled(),
      )
      const pendingWrite = deferred<CollectionSchedule>()
      updateMock.mockReturnValueOnce(pendingWrite.promise)
      const pendingDetail = deferred<CollectionSchedule>()
      const pendingList = deferred<CollectionSchedulePage>()
      const old = current
      function startReads() {
        detailMock.mockReturnValueOnce(pendingDetail.promise)
        listMock.mockReturnValueOnce(pendingList.promise)
        void client.invalidateQueries({
          queryKey: COLLECTION_SCHEDULES_QUERY_KEY,
        })
      }
      if (timing === 'before') act(startReads)
      await user.click(screen.getByRole('button', { name: '确认启用' }))
      if (timing === 'during') act(startReads)
      current = {
        ...old,
        enabled: true,
        revision: 2,
        anchor_at: '2026-08-29T01:00:00Z',
        next_due_at: '2026-08-29T02:00:00Z',
      }
      await act(async () => pendingWrite.resolve(current))
      await screen.findByText(
        '启用设置已保存；完整流程尚未开放，当前不会自动执行。',
      )
      await act(async () => {
        pendingDetail.resolve(old)
        pendingList.resolve({ schedules: [old], next_before_id: null })
      })
      expect(screen.getByRole('button', { name: '停用定时任务' })).toBeVisible()
      expect(screen.getByText('定时任务 #4 · 版本 2')).toBeVisible()
      expect(
        client.getQueryData<CollectionSchedule>(scheduleDetailKey(4))?.revision,
      ).toBe(2)
    },
  )
})

describe('normalized form limits', () => {
  const values = {
    ruleId: '7',
    platforms: ['wb'],
    intervalValue: 1,
    intervalUnit: 'minutes',
    maxResultsPerTerm: 10,
  }
  it.each([
    { intervalValue: 1, intervalUnit: 'minutes' },
    { intervalValue: 43200, intervalUnit: 'minutes' },
    { intervalValue: 720, intervalUnit: 'hours' },
  ])('accepts %o', (interval) => {
    expect(
      scheduleFormSchema.safeParse({ ...values, ...interval }).success,
    ).toBe(true)
  })
  it.each([
    { intervalValue: 0 },
    { intervalValue: 1.5 },
    { intervalValue: 43201 },
    { intervalValue: 721, intervalUnit: 'hours' },
    { platforms: [] },
    { platforms: ['wb', 'wb'] },
    { maxResultsPerTerm: 51 },
  ])('rejects %o', (change) => {
    expect(scheduleFormSchema.safeParse({ ...values, ...change }).success).toBe(
      false,
    )
  })
})
