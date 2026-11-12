import React from 'react'
import { Card, Skeleton } from 'antd'

export default function PublicSiteSkeleton() {
  return <main className="private-entry" role="status" aria-label="页面加载中" aria-busy="true"><Card className="private-entry-card"><Skeleton active paragraph={{ rows: 3 }} /></Card></main>
}
