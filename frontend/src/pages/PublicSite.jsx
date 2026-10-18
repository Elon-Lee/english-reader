import React, { useEffect, useMemo, useState } from 'react'
import { ArrowRightOutlined, CheckCircleFilled, CustomerServiceOutlined, LockOutlined, PlayCircleFilled } from '@ant-design/icons'
import { Alert, Button, Card, Col, Empty, Input, Modal, Row, Skeleton, Space, Tag, Typography } from 'antd'

import { getJson, postJson } from '../api/client'

const { Paragraph, Text, Title } = Typography

function formatPrice(cents) {
  const amount = Number(cents || 0) / 100
  return `¥${Number.isInteger(amount) ? amount.toFixed(0) : amount.toFixed(2)}`
}

export function PriceDisplay({ product }) {
  const discount = Number(product.discountPercent || 100)
  const sale = formatPrice(product.amountCents)
  if (!product.amountCents || discount >= 100) return <b>{sale}</b>
  const original = formatPrice(product.originalAmountCents)
  const label = `${Number.isInteger(discount / 10) ? discount / 10 : (discount / 10).toFixed(1)}折`
  return <span className="public-sale-price"><b>{sale}</b><del>{original}</del><Tag color="red">{label}</Tag></span>
}

function PublicHeader({ authenticated, compact = false }) {
  return <header className={`public-header ${compact ? 'is-compact' : ''}`}>
    <a className="public-brand" href="/"><span className="public-brand-mark">拾</span><span><b>拾页</b><small>ENGLISH WORKSPACE</small></span></a>
    <nav aria-label="公开站点导航"><a href="/#product">产品</a><a href="/pricing">套餐</a><a href="/support">支持</a></nav>
    <Space><Button href={authenticated ? '/app' : '/login'}>{authenticated ? '进入控制台' : '登录'}</Button><Button type="primary" href="/pricing">查看套餐</Button></Space>
  </header>
}

function ProductCard({ product, authenticated, onPurchase }) {
  const freeHref = authenticated ? '/app' : '/register'
  return <Card className={`public-price-card ${product.featured ? 'is-featured' : ''}`}>
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      <div>{product.featured && <Tag color="green">推荐</Tag>}<Text className="public-plan-family">{product.family === 'pro' ? 'PRO' : product.family === 'free' ? 'FREE' : 'ADVANCED'}</Text></div>
      <div><Title level={3}>{product.shortName}</Title><Paragraph>{product.tagline}</Paragraph></div>
      <div className="public-price"><PriceDisplay product={product} /><span>{product.family === 'free' ? '永久免费' : ' / 30 天'}</span></div>
      <Text type="secondary">{product.family === 'free' ? '注册即可使用' : '单次购买，不自动续费'}</Text>
      <ul>{product.benefits.slice(0, 9).map(item => <li key={item}><CheckCircleFilled />{item}</li>)}</ul>
      {product.family === 'free'
        ? <Button block type={product.featured ? 'primary' : 'default'} size="large" href={freeHref}>{authenticated ? '进入学习空间' : '免费开始使用'}</Button>
        : <Button block type={product.featured ? 'primary' : 'default'} size="large" onClick={() => onPurchase(product)} disabled={!product.purchaseUrl}>{product.purchaseUrl ? '购买 / 兑换' : '商品上线准备中'}</Button>}
    </Space>
  </Card>
}

export function PricingSection({ authenticated, products, loading = false, title = '选一个与你节奏相配的期限', onPurchase }) {
  return <section className="public-section public-pricing" id="pricing"><div className="public-section-heading"><Text>MEMBERSHIP</Text><Title level={2}>{title}</Title><Paragraph>付费方案一次购买 30 天、不自动续费；免费版可持续使用。</Paragraph></div>{loading ? <Row gutter={[20, 20]}>{[1, 2, 3].map(item => <Col xs={24} md={12} xl={8} key={item}><Card><Skeleton active /></Card></Col>)}</Row> : products.length ? <Row gutter={[20, 20]}>{products.map(product => <Col xs={24} md={12} xl={8} key={product.id}><ProductCard product={product} authenticated={authenticated} onPurchase={onPurchase} /></Col>)}</Row> : <Empty description="套餐正在准备中" />}</section>
}

