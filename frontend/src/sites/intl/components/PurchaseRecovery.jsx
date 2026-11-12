import React, { useState } from 'react'
import { Alert, Button, Card, Skeleton, Space, Steps, Typography } from 'antd'
import { updateJourney } from '../../../api/journey'
import useJourney from '../../../hooks/useJourney'

const { Paragraph, Text, Title } = Typography

export function PurchaseRecoveryView({ pending }) {
  const [clearing, setClearing] = useState(false)
  const [error, setError] = useState('')
  if (!pending) return null
  const clear = async () => {
    setClearing(true); setError('')
    try { await updateJourney({ action: 'clear_purchase' }) }
    catch (failure) { setError(failure.message || '暂时无法关闭提醒，请重试') }
    finally { setClearing(false) }
  }
  return <div className="purchase-recovery"><Alert showIcon type="info"
    message={pending.phase === 'departed' ? `已前往购买${pending.name}，回来兑换后才会开通` : `继续上次选择的${pending.name}`}
    description={<><Text>已付款可粘贴云猫发放的兑换码；尚未付款也可以重新比较方案。</Text>{error && <Paragraph type="danger" role="alert">{error}</Paragraph>}</>}
    action={<Space><Button type="primary" href={`/app?screen=membership&purchase=${encodeURIComponent(pending.slug)}`}>继续购买 / 兑换</Button><Button loading={clearing} onClick={clear}>不再提醒</Button></Space>} /></div>
}

export function PurchaseRecovery({ authenticated = true }) {
  const { state, error, reload } = useJourney(authenticated)
  if (!authenticated) return null
  if (error) return <Alert className="purchase-recovery" type="warning" showIcon message="暂时无法读取上次选择的方案" action={<Button onClick={reload}>重试</Button>} />
  return <PurchaseRecoveryView pending={state?.pendingPurchase} />
}
