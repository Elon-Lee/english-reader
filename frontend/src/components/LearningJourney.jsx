import React, { useState } from 'react'
import { Alert, Button, Card, Skeleton, Space, Steps, Typography } from 'antd'
import { updateJourney } from '../api/journey'
import useJourney from '../hooks/useJourney'

const { Paragraph, Text, Title } = Typography

export default function LearningJourney({ continueBook, selectScreen, openReader }) {
  const { state, loading, error, reload } = useJourney()
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const guide = state?.guide
  const complete = guide?.hasRead && guide?.hasWord
  const update = async action => {
    setSaving(true); setSaveError('')
    try { await updateJourney({ action }) }
    catch (failure) { setSaveError(failure.message || '暂时无法保存，请重试') }
    finally { setSaving(false) }
  }
  if (loading && !state) return <Card><Skeleton active title={false} paragraph={{ rows: 2 }} /></Card>
  if (error) return <Alert type="warning" showIcon message="学习指引暂时无法读取" description={error} action={<Button onClick={reload}>重试</Button>} />
  const start = () => continueBook ? openReader(continueBook, { guided: true }) : selectScreen('catalog', 'onboarding')
  return <>
    {guide && !complete && (guide.dismissed
      ? <Button className="learning-guide-restore" type="link" loading={saving} onClick={() => update('restore_guide')}>打开首次学习指引</Button>
      : <Card className="learning-guide"><div className="learning-guide-heading"><div><Text className="card-kicker">第一次使用 纸间微光</Text><Title level={3}>读懂一句话，留下第一个生词</Title></div><Button type="text" loading={saving} onClick={() => update('dismiss_guide')}>跳过指引</Button></div>
        <Steps size="small" items={[
          { title: '挑一篇内容', description: '去书城试读，喜欢后加入书架', status: guide.hasBook ? 'finish' : 'process' },
          { title: '听读一句', description: '播放原音或阅读正文，结束时保存学习', status: guide.hasRead ? 'finish' : guide.hasBook ? 'process' : 'wait' },
          { title: '保存一个生词', description: '点击正文单词，再选择认识程度', status: guide.hasWord ? 'finish' : guide.hasRead ? 'process' : 'wait' },
        ]} />
        <div className="learning-guide-actions"><Text type="secondary">从能理解大意的短内容开始。进度自动保存，下次从原处继续。</Text><Button type="primary" onClick={start}>{continueBook ? '继续这篇，完成首次学习' : '去书城挑选内容'} →</Button></div>
      </Card>)}
    {saveError && <Alert type="error" showIcon message={saveError} />}
  </>
}
