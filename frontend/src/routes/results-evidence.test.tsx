import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { expect, it, vi } from 'vitest'

import { analysisAttemptFixture } from '@/lib/api/analysis-fixtures'
import { SavedAnalysisEvidence } from '@/routes/results-evidence'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

it('distinguishes a known inventory from downloaded files and explains missing media', () => {
  const attempt = analysisAttemptFixture()
  attempt.input = {
    ...attempt.input!,
    status: 'partial',
    detected_modalities: ['text', 'image'],
    issues: ['asset_unavailable'],
    assets: [
      {
        position: 0,
        kind: 'image',
        status: 'unavailable',
        sha256: null,
        mime_type: null,
        byte_size: null,
        width: null,
        height: null,
        duration_ms: null,
        audio_track: 'not_applicable',
        coverage: 'unknown',
        issue_code: 'asset_unavailable',
      },
    ],
  }
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <SavedAnalysisEvidence
          attempt={attempt}
          controls={{
            pending: false,
            activeKey: null,
            feedback: null,
            open: vi.fn(),
          }}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(screen.getByText('媒体清单')).toBeInTheDocument()
  expect(screen.queryByText('已确认齐全')).not.toBeInTheDocument()
  expect(screen.getByText(/源文件不可用/)).toBeInTheDocument()
  expect(
    screen.getByText(/本次提交模型：0 张图片，0 段视频/),
  ).toBeInTheDocument()
})
