import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, Outlet } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchPlatformConnections,
  type PlatformConnection,
  type PlatformConnectionsResponse,
} from '@/lib/api/platform-connections'
import {
  fetchWorkbench,
  WorkbenchApiError,
  type WorkbenchSnapshot,
} from '@/lib/api/workbench'
import {
  completedReport,
  workbenchFixture,
  workbenchTimestamp,
} from '@/lib/api/workbench.fixtures'
import { Workbench } from '@/routes/workbench'

vi.mock('@/lib/api/workbench', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/workbench')>()),
  fetchWorkbench: vi.fn(),
}))
vi.mock('@/lib/api/platform-connections', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/platform-connections')>()),
  fetchPlatformConnections: vi.fn(),
}))

function platform(
  platform: PlatformConnection['platform'],
  displayName: string,
  status: PlatformConnection['status'] = 'connected',
): PlatformConnection {
  return {
    platform,
    display_name: displayName,
    availability: 'enabled',
    status,
    guidance: status === 'action_required' ? 'complete_login' : 'none',
    last_checked_at: workbenchTimestamp,
    active_attempt_id: null,
  }
}

function catalog(
  statuses: Partial<
    Record<PlatformConnection['platform'], PlatformConnection['status']>
  > = {},
): PlatformConnectionsResponse {
  return {
    platforms: [
      platform('wb', '微博', statuses.wb),
      platform('dy', '抖音', statuses.dy),
      platform('ks', '快手', statuses.ks),
      platform('xhs', '小红书', statuses.xhs),
      platform('toutiao', '今日头条', statuses.toutiao),
    ],
  }
}

const mockedWorkbench = vi.mocked(fetchWorkbench)
const mockedPlatforms = vi.mocked(fetchPlatformConnections)
const retryHealth = vi.fn()

function renderWorkbench() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <Outlet
            context={{
              healthState: {
                status: 'connected',
                data: { status: 'ok', service: 'longtian-api' },
              },
              retryHealth,
            }}
          />
        ),
        children: [
          { index: true, element: <Workbench /> },
          { path: '*', element: <p>目标页面</p> },
        ],
      },
    ],
    { initialEntries: ['/'] },
  )
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { queryClient, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedWorkbench.mockResolvedValue(workbenchFixture())
  mockedPlatforms.mockResolvedValue(catalog())
})

