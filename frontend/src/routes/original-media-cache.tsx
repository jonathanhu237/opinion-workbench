import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { Button, buttonVariants } from '@/components/ui/button'
import { fetchMediaCache, originalMediaUrl } from '@/lib/api/media-cache'

const labels = {
  cached: '原文件仍在本地',
  not_acquired: '当时未取得原文件',
  not_stored: '没有持久缓存（可能未启用或容量不足）',
  missing: '本地原文件已丢失',
  corrupt: '本地文件校验失败',
  cleared: '原文件已按策略清理',
  unavailable: '无法安全读取本地原文件',
}

export function OriginalMediaCache({ attemptId }: { attemptId: number }) {
  const [enabled, setEnabled] = useState(false)
  const query = useQuery({
    queryKey: ['media-cache', attemptId],
    enabled,
    retry: false,
    queryFn: ({ signal }) => fetchMediaCache(attemptId, signal),
  })
  return (
    <section className="mt-3 space-y-2">
      <p className="text-xs text-muted-foreground">
        上面记录的是当时的获取和分析情况。原文件采用有期限的本地缓存；
        检查或打开本地缓存不会重新下载，清理也不会删除正文、总结或报告。
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={query.isFetching}
        onClick={() => {
          setEnabled(true)
          if (enabled) void query.refetch()
        }}
      >
        {query.isFetching ? '正在校验本地文件…' : '检查本地原媒体'}
      </Button>
      {query.isError && (
        <p role="status" className="text-sm">
          无法检查本地缓存，请稍后重试。没有启动下载。
        </p>
      )}
      {query.data && (
        <ul className="space-y-2 text-sm">
          {query.data.items.map((item) => (
            <li
              key={item.position}
              className="flex flex-wrap items-center gap-2"
            >
              <span>
                {item.position + 1}. {item.kind === 'image' ? '图片' : '视频'} ·{' '}
                {labels[item.state]}
              </span>
              {item.state === 'cached' && (
                <a
                  className={buttonVariants({ variant: 'outline', size: 'sm' })}
                  href={originalMediaUrl(attemptId, item.position)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  打开本地{item.kind === 'image' ? '图片' : '视频'}
                </a>
              )}
            </li>
          ))}
          {query.data.items.length === 0 && <li>这次分析没有媒体记录。</li>}
        </ul>
      )}
    </section>
  )
}
