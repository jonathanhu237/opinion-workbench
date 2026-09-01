import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAutomationOccurrences,
  fetchAutomationRun,
  fetchAutomationRuns,
  fetchAutomationTask,
  fetchAutomationTasks,
  runAutomationTaskNow,
} from '@/lib/api/automation-workflows'
import { fetchMonitoringRules } from '@/lib/api/monitoring-rules'
import {
  automationRunDetailKey,
  automationRunsKey,
  cacheSavedAutomationRun,
} from '@/hooks/use-automation-workflows'
import { AutomationRunDetail } from '@/routes/automation-run-detail'
import { nextRunPreview } from '@/routes/automation-task-editor'
import { AutomationTaskRuns, AutomationTasks } from '@/routes/automation-tasks'
import {
  automationRun,
  automationTask,
} from '@/lib/api/automation-workflows.fixtures'

vi.mock('@/lib/api/automation-workflows', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/automation-workflows')>()),
  fetchAutomationOccurrences: vi.fn(),
  fetchAutomationRun: vi.fn(),
  fetchAutomationRuns: vi.fn(),
  fetchAutomationTask: vi.fn(),
  fetchAutomationTasks: vi.fn(),
  runAutomationTaskNow: vi.fn(),
}))

vi.mock('@/lib/api/monitoring-rules', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/monitoring-rules')>()),
  fetchMonitoringRules: vi.fn(),
}))

const mockedTasks = vi.mocked(fetchAutomationTasks)
const mockedTask = vi.mocked(fetchAutomationTask)
const mockedRuns = vi.mocked(fetchAutomationRuns)
const mockedOccurrences = vi.mocked(fetchAutomationOccurrences)
const mockedRun = vi.mocked(fetchAutomationRun)
const mockedRunNow = vi.mocked(runAutomationTaskNow)

function renderRoute(
  routes: Parameters<typeof createMemoryRouter>[0],
  initialEntry: string,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(routes, { initialEntries: [initialEntry] })
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return {
    router,
    ...render(<RouterProvider router={router} />, { wrapper: Wrapper }),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedTasks.mockResolvedValue({
    tasks: [automationTask()],
    next_before_id: null,
  })
  mockedTask.mockResolvedValue(automationTask())
  mockedRuns.mockResolvedValue({
    runs: [automationRun()],
    next_before_id: null,
  })
  mockedOccurrences.mockResolvedValue({ occurrences: [], next_before_id: null })
  mockedRun.mockResolvedValue(automationRun())
  mockedRunNow.mockResolvedValue(automationRun({ id: 102, revision: 1 }))
  vi.mocked(fetchMonitoringRules).mockResolvedValue({
    rules: [
      {
        id: 9,
        name: '公共事务',
        monitoring_objects: ['街道'],
        issue_keywords: [],
        terms: ['街道'],
        enabled: true,
      },
    ],
  })
})

describe('automation task route', () => {
  it('shows task-specific goal, fixed pipeline copy and run actions', async () => {
    const user = userEvent.setup()
    renderRoute(
      [{ path: '/automation-tasks', element: <AutomationTasks /> }],
      '/automation-tasks',
    )

    expect(
      await screen.findByRole('heading', { name: '自动任务' }),
    ).toBeVisible()
    expect(
      await screen.findByText('识别需要街道回应的公共事务内容。'),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: '立即运行' })).toBeEnabled()
    expect(screen.getByRole('link', { name: /查看运行/u })).toHaveAttribute(
      'href',
      '/automation-tasks/7/runs',
    )

    await user.click(screen.getByRole('button', { name: '立即运行' }))
    expect(
      screen.getByRole('alertdialog', { name: '立即运行自动任务？' }),
    ).toBeVisible()
    expect(
      within(screen.getByRole('alertdialog')).getByText(
        /按顺序采集、分析并生成报告/u,
      ),
    ).toBeVisible()
    expect(
      within(screen.getByRole('alertdialog')).getByText(
        /不会改变下一次计划时间/u,
      ),
    ).toBeVisible()
  })

  it('opens the editor with the fixed stages presented as read-only copy', async () => {
    const user = userEvent.setup()
    renderRoute(
      [{ path: '/automation-tasks', element: <AutomationTasks /> }],
      '/automation-tasks',
    )
    await user.click(
      await screen.findByRole('button', { name: '新建自动任务' }),
    )

    expect(screen.getByRole('dialog', { name: '新建自动任务' })).toBeVisible()
    expect(screen.getByText('处理流程')).toBeVisible()
    expect(screen.getByText('采集内容')).toBeVisible()
    expect(screen.getByText('初步理解内容')).toBeVisible()
    expect(screen.getByText('相关性判断与报告')).toBeVisible()
    expect(screen.queryByText('每次任务都会按这个顺序处理。')).toBeNull()
    expect(screen.queryByText(/固定工作流/u)).toBeNull()
    expect(
      screen.getByRole('button', { name: '创建停用的自动任务' }),
    ).toBeEnabled()
  })

  it('submits run-now only after an explicit confirmation and navigates to the run', async () => {
    const user = userEvent.setup()
    const { router } = renderRoute(
      [
        { path: '/automation-tasks', element: <AutomationTasks /> },
        { path: '/automation-runs/:runId', element: <p>运行详情</p> },
      ],
      '/automation-tasks',
    )
    await user.click(await screen.findByRole('button', { name: '立即运行' }))
    await user.click(screen.getByRole('button', { name: '确认立即运行' }))
    await waitFor(() => expect(mockedRunNow).toHaveBeenCalledOnce())
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/automation-runs/102'),
    )
  })
})

