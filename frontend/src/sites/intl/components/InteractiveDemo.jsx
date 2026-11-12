import React from 'react'
import { Button, Typography } from 'antd'

export default function InteractiveDemo({ authenticated }) {
  return <section className="public-product-story" aria-label="阅读器产品界面预览"><div className="public-story-copy"><Typography.Text>READ IN CONTEXT</Typography.Text><Typography.Title level={2}>在原文中理解，而后继续阅读。</Typography.Title><Typography.Paragraph>产品界面预览。登录后可用自己的读物体验原音播放、逐句阅读和语境查词。</Typography.Paragraph><Button href={authenticated ? '/app?screen=catalog' : '/login'}>进入阅读空间</Button></div><div className="public-screenshot-stage"><img src="/product/reader-lookup-20261026.webp" width="2560" height="1338" loading="lazy" alt="阅读器产品界面预览：原声、逐句字幕和语境查词" /></div></section>
}
