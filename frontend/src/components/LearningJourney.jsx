import React, { useState } from 'react'
import { Alert, Button, Card, Skeleton, Space, Steps, Typography } from 'antd'
import { updateJourney } from '../api/journey'
import useJourney from '../hooks/useJourney'

const { Paragraph, Text, Title } = Typography

export function PurchaseRecoveryView({ pending }) {
  const [clearing, setClearing] = useState(false)
  const [error, setError] = useState('')
  if (!pending) return null
  const clear = async () => {
    setClearing(true); setError('')
    try { await updateJourney({ action: 'clear_purchase' }) }
    catch (failure) { setError(failure.message || '暂时无法移除，请重试') }
    finally { setClearing(false) }
  }
  return <div className="purchase-recovery"><Alert showIcon type="info"
    message={pending.phase === 'departed' ? `已前往购买${pending.name}，回来兑换后才会开通` : `继续上次选择的${pending.name}`}
    description={<><Text>已付款可粘贴云猫发放的兑换码；尚未付款也可以重新比较方案。</Text>{error && <Paragraph type="danger" role="alert">{error}</Paragraph>}</>}
    action={<Space><Button type="primary" href={`/app?screen=membership&purchase=${encodeURIComponent(pending.slug)}`}>继续购买 / 兑换</Button><Button loading={clearing} onClick={clear}>移除提醒</Button></Space>} /></div>
}

export function PurchaseRecovery({ authenticated = true }) {
  const { state, error, reload } = useJourney(authenticated)
  if (!authenticated) return null
  if (error) return <Alert className="purchase-recovery" type="warning" showIcon message="暂时无法读取上次选择的方案" action={<Button onClick={reload}>重试</Button>} />
  return <PurchaseRecoveryView pending={state?.pendingPurchase} />
}

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
    <PurchaseRecoveryView pending={state?.pendingPurchase} />
    {guide && !complete && (guide.dismissed
      ? <Button className="learning-guide-restore" type="link" loading={saving} onClick={() => update('restore_guide')}>打开首次学习指引</Button>
      : <Card className="learning-guide"><div className="learning-guide-heading"><div><Text className="card-kicker">第一次使用拾页</Text><Title level={3}>读懂一句话，留下第一个生词</Title></div><Button type="text" loading={saving} onClick={() => update('dismiss_guide')}>跳过指引</Button></div>
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