describe('automation run routes', () => {
  it('renders the three-stage history and planned occurrence area', async () => {
    renderRoute(
      [
        {
          path: '/automation-tasks/:taskId/runs',
          element: <AutomationTaskRuns />,
        },
      ],
      '/automation-tasks/7/runs',
    )
    expect(
      await screen.findByRole('heading', { name: /运行记录/u }),
    ).toBeVisible()
    expect(screen.getByText(/每次运行都会保留任务版本/u)).toBeVisible()
    expect(screen.queryByText(/冻结|修订|运行快照|已保存产物/u)).toBeNull()
    expect(screen.getByText(/采集 · 已完成/u)).toBeVisible()
    expect(screen.getByText(/计划记录/u)).toBeVisible()
  })

  it('keeps the empty zero-model outcome and report link visible in run detail', async () => {
    const empty = automationRun({ outcome: 'no_new_sources' })
    mockedRun.mockResolvedValue(empty)
    renderRoute(
      [{ path: '/automation-runs/:runId', element: <AutomationRunDetail /> }],
      '/automation-runs/101',
    )
    expect(await screen.findAllByText('本轮没有新内容')).toHaveLength(2)
    expect(screen.getByText('这次没有新的可分析内容')).toBeVisible()
    expect(screen.getByText('处理过程')).toBeVisible()
    expect(screen.getByText('本次任务设置')).toBeVisible()
    expect(screen.getByRole('link', { name: /查看本轮报告/u })).toHaveAttribute(
      'href',
      '/results?report=401',
    )
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })

  it('shows model usage and prior attempts without replacing the fixed stages', async () => {
    const user = userEvent.setup()
    const collection = automationRun().stages[0]!
    const analysis = automationRun().stages[1]!
    const failedReport = {
      ...automationRun().stages[2]!,
      status: 'failed' as const,
      usage_attempted: 1,
      usage_tokens: 20,
      error: { code: 'stage_failed', message: '第一次报告失败。' },
    }
    const currentReport = {
      ...automationRun().stages[2]!,
      attempt_number: 2,
      child_id: 402,
      usage_attempted: 2,
      usage_tokens: 100,
    }
    mockedRun.mockResolvedValue(
      automationRun({
        stages: [collection, analysis, currentReport],
        attempts: [collection, analysis, failedReport, currentReport],
      }),
    )
    renderRoute(
      [{ path: '/automation-runs/:runId', element: <AutomationRunDetail /> }],
      '/automation-runs/101',
    )
    expect(await screen.findByText('模型调用：2 次 · Token：100')).toBeVisible()
    await user.click(screen.getByText('查看之前 1 次记录'))
    expect(screen.getByText('第一次报告失败。')).toBeVisible()
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
  })
})

describe('automation boundary helpers', () => {
  it('keeps a newer polled run when an older mutation response arrives', async () => {
    const client = new QueryClient()
    const newer = automationRun({ revision: 8 })
    const stale = automationRun({ revision: 7 })
    client.setQueryData(automationRunDetailKey(101), newer)
    client.setQueryData(automationRunsKey(7), {
      runs: [newer],
      next_before_id: null,
    })
    await cacheSavedAutomationRun(client, stale)
    expect(client.getQueryData(automationRunDetailKey(101))).toEqual(newer)
    expect(
      client.getQueryData<{ runs: Array<typeof newer> }>(automationRunsKey(7))
        ?.runs[0]?.revision,
    ).toBe(8)
  })

  it('previews daily wall time in the target IANA zone including a DST gap', () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date('2026-08-30T00:00:00Z'))
      expect(
        nextRunPreview({
          scheduleKind: 'daily',
          intervalMinutes: 60,
          dailyTime: '09:30',
          timezone: 'Asia/Shanghai',
        })?.toISOString(),
      ).toBe('2026-08-30T01:30:00.000Z')

      vi.setSystemTime(new Date('2024-03-09T12:00:00Z'))
      expect(
        nextRunPreview({
          scheduleKind: 'daily',
          intervalMinutes: 60,
          dailyTime: '02:30',
          timezone: 'America/New_York',
        })?.toISOString(),
      ).toBe('2024-03-10T07:00:00.000Z')
    } finally {
      vi.useRealTimers()
    }
  })
})
