import React, { useState } from 'react'
import { Empty, Typography } from 'antd'

export const formatBytes = value => {
  if (value == null) return '—'
  const number = Number(value), units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  const index = number > 0 ? Math.min(units.length - 1, Math.floor(Math.log(number) / Math.log(1024))) : 0
  return `${(number / 1024 ** index).toFixed(index ? 2 : 0)} ${units[index]}`
}

export default function AdminTelemetryChart({ points, valueKey, labelKey, label, format = String, line = false, fixedMax }) {
  const [hovered, setHovered] = useState(null)
  const usable = points.filter(point => point[valueKey] != null)
  if (!usable.length || (!line && !usable.some(point => Number(point[valueKey]) > 0))) return <Empty description={line ? '正在积累采样数据' : '该时段暂无新增资源'} />
  const max = fixedMax || Math.max(1, ...usable.map(point => Number(point[valueKey]))) * 1.1
  const width = 1000, height = 230, left = 100, right = 25, top = 18, bottom = 38
  const plotWidth = width - left - right, plotHeight = height - top - bottom
  const x = index => left + (index + .5) * plotWidth / points.length
  const y = value => top + plotHeight * (1 - Math.min(max, Math.max(0, Number(value))) / max)
  const selected = hovered != null && points[hovered] ? points[hovered] : usable.at(-1)
  const sparse = Math.max(1, Math.ceil(points.length / 8))
  return <div className="admin-telemetry-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      {[0, 1, 2, 3, 4].map(tick => { const value = max * tick / 4; return <g key={tick}><line x1={left} y1={y(value)} x2={width - right} y2={y(value)} stroke="#e1e8e1" /><text x={left - 12} y={y(value) + 4} textAnchor="end">{format(value)}</text></g> })}
      {line && points.map((point, index) => index && point[valueKey] != null && points[index - 1][valueKey] != null ? <line key={index} x1={x(index - 1)} y1={y(points[index - 1][valueKey])} x2={x(index)} y2={y(point[valueKey])} stroke="#31715a" strokeWidth="2.5" /> : null)}
      {points.map((point, index) => <g key={`${point[labelKey]}-${index}`}>
        {point[valueKey] != null && (line ? <circle cx={x(index)} cy={y(point[valueKey])} r="4" fill="#31715a" /> : <rect x={x(index) - Math.max(1, plotWidth / points.length * .32)} y={y(point[valueKey])} width={Math.max(1, plotWidth / points.length * .64)} height={top + plotHeight - y(point[valueKey])} rx="2" fill="#659478" />)}
        <rect x={left + index * plotWidth / points.length} y={top} width={plotWidth / points.length} height={plotHeight} fill="transparent" tabIndex={0} role="button" aria-label={`${point[labelKey]}，${label} ${format(point[valueKey])}`} onMouseEnter={() => setHovered(index)} onFocus={() => setHovered(index)} onClick={() => setHovered(index)}><title>{point[labelKey]} · {format(point[valueKey])}</title></rect>
        {(index % sparse === 0 || index === points.length - 1) && <text x={x(index)} y={height - 12} textAnchor="middle">{point[labelKey]}</text>}
      </g>)}
    </svg>
    <Typography.Text type="secondary" role="status">{selected[labelKey]} · {label} {format(selected[valueKey])}{selected.assets != null ? ` · 新增资产 ${selected.assets} 个 · 衍生文件 ${selected.variants} 个 · 登记空间 ${formatBytes(selected.bytes)}` : ''}</Typography.Text>
  </div>
}
