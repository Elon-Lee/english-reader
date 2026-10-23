import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Alert, App as AntApp, Avatar, Badge, Button, Card, Col, ConfigProvider, Descriptions,
  Drawer, Dropdown, Empty, Form, Input, InputNumber, Layout, List, Menu, Modal, Progress, Row,
  Radio, Segmented, Select, Skeleton, Space, Statistic, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  AppstoreOutlined, BarChartOutlined, BookOutlined, CheckCircleFilled, CloudUploadOutlined,
  CustomerServiceOutlined, DashboardOutlined, FileTextOutlined, MenuOutlined, MoreOutlined,
  PlusOutlined, ReadOutlined, SettingOutlined, ShopOutlined, StarOutlined, GiftOutlined, ThunderboltFilled, UserOutlined,
} from '@ant-design/icons'
import { csrfHeaders, deleteJson, fetchWithCsrf, getJson, postJson } from './api/client'
import { handleMembershipLimit } from './api/membershipLimit'
import ImportModal from './components/ImportModal'
import MembershipLimitModal from './components/MembershipLimitModal'
import { DEFAULT_PREFERENCES } from './config/preferences'
import CatalogPage from './pages/CatalogPage'
import AdminPage from './pages/AdminPage'
import LibraryPage from './pages/LibraryPage'
import MembershipPage from './pages/MembershipPage'
import PageErrorBoundary from './components/PageErrorBoundary'
import PlatformOperationsPage from './pages/PlatformOperationsPage'
import ReaderPage from './pages/ReaderPage'
import RewardsPageNew from './pages/RewardsPage'
import SettingsPage from './pages/SettingsPage'
import StatsPageNew from './pages/StatsPage'
import VocabularyPage from './pages/VocabularyPage'
import WorkspacePage from './pages/WorkspacePage'
import PageSkeleton from './components/PageSkeleton'
import AppSkeleton from './components/AppSkeleton'
import PublicSiteSkeleton from './components/PublicSiteSkeleton'
import PublicSite, { PurchasePage } from './pages/PublicSite'
import LegalPage, { isLegalPath, legalPageTitle } from './pages/LegalPage'
import './styles.css'

const { Header, Sider, Content } = Layout
const { Title, Text, Paragraph } = Typography

function modernEntryPath() {
  return '/app'
}

const bookAccents = ['#d9eadf', '#f5dfba', '#d8e1ef', '#ecd8d0']

function normalizeBook(book, index = 0, source = '私人读物') {
  const progress = book.progress || {}
  const durationMinutes = Number(book.estimatedMinutes || (book.duration ? Number(book.duration) / 60 : 0))
  const readingSeconds = Number(progress.readingSeconds || 0)
  const title = book.title || book.englishTitle || '未命名读物'
  const seriesTitle = typeof book.series === 'string' ? book.series : book.series?.title
  return { ...book, id: book.id || '', title, subtitle: book.subtitle || book.description || seriesTitle || '', author: book.author || '', level: book.level || '', source, accent: book.accent || bookAccents[index % bookAccents.length], cover: String(title).slice(0, 2).toUpperCase(), readingProgress: progress, progress: Number(book.progressPercent ?? progress.percent ?? (progress.completedAt ? 100 : 0)), minutes: Math.round(readingSeconds / 60), estimatedMinutes: durationMinutes, coverUrl: book.coverUrl || '' }
}

function Cover({ book, large = false }) { return <div className={`book-cover ${large ? 'book-cover-large' : ''}`} style={{ '--cover': book.accent }}><span>{book.cover}</span><small>{book.title}</small></div> }

