import React from 'react'
import { Button, Card, Space, Typography } from 'antd'
import BrandLogo from '../components/BrandLogo'
import { BRAND_NAME, BRAND_SLOGAN } from '../config/brand.mjs'

const { Title, Paragraph, Text } = Typography

export function PublicHeader({ authenticated }) {
  return <header className="public-header"><a href="/" aria-label={`${BRAND_NAME}首页`}><BrandLogo variant="public" /></a><Space><Button href="/support">使用帮助</Button><Button type="primary" href={authenticated ? '/app' : '/login'}>{authenticated ? '进入个人空间' : '登录'}</Button></Space></header>
}

export default function PublicSite({ authenticated, page = 'home' }) {
  return <div className="public-site"><PublicHeader authenticated={authenticated} /><main className="private-entry"><Card className="private-entry-card">
    {page === 'support' ? <><Title level={1}>使用帮助</Title><Paragraph>此空间仅向受邀用户开放。账号、邀请码或使用问题，请通过原有联系渠道联系邀请人或管理员。</Paragraph><Paragraph>请勿发送密码、验证码或私人学习资料。遇到内容权属问题，可提供内容标题及问题说明。</Paragraph><Space><Button type="primary" href="/login">返回登录</Button><Button href="/register">已有邀请码，受邀注册</Button></Space></> : <><Text className="eyebrow">个人阅读记录</Text><Title level={1}>{BRAND_NAME}</Title><Paragraph>{BRAND_SLOGAN}</Paragraph><Paragraph type="secondary">整理阅读笔记，记录学习心得。已有账号可登录继续，受邀用户可凭有效邀请码注册。</Paragraph><Space><Button type="primary" size="large" href={authenticated ? '/app' : '/login'}>{authenticated ? '继续阅读' : '登录个人空间'}</Button>{!authenticated && <Button size="large" href="/register">受邀注册</Button>}</Space></>}
  </Card></main><footer className="private-footer"><Space wrap><a href="/terms">使用约定</a><a href="/privacy">隐私说明</a><a href="/content-policy">内容规范</a><a href="/copyright">版权说明</a></Space></footer></div>
}
