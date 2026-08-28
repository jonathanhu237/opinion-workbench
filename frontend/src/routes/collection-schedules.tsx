import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Clock3, Plus, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import {
  cacheSavedSchedule,
  scheduleConfigurationChanged,
  useCollectionOccurrences,
  useCollectionSchedule,
  useCollectionSchedules,
} from '@/hooks/use-collection-schedules'
import {
  COLLECTION_SCHEDULES_QUERY_KEY,
  scheduleErrorMessage,
  scheduleUpdatePayload,
  updateCollectionSchedule,
  type CollectionOccurrence,
  type CollectionOccurrenceReason,
  type CollectionSchedule,
} from '@/lib/api/collection-schedules'
import { CollectionScheduleEditor } from '@/routes/collection-schedule-editor'
import {
  searchBatchStatusLabel,
  searchPlatformPresenters,
} from '@/routes/search-run-presenters'

const reasonLabels: Record<CollectionOccurrenceReason, string> = {
  browser_operation_active:
    '浏览器正在执行其他操作；本轮已跳过，不取消或重叠当前任务。',
  browser_unavailable:
    '浏览器会话不可用；本轮未采集。请到“平台账号”手动检查连接，后端重启后需重新确认会话。',
  monitoring_rule_not_found:
    '监控规则已删除；本轮未采集。请编辑定时任务选择其他规则。',
  monitoring_rule_disabled: '监控规则已停用；本轮未采集。请检查规则设置。',
  invalid_monitoring_rule: '监控规则不可执行；本轮未采集。请检查规则设置。',
  too_many_search_terms: '规则超过 20 个搜索词；本轮未采集。请拆分规则。',
  schedule_changed: '定时配置已变化；本轮未采集，按最新设置安排后续执行。',
  storage_unavailable: '本轮调度因数据存储不可用而跳过；未确认采集开始。',
  dispatch_interrupted:
    '调度中断，不会自动重放。已有批次请在采集详情中核对并手动恢复。',
  offline: '服务离线期间错过的轮次不会补采；已保存的结果与任务仍保留。',
  clock_jump: '时钟向前变化，错过的轮次不会补采；后续按新的到期时间执行。',
}
const occurrenceLabels: Record<CollectionOccurrence['status'], string> = {
  claimed: '正在调度',
  dispatched: '已提交采集',
  skipped: '已跳过',
  missed: '错过执行',
  interrupted: '调度中断',
}
const ruleStateLabels: Record<CollectionSchedule['rule_state'], string> = {
  enabled: '规则可执行',
  disabled: '规则已停用',
  deleted: '规则已删除',
  invalid: '规则不可执行',
}
function formatScheduleDate(value: string | null) {
  return value === null
    ? '未安排'
    : new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(new Date(value))
}
function intervalLabel(minutes: number) {
  return minutes % 60 === 0 ? `每 ${minutes / 60} 小时` : `每 ${minutes} 分钟`
}
function parseId(value: string | null): number | null {
  if (value === null || !/^[1-9]\d*$/.test(value)) return null
  const id = Number(value)
  return Number.isSafeInteger(id) ? id : null
}
function OccurrenceSummary({
  occurrence,
}: {
  occurrence: CollectionOccurrence
}) {
  return (
    <div className="min-w-0 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            occurrence.status === 'interrupted' ? 'destructive' : 'outline'
          }
        >
          {occurrenceLabels[occurrence.status]}
        </Badge>
        {occurrence.batch_status && (
          <span className="text-sm">
            采集状态：{searchBatchStatusLabel(occurrence.batch_status)}
          </span>
        )}
      </div>
      {occurrence.reason && (
        <p className="text-sm leading-6 text-muted-foreground">
          {reasonLabels[occurrence.reason]}
        </p>
      )}
      {occurrence.status === 'claimed' && (
        <p className="text-sm text-muted-foreground">尚未确认采集开始。</p>
      )}
      {occurrence.status === 'missed' && (
        <p className="text-sm">
          共错过 {occurrence.missed_count} 轮 · 截至{' '}
          {formatScheduleDate(occurrence.missed_until)}
        </p>
      )}
      {occurrence.batch_id !== null && (
        <Link
          className={buttonVariants({
            variant: 'link',
            className: 'h-auto min-h-11 px-0',
          })}
          to={`/collection-batches/${occurrence.batch_id}`}
        >
          查看采集批次 #{occurrence.batch_id}
        </Link>
      )}
    </div>
  )
}
function CursorControls({
  beforeId,
  nextId,
  pending,
  onChange,
  label,
}: {
  beforeId: number | null
  nextId: number | null
  pending: boolean
  onChange: (id: number | null) => void
  label: string
}) {
  if (beforeId === null && nextId === null) return null
  return (
    <nav
      aria-label={`${label}分页`}
      className="flex flex-wrap gap-2 border-t pt-4"
    >
      <Button
        variant="outline"
        disabled={pending || beforeId === null}
        onClick={() => onChange(null)}
      >
        最新{label}
      </Button>
      <Button
        variant="outline"
        disabled={pending || nextId === null}
        onClick={() => onChange(nextId)}
      >
        更早{label}
      </Button>
    </nav>
  )
}

