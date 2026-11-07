import React from 'react'
import { BRAND_MARK, BRAND_SLOGAN } from '../config/brand.mjs'
import './BrandLogo.css'

export default function BrandLogo({ variant = 'workspace', subtitle = BRAND_SLOGAN }) {
  const context = variant === 'auth' ? 'modern-auth-brand' : variant === 'workspace' ? 'modern-brand' : ''
  return <div className={`ryn-brand ryn-brand-${variant} ${context}`}>
    <img className="ryn-brand-mark" src={BRAND_MARK} width="40" height="40" alt="" aria-hidden="true" />
    <div className="ryn-brand-copy"><span className="ryn-brand-name"><span>Ryn</span><span>English</span></span>{subtitle && <span className="ryn-brand-slogan">{subtitle}</span>}</div>
  </div>
}
