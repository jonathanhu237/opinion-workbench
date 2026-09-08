import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AISettings } from '@/routes/ai-settings'

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
    </div>
  )
}
