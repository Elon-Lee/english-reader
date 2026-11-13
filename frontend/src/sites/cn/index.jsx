export { default as PublicSite } from '../../pages/PublicSite'
export { default as SiteFrame } from './SiteFrame'
export { default as BrandLogo } from '../../components/BrandLogo'
export { BRAND_NAME, BRAND_SLOGAN } from '../../config/brand.mjs'
export { resolvePrivateRoute as resolveSiteRoute, safeNextPath } from '../../utils/privateRoutes.mjs'
export { default as LegalPage, isLegalPath, legalPageTitle } from '../../pages/LegalPage'

export const navigationItems = []
export const commercialRoutes = {}
export const siteAdminTabs = () => []
export const privateImportsEnabled = false
export const requestPrivateImport = async () => false
