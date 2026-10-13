import React, { useEffect, useMemo, useState } from 'react'
import { ArrowRightOutlined, CheckCircleFilled, CustomerServiceOutlined, LockOutlined, PlayCircleFilled } from '@ant-design/icons'
import { Alert, Button, Card, Col, Empty, Modal, Row, Skeleton, Space, Tag, Typography } from 'antd'

import { getJson, postJson } from '../api/client'

const { Paragraph, Text, Title } = Typography

function formatPrice(cents) {
  return `¥${(Number(cents || 0) / 100).toFixed(0)}`
}

function PublicHeader({ authenticated, compact = false }) {
  return <header className={`public-header ${compact ? 'is-compact' : ''}`}>
    <a className="public-brand" href="/"><span className="public-brand-mark">拾</span><span><b>拾页</b><small>ENGLISH WORKSPACE</small></span></a>
    <nav aria-label="公开站点导航"><a href="/#product">产品</a><a href="/pricing">套餐</a><a href="/support">支持</a></nav>
    <Space><Button href={authenticated ? '/app' : '/login'}>{authenticated ? '进入控制台' : '登录'}</Button><Button type="primary" href="/pricing">查看套餐</Button></Space>
  </header>
}

function ProductCard({ product, authenticated }) {
  return <Card className={`public-price-card ${product.featured ? 'is-featured' : ''}`}>
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      <div>{product.featured && <Tag color="green">推荐</Tag>}<Text className="public-plan-family">{product.family === 'pro' ? 'PRO' : 'ADVANCED'}</Text></div>
      <div><Title level={3}>{product.shortName}</Title><Paragraph>{product.tagline}</Paragraph></div>
      <div className="public-price"><b>{formatPrice(product.amountCents)}</b><span> / {product.durationDays} 天</span></div>
      <Text type="secondary">单次购买，不自动续费</Text>
      <ul>{product.benefits.slice(0, 6).map(item => <li key={item}><CheckCircleFilled />{item}</li>)}</ul>
      <Button block type={product.featured ? 'primary' : 'default'} size="large" href={authenticated ? `/purchase/${product.slug}` : `/login?next=${encodeURIComponent(`/purchase/${product.slug}`)}`}>{authenticated ? '选择此方案' : '登录后购买'}</Button>
    </Space>
  </Card>
}

export function PricingSection({ authenticated, products, loading = false, title = '选一个与你节奏相配的期限' }) {
  return <section className="public-section public-pricing" id="pricing"><div className="public-section-heading"><Text>MEMBERSHIP</Text><Title level={2}>{title}</Title><Paragraph>所有方案均为固定期限权益。没有默认勾选，没有自动续费，到期前由你决定是否继续。</Paragraph></div>{loading ? <Row gutter={[20, 20]}>{[1, 2, 3, 4].map(item => <Col xs={24} md={12} xl={6} key={item}><Card><Skeleton active /></Card></Col>)}</Row> : products.length ? <Row gutter={[20, 20]}>{products.map(product => <Col xs={24} md={12} xl={6} key={product.id}><ProductCard product={product} authenticated={authenticated} /></Col>)}</Row> : <Empty description="套餐正在准备中" />}</section>
}

