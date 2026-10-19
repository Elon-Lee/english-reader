import React, { useMemo } from 'react'
import { Button, Typography } from 'antd'
import { PublicHeader } from './PublicSite'
import terms from '../../../reader/legal/terms.html?raw'
import privacy from '../../../reader/legal/privacy.html?raw'
import contentPolicy from '../../../reader/legal/content-policy.html?raw'
import refunds from '../../../reader/legal/refunds.html?raw'
import copyright from '../../../reader/legal/copyright.html?raw'

const sources = { '/terms': terms, '/privacy': privacy, '/content-policy': contentPolicy, '/refunds': refunds, '/copyright': copyright }
export const isLegalPath = path => Object.hasOwn(sources, path)
export const legalPageTitle = path => sources[path]?.match(/<title>(.*?)<\/title>/)?.[1]

// Reuse the maintained policy text, rendering only supported document elements.
function renderNode(node, key) {
  if (node.nodeType === 3) return node.textContent
  const children = Array.from(node.childNodes).map(renderNode)
  if (node.tagName === 'H1') return <Typography.Title key={key}>{children}</Typography.Title>
  if (node.tagName === 'H2') return <Typography.Title level={2} key={key}>{children}</Typography.Title>
  if (node.tagName === 'P') return <Typography.Paragraph key={key}>{children}</Typography.Paragraph>
  if (node.tagName === 'STRONG') return <Typography.Text strong key={key}>{children}</Typography.Text>
  if (node.tagName === 'A' && /^\/(?!\/)/.test(node.getAttribute('href') || '')) return <a key={key} href={node.getAttribute('href')}>{children}</a>
  return null
}

export default function LegalPage({ path, authenticated }) {
  const content = useMemo(() => Array.from(new DOMParser().parseFromString(sources[path], 'text/html').body.childNodes).map(renderNode), [path])
  return <div className="public-site"><PublicHeader authenticated={authenticated} compact /><main className="public-policy"><Button type="link" href="/">← 返回首页</Button>{content}<Button href="/support">联系支持</Button></main></div>
}
