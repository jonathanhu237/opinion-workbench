import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from '@/components/ui/field'
import type { AISettings } from '@/lib/api/ai-settings'

export function CollectionSummaryConfirmation({
  sourceCount,
  settings,
  pending,
  locked = false,
  blocked = false,
  error,
  onClose,
  onConfirm,
}: {
  sourceCount: number
  settings: AISettings
  pending: boolean
  locked?: boolean
  blocked?: boolean
  error: string | null
  onClose: () => void
  onConfirm: (forceRefresh: boolean) => void
}) {
  const [forceRefresh, setForceRefresh] = useState(false)

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose()
      }}
    >
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg"
        showCloseButton={!pending}
      >
        <DialogHeader>
          <DialogTitle>生成汇总</DialogTitle>
          <DialogDescription>
            分析这次采集的全部 {sourceCount}{' '}
            条内容，包括新增和之前发现过的内容，不受当前筛选或分页影响。
          </DialogDescription>
        </DialogHeader>

        <dl className="grid gap-3 rounded-lg border p-3 text-sm">
          <div>
            <dt className="text-muted-foreground">模型服务地址</dt>
            <dd className="mt-1 [overflow-wrap:anywhere]">
              {settings.base_url}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">模型</dt>
            <dd className="mt-1 [overflow-wrap:anywhere]">{settings.model}</dd>
          </div>
        </dl>

        <p className="text-sm leading-6 text-muted-foreground">
          标题和正文将发送到上述模型服务，可能消耗 API
          额度。每条内容会单独分析，最后再用文字生成汇总。
        </p>

        <Field orientation="horizontal" data-disabled={pending || locked}>
          <Checkbox
            id="summary-force-refresh"
            checked={forceRefresh}
            disabled={pending || locked}
            onCheckedChange={setForceRefresh}
            aria-describedby="summary-force-refresh-description"
          />
          <FieldContent>
            <FieldLabel htmlFor="summary-force-refresh">
              重新获取并分析全部内容
            </FieldLabel>
            <FieldDescription id="summary-force-refresh-description">
              默认使用已有分析，不重新打开原文。勾选后会重新获取文字并调用模型。
            </FieldDescription>
          </FieldContent>
        </Field>

        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={pending || blocked}
            aria-busy={pending}
            onClick={() => onConfirm(forceRefresh)}
          >
            {pending ? '正在提交…' : '开始生成'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
