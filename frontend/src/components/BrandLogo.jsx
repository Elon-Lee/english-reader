import React from 'react'
import { BRAND_NAME, BRAND_MARK, BRAND_SLOGAN } from '../config/brand.mjs'
import './BrandLogo.css'

export default function BrandLogo({ variant = 'workspace', subtitle = BRAND_SLOGAN, name = BRAND_NAME, mark = BRAND_MARK }) {
  const context = variant === 'auth' ? 'modern-auth-brand' : variant === 'workspace' ? 'modern-brand' : ''
  return <div className={`ryn-brand ryn-brand-${variant} ${context}`}>
    <img className="ryn-brand-mark" src={mark} width="40" height="40" alt="" aria-hidden="true" />
    <div className="ryn-brand-copy"><span className="ryn-brand-name">{name}</span>{subtitle && <span className="ryn-brand-slogan">{subtitle}</span>}</div>
  </div>
}
