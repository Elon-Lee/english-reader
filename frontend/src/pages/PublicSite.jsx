import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRightOutlined, CheckCircleFilled, CustomerServiceOutlined, LockOutlined, PlayCircleFilled } from '@ant-design/icons'
import { Alert, Button, Card, Col, Collapse, Empty, Input, Modal, Row, Skeleton, Space, Tag, Typography } from 'antd'

import { getJson, postJson } from '../api/client'
import usePurchasePreviews from '../hooks/usePurchasePreviews'
import { displayBenefits, displayDate, featuredProductId, planHighlights, purchaseAction, sharedBenefits } from '../utils/presentation.mjs'
import { refreshJourney, updateJourney } from '../api/journey'
import { PurchaseRecovery } from '../components/LearningJourney'

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
  return <span className="public-sale-price"><b>{sale}</b><del aria-label={`原价${original}`}>{original}</del><Tag>{label}</Tag></span>
}

export function PublicHeader({ authenticated, compact = false }) {
  return <header className={`public-header ${compact ? 'is-compact' : ''}`}>
    <a className="public-brand" href="/"><span className="public-brand-mark">拾</span><span><b>拾页</b><small>ENGLISH WORKSPACE</small></span></a>
    <nav aria-label="公开站点导航"><a href="/#product">产品</a><a href="/pricing">套餐</a><a href="/support">支持</a></nav>
    <Space><Button href={authenticated ? '/app' : '/login'}>{authenticated ? '进入学习空间' : '登录'}</Button><Button type="primary" href={authenticated ? '/pricing' : '/register'}>{authenticated ? '查看套餐' : '免费注册'}</Button></Space>
  </header>
}

export function ProductCard({ product, authenticated, onPurchase, featured = false, state, onRetry }) {
  const freeHref = authenticated ? '/app' : '/register'
  const action = purchaseAction(product, authenticated, state)
  return <Card className={`public-price-card ${featured ? 'is-featured' : ''}`}>
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      <div className="public-plan-label"><Tag color={featured ? 'green' : 'default'}>{featured ? '推荐方案' : product.family === 'free' ? '免费体验' : '更多学习空间'}</Tag><Text className="public-plan-family">{product.family === 'pro' ? 'PRO' : product.family === 'free' ? 'FREE' : 'ADVANCED'}</Text></div>
      <div><Title level={3}>{product.shortName}</Title><Paragraph>{product.tagline}</Paragraph></div>
      <div className="public-price"><PriceDisplay product={product} /><span>{product.family === 'free' ? '永久免费' : ` / ${product.durationDays} 天`}</span></div>
      <Text type="secondary">{product.family === 'free' ? '使用邀请码注册，验证邮箱后开始' : '单次购买，不自动续费'}</Text>
      <PlanHighlights product={product} />
      {product.family === 'free'
        ? <Button block size="large" href={freeHref}>{action.label}</Button>
        : <div className="public-plan-action"><Button block type={featured ? 'primary' : 'default'} size="large" loading={action.loading} disabled={action.disabled} onClick={() => action.retry ? onRetry() : onPurchase(product)}>{action.label}</Button>{state?.error && action.retry && <Text type="danger">权益暂时未能读取，请重试。</Text>}{!product.purchaseUrl && <Text type="secondary">暂未开放购买，可使用已有兑换码</Text>}</div>}
    </Space>
  </Card>
}