export function CollectionSchedules() {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const scheduleId = parseId(params.get('schedule'))
  const beforeId = parseId(params.get('schedulesBefore'))
  const occurrenceBefore = parseId(params.get('occurrencesBefore'))
  const invalidLink = ['schedule', 'schedulesBefore', 'occurrencesBefore'].some(
    (key) => params.has(key) && parseId(params.get(key)) === null,
  )
  const list = useCollectionSchedules(beforeId ?? undefined)
  const selected = useCollectionSchedule(scheduleId)
  const history = useCollectionOccurrences(
    selected.data,
    occurrenceBefore ?? undefined,
  )
  const [editor, setEditor] = useState<{
    schedule: CollectionSchedule | null
  } | null>(null)
  const [toggle, setToggle] = useState<CollectionSchedule | null>(null)
  const toggledVersion = useCollectionSchedule(toggle?.id ?? null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const historyHeading = useRef<HTMLHeadingElement>(null)
  const createButton = useRef<HTMLButtonElement>(null)
  const toggleStale =
    toggle !== null &&
    toggledVersion.data !== undefined &&
    scheduleConfigurationChanged(toggle, toggledVersion.data)
  const mutation = useMutation({
    mutationFn: (schedule: CollectionSchedule) =>
      updateCollectionSchedule(
        schedule.id,
        scheduleUpdatePayload(schedule, !schedule.enabled),
      ),
    retry: false,
    onSuccess: async (saved) => {
      await cacheSavedSchedule(client, saved)
      setToggle(null)
      setFeedback(
        saved.enabled
          ? saved.available
            ? '定时任务已启用，请查看下一次执行时间。'
            : '启用设置已保存；完整流程尚未开放，当前不会自动执行。'
          : '定时任务已停用，仅停止后续执行；已提交的采集批次继续保留。',
      )
    },
    onError: () => {
      void client.invalidateQueries({
        queryKey: COLLECTION_SCHEDULES_QUERY_KEY,
      })
    },
  })
  useEffect(() => {
    if (selected.data?.id === scheduleId) historyHeading.current?.focus()
  }, [scheduleId, selected.data?.id])
  function changeParams(values: Record<string, number | null>) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      for (const [key, value] of Object.entries(values)) {
        if (value === null) next.delete(key)
        else next.set(key, String(value))
      }
      return next
    })
  }
  function closeHistory() {
    changeParams({ schedule: null, occurrencesBefore: null })
    const trigger = document.getElementById(
      `schedule-history-open-${scheduleId}`,
    )
    const focusTarget = trigger ?? createButton.current
    focusTarget?.focus()
  }
  return (
    <section aria-labelledby="collection-schedules-title" className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-4 border-b sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <h2
              id="collection-schedules-title"
              className="flex items-center gap-2 font-display text-xl"
            >
              <Clock3 className="size-5" aria-hidden />
              定时采集
            </h2>
            <p className="text-sm leading-6 text-muted-foreground">
              按规则周期执行，结果统一保存。到期忙碌则跳过，停机不补采；人工验证仍需到采集批次手动处理。
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={
                list.isFetching || selected.isFetching || history.isFetching
              }
              onClick={() => {
                void client.invalidateQueries({
                  queryKey: COLLECTION_SCHEDULES_QUERY_KEY,
                })
              }}
            >
              <RefreshCw aria-hidden />
              刷新定时任务
            </Button>
            <Button
              ref={createButton}
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => {
                setFeedback(null)
                setEditor({ schedule: null })
              }}
            >
              <Plus aria-hidden />
              新建定时采集
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-5">
          <p className="text-sm text-muted-foreground">
            时间按北京时间显示。
            <Link to="/results" className="ml-1 underline underline-offset-4">
              查看已保存的结果
            </Link>
          </p>
          {feedback && (
            <p role="status" className="text-sm">
              {feedback}
            </p>
          )}
          {invalidLink && (
            <div role="alert" className="space-y-2 text-sm text-destructive">
              <p>定时任务链接中的编号或分页位置无效。</p>
              <Button
                variant="outline"
                onClick={() =>
                  changeParams({
                    schedule: null,
                    schedulesBefore: null,
                    occurrencesBefore: null,
                  })
                }
              >
                重置定时任务视图
              </Button>
            </div>
          )}
          {list.isPending ? (
            <div aria-label="正在加载定时任务" className="space-y-3">
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </div>
          ) : list.isError ? (
            <div role="alert" className="space-y-2">
              <p>{scheduleErrorMessage(list.error)}</p>
              <Button variant="outline" onClick={() => list.refetch()}>
                重新加载定时任务
              </Button>
            </div>
          ) : (
            <>
              {list.data.schedules.length === 0 && (
                <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                  {beforeId
                    ? '这一页没有更早的定时任务。'
                    : '还没有定时任务。新建后先检查规则、平台和间隔，再单独启用。手动采集仍可直接使用。'}
                </p>
              )}
              <div className="space-y-4">
                {list.data.schedules.map((schedule) => (
                  <article
                    key={schedule.id}
                    aria-label={`定时任务 ${schedule.id}：${schedule.rule_name}`}
                    className="min-w-0 space-y-4 rounded-lg border p-4"
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0 space-y-2">
                        <h3 className="font-medium wrap-anywhere">
                          {schedule.rule_name}
                        </h3>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge
                            variant={schedule.enabled ? 'secondary' : 'outline'}
                          >
                            {schedule.enabled ? '已启用' : '已停用'}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            定时任务 #{schedule.id} · 版本 {schedule.revision}
                          </span>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        <Button
                          variant="outline"
                          onClick={() => setEditor({ schedule })}
                          disabled={mutation.isPending}
                        >
                          编辑定时任务
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => {
                            mutation.reset()
                            setToggle(schedule)
                          }}
                          disabled={
                            mutation.isPending ||
                            (!schedule.enabled &&
                              schedule.rule_state !== 'enabled')
                          }
                        >
                          {schedule.enabled ? '停用定时任务' : '启用定时任务'}
                        </Button>
                      </div>
                    </div>
                    <dl className="grid gap-3 text-sm sm:grid-cols-2">
                      <div>
                        <dt className="text-muted-foreground">执行频率</dt>
                        <dd className="mt-1">
                          {intervalLabel(schedule.interval_minutes)} · 每词最多{' '}
                          {schedule.max_results_per_term} 条
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">下一次执行</dt>
                        <dd className="mt-1 font-utility">
                          {formatScheduleDate(schedule.next_due_at)}
                        </dd>
                      </div>
                      <div className="sm:col-span-2">
                        <dt className="text-muted-foreground">采集平台</dt>
                        <dd className="mt-1 flex flex-wrap gap-x-4 gap-y-2">
                          {schedule.platforms.map((platform) => (
                            <span
                              key={platform}
                              className="flex items-center gap-1.5"
                            >
                              <img
                                src={searchPlatformPresenters[platform].logoSrc}
                                alt=""
                                className="size-4"
                              />
                              {searchPlatformPresenters[platform].label}
                            </span>
                          ))}
                        </dd>
                      </div>
                    </dl>
                    {!schedule.available && (
                      <p className="text-sm text-warning-foreground">
                        完整流程尚未开放；可保存定时配置，当前不会自动执行。
                      </p>
                    )}
                    {schedule.rule_state !== 'enabled' && (
                      <p className="text-sm text-warning-foreground">
                        {ruleStateLabels[schedule.rule_state]}。
                        {schedule.enabled
                          ? '到期时将跳过，不会当作成功采集。'
                          : '请选择可执行规则后再启用定时任务。'}
                      </p>
                    )}
                    {schedule.latest_occurrence && (
                      <div className="space-y-2 border-t pt-3">
                        <p className="text-xs text-muted-foreground">
                          最近调度 ·{' '}
                          {formatScheduleDate(
                            schedule.latest_occurrence.due_at,
                          )}
                        </p>
                        <OccurrenceSummary
                          occurrence={schedule.latest_occurrence}
                        />
                      </div>
                    )}
                    <Button
                      id={`schedule-history-open-${schedule.id}`}
                      variant="ghost"
                      aria-expanded={scheduleId === schedule.id}
                      onClick={() =>
                        changeParams({
                          schedule: schedule.id,
                          occurrencesBefore: null,
                        })
                      }
                    >
                      查看定时执行记录
                    </Button>
                  </article>
                ))}
              </div>
              <CursorControls
                beforeId={beforeId}
                nextId={list.data.next_before_id}
                pending={list.isFetching}
                onChange={(id) => changeParams({ schedulesBefore: id })}
                label="定时任务"
              />
            </>
          )}
        </CardContent>
      </Card>
      {scheduleId !== null && (
        <Card aria-labelledby="schedule-history-heading">
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h3
              ref={historyHeading}
              tabIndex={-1}
              id="schedule-history-heading"
              className="font-display text-xl font-semibold"
            >
              定时执行记录 · #{scheduleId}
            </h3>
            <Button variant="ghost" onClick={closeHistory}>
              收起记录
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {selected.isPending ? (
              <p role="status">正在加载定时任务…</p>
            ) : selected.isError ? (
              <div role="alert" className="space-y-2">
                <p>{scheduleErrorMessage(selected.error)}</p>
                <Button variant="outline" onClick={() => selected.refetch()}>
                  重新加载所选任务
                </Button>
              </div>
            ) : (
              <>
                <p className="text-sm wrap-anywhere">
                  {selected.data.rule_name} · 当前版本 {selected.data.revision}{' '}
                  · 下一次执行 {formatScheduleDate(selected.data.next_due_at)}
                </p>
                {history.isPending ? (
                  <p role="status">正在加载执行记录…</p>
                ) : history.isError ? (
                  <div role="alert" className="space-y-2">
                    <p>{scheduleErrorMessage(history.error)}</p>
                    <Button variant="outline" onClick={() => history.refetch()}>
                      重新加载执行记录
                    </Button>
                  </div>
                ) : (
                  history.data && (
                    <>
                      {history.data.occurrences.length === 0 && (
                        <p className="text-sm text-muted-foreground">
                          还没有这一页的执行记录；保存配置不代表已经采集。
                        </p>
                      )}
                      <ol className="space-y-4">
                        {history.data.occurrences.map((occurrence) => (
                          <li
                            key={occurrence.id}
                            className="space-y-3 rounded-lg border p-4"
                          >
                            <p className="text-sm">
                              计划时间 {formatScheduleDate(occurrence.due_at)} ·
                              配置版本 {occurrence.schedule_revision}
                            </p>
                            <OccurrenceSummary occurrence={occurrence} />
                          </li>
                        ))}
                      </ol>
                      <CursorControls
                        beforeId={occurrenceBefore}
                        nextId={history.data.next_before_id}
                        pending={history.isFetching}
                        onChange={(id) =>
                          changeParams({ occurrencesBefore: id })
                        }
                        label="执行记录"
                      />
                    </>
                  )
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
      {editor && (
        <CollectionScheduleEditor
          schedule={editor.schedule}
          onClose={() => setEditor(null)}
          onSaved={(saved) => {
            const creating = editor.schedule === null
            setEditor(null)
            setFeedback(
              creating
                ? '定时任务已创建，当前为停用状态。核对后可单独启用。'
                : '定时配置已保存；已提交的采集批次不受影响。',
            )
            changeParams({
              schedulesBefore: null,
              schedule: saved.id,
              occurrencesBefore: null,
            })
          }}
        />
      )}
      {toggle && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open && !mutation.isPending) setToggle(null)
          }}
        >
          <DialogContent showCloseButton={!mutation.isPending}>
            <DialogHeader>
              <DialogTitle>
                {toggle.enabled ? '停用定时采集？' : '启用定时采集？'}
              </DialogTitle>
              <DialogDescription>
                {toggle.enabled
                  ? '仅停止未来的定时执行。已提交的采集批次不会取消，人工验证暂停仍需在批次详情中处理。'
                  : `将按${intervalLabel(toggle.interval_minutes)}采集“${toggle.rule_name}”。下一次从本次保存时间计算；需要后端服务及可用浏览器，忙碌和停机期间不补采。`}
              </DialogDescription>
            </DialogHeader>
            {!toggle.available && (
              <p className="text-sm text-warning-foreground">
                完整流程尚未开放，本次只保存设置，不会启动自动采集。
              </p>
            )}
            {toggleStale && (
              <div className="space-y-2">
                <p role="alert">定时配置已更新，请核对后重新确认操作。</p>
                <Button
                  variant="outline"
                  onClick={() => {
                    if (toggledVersion.data) setToggle(toggledVersion.data)
                    mutation.reset()
                  }}
                >
                  核对最新设置
                </Button>
              </div>
            )}
            {toggledVersion.isError && (
              <div role="alert" className="space-y-2">
                <p>{scheduleErrorMessage(toggledVersion.error)}</p>
                <Button
                  variant="outline"
                  onClick={() => toggledVersion.refetch()}
                >
                  重新加载任务版本
                </Button>
              </div>
            )}
            {mutation.isError && (
              <p role="alert" className="text-sm text-destructive">
                {scheduleErrorMessage(mutation.error)}
              </p>
            )}
            <DialogFooter>
              <Button
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => setToggle(null)}
              >
                取消
              </Button>
              <Button
                disabled={
                  mutation.isPending ||
                  toggledVersion.isPending ||
                  toggledVersion.isError ||
                  toggleStale ||
                  (!toggle.enabled &&
                    (toggledVersion.data ?? toggle).rule_state !== 'enabled')
                }
                aria-busy={mutation.isPending}
                onClick={() => mutation.mutate(toggle)}
              >
                {mutation.isPending
                  ? '正在保存…'
                  : toggle.enabled
                    ? '确认停用'
                    : '确认启用'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </section>
  )
}