export function CloudCatPurchaseModal({ product, open, authenticated, returnTo = '/pricing', onClose, onRedeemed }) {
  const [redeemCode, setRedeemCode] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [redeemResult, setRedeemResult] = useState(null)
  const [redeemError, setRedeemError] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewError, setPreviewError] = useState('')

  useEffect(() => {
    let active = true
    setRedeemCode('')
    setRedeemResult(null)
    setRedeemError('')
    setPreview(null)
    setPreviewError('')
    if (open && authenticated && product?.planVersion) getJson(`/api/membership/change-preview?targetPlan=${encodeURIComponent(product.planVersion)}`).then(value => { if (active) setPreview(value) }).catch(error => { if (active) setPreviewError(error.message || '套餐预览失败，请关闭后重试。') })
    return () => { active = false }
  }, [product?.id, open, authenticated])

  const submitRedeem = async () => {
    if (!authenticated) {
      const separator = returnTo.includes('?') ? '&' : '?'
      location.href = `/login?next=${encodeURIComponent(`${returnTo}${separator}purchase=${product.slug}`)}`
      return
    }
    const code = redeemCode.trim().toUpperCase()
    if (!/^SY-[A-F0-9]{32}$/.test(code)) {
      setRedeemError('请输入云猫发放的兑换码（SY- 后接 32 位字符）。')
      return
    }
    setRedeeming(true)
    setRedeemError('')
    try {
      const result = await postJson('/api/membership/redeem', { code, idempotencyKey: `membership-redeem-${crypto.randomUUID?.() || Date.now()}` })
      setRedeemResult(result)
      setRedeemCode('')
      try { await onRedeemed?.(result) } catch { /* Redemption already succeeded; keep its confirmation visible. */ }
    } catch (error) {
      setRedeemError(error.message || '兑换失败，请核对兑换码后重试。')
    } finally {
      setRedeeming(false)
    }
  }

  return <Modal className="public-purchase-modal" title={null} open={open && Boolean(product)} onCancel={onClose} footer={null} destroyOnClose>
    {product && <div className="public-purchase-modal-content">
      <Text className="public-plan-family">购买与开通</Text>
      <Title level={3}>{product.name}</Title>
      <div className="public-price"><PriceDisplay product={product} /><span> / {product.durationDays} 天</span></div>
      <div className="public-purchase-modal-steps"><span>1. 云猫付款并复制自动发放的兑换码</span><span>2. 回到这里粘贴兑换码，立即开通</span></div>
      {preview && <Alert showIcon type="info" message={preview.changeType === 'upgrade' ? `立即升级到${preview.targetPlan.name}` : preview.changeType === 'renewal' ? `立即续费并延长 ${preview.durationDays} 天` : `立即开通${preview.targetPlan.name} ${preview.durationDays}天`} description={preview.changeType === 'upgrade' ? `按套餐价值折算：当前剩余权益约折算 ${preview.carryDays} 天 Pro，有效期预计至 ${new Date(preview.endsAt).toLocaleDateString('zh-CN')}` : preview.changeType === 'renewal' ? `续费后会员有效期延长至 ${new Date(preview.endsAt).toLocaleDateString('zh-CN')}` : `立即生效，预计有效至 ${new Date(preview.endsAt).toLocaleDateString('zh-CN')}`} />}
      {previewError && <Alert showIcon type="error" message="暂时无法购买该套餐" description={previewError} />}
      <Button block type="primary" size="large" href={product.purchaseUrl || undefined} target="_blank" rel="noreferrer" disabled={!product.purchaseUrl || Boolean(previewError) || (authenticated && !preview)}>打开云猫购买</Button>
      <div className="public-purchase-modal-redeem">
        <Text strong>已有兑换码？</Text>
        {authenticated
          ? <><Input aria-label="云猫兑换码" value={redeemCode} onChange={event => { setRedeemCode(event.target.value.toUpperCase()); setRedeemError('') }} onPressEnter={submitRedeem} placeholder="SY- 后接 32 位兑换码" maxLength={35} autoComplete="off" disabled={Boolean(redeemResult) || Boolean(previewError)} /><Button block onClick={submitRedeem} loading={redeeming} disabled={Boolean(redeemResult) || Boolean(previewError)}>{redeemResult ? '兑换成功' : '立即兑换'}</Button></>
          : <><Text type="secondary">登录后即可将权益开通到当前账号。</Text><Button block href={`/login?next=${encodeURIComponent(`${returnTo}${returnTo.includes('?') ? '&' : '?'}purchase=${product.slug}`)}`}>登录后继续</Button></>}
        {redeemError && <Alert showIcon type="error" message={redeemError} />}
        {redeemResult && <Alert showIcon type="success" message={`${redeemResult.planName}已处理`} description={`${redeemResult.changeOrder?.changeType === 'renewal' ? '已完成同级续费' : redeemResult.changeOrder?.changeType === 'upgrade' ? `已立即升级，折算约 ${redeemResult.changeOrder?.carryDays || 0} 天` : '已开通'}；预计有效至 ${new Date(redeemResult.endsAt).toLocaleDateString('zh-CN')}`} action={<Button type="link" href="/app?screen=membership">查看会员</Button>} />}
      </div>
    </div>}
  </Modal>
}

