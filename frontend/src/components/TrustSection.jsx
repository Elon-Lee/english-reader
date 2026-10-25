import React, { useEffect, useState } from 'react'
import { Skeleton } from 'antd'
import { getJson } from '../api/client'

export default function TrustSection() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    getJson('/api/public/stats')
      .then(data => {
        if (active) {
          setStats(data)
          setLoading(false)
        }
      })
      .catch(() => {
        if (active) {
          // 失败时使用默认数据，不影响页面展示
          setStats({ totalSentences: 0, totalHours: 0, retentionRate: 0 })
          setLoading(false)
        }
      })
    return () => { active = false }
  }, [])

  if (loading) {
    return (
      <section className="public-trust">
        <h2>已经有学习者在用拾页建立习惯</h2>
        <div className="trust-stats">
          {[1, 2, 3].map(i => (
            <div className="trust-metric" key={i}>
              <Skeleton.Input active size="large" style={{ width: 120 }} />
              <Skeleton.Input active size="small" style={{ width: 100, marginTop: 8 }} />
            </div>
          ))}
        </div>
      </section>
    )
  }

  // 只在有真实数据时展示
  if (!stats || (stats.totalSentences === 0 && stats.totalHours === 0)) {
    return null
  }

  const formatNumber = (num) => {
    if (num >= 10000) {
      return `${(num / 10000).toFixed(1)}万`
    }
    return num.toLocaleString('zh-CN')
  }

  return (
    <section className="public-trust">
      <h2>已经有学习者在用拾页建立习惯</h2>

      <div className="trust-stats">
        {stats.totalSentences > 0 && (
          <div className="trust-metric">
            <b>{formatNumber(stats.totalSentences)}</b>
            <span>句子被精读理解</span>
            <small>近 30 天</small>
          </div>
        )}

        {stats.totalHours > 0 && (
          <div className="trust-metric">
            <b>{formatNumber(stats.totalHours)}</b>
            <span>小时沉浸学习</span>
            <small>近 30 天</small>
          </div>
        )}

        {stats.retentionRate > 0 && (
          <div className="trust-metric">
            <b>{stats.retentionRate}%</b>
            <span>用户坚持 30 天以上</span>
            <small>近 60 天留存</small>
          </div>
        )}
      </div>
    </section>
  )
}
