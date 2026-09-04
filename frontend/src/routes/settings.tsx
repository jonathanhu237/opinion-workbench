import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AISettings } from '@/routes/ai-settings'
import { MediaSettings } from '@/routes/media-settings'

export function Settings() {
  return (
    <div className="flex flex-col gap-6">
      <Card id="ai" className="scroll-mt-24">
        <CardHeader>
          <CardTitle>
            <h2>AI 配置</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AISettings embedded />
        </CardContent>
      </Card>

      <Card id="media" className="scroll-mt-24">
        <CardHeader>
          <CardTitle>
            <h2>媒体缓存</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <MediaSettings embedded />
        </CardContent>
      </Card>
    </div>
  )
}