export default function PublicSite({ authenticated, page = 'home' }) {
  const [catalog, setCatalog] = useState({ products: [], support: { value: '289614546' }, payment: {} })
  const [loading, setLoading] = useState(true)
  const [purchaseProduct, setPurchaseProduct] = useState(null)
  useEffect(() => { getJson('/api/commerce/products', { products: [], support: { value: '289614546' }, payment: {} }).then(setCatalog).finally(() => setLoading(false)) }, [])
  const monthly = useMemo(() => catalog.products.filter(item => item.family === 'free' || item.durationDays === 30), [catalog.products])
  useEffect(() => {
    const slug = new URLSearchParams(location.search).get('purchase')
    if (!slug || !catalog.products.length) return
    const product = catalog.products.find(item => item.slug === slug && item.purchaseUrl)
    if (product) setPurchaseProduct(product)
  }, [catalog.products])

  const openPurchase = product => {
    setPurchaseProduct(product)
    const params = new URLSearchParams(location.search)
    params.set('purchase', product.slug)
    history.replaceState({}, '', `${location.pathname}?${params}`)
  }
  const closePurchase = () => {
    setPurchaseProduct(null)
    const params = new URLSearchParams(location.search)
    params.delete('purchase')
    const query = params.toString()
    history.replaceState({}, '', `${location.pathname}${query ? `?${query}` : ''}`)
  }
  const purchaseDialog = <CloudCatPurchaseModal product={purchaseProduct} open={Boolean(purchaseProduct)} authenticated={authenticated} returnTo={location.pathname} onClose={closePurchase} />

  if (page === 'pricing') return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><PricingSection authenticated={authenticated} products={catalog.products} loading={loading} title="一次购买，专注学完这一程" onPurchase={openPurchase} />{purchaseDialog}<TrustFooter support={catalog.support} /></main>
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

    <PricingSection authenticated={authenticated} products={monthly} loading={loading} title="给自己一段不被打断的学习时间" onPurchase={openPurchase} />
    <section className="public-final-cta"><Text>START WHERE YOU ARE</Text><Title level={2}>不用准备更多材料。<br />从你已经想读懂的那一篇开始。</Title><Space><Button type="primary" size="large" href={authenticated ? '/app' : '/login'}>{authenticated ? '进入学习空间' : '登录拾页'}</Button><Button size="large" href="/pricing">查看全部套餐</Button></Space></section>
    {purchaseDialog}
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
  const [redeemCode, setRedeemCode] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [redeemResult, setRedeemResult] = useState(null)
  const [redeemError, setRedeemError] = useState('')
  useEffect(() => { getJson(`/api/commerce/products/${encodeURIComponent(slug)}`, null).then(setData).finally(() => setLoading(false)) }, [slug])
  if (loading) return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-purchase"><Skeleton active paragraph={{ rows: 8 }} /></section></main>
  if (!data?.product) return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-purchase"><Empty description="商品不存在或已停止销售" /><Button href="/pricing">返回套餐页</Button></section></main>
  const product = data.product
  const submitRedeem = async () => {
    const code = redeemCode.trim().toUpperCase()
    if (!authenticated) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`
      return
    }
    if (!/^SY-[A-F0-9]{32}$/.test(code)) {
      setRedeemError('请输入云猫发放的 35 位兑换码，格式如 SY- 后接 32 位字符。')
      return
    }
    setRedeeming(true)
    setRedeemError('')
    try {
      setRedeemResult(await postJson('/api/membership/redeem', { code }))
      setRedeemCode('')
    } catch (error) {
      setRedeemError(error.message || '兑换失败，请检查兑换码后重试。')
    } finally {
      setRedeeming(false)
    }
  }
  return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-purchase"><div className="public-purchase-summary"><Text>PURCHASE REVIEW</Text><Title>确认你的学习方案</Title><Paragraph>先在云猫完成支付，再回到这里输入兑换码。兑换成功后，权益会立即写入你的拾页账号。</Paragraph><Card><Space direction="vertical" size={14} style={{ width: '100%' }}><Tag color="green">固定期限 · 不自动续费</Tag><Title level={2}>{product.name}</Title><Paragraph>{product.description}</Paragraph><div className="public-price"><PriceDisplay product={product} /><span> / {product.durationDays} 天</span></div><ul>{product.benefits.map(item => <li key={item}><CheckCircleFilled />{item}</li>)}</ul></Space></Card></div><aside className="public-order-card"><Title level={3}>购买与兑换</Title><div><span>商品版本</span><b>V{product.version}</b></div><div><span>服务期限</span><b>{product.durationDays} 天</b></div><div><span>价格</span><PriceDisplay product={product} /></div><div className="public-purchase-steps"><div><b>1</b><span>打开云猫，完成付款并复制自动发放的兑换码。</span></div><div><b>2</b><span>回到本页面，把兑换码粘贴到下方。</span></div><div><b>3</b><span>确认兑换，会员权益立即生效。</span></div></div><Alert showIcon type="info" message="兑换码只使用一次" description="请不要把兑换码发给他人。购买、退款和发码记录以云猫订单为准。" /><Paragraph className="public-order-terms">购买即表示同意<a href="/terms">用户协议</a>和<a href="/refunds">退款规则</a>。如需退款，请通过云猫订单或联系拾页客服核对。</Paragraph>{product.purchaseUrl ? <Button block type="primary" size="large" href={product.purchaseUrl} target="_blank" rel="noreferrer">打开云猫购买</Button> : <Button block type="primary" size="large" disabled>商品链接尚未配置</Button>}<div className="public-redemption-panel"><Text strong>买完回来，输入兑换码</Text>{authenticated ? <><Input aria-label="云猫兑换码" value={redeemCode} onChange={event => { setRedeemCode(event.target.value.toUpperCase()); setRedeemError('') }} onPressEnter={submitRedeem} placeholder="SY- 后接 32 位兑换码" maxLength={35} autoComplete="off" disabled={Boolean(redeemResult)} /><Button block type="default" onClick={submitRedeem} loading={redeeming} disabled={Boolean(redeemResult)}>{redeemResult ? '已兑换' : '立即兑换到当前账号'}</Button></> : <><Paragraph>登录后才能把权益安全写入你的账号。</Paragraph><Button block href={`/login?next=${encodeURIComponent(location.pathname)}`}>登录后继续兑换</Button></>}{redeemError && <Alert showIcon type="error" message={redeemError} />}{redeemResult && <Alert showIcon type="success" message={`${redeemResult.planName} 已开通`} description={`有效期至 ${new Date(redeemResult.endsAt).toLocaleDateString('zh-CN')}`} action={<Button size="small" type="link" href="/app?screen=membership">查看会员中心</Button>} />}</div><Button block href="/pricing">重新选择套餐</Button></aside></section><TrustFooter support={data.support} /></main>
}
