import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  MEDIA_POLICY_KEY,
  cleanMediaCache,
  fetchMediaPolicy,
  mediaPolicyUpdateSchema,
  saveMediaPolicy,
  type MediaPolicy,
  type MediaPolicyResult,
} from '@/lib/api/media-cache'
import { analysisErrorMessage } from '@/lib/api/analysis-shared'

function PolicyForm({ policy }: { policy: MediaPolicy }) {
  const client = useQueryClient()
  const [draft, setDraft] = useState(() => ({
    days: String(policy.retention_days),
    capacity: String(policy.capacity_mib),
    revision: policy.revision,
  }))
  const [feedback, setFeedback] = useState<string | null>(null)
  const accept = (result: MediaPolicyResult) => {
    client.setQueryData(MEDIA_POLICY_KEY, result.policy)
    void client.invalidateQueries({ queryKey: ['media-cache'] })
    setDraft({
      days: String(result.policy.retention_days),
      capacity: String(result.policy.capacity_mib),
      revision: result.policy.revision,
    })
    setFeedback(
      result.cleanup.deferred
        ? '策略已保存；部分文件正在使用或无法确认归属，清理暂缓。无法安全腾出空间时不会新增缓存。'
        : `已按策略清理 ${result.cleanup.removed_files} 个文件，释放 ${(result.cleanup.removed_bytes / 1048576).toFixed(2)} MiB。`,
    )
  }
  const save = useMutation({ mutationFn: saveMediaPolicy, onSuccess: accept })
  const clean = useMutation({ mutationFn: cleanMediaCache, onSuccess: accept })
  const pending = save.isPending || clean.isPending
  const stale = draft.revision !== policy.revision
  const dirty =
    draft.days !== String(policy.retention_days) ||
    draft.capacity !== String(policy.capacity_mib)
  const error = save.error || clean.error
  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault()
        if (pending || stale) return
        const value = mediaPolicyUpdateSchema.safeParse({
          retention_days: Number(draft.days),
          capacity_mib: Number(draft.capacity),
          expected_revision: draft.revision,
        })
        if (
          !value.success ||
          !/^\d+$/u.test(draft.days) ||
          !/^\d+$/u.test(draft.capacity)
        ) {
          setFeedback('请填写范围内的整数：1–3650 天、1–20480 MiB。')
          return
        }
        clean.reset()
        setFeedback(null)
        save.mutate(value.data)
      }}
    >
      <FieldGroup className="max-w-md">
        <Field>
          <FieldLabel htmlFor="media-days">保留期限（天）</FieldLabel>
          <Input
            id="media-days"
            type="number"
            min={1}
            max={3650}
            step={1}
            required
            value={draft.days}
            disabled={pending}
            aria-describedby="media-policy-help"
            onChange={(event) =>
              setDraft({ ...draft, days: event.target.value })
            }
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="media-capacity">容量上限（MiB）</FieldLabel>
          <Input
            id="media-capacity"
            type="number"
            min={1}
            max={20480}
            step={1}
            required
            value={draft.capacity}
            disabled={pending}
            aria-describedby="media-policy-help"
            onChange={(event) =>
              setDraft({ ...draft, capacity: event.target.value })
            }
          />
        </Field>
      </FieldGroup>
      <p
        id="media-policy-help"
        className="max-w-2xl text-sm leading-6 text-muted-foreground"
      >
        默认 30 天、1024 MiB（1
        GiB）。从原文件首次保存时计时，查看或复用不延长期限。
        先清理到期文件，再按最早保存的顺序腾出空间；正在使用的文件会跳过。
        最多保留 10,000
        个活跃文件。保存策略、新增缓存及后台每分钟检查时执行安全清理。
      </p>
      <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
        已被报告引用的原文件也可以清理，但不会删除正文、总结或报告。
        这是磁盘缓存策略，不会改变搜索数量或单帖模型输入预算；清理后查看历史不会自动下载。
      </p>
      {stale && (
        <div role="status" className="space-y-2 text-sm">
          <p>策略已在其他页面更新。你的输入暂时保留，请重新载入后确认。</p>
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              setDraft({
                days: String(policy.retention_days),
                capacity: String(policy.capacity_mib),
                revision: policy.revision,
              })
            }
          >
            重新载入当前策略
          </Button>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending || stale}>
          {save.isPending ? '正在保存并清理…' : '保存策略并执行安全清理'}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={pending || stale || dirty}
          onClick={() => {
            save.reset()
            setFeedback(null)
            clean.mutate(draft.revision)
          }}
        >
          {clean.isPending ? '正在安全清理…' : '按当前策略清理'}
        </Button>
      </div>
      {error && (
        <div role="alert" className="space-y-2 text-sm text-destructive">
          <p>{analysisErrorMessage(error)}</p>
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              void client.invalidateQueries({ queryKey: MEDIA_POLICY_KEY })
            }
          >
            刷新已保存策略
          </Button>
        </div>
      )}
      {feedback && (
        <p role="status" className="max-w-2xl text-sm">
          {feedback}
        </p>
      )}
    </form>
  )
}

export function MediaSettings({ embedded = false }: { embedded?: boolean }) {
  const query = useQuery({
    queryKey: MEDIA_POLICY_KEY,
    queryFn: ({ signal }) => fetchMediaPolicy(signal),
    retry: false,
  })
  return (
    <section className="flex flex-col gap-6" aria-label="原媒体保留策略">
      {!embedded && (
        <header>
          <h2 className="font-display text-2xl">原媒体保留策略</h2>
        </header>
      )}
      {query.isPending && <p role="status">正在读取媒体策略…</p>}
      {query.isError && (
        <div role="alert" className="space-y-2 text-sm">
          <p>{analysisErrorMessage(query.error)}</p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            重新读取
          </Button>
        </div>
      )}
      {query.data && (
        <>
          <p className="rounded-lg border bg-muted/30 p-4 text-sm">
            已分配 {(query.data.reserved_bytes / 1048576).toFixed(2)} MiB ·{' '}
            {query.data.files} 个文件， 其中 {query.data.pending_files}{' '}
            个写入未完成。已分配空间包含未完成的容量预留，不等于全部文件都可打开。
          </p>
          <PolicyForm policy={query.data} />
        </>
      )}
    </section>
  )
}
