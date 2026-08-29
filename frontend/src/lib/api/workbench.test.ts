import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchWorkbench, WorkbenchApiError } from '@/lib/api/workbench'
import { completedReport, workbenchFixture } from '@/lib/api/workbench.fixtures'

describe('workbench API boundary', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => vi.unstubAllGlobals())

  it('accepts one exact, internally consistent snapshot', async () => {
    const snapshot = workbenchFixture({ latest_report: completedReport() })
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(snapshot), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const controller = new AbortController()

    await expect(fetchWorkbench(controller.signal)).resolves.toEqual(snapshot)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/workbench', {
      cache: 'no-store',
      redirect: 'error',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
  })

  it('rejects extra fields and inconsistent report coverage', async () => {
    const snapshot = workbenchFixture({
      latest_report: {
        ...completedReport(),
        coverage: { ...completedReport().coverage, ready: 7 },
      },
    })
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ ...snapshot, secret: 'credential-sentinel' }),
        {
          status: 200,
        },
      ),
    )

    const result = fetchWorkbench(new AbortController().signal)
    await expect(result).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(result).rejects.not.toThrow(/credential-sentinel/u)
  })

  it('accepts only the exact safe backend error contract', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'workbench_storage_unavailable',
            message: '工作台数据暂时无法读取，请稍后重试。',
          },
        }),
        { status: 503 },
      ),
    )

    await expect(
      fetchWorkbench(new AbortController().signal),
    ).rejects.toMatchObject({
      code: 'workbench_storage_unavailable',
      status: 503,
    })
  })

  it('bounds malformed errors and unreachable service failures', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: {
            code: 'workbench_storage_unavailable',
            message: 'raw private credential sentinel',
          },
        }),
        { status: 503 },
      ),
    )
    await expect(
      fetchWorkbench(new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid_response' })

    fetchMock.mockRejectedValueOnce(new TypeError('network private path'))
    const result = fetchWorkbench(new AbortController().signal)
    await expect(result).rejects.toBeInstanceOf(WorkbenchApiError)
    await expect(result).rejects.toMatchObject({
      code: 'service_unavailable',
      message: '无法连接本机后端服务，请确认服务已经启动。',
    })
  })
})
