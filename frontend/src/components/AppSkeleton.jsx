import React from 'react'
import { Layout, Skeleton } from 'antd'
import PageSkeleton from './PageSkeleton'

const { Sider, Header, Content } = Layout

export default function AppSkeleton({ reader = false }) {
  if (reader) return <main className="modern-reader app-loading-reader" role="status" aria-label="正在恢复登录状态" aria-busy="true"><PageSkeleton reader /></main>

  return <Layout className="modern-shell app-loading" role="status" aria-label="正在恢复登录状态" aria-busy="true">
    <Sider width={248} className="modern-sider app-loading-sider" breakpoint="lg" collapsedWidth={0} trigger={null}>
      <div className="modern-brand"><Skeleton.Avatar active shape="square" size={38} /><Skeleton.Input active size="small" style={{ width: 110 }} /></div>
      <div className="app-loading-nav">{Array.from({ length: 7 }, (_, index) => <Skeleton.Input key={index} active block style={{ width: '100%' }} />)}</div>
      <div className="sider-bottom"><Skeleton active title={false} paragraph={{ rows: 2 }} /></div>
    </Sider>
    <Layout>
      <Header className="modern-header"><Skeleton.Input active size="small" style={{ width: 220 }} /><Skeleton.Avatar active size={32} /></Header>
      <Content className="modern-content"><PageSkeleton /></Content>
    </Layout>
  </Layout>
}
