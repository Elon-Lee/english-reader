import React, { useEffect, useState } from 'react'
import { Alert, Button, Skeleton } from 'antd'
import { getJson } from '../../../api/client'
import MembershipPage from './MembershipPage'

export default function MembershipWorkspace() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    Promise.all([getJson('/api/membership/usage'), getJson('/api/membership/orders')])
      .then(([membership, orders]) => { if (active) setData({ membership, membershipOrders: orders.orders || [] }) })
      .catch(failure => { if (active) setError(failure.message || '会员信息加载失败') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [revision])
  if (loading && !data) return <Skeleton active paragraph={{ rows: 8 }} />
  if (error) return <Alert showIcon type="error" message="会员信息暂时无法加载" description={error} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} />
  return <MembershipPage {...data} onRefresh={() => setRevision(value => value + 1)} />
}