export function PlanHighlights({ product }) {
  return <dl className="plan-highlights">{planHighlights(product).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

export function PricingSection({ authenticated, products, loading = false, error = '', onRetry, title = '找到适合你的学习方案', onPurchase, headingLevel = 2 }) {
  const { states, retry } = usePurchasePreviews(products, authenticated)
  const featured = featuredProductId(products)
  const common = sharedBenefits(products)
  return <section className="public-section public-pricing" id="pricing">
    <div className="public-section-heading"><Text>MEMBERSHIP</Text><Title level={headingLevel}>{title}</Title><Paragraph>免费开始，按空间和收藏数量选择。付费方案均含不限次 AI 分析，不自动续费。</Paragraph></div>
    {loading ? <Row gutter={[20, 20]}>{[1, 2, 3].map(item => <Col xs={24} md={12} xl={8} key={item}><Card><Skeleton active /></Card></Col>)}</Row>
      : error ? <Alert type="error" showIcon message="套餐暂时无法加载" description={error} action={<Button onClick={onRetry}>重试</Button>} />
        : products.length ? <><Row gutter={[20, 20]}>{products.map(product => <Col xs={24} md={12} xl={8} key={product.id}><ProductCard product={product} authenticated={authenticated} onPurchase={onPurchase} featured={product.id === featured} state={states[product.planVersion]} onRetry={retry} /></Col>)}</Row>
          {common.length > 0 && <div className="plan-common-benefits"><Text strong>所有方案都包含</Text><ul>{common.map(item => <li key={item}><CheckCircleFilled aria-hidden />{item}</li>)}</ul></div>}
          <Collapse className="plan-full-benefits" ghost items={[{ key: 'full', label: '展开完整权益与方案说明', children: <Row gutter={[24, 16]}>{products.map(product => <Col span={8} key={product.id}><Title level={4}>{product.shortName || product.name}</Title><ul>{displayBenefits(product).map(item => <li key={item}>{item}</li>)}</ul>{product.configuredBenefits?.map((benefit, index) => <Paragraph key={benefit.id || index}>{benefit.text || benefit.name}</Paragraph>)}</Col>)}</Row> }]} />
        </> : <Empty description="暂无在售套餐，请稍后再来" />}
    <Paragraph className="public-capacity-note">音视频收藏按官方书架与私人内容合计；移出官方书架或删除私人读物可释放名额。注册需要有效邀请码，<a href="/support#invitation">没有邀请码？</a></Paragraph>
  </section>
}

function PricingFAQ() {
  return <section className="public-faq"><Title level={2}>购买前，你可能想知道</Title><Collapse items={[
    { key: 'free', label: '可以先免费使用吗？', children: '可以。使用有效邀请码注册并验证邮箱后，即可使用免费方案。没有邀请码时，可联系支持页客服咨询。' },
    { key: 'pay', label: '付款后如何开通？', children: '先登录拾页核对当前方案，再前往云猫付款。复制云猫发放的兑换码，回到拾页原弹窗兑换。只有兑换成功后，会员权益才会生效。' },
    { key: 'renew', label: '会自动扣款吗？续费和升级怎么算？', children: '不会自动续费。同等级兑换立即延长有效期；升级时按剩余权益价值折算时长。购买前会显示预计到期日；当前不支持购买低于有效会员等级的方案。' },
    { key: 'capacity', label: '到期或达到收藏上限后怎么办？', children: '到期后按免费权益使用，已有超限内容不会自动删除；新增收藏或导入会受当前额度限制。移出官方收藏或删除不再需要的私人读物可释放名额，归档仍占名额。' },
    { key: 'help', label: '兑换、退款或账号有问题怎么办？', children: <span>保留购买订单号和时间，通过<a href="/support">支持页</a>联系咨询；具体处理见<a href="/refunds">退款规则</a>。不要向他人发送完整兑换码或账号密码。</span> },
  ]} /></section>
}

export function CloudCatPurchaseModal({ product, open, authenticated, returnTo = '/pricing', onClose, onRedeemed }) {
  const [redeemCode, setRedeemCode] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [redeemResult, setRedeemResult] = useState(null)
  const [redeemError, setRedeemError] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewError, setPreviewError] = useState('')
  const [previewCode, setPreviewCode] = useState('')
  const [previewRevision, setPreviewRevision] = useState(0)
  const [departed, setDeparted] = useState(false)
  const [recoveryError, setRecoveryError] = useState('')
  const redeemInput = useRef(null)
  const purchaseTracking = useRef(Promise.resolve())
  const trackingSequence = useRef(0)
  const inFlight = useRef(false)
  const redeemAttempt = useRef({ code: '', key: '' })

  useEffect(() => {
    let active = true
    setPreview(null)
    setPreviewError('')
    setPreviewCode('')
    if (open && authenticated && product?.planVersion) getJson(`/api/membership/change-preview?targetPlan=${encodeURIComponent(product.planVersion)}`).then(value => { if (active) setPreview(value) }).catch(error => { if (active) { setPreviewCode(error.code || ''); setPreviewError(error.code === 'membership_downgrade_not_allowed' ? '你的有效会员等级高于此方案，请选择当前等级续费或更高等级升级。' : error.message || '权益预览暂时不可用，请重试。') } })
    return () => { active = false }
  }, [product?.id, open, authenticated, previewRevision])

  useEffect(() => {
    const sequence = ++trackingSequence.current
    setRedeemCode(''); setRedeemResult(null); setRedeemError(''); setDeparted(false); setRecoveryError('')
    if (!open || !authenticated || !product?.id) return
    purchaseTracking.current = updateJourney({ action: 'plan_selected', productVersionId: product.id, idempotencyKey: `plan-${crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`}` })
      .then(state => { if (sequence === trackingSequence.current) setDeparted(state.pendingPurchase?.phase === 'departed') })
      .catch(() => { if (sequence === trackingSequence.current) setRecoveryError('暂时无法保存所选方案，请保留此页面，付款后回到这里兑换。') })
    return () => { trackingSequence.current += 1 }
  }, [product?.id, open, authenticated])

  const depart = () => {
    const sequence = trackingSequence.current
    setDeparted(true)
    purchaseTracking.current = purchaseTracking.current.then(() => updateJourney({ action: 'purchase_departure', productVersionId: product.id, idempotencyKey: `depart-${crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`}` }))
      .then(() => { if (sequence === trackingSequence.current) setRecoveryError('') })
      .catch(() => { if (sequence === trackingSequence.current) setRecoveryError('暂时无法保存购买入口，请保留此页面，付款后回到这里兑换。') })
  }

  const submitRedeem = async () => {
    if (inFlight.current || redeemResult) return
    if (!authenticated) {
      const separator = returnTo.includes('?') ? '&' : '?'
      location.href = `/login?next=${encodeURIComponent(`${returnTo}${separator}purchase=${product.slug}`)}`
      return
    }
    if (!preview || previewError) return
    const code = redeemCode.trim().toUpperCase()
    if (!/^SY-[A-F0-9]{32}$/.test(code)) {
      setRedeemError('请输入云猫发放的兑换码（SY- 后接 32 位字符）。')
      return
    }
    inFlight.current = true
    setRedeeming(true)
    setRedeemError('')
    try {
      if (redeemAttempt.current.code !== code) redeemAttempt.current = { code, key: `membership-redeem-${crypto.randomUUID?.() || Date.now()}` }
      const result = await postJson('/api/membership/redeem', { code, idempotencyKey: redeemAttempt.current.key })
      setRedeemResult(result)
      setRedeemCode('')
      void refreshJourney().catch(() => {})
      try { await onRedeemed?.(result) } catch { /* Redemption already succeeded; keep its confirmation visible. */ }
    } catch (error) {
      setRedeemError(error.message || '兑换失败，请核对兑换码后重试。')
    } finally {
      inFlight.current = false
      setRedeeming(false)
    }
  }

  const loginHref = product ? `/login?next=${encodeURIComponent(`${returnTo}${returnTo.includes('?') ? '&' : '?'}purchase=${product.slug}`)}` : '/login'
  return <Modal className="public-purchase-modal" title="购买与开通" open={open && Boolean(product)} onCancel={redeeming ? undefined : onClose} closable={!redeeming} maskClosable={!redeeming} keyboard={!redeeming} footer={null} destroyOnClose>
    {product && <div className="public-purchase-modal-content">
      <Title level={3}>{product.name}</Title>
      <div className="public-price"><PriceDisplay product={product} /><span> / {product.durationDays} 天</span></div>
      <div className="public-purchase-modal-steps"><span>1. 云猫付款并复制自动发放的兑换码</span><span>2. 回到这里粘贴兑换码，立即开通</span></div>
      {preview && <Alert showIcon type="info" message={preview.changeType === 'upgrade' ? `立即升级到${preview.targetPlan.name}` : preview.changeType === 'renewal' ? `立即续费并延长 ${preview.durationDays} 天` : `立即开通${preview.targetPlan.name} ${preview.durationDays}天`} description={preview.changeType === 'upgrade' ? `按套餐价值折算：当前剩余权益约折算 ${preview.carryDays} 天${preview.targetPlan.name}，有效期预计至 ${displayDate(preview.endsAt)}` : preview.changeType === 'renewal' ? `续费后会员有效期延长至 ${displayDate(preview.endsAt)}` : `立即生效，预计有效至 ${displayDate(preview.endsAt)}`} />}
      {authenticated && !preview && !previewError && <Skeleton active title={false} paragraph={{ rows: 2 }} />}
      {previewError && <Alert showIcon type={previewCode === 'membership_downgrade_not_allowed' ? 'info' : 'error'} message={previewCode === 'membership_downgrade_not_allowed' ? '当前会员高于此方案' : '暂时无法核对权益'} description={previewError} action={previewCode !== 'membership_downgrade_not_allowed' && <Button onClick={() => setPreviewRevision(value => value + 1)}>重试</Button>} />}
      {authenticated && departed && !redeemResult && <Alert showIcon type="info" message="已前往云猫，付款后请回来兑换" description="此处无法自动核实外部付款。已付款请复制云猫发放的兑换码，无需再次购买。" />}
      {recoveryError && <Alert showIcon type="warning" message={recoveryError} />}
      {authenticated ? <Space direction="vertical" style={{ width: '100%' }}><Button block type={departed ? 'default' : 'primary'} size="large" href={product.purchaseUrl || undefined} target="_blank" rel="noreferrer" onClick={depart} disabled={!product.purchaseUrl || Boolean(previewError) || !preview || Boolean(redeemResult)}>{departed ? '再次前往云猫商品页' : '打开云猫购买'}</Button>{!redeemResult && <Button block type="link" disabled={!preview || Boolean(previewError)} onClick={() => redeemInput.current?.focus()}>已购买，直接输入兑换码 ↓</Button>}</Space> : <Button block type="primary" size="large" href={loginHref}>登录后核对方案</Button>}
      <Paragraph className="purchase-reassurance">由云猫完成收款并发放兑换码，兑换后在拾页生效；不自动续费。付款前请查看<a href="/refunds" target="_blank" rel="noreferrer">退款规则</a>。{!product.purchaseUrl && '此方案暂未开放新购，已有兑换码仍可开通。'}</Paragraph>
      <div className="public-purchase-modal-redeem">
        <Text strong>已有兑换码？</Text>
        {authenticated
          ? <><Input ref={redeemInput} aria-label="云猫兑换码" value={redeemCode} status={redeemError ? 'error' : undefined} onChange={event => { setRedeemCode(event.target.value.toUpperCase()); setRedeemError('') }} onPressEnter={submitRedeem} placeholder="SY- 后接 32 位兑换码" maxLength={35} autoComplete="off" disabled={redeeming || Boolean(redeemResult) || !preview || Boolean(previewError)} /><Button block type={departed ? 'primary' : 'default'} onClick={submitRedeem} loading={redeeming} disabled={Boolean(redeemResult) || !preview || Boolean(previewError)}>{redeemResult ? '兑换成功' : '立即兑换'}</Button></>
          : <><Text type="secondary">登录后即可将权益开通到当前账号。</Text><Button block href={`/login?next=${encodeURIComponent(`${returnTo}${returnTo.includes('?') ? '&' : '?'}purchase=${product.slug}`)}`}>登录后继续</Button></>}
        {redeemError && <Alert showIcon type="error" message={redeemError} description={<span>核对兑换码和登录账号后重试。仍无法开通时，请保留云猫订单号、购买时间和注册邮箱，<a href="/support#payment" target="_blank" rel="noreferrer">联系支持</a>。</span>} />}
        {redeemResult && <Alert showIcon type="success" message={`${redeemResult.planName}已处理`} description={`${redeemResult.changeOrder?.changeType === 'renewal' ? '已完成同级续费' : redeemResult.changeOrder?.changeType === 'upgrade' ? `已立即升级，折算约 ${redeemResult.changeOrder?.carryDays || 0} 天` : '已开通'}；预计有效至 ${displayDate(redeemResult.endsAt)}`} action={<Button type="link" href="/app?screen=membership">查看会员</Button>} />}
      </div>
    </div>}
  </Modal>
}

export default function PublicSite({ authenticated, page = 'home' }) {
  const [catalog, setCatalog] = useState({ products: [], support: { value: '289614546' }, payment: {} })
  const [loading, setLoading] = useState(true)
  const [purchaseProduct, setPurchaseProduct] = useState(null)
  const [catalogError, setCatalogError] = useState('')
  const [catalogRevision, setCatalogRevision] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setCatalogError('')
    getJson('/api/commerce/products').then(value => { if (active) setCatalog(value) }).catch(error => { if (active) setCatalogError(error.message || '请检查网络后重试') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [catalogRevision])
  const monthly = useMemo(() => catalog.products.filter(item => item.family === 'free' || item.durationDays === 30), [catalog.products])
  useEffect(() => {
    const slug = new URLSearchParams(location.search).get('purchase')
    if (!slug || !catalog.products.length) return
    const product = catalog.products.find(item => item.slug === slug && item.family !== 'free')
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
  const purchaseDialog = <CloudCatPurchaseModal product={purchaseProduct} open={Boolean(purchaseProduct)} authenticated={authenticated} returnTo={location.pathname} onClose={closePurchase} onRedeemed={() => setCatalogRevision(value => value + 1)} />
  const pricingProps = { authenticated, loading, error: catalogError, onRetry: () => setCatalogRevision(value => value + 1), onPurchase: openPurchase }

  if (page === 'pricing') return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><PurchaseRecovery authenticated={authenticated} /><PricingSection key={catalogRevision} {...pricingProps} products={catalog.products} headingLevel={1} title="按你的学习节奏，选择合适的空间" /><PricingFAQ />{purchaseDialog}<TrustFooter support={catalog.support} /></main>
  if (page === 'support') return <main className="public-site"><PublicHeader authenticated={authenticated} compact /><section className="public-support"><Text>SUPPORT</Text><Title>购买前后，都有人回应</Title><Paragraph>套餐、支付、退款或账号问题，请联系 QQ <b>{catalog.support?.value || '289614546'}</b>。我们会在 1 个工作日内响应，并尽量在 3 个工作日内给出处理结论。</Paragraph><Row gutter={[20, 20]}><Col xs={24} md={8}><Card id="invitation"><CustomerServiceOutlined /><Title level={4}>邀请码与注册</Title><Paragraph>还没有邀请码？联系上方 QQ，说明你的学习需求，咨询当前开放情况。已有邀请码但注册失败，请附上错误提示。</Paragraph><Text type="secondary">获得有效邀请码并完成邮箱验证后，即可免费开始。</Text><Button href="/register">已有邀请码，去注册</Button></Card></Col><Col xs={24} md={8}><Card id="payment"><LockOutlined /><Title level={4}>付款后未开通？</Title><Paragraph>先查看云猫订单是否已发放兑换码，再回到拾页兑换；如果兑换失败，请提供订单号、注册邮箱、购买时间和错误提示。</Paragraph><Text type="secondary">请勿发送账号密码或完整兑换码。退款处理见退款规则。</Text><Button href="/app?screen=membership">已有兑换码，去开通</Button></Card></Col><Col xs={24} md={8}><Card><CheckCircleFilled /><Title level={4}>内容与版权</Title><Text>私人材料仅用于个人学习，官方内容仅使用公版或授权资源。</Text></Card></Col></Row></section><TrustFooter support={catalog.support} /></main>

  return <main className="public-site">
    <PublicHeader authenticated={authenticated} />
    <PurchaseRecovery authenticated={authenticated} />
    <section className="public-hero">
      <div className="public-hero-copy"><Text>原声听读 · 语境理解 · 生词复习</Text><Title><span>不是看过。</span><span>是终于读懂。</span></Title><Paragraph>用原声视频、音频和文章逐句学英语。查懂一个词，听清一句话，把每次理解留在自己的学习空间。</Paragraph><Space size={14}><Button type="primary" size="large" href={authenticated ? '/app' : '/register'}>{authenticated ? '继续学习' : '免费开始学习'}<ArrowRightOutlined /></Button><Button size="large" href="#product">了解学习方式</Button></Space>{!authenticated && <Text className="signup-note">注册需要邀请码 · 验证邮箱后开始 · 无需支付</Text>}<div className="public-hero-notes"><span><CheckCircleFilled /> 使用原始音视频</span><span><CheckCircleFilled /> 私人学习空间</span><span><CheckCircleFilled /> 自动保存学习进度</span></div></div>
      <div className="public-hero-visual" aria-label="拾页逐句阅读器产品画面"><div className="public-device-frame"><img src="/product/reader-word-panel.jpg" alt="拾页视频逐句学习、单词释义和跟读界面" /></div><div className="public-floating-note"><PlayCircleFilled /><span><b>逐句同步</b><small>原声、字幕与解释保持在同一个学习现场</small></span></div></div>
    </section>

    <section className="public-pain"><Text>真正的问题，不是缺少材料</Text><Title level={2}>而是每次学习都从零开始。</Title><Row gutter={[28, 28]}><Col xs={24} md={8}><div><b>读到一半就放弃</b><p>长文章和视频没有清晰切分，难点出现时只能来回拖动。</p></div></Col><Col xs={24} md={8}><div><b>查完的词又忘了</b><p>词典、上下文与复习彼此分离，知道意思却没有形成记忆。</p></div></Col><Col xs={24} md={8}><div><b>学了多久没有答案</b><p>零散工具不记录你的阅读位置、投入时间和真实进度。</p></div></Col></Row></section>

    <section className="public-product-story" id="product">
      <div className="public-story-copy"><Text>READ DEEPLY</Text><Title level={2}>一句一句，把模糊变清楚。</Title><Paragraph>原始视频、字幕、词义、语法和跟读并排工作。遇到难句时停下来理解，理解之后继续听，不需要在多个工具之间切换。</Paragraph></div>
      <div className="public-screenshot-stage"><img src="/product/reader-word-panel.jpg" loading="lazy" alt="真实阅读器中的原声视频、同步字幕与单词语境释义" /></div>
    </section>
    <section className="public-product-story reverse">
      <div className="public-story-copy"><Text>KEEP THE THREAD</Text><Title level={2}>今天学到哪里，明天从那里继续。</Title><Paragraph>私人书架、阅读位置、学习时长和复习任务集中在一个空间。你的每一次投入，都能成为下一次学习的起点。</Paragraph></div>
      <div className="public-screenshot-stage"><img src="/product/workspace-current.jpg" loading="lazy" alt="拾页个人英语学习空间：继续阅读、复习生词与每周学习记录" /></div>
    </section>
    <section className="public-product-story">
      <div className="public-story-copy"><Text>SEE THE PROGRESS</Text><Title level={2}>看见积累，才更容易坚持。</Title><Paragraph>学习天数、听读时间、完成句子和热力记录形成可回看的轨迹。不用凭感觉猜测自己有没有进步。</Paragraph></div>
      <div className="public-screenshot-stage"><img src="/product/learning-insights.png" loading="lazy" alt="拾页英语学习记录与热力图" /></div>
    </section>

    <PricingSection key={catalogRevision} {...pricingProps} products={monthly} title="先开始，再选择适合你的方案" />
    <section className="public-final-cta"><Text>START WHERE YOU ARE</Text><Title level={2}>从你想读懂的那一篇开始。</Title><Paragraph>挑选官方读物，或导入自己的材料。一次只专注一句。</Paragraph><Space><Button type="primary" size="large" href={authenticated ? '/app?screen=catalog' : '/register'}>{authenticated ? '去书城挑选读物' : '使用邀请码免费注册'}</Button><Button size="large" href="/pricing">比较全部套餐</Button></Space></section>
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
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [open, setOpen] = useState(true)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    getJson(`/api/commerce/products/${encodeURIComponent(slug)}`).then(value => { if (active) setData(value) }).catch(failure => { if (active) setError(failure.status === 404 ? '该商品不存在或已停止新售，请选择其他方案。' : failure.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [slug, revision])
  return <main className="public-site"><PublicHeader authenticated={authenticated} compact />
    <section className="public-purchase-summary-page">
      {loading ? <Skeleton active /> : error ? <Alert showIcon type="error" message={error} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} /> : data?.product ? <>
        <Text className="eyebrow">YOUR LEARNING PLAN</Text><Title level={1}>{data.product.name}</Title>
        <Paragraph>{data.product.description}</Paragraph><div className="public-price"><PriceDisplay product={data.product} /><span> / {data.product.durationDays} 天</span></div>
        <Space><Button type="primary" size="large" onClick={() => setOpen(true)}>购买 / 兑换</Button><Button href="/pricing">比较其他套餐</Button></Space>
        <CloudCatPurchaseModal product={data.product} open={open} authenticated={authenticated} returnTo={location.pathname} onClose={() => setOpen(false)} />
      </> : <Empty description="暂无商品信息" />}
    </section><TrustFooter support={data?.support} />
  </main>
}
