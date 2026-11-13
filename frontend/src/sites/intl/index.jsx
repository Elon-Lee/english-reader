import React from 'react'
import { CrownOutlined } from '@ant-design/icons'
import InternationalPublicSite, { PurchasePage } from './pages/PublicSite'
import MembershipWorkspace from './pages/MembershipWorkspace'
import { siteAdminTabs } from './components/CommerceWorkspace'
import './styles.css'

export { default as BrandLogo } from './BrandLogo'
export { BRAND_NAME, BRAND_SLOGAN } from './brand.mjs'
export { resolveInternationalRoute as resolveSiteRoute, safeInternationalNextPath as safeNextPath } from './routes.mjs'
export { default as LegalPage, isLegalPath, legalPageTitle } from './pages/LegalPage'
export { siteAdminTabs }
export { requestPrivateImport } from './importAccess'
export const privateImportsEnabled = true
export const navigationItems = [{ key: 'membership', icon: <CrownOutlined />, label: '会员中心' }]
export const commercialRoutes = { membership: MembershipWorkspace }

export function SiteFrame({ children }) { return children }

export function PublicSite({ page, ...props }) {
  return page === 'purchase' ? <PurchasePage {...props} /> : <InternationalPublicSite page={page} {...props} />
}