function App() {
  const routePath = location.pathname
  const routeParams = new URLSearchParams(location.search)
  const legacyConsoleRoute = routeParams.has('screen')
  const consoleRoute = routePath === '/app' || legacyConsoleRoute
  const publicPage = legacyConsoleRoute ? '' : routePath === '/' ? 'home' : routePath === '/pricing' ? 'pricing' : routePath === '/support' ? 'support' : ''
  const purchaseRoute = routePath.startsWith('/purchase/')
  const [authState, setAuthState] = useState('loading')
  const [pageLoading, setPageLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const loadSequence = useRef(0)
  const [screen, setScreen] = useState(new URLSearchParams(location.search).get('screen') || 'workspace')
  const [books, setBooks] = useState([])
  const [catalogBooks, setCatalogBooks] = useState([])
  const [libraryBooks, setLibraryBooks] = useState([])
  const [learningDays, setLearningDays] = useState([])
  const [learning, setLearning] = useState(null)
  const [membership, setMembership] = useState(null)
  const [membershipOrders, setMembershipOrders] = useState([])
  const [rewardStatus, setRewardStatus] = useState(null)
  const [rewardsCatalog, setRewardsCatalog] = useState([])
  const [rewardsLedger, setRewardsLedger] = useState([])
  const [vocabulary, setVocabulary] = useState([])
  const [importTasks, setImportTasks] = useState([])
  const [adminData, setAdminData] = useState(null)
  const [currentUser, setCurrentUser] = useState(null)
  const [devices, setDevices] = useState([])
  const [preferences, setPreferences] = useState(DEFAULT_PREFERENCES)
  const preferencesLoaded = useRef(false)
  const [deletionStatus, setDeletionStatus] = useState({ status: 'none' })
  const [health, setHealth] = useState({ saasEnabled: true })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('全部')
  const [messageApi, contextHolder] = message.useMessage()
  const adminEntitlementRequests = useRef(new Map())
  const writeAdminEntitlement = (path, payload) => {
    const identity = `${path}:${JSON.stringify(payload)}`
    const record = adminEntitlementRequests.current.get(identity) || { key: payload.idempotencyKey || crypto.randomUUID?.() || `admin-${Date.now()}-${Math.random()}` }
    if (record.promise) return record.promise
    record.promise = postJson(path, { ...payload, idempotencyKey: record.key }).then(result => {
      adminEntitlementRequests.current.delete(identity)
      return result
    }, error => { record.promise = null; throw error })
    adminEntitlementRequests.current.set(identity, record)
    return record.promise
  }
  useEffect(() => {
    document.title = legalPageTitle(routePath) || (publicPage ? '拾页 · 把英语材料真正读懂' : purchaseRoute ? '确认学习方案 · 拾页' : '拾页 · 英语学习工作台')
  }, [publicPage, purchaseRoute, routePath])

  const reloadWorkspace = async ({ silent = false, targetScreen = screen } = {}) => {
    const loadId = silent ? loadSequence.current : ++loadSequence.current
    if (!silent) { setPageLoading(true); setPageError('') }
    let authenticated = false
    let initialPreferences = null
    try {
      const authResponse = await fetch('/api/auth/me', { credentials: 'include' })
      if (authResponse.status === 401) { setAuthState('unauthenticated'); return }
      if (!authResponse.ok) throw new Error('无法读取登录状态')
      const userData = await authResponse.json()
      authenticated = true
      setCurrentUser(userData.user || null)
      if (!consoleRoute) { setAuthState('authenticated'); return }
      if (!preferencesLoaded.current) {
        initialPreferences = await getJson('/api/preferences', DEFAULT_PREFERENCES)
        if (loadId !== loadSequence.current) return
        setPreferences(current => ({ ...current, ...(initialPreferences || {}) }))
        preferencesLoaded.current = true
      }
      setAuthState('authenticated')
    const needBooks = ['workspace', 'library', 'stats'].includes(targetScreen)
    const [healthData, deviceData, workspaceData, vocabularyData, catalogData, libraryData, daysData, membershipData, membershipOrderData, rewardData, rewardsCatalogData, rewardsLedgerData, importsData, preferencesData, deletionData] = await Promise.all([
      getJson('/api/health', health),
      targetScreen === 'settings' ? getJson('/api/auth/devices', { devices: [] }) : Promise.resolve({ devices }),
      needBooks ? getJson('/api/workspace/books') : Promise.resolve({ books: [] }),
      Promise.resolve({ items: vocabulary }),
      targetScreen === 'catalog' ? getJson('/api/catalog?limit=60') : Promise.resolve({ books: [] }),
      needBooks ? getJson('/api/library') : Promise.resolve({ items: [] }),
      ['workspace', 'stats'].includes(targetScreen) ? getJson('/api/workspace/learning') : Promise.resolve({ days: learningDays }),
      targetScreen === 'membership' ? getJson('/api/membership/usage') : Promise.resolve(membership),
      targetScreen === 'membership' ? getJson('/api/membership/orders') : Promise.resolve({ orders: membershipOrders }),
      targetScreen === 'rewards' ? getJson('/api/rewards/status', null) : Promise.resolve(rewardStatus),
      targetScreen === 'rewards' ? getJson('/api/rewards/catalog', { rewards: [] }) : Promise.resolve({ rewards: rewardsCatalog }),
      targetScreen === 'rewards' ? getJson('/api/rewards/ledger', { items: [] }) : Promise.resolve({ items: rewardsLedger }),
      targetScreen === 'library' ? getJson('/api/workspace/imports', { tasks: [] }) : Promise.resolve({ tasks: importTasks }),
      ['settings', 'reader'].includes(targetScreen) && !initialPreferences ? getJson('/api/preferences', preferences) : Promise.resolve(initialPreferences || preferences),
      targetScreen === 'settings' ? getJson('/api/account/deletion-status', { status: 'none' }) : Promise.resolve(deletionStatus),
    ])
    if (loadId !== loadSequence.current) return
    setPageError('')
    setHealth(healthData)
    setDevices(deviceData.devices || [])
    setVocabulary(vocabularyData.items || [])
    setPreferences(current => ({ ...current, ...(preferencesData || {}) }))
    if (['settings', 'reader'].includes(targetScreen) || !preferencesLoaded.current) preferencesLoaded.current = true
    setDeletionStatus(deletionData || { status: 'none' })
    const workspaceBooks = (workspaceData.books || []).map((book, i) => normalizeBook(book, i, '私人读物'))
    const officialBooks = (catalogData.books || []).map((book, i) => normalizeBook(book, i, '官方读物'))
    const savedBooks = (libraryData.items || []).map((book, i) => normalizeBook(book, i, '官方读物'))
    if (needBooks) setBooks([...workspaceBooks, ...savedBooks])
    if (targetScreen === 'library') setLibraryBooks([...workspaceBooks, ...savedBooks])
    if (targetScreen === 'catalog') setCatalogBooks(officialBooks)
    setLearningDays(daysData.days || [])
    if (['workspace', 'stats'].includes(targetScreen)) setLearning(daysData)
    setMembership(membershipData)
    setMembershipOrders(membershipOrderData.orders || [])
    setRewardStatus(rewardData)
    setRewardsCatalog(rewardsCatalogData.rewards || [])
    setRewardsLedger(rewardsLedgerData.items || [])
    setImportTasks(importsData.tasks || [])
    if (targetScreen === 'admin' && userData.user?.isAdmin) {
      const [adminDashboard, adminUsers, adminPlanVersions, adminCommerce, adminEntitlements] = await Promise.all([
        getJson('/api/admin/dashboard', null), getJson('/api/admin/users?limit=50', { users: [] }), getJson('/api/admin/plan-versions', { planVersions: [] }), getJson('/api/admin/commerce/products', { products: [] }), getJson('/api/admin/commerce/entitlements', { builtIn: [], configured: [] }),
      ])
      setAdminData({ dashboard: adminDashboard, users: adminUsers.users || [], audit: [], planVersions: adminPlanVersions.planVersions || [], commerceProducts: adminCommerce.products || [], commerceEntitlements: adminEntitlements })
    }
    } catch (error) {
      if (loadId === loadSequence.current && authenticated) {
        setAuthState('authenticated')
        setPageError(error.message || '页面数据加载失败，请重试。')
      }
      error.afterAuthentication = authenticated
      throw error
    } finally {
      if (!silent && loadId === loadSequence.current) setPageLoading(false)
    }
  }
  useEffect(() => { reloadWorkspace({ targetScreen: screen }).catch(error => { messageApi.error(error.message || '工作台加载失败'); if (!error.afterAuthentication) setAuthState('unauthenticated') }) }, [screen])
  useEffect(() => { const syncRoute = () => { const next = new URLSearchParams(location.search).get('screen') || 'workspace'; if (next === screen) reloadWorkspace({ targetScreen: next }).catch(error => messageApi.error(error.message || '页面刷新失败')); else { setPageLoading(true); setScreen(next) } }; addEventListener('popstate', syncRoute); return () => removeEventListener('popstate', syncRoute) }, [screen])
  useEffect(() => {
    if (screen !== 'library' || !importTasks.some(task => ['queued', 'uploading', 'running', 'processing', 'awaiting_processor'].includes(task.status))) return undefined
    const timer = setInterval(() => reloadWorkspace({ silent: true }), 3000)
    return () => clearInterval(timer)
  }, [importTasks, screen])
  const catalogAction = async book => {
    try {
      await postJson('/api/library/items', { bookId: book.id, shelfState: 'active' })
      await reloadWorkspace({ silent: true })
      messageApi.success('已加入我的书架')
    } catch (error) { if (!handleMembershipLimit(error, { onContinue: () => catalogAction(book) })) messageApi.error(error.message || '书架操作失败') }
  }
  const cancelImport = async task => {
    try { await postJson(`/api/workspace/imports/${encodeURIComponent(task.id)}/cancel`, {}); await reloadWorkspace({ silent: true }); messageApi.success('导入任务已取消') } catch (error) { messageApi.error(error.message || '取消任务失败') }
  }
  const retryImport = async task => {
    try {
      await postJson(`/api/workspace/imports/${encodeURIComponent(task.id)}/retry`, {})
      await reloadWorkspace({ silent: true })
      messageApi.success('已重新开始导入')
      void postJson(`/api/workspace/imports/${encodeURIComponent(task.id)}/complete`, {}).then(async result => {
        await reloadWorkspace({ silent: true })
        if (result.task?.status === 'complete') messageApi.success('内容已重新导入学习空间')
      }).catch(async error => { await reloadWorkspace({ silent: true }); if (!handleMembershipLimit(error, { onContinue: () => retryImport(task) })) messageApi.error(error.message || '重试导入失败') })
    } catch (error) { messageApi.error(error.message || '重试导入失败'); throw error }
  }
  const updateUserStatus = async (user, status) => {
    try { await postJson(`/api/admin/users/${encodeURIComponent(user.id)}/status`, { status, reason: status === 'suspended' ? '运营后台手动暂停' : '运营后台恢复账号' }); await reloadWorkspace({ silent: true }); messageApi.success(status === 'suspended' ? '用户已暂停' : '用户已恢复') } catch (error) { messageApi.error(error.message || '用户状态更新失败') }
  }
  const verifyAdminUser = async user => { try { await postJson(`/api/admin/users/${encodeURIComponent(user.id)}/verify`, {}); await reloadWorkspace({ silent: true, targetScreen: 'admin' }); messageApi.success('账号已标记为已验证') } catch (error) { messageApi.error(error.message || '标记验证失败'); throw error } }
  const deleteUnverifiedAdminUser = async user => { try { await deleteJson(`/api/admin/users/${encodeURIComponent(user.id)}`); await reloadWorkspace({ silent: true, targetScreen: 'admin' }); messageApi.success('待验证账号已删除') } catch (error) { messageApi.error(error.message || '删除账号失败'); throw error } }
  const createInvitation = async payload => {
    try { const result = await postJson('/api/admin/invitations', payload); await reloadWorkspace({ silent: true }); const items = result.invitations || [result]; messageApi.success(items.length > 1 ? `已生成 ${items.length} 个邀请码` : `邀请码 ${items[0]?.code || ''} 已创建`); return result } catch (error) { messageApi.error(error.message || '邀请码创建失败'); throw error }
  }
  const deleteUnusedInvitations = async (batchId, invitationIds) => { try { const result = await deleteJson(`/api/admin/invitation-batches/${encodeURIComponent(batchId)}/invitations`, { invitationIds }); await reloadWorkspace({ silent: true, targetScreen: 'admin' }); messageApi.success(`已删除 ${result.deleted || 0} 个未使用邀请码`); return result } catch (error) { messageApi.error(error.message || '删除邀请码失败'); throw error } }
  const revokeDevice = async (userId, deviceId) => {
    Modal.confirm({ title: '确认撤销该设备？', content: '撤销后，该设备的活跃会话会立即失效，需要重新登录。', okText: '确认撤销', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { try { const response = await fetchWithCsrf(`/api/admin/users/${encodeURIComponent(userId)}/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '设备撤销失败'); await reloadWorkspace({ silent: true }); messageApi.success('设备已撤销') } catch (error) { messageApi.error(error.message || '设备撤销失败'); throw error } } })
  }
  const adjustQuota = async (userId, payload) => {
    try { await writeAdminEntitlement('/api/admin/quotas/adjust', { ...payload, userId }); await reloadWorkspace({ silent: true }); messageApi.success('额度调整已完成') } catch (error) { messageApi.error(error.message || '额度调整失败'); throw error }
  }
  const updateSubscription = async payload => {
    try { await writeAdminEntitlement('/api/admin/subscriptions', payload); await reloadWorkspace({ silent: true }); messageApi.success('订阅状态已更新') } catch (error) { messageApi.error(error.message || '订阅更新失败'); throw error }
  }
  const createManualOrder = async payload => {
    try { await writeAdminEntitlement('/api/admin/manual-orders', payload); await reloadWorkspace({ silent: true }); messageApi.success('人工订阅已创建') } catch (error) { messageApi.error(error.message || '人工订阅创建失败'); throw error }
  }
  const createCommerceProduct = async payload => { try { const result = await postJson('/api/admin/commerce/products', payload); await reloadWorkspace({ silent: true }); messageApi.success('套餐已创建，请继续配置首个版本'); return result } catch (error) { messageApi.error(error.message || '套餐创建失败'); throw error } }
  const createCommerceVersion = async (productId, payload) => { try { await postJson(`/api/admin/commerce/products/${encodeURIComponent(productId)}/versions`, payload); await reloadWorkspace({ silent: true }); messageApi.success('商品新版本已保存为草稿') } catch (error) { messageApi.error(error.message || '商品版本创建失败'); throw error } }
  const publishCommerceVersion = async versionId => { try { await postJson(`/api/admin/commerce/versions/${encodeURIComponent(versionId)}/publish`, {}); await reloadWorkspace({ silent: true }); messageApi.success('商品版本已发布，旧版本已停止新售') } catch (error) { messageApi.error(error.message || '商品版本发布失败'); throw error } }
  const setCommerceProductActive = async (productId, active) => { try { await postJson(`/api/admin/commerce/products/${encodeURIComponent(productId)}/status`, { active }); await reloadWorkspace({ silent: true }); messageApi.success(active ? '商品已恢复销售' : '商品已停止新售') } catch (error) { messageApi.error(error.message || '商品状态更新失败'); throw error } }
  const deleteCommerceProduct = async productId => { try { await postJson(`/api/admin/commerce/products/${encodeURIComponent(productId)}/delete`, {}); await reloadWorkspace({ silent: true, targetScreen: 'admin' }); messageApi.success('未上架套餐已删除') } catch (error) { messageApi.error(error.message || '套餐删除失败'); throw error } }
  const createConfiguredBenefit = async payload => { try { await postJson('/api/admin/commerce/configured-benefits', payload); await reloadWorkspace({ silent: true }); messageApi.success('配置权益已创建') } catch (error) { messageApi.error(error.message || '配置权益创建失败'); throw error } }
  const updateConfiguredBenefit = async (benefitId, payload) => { try { await postJson(`/api/admin/commerce/configured-benefits/${encodeURIComponent(benefitId)}`, payload); await reloadWorkspace({ silent: true }); messageApi.success('配置权益已更新') } catch (error) { messageApi.error(error.message || '配置权益更新失败'); throw error } }
  const login = async values => { const stored = localStorage.getItem('shiyue-modern-device') || `modern-${crypto.randomUUID?.() || Date.now()}-device`; localStorage.setItem('shiyue-modern-device', stored); const { deviceReplacement, ...payload } = values; try { const result = await postJson(deviceReplacement ? '/api/auth/login/replace-device' : '/api/auth/login', { ...payload, deviceId: stored }); setAuthState('authenticated'); return result } catch (error) { if (error.code === 'device_limit_exceeded') return { deviceLimit: error.payload }; messageApi.error(error.message || '登录失败'); throw error } }
  const register = async values => { try { const result = await postJson('/api/auth/register', values); messageApi.success('账号已创建，请前往邮箱完成验证'); return result } catch (error) { messageApi.error(error.message || '注册失败'); throw error } }
  const forgotPassword = async values => { try { const result = await postJson('/api/auth/forgot-password', values); messageApi.success('如果账号存在，重置邮件已发送'); return result } catch (error) { messageApi.error(error.message || '发送失败'); throw error } }
  const logout = async () => { try { await postJson('/api/auth/logout', {}); setCurrentUser(null); setAuthState('unauthenticated') } catch (error) { messageApi.error(error.message || '退出登录失败') } }
  const savePreferences = async values => { const themeOnly = Object.keys(values || {}).length === 1 && 'theme' in values; try { const result = await postJson('/api/preferences', values); setPreferences(current => ({ ...current, ...(result.preferences || result || values) })); messageApi.success(themeOnly ? '界面主题已保存' : '阅读偏好已保存') } catch (error) { messageApi.error(error.message || (themeOnly ? '界面主题保存失败' : '阅读偏好保存失败')); throw error } }
  const mergePreferences = values => setPreferences(current => ({ ...current, ...values }))
  const requestDeletion = () => { Modal.confirm({ title: '确认申请注销账户？', content: '提交后会退出当前设备，并进入 30 天宽限期。期间重新登录可以取消。', okText: '申请注销', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { try { await postJson('/api/account/deletion', { reason: '用户在新版工作台申请注销' }); setAuthState('unauthenticated'); messageApi.success('注销申请已提交') } catch (error) { messageApi.error(error.message || '注销申请失败'); throw error } } }) }
  const cancelDeletion = async () => { try { await postJson('/api/account/deletion/cancel', {}); await reloadWorkspace({ silent: true }); messageApi.success('注销申请已取消') } catch (error) { messageApi.error(error.message || '取消注销失败') } }
  const revokeOwnDevice = async deviceId => {
    Modal.confirm({ title: '确认撤销此设备？', content: '撤销后，该设备需要重新登录才能访问工作台。', okText: '确认撤销', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { try { const response = await fetchWithCsrf(`/api/auth/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '设备撤销失败'); await reloadWorkspace({ silent: true }); messageApi.success('设备已撤销') } catch (error) { messageApi.error(error.message || '设备撤销失败'); throw error } } })
  }
  const exportAdminSummary = async () => { try { const response = await fetch('/api/admin/exports/summary', { credentials: 'include' }); const data = await response.json(); if (!response.ok) throw new Error(data.error || '导出失败'); const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `shiyue-admin-summary-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(url); messageApi.success('运营摘要已导出') } catch (error) { messageApi.error(error.message || '导出失败') } }
  const checkIn = async () => { try { await postJson('/api/checkins', {}); await reloadWorkspace({ silent: true }); messageApi.success('签到成功，成长值已更新') } catch (error) { messageApi.error(error.message || '签到失败') } }
  const redeemReward = async (code, idempotencyKey) => { await postJson('/api/rewards/redeem', { code, idempotencyKey }); await reloadWorkspace({ silent: true }); messageApi.success('奖励兑换成功') }
  const filteredBooks = useMemo(() => books.filter(book => `${book.title} ${book.subtitle} ${book.author}`.toLowerCase().includes(query.toLowerCase()) && (filter === '全部' || book.source === filter)), [books, query, filter])

  const nav = [{ key: 'workspace', icon: <DashboardOutlined />, label: '学习空间' }, { key: 'catalog', icon: <ShopOutlined />, label: '书城' }, { key: 'library', icon: <BookOutlined />, label: '我的书架' }, { key: 'stats', icon: <BarChartOutlined />, label: '学习记录' }, { key: 'vocab', icon: <StarOutlined />, label: '生词复习' }, { key: 'rewards', icon: <GiftOutlined />, label: '成长奖励' }, { key: 'membership', icon: <ThunderboltFilled />, label: '会员中心' }, { key: 'admin', icon: <AppstoreOutlined />, label: '运营后台' }, { key: 'platform', icon: <SettingOutlined />, label: '平台与部署' }].filter(item => item.key === 'platform' ? currentUser?.isAdmin && currentUser?.canManagePlatform : item.key !== 'admin' || currentUser?.isAdmin)
  const settings = [{ key: 'settings', icon: <SettingOutlined />, label: '系统设置' }]
  const selectScreen = (key, tab) => { setMobileOpen(false); if (key === screen) { if (pageLoading) reloadWorkspace({ targetScreen: key }).catch(error => messageApi.error(error.message || '页面刷新失败')); return } setPageLoading(true); history.pushState({}, '', `${modernEntryPath()}?screen=${key}${key === 'admin' && tab === 'catalog' ? '&adminTab=catalog' : key === 'catalog' && tab === 'onboarding' ? '&onboarding=1' : ''}`); setScreen(key) }
  const openReader = (book, options = {}) => { const kind = book.source === '官方读物' || book.trial ? 'official' : 'workspace'; location.href = `${modernEntryPath()}?screen=reader&reader=${kind}&id=${encodeURIComponent(book.id)}${book.trial ? '&trial=1' : ''}${options.guided || new URLSearchParams(location.search).get('onboarding') === '1' ? '&onboarding=1' : ''}` }

  const themePalettes = {
    pine: { primary: '#285c45', info: '#285c45', sider: '#f7f8f4', header: '#fcfcf8', selected: '#e7efe8', hover: '#eef2ed' },
    mist: { primary: '#426b84', info: '#426b84', sider: '#f2f5f7', header: '#fbfcfd', selected: '#e1ebf1', hover: '#edf3f6' },
    iris: { primary: '#71638d', info: '#71638d', sider: '#f5f3f8', header: '#fcfbfd', selected: '#ebe6f2', hover: '#f2eff6' },
  }
  const activePalette = themePalettes[preferences.theme] || themePalettes.pine
  const theme = { token: { colorPrimary: activePalette.primary, colorInfo: activePalette.info, borderRadius: 8, fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif' }, components: { Layout: { siderBg: activePalette.sider, headerBg: activePalette.header }, Menu: { lightItemBg: activePalette.sider, lightItemSelectedBg: activePalette.selected, lightItemSelectedColor: activePalette.primary, lightItemHoverBg: activePalette.hover, itemBorderRadius: 6 } } }
  if (['/verify-email', '/reset-password'].includes(location.pathname)) return <ConfigProvider theme={theme}><AntApp>{contextHolder}<AuthActionPage path={location.pathname} /></AntApp></ConfigProvider>
  if (isLegalPath(routePath)) return <ConfigProvider theme={theme}><AntApp><LegalPage path={routePath} authenticated={authState === 'authenticated'} /></AntApp></ConfigProvider>
  if (authState === 'loading') return <ConfigProvider theme={theme}><AntApp>{contextHolder}{consoleRoute ? <AppSkeleton reader={screen === 'reader'} /> : publicPage ? <PublicSiteSkeleton page={publicPage} /> : <main className="modern-auth"><Card className="modern-auth-card"><Skeleton active avatar title paragraph={{ rows: 6 }} /></Card></main>}</AntApp></ConfigProvider>
  if (publicPage) return <ConfigProvider theme={theme}><AntApp>{contextHolder}<PublicSite authenticated={authState === 'authenticated'} page={publicPage} /></AntApp></ConfigProvider>
  if (purchaseRoute) return <ConfigProvider theme={theme}><AntApp>{contextHolder}<PageErrorBoundary key={routePath}><PurchasePage authenticated={authState === 'authenticated'} /></PageErrorBoundary></AntApp></ConfigProvider>
  if (routePath === '/login' || routePath === '/register') {
    const next = routeParams.get('next') || '/app'
    if (authState === 'authenticated') { location.replace(next); return null }
    return <ConfigProvider theme={theme}><AntApp>{contextHolder}<AuthPage loading={false} initialMode={routePath === '/register' ? 'register' : 'login'} next={next} onLogin={login} onRegister={register} onForgot={forgotPassword} /></AntApp></ConfigProvider>
  }
  if (authState !== 'authenticated') return <ConfigProvider theme={theme}><AntApp>{contextHolder}<AuthPage loading={false} next="/app" onLogin={login} onRegister={register} onForgot={forgotPassword} /></AntApp></ConfigProvider>
  return <ConfigProvider theme={theme}>
    <AntApp>{contextHolder}<Layout data-study-theme={preferences.theme || DEFAULT_PREFERENCES.theme} style={{ '--study-primary': activePalette.primary, '--study-tint': activePalette.selected, '--study-tint-soft': activePalette.hover }} className={`modern-shell ${screen === 'reader' ? 'reader-shell' : ''}`}>
      <Sider className="modern-sider" width={248} breakpoint="lg" collapsedWidth={0} trigger={null} onBreakpoint={broken => { if (broken) setMobileOpen(false) }}>
        <Brand /><SidebarMenu nav={nav} settings={settings} screen={screen} selectScreen={selectScreen} />
        <div className="sider-bottom"><div className="plan-chip"><div><Text className="plan-label">{currentUser?.displayName || '我的学习账号'}</Text><Text className="plan-copy">{currentUser?.email || '正在读取账户'}</Text></div></div><Text className="sider-version">让每次阅读有所积累</Text></div>
      </Sider>
      <Drawer placement="left" open={mobileOpen} onClose={() => setMobileOpen(false)} closable={false} width={280} styles={{ body: { padding: 0, background: '#17392b' } }}><Brand /><SidebarMenu nav={nav} settings={settings} screen={screen} selectScreen={selectScreen} /></Drawer>
      <Layout><Header className="modern-header"><Button className="mobile-menu" type="text" icon={<MenuOutlined />} onClick={() => setMobileOpen(true)} /><div className="header-context"><Text className="eyebrow">WORKSPACE / {nav.find(n => n.key === screen)?.label || '设置'}</Text><Text className="header-status">原声听读 · 逐句积累</Text></div></Header>
        <Content className="modern-content"><PageErrorBoundary key={screen}>{pageError ? <Alert showIcon type="error" message="页面暂时无法加载" description={pageError} action={<Button onClick={() => reloadWorkspace({ targetScreen: screen }).catch(() => {})}>重试</Button>} /> : <Page loading={pageLoading} screen={screen} books={filteredBooks} allBooks={books} catalogBooks={catalogBooks} libraryBooks={libraryBooks} importTasks={importTasks} learningDays={learningDays} learning={learning} membership={membership} membershipOrders={membershipOrders} rewardStatus={rewardStatus} vocabulary={vocabulary} rewardsCatalog={rewardsCatalog} rewardsLedger={rewardsLedger} adminData={adminData} currentUser={currentUser} devices={devices} preferences={preferences} deletionStatus={deletionStatus} query={query} setQuery={setQuery} filter={filter} setFilter={setFilter} selectScreen={selectScreen} openReader={openReader} openImport={() => setImportOpen(true)} messageApi={messageApi} health={health} onRefresh={() => reloadWorkspace({ silent: true, targetScreen: screen })} onCatalogAction={catalogAction} onCancelImport={cancelImport} onRetryImport={retryImport} onUpdateUserStatus={updateUserStatus} onVerifyUser={verifyAdminUser} onDeleteUnverifiedUser={deleteUnverifiedAdminUser} onCreateInvitation={createInvitation} onDeleteUnusedInvitations={deleteUnusedInvitations} onRevokeDevice={revokeDevice} onAdjustQuota={adjustQuota} onUpdateSubscription={updateSubscription} onCreateManualOrder={createManualOrder} onCreateCommerceProduct={createCommerceProduct} onCreateCommerceVersion={createCommerceVersion} onPublishCommerceVersion={publishCommerceVersion} onSetCommerceProductActive={setCommerceProductActive} onDeleteCommerceProduct={deleteCommerceProduct} onCreateConfiguredBenefit={createConfiguredBenefit} onUpdateConfiguredBenefit={updateConfiguredBenefit} onRevokeOwnDevice={revokeOwnDevice} onExportAdminSummary={exportAdminSummary} onCheckIn={checkIn} onRedeemReward={redeemReward} onSavePreferences={savePreferences} onPreferencesChange={mergePreferences} onLogout={logout} onRequestDeletion={requestDeletion} onCancelDeletion={cancelDeletion} />}</PageErrorBoundary></Content>
      </Layout>
    </Layout><ImportModal open={importOpen} onClose={() => setImportOpen(false)} onResume={() => setImportOpen(true)} onCreated={() => reloadWorkspace({ silent: true })} messageApi={messageApi} /><MembershipLimitModal onRefresh={async () => { setMembership(await getJson('/api/membership/usage')); await reloadWorkspace({ silent: true }) }} /></AntApp>
  </ConfigProvider>
}

function Brand() { return <div className="modern-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name">拾页</Text><Text className="brand-subtitle">ENGLISH WORKSPACE</Text></div></div> }
function AuthPage({ loading, initialMode = 'login', next = '/app', onLogin, onRegister, onForgot }) {
  const [form] = Form.useForm()
  const [mode, setMode] = useState(initialMode)
  const [submitting, setSubmitting] = useState(false)
  const [registrationEmail, setRegistrationEmail] = useState('')
  const [deviceConflict, setDeviceConflict] = useState(null)
  const [selectedDevice, setSelectedDevice] = useState('')
  const [loginValues, setLoginValues] = useState(null)
  const submit = async values => {
    setSubmitting(true)
    try {
      if (mode === 'login') {
        const result = await onLogin(values)
        if (result?.deviceLimit) { setLoginValues(values); setDeviceConflict(result.deviceLimit); setSelectedDevice(''); return }
        location.href = next
      }
      else if (mode === 'register') {
        await onRegister({ invitationCode: values.invitationCode, email: values.email, password: values.password })
        setRegistrationEmail(values.email)
        setMode('login')
        form.setFieldsValue({ invitationCode: undefined, password: undefined })
      } else {
        await onForgot({ email: values.email })
        setMode('login')
        form.setFieldsValue({ password: undefined })
      }
    } finally { setSubmitting(false) }
  }
  const replaceDevice = async () => {
    if (!selectedDevice || !loginValues) return
    setSubmitting(true)
    try {
      const result = await onLogin({ ...loginValues, replaceDeviceId: selectedDevice, deviceReplacement: true })
      if (result?.deviceLimit) { setDeviceConflict(result.deviceLimit); setSelectedDevice(''); return }
      location.href = next
    } finally { setSubmitting(false) }
  }
  const confirmDeviceReplacement = () => {
    const selected = deviceConflict?.devices?.find(device => device.id === selectedDevice)
    if (!selected) return
    Modal.confirm({ title: '确认解除这台设备？', content: `${selected.label || '已登录设备'}将立即退出并失去访问权限。解除后会在当前设备自动登录。`, okText: '解除并登录', cancelText: '再想一下', okButtonProps: { danger: true }, onOk: replaceDevice })
  }
  return <main className="modern-auth"><Card className="modern-auth-card"><div className="modern-auth-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name auth-brand-name">拾页</Text><Text className="brand-subtitle auth-brand-subtitle">ENGLISH WORKSPACE</Text></div></div>{deviceConflict ? <section aria-labelledby="device-limit-title"><Title level={2} id="device-limit-title">选择要解除的设备</Title><Paragraph>此账号已连接 {deviceConflict.activeDevices} 台设备（上限 {deviceConflict.limit} 台）。解除一台旧设备后，会自动在当前设备登录。</Paragraph><Alert type="warning" showIcon message="被解除设备上的登录会立即失效" description="请选择你不再使用的设备。" /><Radio.Group className="device-replacement-list" value={selectedDevice} onChange={event => setSelectedDevice(event.target.value)} aria-label="选择要解除的已登录设备">{(deviceConflict.devices || []).map(device => <Radio key={device.id} value={device.id} className="device-replacement-option"><span className="device-replacement-copy"><strong>{device.label || '已登录设备'}</strong><small>{device.userAgent || '未知浏览器或系统'}</small><small>最近活动：{device.lastSeenAt ? new Date(device.lastSeenAt).toLocaleString('zh-CN') : '未知'}</small></span></Radio>)}</Radio.Group><Space direction="vertical" className="device-replacement-actions" size={10}><Button block type="primary" size="large" disabled={!selectedDevice} loading={submitting} onClick={confirmDeviceReplacement}>解除所选设备并继续登录</Button><Button block size="large" disabled={submitting} onClick={() => { setDeviceConflict(null); setSelectedDevice(''); if (loginValues) form.setFieldsValue(loginValues) }}>返回登录</Button></Space></section> : <><Text className="eyebrow">SHIYUE MEMBERS</Text><Title level={1}>{mode === 'login' ? '登录拾页' : mode === 'register' ? '创建账号' : '找回密码'}</Title><Paragraph>{mode === 'login' ? '登录后进入书城、学习空间和会员中心。未激活邮箱的账号需要先完成邮件验证。' : mode === 'register' ? '使用有效邀请码创建学习账号，完成邮箱激活后才能登录。' : '输入注册邮箱，我们会发送密码重置邮件。'}</Paragraph><Segmented block value={mode} onChange={value => { setMode(value); setDeviceConflict(null) }} options={[{ label: '登录', value: 'login' }, { label: '注册', value: 'register' }, { label: '找回密码', value: 'forgot' }]} />{registrationEmail && <Alert className="auth-action-alert" type="success" showIcon message="账号已创建，请先验证邮箱" description={`验证邮件已发送到 ${registrationEmail}。打开邮件中的链接完成激活，再回来登录；未收到时请检查垃圾邮件。`} />}<Form form={form} layout="vertical" onFinish={submit} disabled={loading || submitting} className="modern-auth-form">{mode === 'register' && <Form.Item label="邀请码" name="invitationCode" extra={<a href="/support#invitation" target="_blank" rel="noreferrer">没有邀请码？联系支持咨询</a>} rules={[{ required: true, message: '请输入邀请码' }]}><Input size="large" autoComplete="off" /></Form.Item>}<Form.Item label="邮箱" name="email" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}><Input size="large" autoComplete="email" /></Form.Item>{mode !== 'forgot' && <Form.Item label="密码" name="password" rules={[{ required: true, min: 10, message: '密码至少 10 位' }]}><Input.Password size="large" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></Form.Item>}<Button block type="primary" size="large" htmlType="submit" loading={submitting || loading}>{mode === 'login' ? '登录' : mode === 'register' ? '创建账号' : '发送重置邮件'}</Button></Form><Text type="secondary">继续即表示同意用户协议、隐私政策与内容声明。</Text></>}</Card></main>
}

function AuthActionPage({ path }) {
  const token = new URLSearchParams(location.search).get('token') || ''
  const [status, setStatus] = useState(path === '/verify-email' ? 'loading' : 'ready')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  useEffect(() => {
    if (path !== '/verify-email') return
    if (!token) { setStatus('error'); setError('验证链接缺少必要参数。'); return }
    postJson('/api/auth/verify-email', { token })
      .then(() => setStatus('success'))
      .catch(reason => { setStatus('error'); setError(reason.message || '邮箱验证失败') })
  }, [path, token])
  const backToLogin = () => { location.href = '/login' }
  if (path === '/verify-email') return <main className="modern-auth"><Card className="modern-auth-card"><div className="modern-auth-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name auth-brand-name">拾页</Text><Text className="brand-subtitle auth-brand-subtitle">EMAIL VERIFICATION</Text></div></div>{status === 'loading' ? <div className="auth-action-state"><Skeleton active title paragraph={{ rows: 4 }} /></div> : status === 'success' ? <div className="auth-action-state"><CheckCircleFilled className="auth-action-success" /><Title level={2}>邮箱已激活</Title><Paragraph>现在可以使用注册邮箱和密码登录拾页。</Paragraph><Button block type="primary" size="large" onClick={backToLogin}>返回登录</Button></div> : <div className="auth-action-state"><Alert type="error" showIcon message="邮箱验证失败" description={error} /><Button block size="large" onClick={backToLogin}>返回登录</Button></div>}</Card></main>
  const resetPassword = async values => {
    setSubmitting(true); setError('')
    try { await postJson('/api/auth/reset-password', { token, password: values.password }); setStatus('success') }
    catch (reason) { setError(reason.message || '密码重置失败') }
    finally { setSubmitting(false) }
  }
  return <main className="modern-auth"><Card className="modern-auth-card"><div className="modern-auth-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name auth-brand-name">拾页</Text><Text className="brand-subtitle auth-brand-subtitle">PASSWORD RESET</Text></div></div>{status === 'success' ? <div className="auth-action-state"><CheckCircleFilled className="auth-action-success" /><Title level={2}>密码已重置</Title><Paragraph>旧设备会话已经失效，请使用新密码重新登录。</Paragraph><Button block type="primary" size="large" onClick={backToLogin}>返回登录</Button></div> : <><Text className="eyebrow">ACCOUNT SECURITY</Text><Title level={1}>设置新密码</Title><Paragraph>新密码至少需要 10 位。完成后请重新登录。</Paragraph>{!token && <Alert type="error" showIcon message="重置链接缺少必要参数" />}{error && <Alert className="auth-action-alert" type="error" showIcon message={error} />}<Form layout="vertical" onFinish={resetPassword} disabled={!token || submitting} className="modern-auth-form"><Form.Item label="新密码" name="password" rules={[{ required: true, min: 10, message: '密码至少 10 位' }]}><Input.Password size="large" autoComplete="new-password" /></Form.Item><Form.Item label="确认新密码" name="confirmPassword" dependencies={['password']} rules={[{ required: true, message: '请再次输入新密码' }, ({ getFieldValue }) => ({ validator(_, value) { return !value || getFieldValue('password') === value ? Promise.resolve() : Promise.reject(new Error('两次输入的密码不一致')) } })]}><Input.Password size="large" autoComplete="new-password" /></Form.Item><Button block type="primary" size="large" htmlType="submit" loading={submitting}>确认重置密码</Button></Form><Button block type="link" onClick={backToLogin}>返回登录</Button></>}</Card></main>
}
function SidebarMenu({ nav, settings, screen, selectScreen }) { return <div className="sidebar-menu-wrap"><Menu theme="light" mode="inline" selectedKeys={[screen]} items={nav} onClick={({ key }) => selectScreen(key)} /><div className="menu-divider" /><Menu theme="light" mode="inline" selectedKeys={[screen]} items={settings} onClick={({ key }) => selectScreen(key)} /></div> }

function Page({ screen, loading, ...props }) {
  if (loading) return <PageSkeleton reader={screen === 'reader'} />
  if (screen === 'platform' && !(props.currentUser?.isAdmin && props.currentUser?.canManagePlatform)) return <Empty description="平台与部署仅允许本地模式的管理员访问" />
  const pages = { workspace: <WorkspacePage {...props} />, catalog: <CatalogPage {...props} />, library: <LibraryPage {...props} />, stats: <StatsPageNew {...props} />, vocab: <VocabularyPage {...props} />, rewards: <RewardsPageNew {...props} />, membership: <MembershipPage {...props} />, admin: <AdminPage {...props} />, platform: <PlatformOperationsPage {...props} />, settings: <SettingsPage {...props} />, reader: <ReaderPage {...props} /> }
  return pages[screen] || pages.workspace
}

function PageIntro({ eyebrow, title, copy, action }) { return <div className="page-intro"><div><Text className="eyebrow">{eyebrow}</Text><Title level={1}>{title}</Title><Paragraph>{copy}</Paragraph></div>{action}</div> }
function BookCard({ book, onClick, onAction, actionLabel, catalog }) { return <Card hoverable className="book-card" onClick={onClick}><div className="book-card-top"><Cover book={book} /><Tag>{book.level}</Tag></div><Title level={4} ellipsis={{ rows: 1 }}>{book.title}</Title><Text type="secondary" ellipsis>{book.subtitle}</Text><div className="book-card-meta"><Text>{book.progress ? `${book.progress}% 已完成` : '尚未开始'}</Text><Text>{book.minutes ? `${book.minutes} 分钟` : '准备开始'}</Text></div><Progress percent={book.progress} showInfo={false} strokeColor="#2f6f50" />{catalog && <Button block type={book.inLibrary && book.inLibrary ? 'default' : 'primary'} disabled={book.inLibrary && book.inLibrary} onClick={event => { event.stopPropagation(); onAction?.() }} style={{ marginTop: 14 }}>{book.inLibrary && book.inLibrary ? '已加入书架' : actionLabel || '加入书架'}</Button>}</Card> }
function SectionHeader({ title, action }) { return <div className="section-header"><Title level={3}>{title}</Title>{action}</div> }
function ActionCard({ icon, title, copy, action, onClick }) { return <Col xs={24} md={8}><Card className="action-card"><div className="action-icon">{icon}</div><Title level={4}>{title}</Title><Paragraph>{copy}</Paragraph><Button type="link" onClick={onClick}>{action} →</Button></Card></Col> }
function Metric({ title, value, suffix, note }) { return <Col xs={12} lg={6}><Card className="metric-card"><Statistic title={title} value={value} suffix={suffix} /><Text type="secondary">{note}</Text></Card></Col> }
function Quota({ title, items }) { return <Col xs={24} md={8}><Card title={title} className="quota-card"><List size="small" dataSource={items} renderItem={item => <List.Item><CheckCircleFilled className="check-icon" />{item}</List.Item>} /></Card></Col> }
createRoot(document.getElementById('root')).render(<App />)