describe('homepage workbench', () => {
  it('shows a known empty state without discovery KPIs or handling lifecycle', async () => {
    renderWorkbench()

    expect(
      await screen.findByRole('heading', { name: '当前运行正常' }),
    ).toBeInTheDocument()
    expect(screen.getByText('还没有可阅读的舆情报告')).toBeInTheDocument()
    expect(screen.getByText('暂无可执行的自动任务。')).toBeInTheDocument()
    expect(screen.getByText('5/5 已连接')).toBeInTheDocument()
    expect(screen.queryByText('需要查看')).toBeNull()
    expect(screen.queryByText('今日发现', { exact: true })).toBeNull()
    expect(screen.queryByText('待跟进', { exact: true })).toBeNull()
    expect(screen.queryByText('已处理', { exact: true })).toBeNull()
    expect(screen.queryByText('风险评分', { exact: true })).toBeNull()
    expect(screen.queryByText('Duty signal')).toBeNull()
    expect(screen.queryByText(/归属|健康状态|投影/u)).toBeNull()
    expect(
      screen.queryByText('自动任务、计划、报告和平台连接均正常。'),
    ).toBeNull()
    expect(screen.queryByText(/当前没有运行中/u)).toBeNull()
  })

  it('prioritizes every attention owner while keeping the last report readable', async () => {
    const snapshot: WorkbenchSnapshot = workbenchFixture({
      attention: [
        {
          kind: 'automation_task',
          severity: 'warning',
          status: 'missed',
          reason: 'offline',
          resource_id: 11,
          owner: '社区计划',
          occurred_at: workbenchTimestamp,
          unsuccessful_count: 2,
        },
        {
          kind: 'collection_batch',
          severity: 'warning',
          status: 'completed_with_failures',
          reason: 'unsuccessful_members',
          resource_id: 12,
          owner: '社区规则',
          occurred_at: workbenchTimestamp,
          unsuccessful_count: 1,
        },
        {
          kind: 'initial_analysis',
          severity: 'warning',
          status: 'unsuccessful_members',
          reason: 'unsuccessful_members',
          resource_id: 13,
          owner: '初步分析',
          occurred_at: workbenchTimestamp,
          unsuccessful_count: 3,
        },
        {
          kind: 'report',
          severity: 'error',
          status: 'failed',
          reason: null,
          resource_id: 14,
          owner: '舆情报告',
          occurred_at: workbenchTimestamp,
          unsuccessful_count: null,
        },
        {
          kind: 'automation_run',
          severity: 'error',
          status: 'failed',
          reason: 'internal_error',
          resource_id: 15,
          owner: '社区自动值守',
          occurred_at: workbenchTimestamp,
          unsuccessful_count: null,
        },
      ],
      activity: {
        automation: {
          run_id: 44,
          task_id: 45,
          task_name: '社区自动值守',
          status: 'reporting',
          active_stage: 'topic_report',
          created_at: workbenchTimestamp,
          started_at: workbenchTimestamp,
        },
        collection: {
          id: 41,
          status: 'running',
          rule_name: '社区规则',
          current_platform: 'wb',
          current_item_position: 1,
          completed_item_count: 1,
          item_count: 5,
          created_at: workbenchTimestamp,
          started_at: workbenchTimestamp,
        },
        initial_analysis: {
          id: 42,
          status: 'running',
          total_count: 20,
          completed_count: 8,
          unsuccessful_count: 1,
          created_at: workbenchTimestamp,
          started_at: workbenchTimestamp,
        },
        report: {
          id: 43,
          status: 'composing',
          total_count: 8,
          completed_count: 8,
          failed_count: 0,
          created_at: workbenchTimestamp,
          started_at: workbenchTimestamp,
        },
      },
      next_automation: {
        id: 51,
        name: '下一班自动任务',
        rule_name: '下一班社区采集',
        due_at: '2026-08-29T09:00:00+00:00',
        schedule: { kind: 'interval', interval_minutes: 60 },
      },
      latest_report: completedReport(),
    })
    mockedWorkbench.mockResolvedValue(snapshot)
    mockedPlatforms.mockResolvedValue(catalog({ wb: 'disconnected' }))
    renderWorkbench()

    expect(
      await screen.findByRole('heading', { name: '当前有 6 项需要查看' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(
        '问题会在同一归属出现更新的健康状态后自动从这里消失。',
      ),
    ).toBeNull()
    expect(
      screen.getByText(
        '多条来源提及社区道路积水，具体地点和发生时间仍需核实。',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('报告生成未正常结束', { exact: false }),
    ).toBeInTheDocument()
    expect(screen.getByText('相关性已判断，正在生成报告')).toBeInTheDocument()
    expect(screen.getByText('社区自动值守')).toBeInTheDocument()
    expect(screen.getByText('下一班自动任务')).toBeInTheDocument()
    expect(screen.getAllByRole('progressbar')).toHaveLength(3)

    const attention = screen.getByRole('heading', { name: '需要查看' })
      .parentElement?.parentElement
    if (!attention) throw new Error('attention region missing')
    const links = within(attention).getAllByRole('link')
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/platform-accounts',
      '/automation-tasks/11/runs',
      '/collection-batches/12',
      '/reports/history?job=13',
      '/reports/history?report=14',
      '/automation-runs/15',
    ])
    expect(screen.getByRole('link', { name: /阅读完整报告/u })).toHaveAttribute(
      'href',
      '/reports/history?report=31',
    )
  })

  it('renders a truthful empty report as a successful readable outcome', async () => {
    mockedWorkbench.mockResolvedValue(
      workbenchFixture({
        latest_report: {
          ...completedReport(),
          status: 'empty',
          overview: null,
          empty_reason: 'no_relevant_sources',
          coverage: {
            ...completedReport().coverage,
            relevant: 0,
            irrelevant: 7,
            uncertain: 1,
          },
        },
      }),
    )
    renderWorkbench()

    expect(
      await screen.findByText('这次没有足够相关的来源，未生成报告正文。'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/任务已完成，但没有足够相关的内容/u),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '需要查看' })).toBeNull()
  })

  it('keeps independent platform readiness when the persistent snapshot fails', async () => {
    mockedWorkbench.mockRejectedValue(
      new WorkbenchApiError('workbench_storage_unavailable', 503),
    )
    renderWorkbench()

    expect(await screen.findByText('最新报告暂时无法读取')).toBeInTheDocument()
    expect(screen.getByText('5/5 已连接')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '当前状态尚未完全确认' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新读取' })).toBeInTheDocument()
  })

  it('retains validated content and labels it stale after a failed refresh', async () => {
    const user = userEvent.setup()
    mockedWorkbench
      .mockResolvedValueOnce(
        workbenchFixture({ latest_report: completedReport() }),
      )
      .mockRejectedValue(
        new WorkbenchApiError('workbench_storage_unavailable', 503),
      )
    renderWorkbench()
    await screen.findByText(
      '多条来源提及社区道路积水，具体地点和发生时间仍需核实。',
    )

    await user.click(screen.getByRole('button', { name: '刷新状态' }))

    expect(await screen.findByRole('alert', { name: '' })).toHaveTextContent(
      '状态更新失败',
    )
    expect(
      screen.getByText(
        '多条来源提及社区道路积水，具体地点和发生时间仍需核实。',
      ),
    ).toBeInTheDocument()
    await waitFor(() => expect(mockedWorkbench).toHaveBeenCalledTimes(2))
  })
})