export default function PublicSite({ authenticated, page = 'home' }) {
  const [catalog, setCatalog] = useState({ products: [], support: { value: '289614546' }, payment: {} })
  const [loading, setLoading] = useState(true)
  useEffect(() => { getJson('/api/commerce/products', { products: [], support: { value: '289614546' }, payment: {} }).then(setCatalog).finally(() => setLoading(false)) }, [])
  const yearly = useMemo(() => catalog.products.filter(item => item.durationDays >= 365), [catalog.products])

  if (page === 'pricing') return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><PricingSection authenticated={authenticated} products={catalog.products} loading={loading} title="一次购买，专注学完这一程" /><TrustFooter support={catalog.support} /></main>
  if (page === 'support') return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-support"><Text>SUPPORT</Text><Title>购买前后，都有人回应</Title><Paragraph>套餐、支付、退款或账号问题，请联系 QQ <b>{catalog.support?.value || '289614546'}</b>。我们会在 1 个工作日内响应，并尽量在 3 个工作日内给出处理结论。</Paragraph><Row gutter={[20, 20]}><Col xs={24} md={8}><Card><CustomerServiceOutlined /><Title level={4}>购买咨询</Title><Text>确认套餐期限、权益和账号绑定方式。</Text></Card></Col><Col xs={24} md={8}><Card><LockOutlined /><Title level={4}>支付与退款</Title><Text>提供订单号、注册邮箱和购买时间，我们会核实处理。</Text></Card></Col><Col xs={24} md={8}><Card><CheckCircleFilled /><Title level={4}>内容与版权</Title><Text>私人材料仅用于个人学习，官方内容仅使用公版或授权资源。</Text></Card></Col></Row></section><TrustFooter support={catalog.support} /></main>

  return <main className="public-site">
    <PublicHeader authenticated={authenticated} />
    <section className="public-hero">
      <div className="public-hero-copy"><Text>为认真学英语的人做的阅读工作台</Text><Title>不是看过。<br />是终于读懂。</Title><Paragraph>材料收藏了一堆，句子还是听不清、读不透、记不住。拾页把文章、音频和视频拆成可以逐句精读、跟读与复习的学习过程。</Paragraph><Space size={14}><Button type="primary" size="large" href={authenticated ? '/app' : '/login'}>{authenticated ? '继续学习' : '开始使用'}<ArrowRightOutlined /></Button><Button size="large" href="#product">看看它怎么工作</Button></Space><div className="public-hero-notes"><span><CheckCircleFilled /> 使用原始音视频</span><span><CheckCircleFilled /> 私人学习空间</span><span><CheckCircleFilled /> 学习记录可积累</span></div></div>
      <div className="public-hero-visual" aria-label="拾页逐句阅读器产品画面"><div className="public-device-frame"><img src="/product/reader-word-panel.jpg" alt="拾页视频逐句学习、单词释义和跟读界面" /></div><div className="public-floating-note"><PlayCircleFilled /><span><b>逐句同步</b><small>原声、字幕与解释保持在同一个学习现场</small></span></div></div>
    </section>

    <section className="public-pain"><Text>真正的问题，不是缺少材料</Text><Title level={2}>而是每次学习都从零开始。</Title><Row gutter={[28, 28]}><Col xs={24} md={8}><div><b>读到一半就放弃</b><p>长文章和视频没有清晰切分，难点出现时只能来回拖动。</p></div></Col><Col xs={24} md={8}><div><b>查完的词又忘了</b><p>词典、上下文与复习彼此分离，知道意思却没有形成记忆。</p></div></Col><Col xs={24} md={8}><div><b>学了多久没有答案</b><p>零散工具不记录你的阅读位置、投入时间和真实进度。</p></div></Col></Row></section>

    <section className="public-product-story" id="product">
      <div className="public-story-copy"><Text>READ DEEPLY</Text><Title level={2}>一句一句，把模糊变清楚。</Title><Paragraph>原始视频、字幕、词义、语法和跟读并排工作。遇到难句时停下来理解，理解之后继续听，不需要在多个工具之间切换。</Paragraph></div>
      <div className="public-screenshot-stage"><img src="/product/reader-overview.jpg" alt="拾页逐句视频阅读器完整界面" /></div>
    </section>
    <section className="public-product-story reverse">
      <div className="public-story-copy"><Text>KEEP THE THREAD</Text><Title level={2}>今天学到哪里，明天从那里继续。</Title><Paragraph>私人书架、阅读位置、学习时长和复习任务集中在一个空间。你的每一次投入，都能成为下一次学习的起点。</Paragraph></div>
      <div className="public-screenshot-stage"><img src="/product/workspace-overview.png" alt="拾页个人英语学习空间" /></div>
    </section>
    <section className="public-product-story">
      <div className="public-story-copy"><Text>SEE THE PROGRESS</Text><Title level={2}>看见积累，才更容易坚持。</Title><Paragraph>学习天数、听读时间、完成句子和热力记录形成可回看的轨迹。不用凭感觉猜测自己有没有进步。</Paragraph></div>
      <div className="public-screenshot-stage"><img src="/product/learning-insights.png" alt="拾页英语学习记录与热力图" /></div>
    </section>

    <PricingSection authenticated={authenticated} products={yearly.length ? yearly : catalog.products} loading={loading} title="给自己一段不被打断的学习时间" />
    <section className="public-final-cta"><Text>START WHERE YOU ARE</Text><Title level={2}>不用准备更多材料。<br />从你已经想读懂的那一篇开始。</Title><Space><Button type="primary" size="large" href={authenticated ? '/app' : '/login'}>{authenticated ? '进入学习空间' : '登录拾页'}</Button><Button size="large" href="/pricing">查看全部套餐</Button></Space></section>
    <TrustFooter support={catalog.support} />
  </main>
}

function TrustFooter({ support }) {
  return <footer className="public-footer"><div className="public-brand"><span className="public-brand-mark">拾</span><span><b>拾页</b><small>ENGLISH WORKSPACE</small></span></div><div><a href="/terms">用户协议</a><a href="/privacy">隐私政策</a><a href="/content-policy">内容规则</a><a href="/copyright">版权投诉</a><a href="/refunds">退款规则</a></div><Text>客服 QQ：{support?.value || '289614546'} · 固定期限权益，不自动续费</Text></footer>
}

