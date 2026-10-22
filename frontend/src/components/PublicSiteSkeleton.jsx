import React from 'react'
import { Skeleton } from 'antd'

export default function PublicSiteSkeleton({ page = 'home' }) {
  return <div className="public-site public-loading" role="status" aria-label="官网加载中" aria-busy="true">
    <header className="public-header">
      <div className="public-loading-brand"><Skeleton.Avatar active shape="square" size={36} /><Skeleton.Input active size="small" style={{ width: 90 }} /></div>
      <div className="public-loading-nav">{[0, 1, 2].map(item => <Skeleton.Input key={item} active size="small" style={{ width: 40 }} />)}</div>
      <div className="public-loading-actions"><Skeleton.Button active /><Skeleton.Button active /></div>
    </header>
    {page === 'home' ? <main className="public-hero">
      <div className="public-hero-copy">
        <Skeleton.Input active size="small" style={{ width: 240, maxWidth: '100%' }} />
        <div className="public-loading-title"><Skeleton.Input active block /><Skeleton.Input active block /></div>
        <Skeleton active title={false} paragraph={{ rows: 3, width: ['100%', '100%', '76%'] }} />
        <div className="public-loading-actions"><Skeleton.Button active size="large" /><Skeleton.Button active size="large" /></div>
        <Skeleton active title={false} paragraph={{ rows: 1, width: '90%' }} />
      </div>
      <div className="public-hero-visual"><div className="public-device-frame public-loading-preview"><Skeleton.Node active><span /></Skeleton.Node></div></div>
    </main> : <main className={page === 'pricing' ? 'public-section public-pricing' : 'public-support'}>
      <div className="public-section-heading"><Skeleton active paragraph={{ rows: 2 }} /></div>
      <div className="public-loading-columns">{[0, 1, 2].map(item => <div key={item}><Skeleton active paragraph={{ rows: page === 'pricing' ? 8 : 3 }} /></div>)}</div>
    </main>}
  </div>
}
