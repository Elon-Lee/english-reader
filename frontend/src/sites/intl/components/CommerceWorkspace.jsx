import React, { useEffect, useState } from 'react'
import { Alert, Button, Skeleton } from 'antd'
import { getJson, postJson } from '../../../api/client'
import CommerceAdmin from './CommerceAdmin'
import BenefitAdmin from './BenefitAdmin'
import RedemptionAdmin from './RedemptionAdmin'
import { PaymentMethodSettings, PaymentOrdersAdmin, RedemptionRecordsAdmin } from './PaymentOperations'

function CommerceWorkspace({ section, messageApi }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    Promise.all([getJson('/api/admin/commerce/products'), getJson('/api/admin/commerce/entitlements')])
      .then(([products, entitlements]) => { if (active) setData({ products: products.products || [], entitlements }) })
      .catch(failure => { if (active) setError(failure.message || '商业配置加载失败') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [revision])
  const write = async (path, payload, success) => {
    try {
      const result = await postJson(path, payload)
      messageApi.success(success)
      setRevision(value => value + 1)
      return result
    } catch (failure) { messageApi.error(failure.message || '保存失败'); throw failure }
  }
  if (loading && !data) return <Skeleton active paragraph={{ rows: 6 }} />
  if (error) return <Alert showIcon type="error" message={error} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} />
  if (section === 'redemptions') return <RedemptionAdmin products={data.products} />
  if (section === 'benefits') return <BenefitAdmin entitlements={data.entitlements} onCreate={payload => write('/api/admin/commerce/configured-benefits', payload, '配置权益已创建')} onUpdate={(id, payload) => write(`/api/admin/commerce/configured-benefits/${encodeURIComponent(id)}`, payload, '配置权益已更新')} />
  return <CommerceAdmin {...data}
    onCreateProduct={payload => write('/api/admin/commerce/products', payload, '套餐已创建')}
    onCreateVersion={(id, payload) => write(`/api/admin/commerce/products/${encodeURIComponent(id)}/versions`, payload, '商品版本已保存为草稿')}
    onPublishVersion={id => write(`/api/admin/commerce/versions/${encodeURIComponent(id)}/publish`, {}, '商品版本已发布')}
    onUpdatePrice={(id, payload) => write(`/api/admin/commerce/products/${encodeURIComponent(id)}/price`, payload, '新价格已发布，历史订单及权益保持不变')}
    onSetProductActive={(id, active) => write(`/api/admin/commerce/products/${encodeURIComponent(id)}/status`, { active }, active ? '商品已恢复销售' : '商品已停止新售')}
    onDeleteProduct={id => write(`/api/admin/commerce/products/${encodeURIComponent(id)}/delete`, {}, '未上架套餐已删除')}
  />
}

export function siteAdminTabs(activeTab, { messageApi }) {
  return [
    { key: 'plans', label: '套餐管理', children: activeTab === 'plans' ? <CommerceWorkspace section="plans" messageApi={messageApi} /> : null },
    { key: 'redemptions', label: '兑换码库存', children: activeTab === 'redemptions' ? <CommerceWorkspace section="redemptions" messageApi={messageApi} /> : null },
    { key: 'redemption-records', label: '兑换记录', children: activeTab === 'redemption-records' ? <RedemptionRecordsAdmin /> : null },
    { key: 'payment-settings', label: '支付方式', children: activeTab === 'payment-settings' ? <PaymentMethodSettings /> : null },
    { key: 'payment-orders', label: '支付订单', children: activeTab === 'payment-orders' ? <PaymentOrdersAdmin /> : null },
    { key: 'benefits', label: '套餐内容', children: activeTab === 'benefits' ? <CommerceWorkspace section="benefits" messageApi={messageApi} /> : null },
  ]
}