export function PurchasePage({ authenticated }) {
  const slug = decodeURIComponent(location.pathname.split('/purchase/')[1] || '')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [paying, setPaying] = useState(false)
  const [order, setOrder] = useState(null)
  const orderId = new URLSearchParams(location.search).get('order') || ''
  useEffect(() => { getJson(`/api/commerce/products/${encodeURIComponent(slug)}`, null).then(setData).finally(() => setLoading(false)) }, [slug])
  useEffect(() => {
    if (!authenticated || !orderId) return undefined
    let stopped = false
    const refresh = async () => {
      try { const result = await getJson(`/api/commerce/orders/${encodeURIComponent(orderId)}`); if (!stopped) setOrder(result) } catch { /* wait for a valid local order */ }
    }
    refresh()
    const timer = setInterval(refresh, 3000)
    return () => { stopped = true; clearInterval(timer) }
  }, [authenticated, orderId])
  if (loading) return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-purchase"><Skeleton active paragraph={{ rows: 8 }} /></section></main>
  if (!data?.product) return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-purchase"><Empty description="商品不存在或已停止销售" /><Button href="/pricing">返回套餐页</Button></section></main>
  const product = data.product
  const startPayment = async () => {
    const paymentWindow = window.open('', '_blank')
    setPaying(true)
    try {
      const result = await postJson('/api/commerce/orders', { slug: product.slug, idempotencyKey: crypto.randomUUID() })
      if (!paymentWindow) throw new Error('浏览器阻止了支付窗口，请允许弹出窗口后重试')
      const parsed = new DOMParser().parseFromString(result.paymentHtml, 'text/html')
      const sourceForm = parsed.querySelector('form')
      const action = sourceForm?.getAttribute('action') || ''
      const target = new URL(action)
      if (target.protocol !== 'https:' || target.hostname !== 'openapi.alipay.com') throw new Error('支付页面地址校验失败')
      paymentWindow.document.title = '正在前往支付宝'
      const heading = paymentWindow.document.createElement('p'); heading.textContent = '正在前往支付宝安全收银台…'; heading.style.cssText = 'font:16px -apple-system,sans-serif;padding:40px;color:#17392b'; paymentWindow.document.body.appendChild(heading)
      const form = paymentWindow.document.createElement('form'); form.method = sourceForm.getAttribute('method') || 'POST'; form.action = action
      sourceForm.querySelectorAll('input').forEach(input => { const field = paymentWindow.document.createElement('input'); field.type = 'hidden'; field.name = input.getAttribute('name') || ''; field.value = input.getAttribute('value') || ''; form.appendChild(field) })
      paymentWindow.document.body.appendChild(form); form.submit()
      const next = new URL(location.href); next.searchParams.set('order', result.orderId); history.replaceState({}, '', next)
      setOrder({ id: result.orderId, status: 'pending' })
    } catch (error) { paymentWindow?.close(); Modal.error({ title: '暂时无法发起支付', content: error.message }) }
    finally { setPaying(false) }
  }
  const paid = order?.status === 'paid'
  return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-purchase"><div className="public-purchase-summary"><Text>PURCHASE REVIEW</Text><Title>确认你的学习方案</Title><Paragraph>付款成功后，权益会自动绑定到当前拾页账号。请在付款前确认账号和期限。</Paragraph><Card><Space direction="vertical" size={14} style={{ width: '100%' }}><Tag color="green">固定期限 · 不自动续费</Tag><Title level={2}>{product.name}</Title><Paragraph>{product.description}</Paragraph><div className="public-price"><b>{formatPrice(product.amountCents)}</b><span> / {product.durationDays} 天</span></div><ul>{product.benefits.map(item => <li key={item}><CheckCircleFilled />{item}</li>)}</ul></Space></Card></div><aside className="public-order-card"><Title level={3}>订单信息</Title><div><span>商品版本</span><b>V{product.version}</b></div><div><span>服务期限</span><b>{product.durationDays} 天</b></div><div><span>应付金额</span><b>{formatPrice(product.amountCents)}</b></div>{paid ? <Alert showIcon type="success" message="付款已核验，会员权益已开通" description={order.endsAt ? `有效期至 ${new Date(order.endsAt).toLocaleDateString('zh-CN')}` : '可进入控制台查看最新权益。'} /> : order?.status === 'pending' ? <Alert showIcon type="info" message="等待支付结果" description="请在支付窗口完成付款。本页会自动刷新本地订单状态。" /> : <Alert showIcon type={data.payment?.configured ? 'info' : 'warning'} message={data.payment?.configured ? '支付宝安全支付' : '在线支付正在开通'} description={data.payment?.configured ? '付款成功后，服务端会主动查单核对金额与商品版本，再开通权益。' : `暂时无法在线付款。如需提前开通，请联系 QQ ${data.support?.value || '289614546'}。`} />}<Paragraph className="public-order-terms">购买即表示同意<a href="/terms">用户协议</a>和<a href="/refunds">退款规则</a>。已售商品始终保留购买时的名称、价格与权益版本。</Paragraph>{paid ? <Button block type="primary" size="large" href="/app?screen=membership">查看会员权益</Button> : authenticated ? <Button block type="primary" size="large" loading={paying} disabled={!data.payment?.configured || order?.status === 'pending'} onClick={startPayment}>{data.payment?.configured ? '前往支付宝付款' : '支付通道审核中'}</Button> : <Button block type="primary" size="large" href={`/login?next=${encodeURIComponent(location.pathname)}`}>登录后购买</Button>}<Button block href="/pricing">重新选择套餐</Button></aside></section><TrustFooter support={data.support} /></main>
}
