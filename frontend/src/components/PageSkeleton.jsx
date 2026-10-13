import React from 'react'
import { Card, Col, Row, Skeleton, Space } from 'antd'

export default function PageSkeleton({ reader = false }) {
  if (reader) {
    return <div className="page-skeleton page-skeleton-reader" aria-label="页面数据加载中">
      <Skeleton.Input active block size="large" />
      <Row gutter={[16, 16]}>
        <Col span={reader ? 16 : 24}><Card><Skeleton active title paragraph={{ rows: 10 }} /></Card></Col>
        <Col span={8}><Card><Skeleton active title paragraph={{ rows: 8 }} /></Card></Col>
      </Row>
      <Skeleton.Input active block size="large" />
    </div>
  }
  return <div className="page-stack page-skeleton" aria-label="页面数据加载中">
    <div className="page-skeleton-heading">
      <Space direction="vertical" size={12} style={{ width: 'min(620px, 72%)' }}>
        <Skeleton.Input active size="small" style={{ width: 160 }} />
        <Skeleton.Input active size="large" style={{ width: 360, maxWidth: '100%' }} />
        <Skeleton.Input active block size="small" />
      </Space>
      <Skeleton.Button active size="large" />
    </div>
    <Row gutter={[16, 16]}>
      {[0, 1, 2, 3].map(item => <Col xs={24} sm={12} xl={6} key={item}><Card><Skeleton active title paragraph={{ rows: 2 }} /></Card></Col>)}
    </Row>
    <Row gutter={[20, 20]}>
      <Col xs={24} xl={16}><Card><Skeleton active title paragraph={{ rows: 7 }} /></Card></Col>
      <Col xs={24} xl={8}><Card><Skeleton active title paragraph={{ rows: 7 }} /></Card></Col>
    </Row>
  </div>
}
