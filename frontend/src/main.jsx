import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Alert, App as AntApp, Avatar, Badge, Button, Card, Col, ConfigProvider, Descriptions,
  Drawer, Dropdown, Empty, Form, Input, InputNumber, Layout, List, Menu, Modal, Progress, Row,
  Segmented, Select, Skeleton, Space, Statistic, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  AppstoreOutlined, BarChartOutlined, BookOutlined, CheckCircleFilled, CloudUploadOutlined,
  CustomerServiceOutlined, DashboardOutlined, FileTextOutlined, MenuOutlined, MoreOutlined,
  PlusOutlined, ReadOutlined, SettingOutlined, ShopOutlined, StarOutlined, GiftOutlined, ThunderboltFilled, UserOutlined,
} from '@ant-design/icons'
import { csrfHeaders, deleteJson, fetchWithCsrf, getJson, postJson } from './api/client'
import { handleMembershipLimit } from './api/membershipLimit'
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
import PublicSite, { PurchasePage } from './pages/PublicSite'
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
  return { ...book, id: book.id || '', title, subtitle: book.subtitle || book.description || book.series?.title || '', author: book.author || '', level: book.level || '', source, accent: book.accent || bookAccents[index % bookAccents.length], cover: String(title).slice(0, 2).toUpperCase(), progress: Number(book.progressPercent ?? (durationMinutes ? Math.min(100, Math.round(readingSeconds / 60 / durationMinutes * 100)) : 0)), minutes: Math.round(readingSeconds / 60) || Number(book.estimatedMinutes || 0), coverUrl: book.coverUrl || '' }
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
  const loadSequence = useRef(0)
  const [screen, setScreen] = useState(new URLSearchParams(location.search).get('screen') || 'workspace')
  const [books, setBooks] = useState([])
  const [catalogBooks, setCatalogBooks] = useState([])
  const [libraryBooks, setLibraryBooks] = useState([])
  const [learningDays, setLearningDays] = useState([])
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
    document.title = publicPage ? '拾页 · 把英语材料真正读懂' : purchaseRoute ? '确认学习方案 · 拾页' : '拾页 · 英语学习工作台'
  }, [publicPage, purchaseRoute])

  const reloadWorkspace = async ({ silent = false, targetScreen = screen } = {}) => {
    const loadId = silent ? loadSequence.current : ++loadSequence.current
    if (!silent) setPageLoading(true)
    let authenticated = false
    try {
      const authResponse = await fetch('/api/auth/me', { credentials: 'include' })
      if (authResponse.status === 401) { setAuthState('unauthenticated'); return }
      if (!authResponse.ok) throw new Error('无法读取登录状态')
      const userData = await authResponse.json()
      authenticated = true
      setAuthState('authenticated')
      setCurrentUser(userData.user || null)
    if (!consoleRoute) return
    const needBooks = ['workspace', 'library', 'stats', 'vocab'].includes(targetScreen)
    const [healthData, deviceData, workspaceData, vocabularyData, catalogData, libraryData, daysData, membershipData, membershipOrderData, rewardData, rewardsCatalogData, rewardsLedgerData, importsData, preferencesData, deletionData] = await Promise.all([
      getJson('/api/health', health),
      targetScreen === 'settings' ? getJson('/api/auth/devices', { devices: [] }) : Promise.resolve({ devices }),
      needBooks ? getJson('/api/workspace/books', { books: [] }) : Promise.resolve({ books: [] }),
      targetScreen === 'vocab' ? getJson('/api/workspace/vocabulary', { items: [] }) : Promise.resolve({ items: vocabulary }),
      targetScreen === 'catalog' ? getJson('/api/catalog?limit=60', { books: [] }) : Promise.resolve({ books: [] }),
      targetScreen === 'library' ? getJson('/api/library', { items: [] }) : Promise.resolve({ items: [] }),
      ['workspace', 'stats'].includes(targetScreen) ? getJson('/api/workspace/learning-days?limit=365', { days: [] }) : Promise.resolve({ days: learningDays }),
      targetScreen === 'membership' ? getJson('/api/membership/usage', null) : Promise.resolve(membership),
      targetScreen === 'membership' ? getJson('/api/membership/orders', { orders: [] }) : Promise.resolve({ orders: membershipOrders }),
      ['workspace', 'rewards'].includes(targetScreen) ? getJson('/api/rewards/status', null) : Promise.resolve(rewardStatus),
      targetScreen === 'rewards' ? getJson('/api/rewards/catalog', { rewards: [] }) : Promise.resolve({ rewards: rewardsCatalog }),
      targetScreen === 'rewards' ? getJson('/api/rewards/ledger', { items: [] }) : Promise.resolve({ items: rewardsLedger }),
      targetScreen === 'library' ? getJson('/api/workspace/imports', { tasks: [] }) : Promise.resolve({ tasks: importTasks }),
      ['settings', 'reader'].includes(targetScreen) ? getJson('/api/preferences', preferences) : Promise.resolve(preferences),
      targetScreen === 'settings' ? getJson('/api/account/deletion-status', { status: 'none' }) : Promise.resolve(deletionStatus),
    ])
    setHealth(healthData)
    setDevices(deviceData.devices || [])
    setVocabulary(vocabularyData.items || [])
    setPreferences(current => ({ ...current, ...(preferencesData || {}) }))
    setDeletionStatus(deletionData || { status: 'none' })
    const workspaceBooks = (workspaceData.books || []).map((book, i) => normalizeBook(book, i, '私人读物'))
    const officialBooks = (catalogData.books || []).map((book, i) => normalizeBook(book, i, '官方读物'))
    const savedBooks = (libraryData.items || []).map((book, i) => normalizeBook(book, i, '官方读物'))
    if (needBooks) setBooks(workspaceBooks)
    if (targetScreen === 'library') setLibraryBooks([...workspaceBooks, ...savedBooks])
    if (targetScreen === 'catalog') setCatalogBooks(officialBooks)
    setLearningDays(daysData.days || [])
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
  const updateUserStatus = async (user, status) => {
    try { await postJson(`/api/admin/users/${encodeURIComponent(user.id)}/status`, { status, reason: status === 'suspended' ? '运营后台手动暂停' : '运营后台恢复账号' }); await reloadWorkspace({ silent: true }); messageApi.success(status === 'suspended' ? '用户已暂停' : '用户已恢复') } catch (error) { messageApi.error(error.message || '用户状态更新失败') }
  }
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
  const createConfiguredBenefit = async payload => { try { await postJson('/api/admin/commerce/configured-benefits', payload); await reloadWorkspace({ silent: true }); messageApi.success('配置权益已创建') } catch (error) { messageApi.error(error.message || '配置权益创建失败'); throw error } }
  const updateConfiguredBenefit = async (benefitId, payload) => { try { await postJson(`/api/admin/commerce/configured-benefits/${encodeURIComponent(benefitId)}`, payload); await reloadWorkspace({ silent: true }); messageApi.success('配置权益已更新') } catch (error) { messageApi.error(error.message || '配置权益更新失败'); throw error } }
  const login = async values => { const stored = localStorage.getItem('shiyue-modern-device') || `modern-${crypto.randomUUID?.() || Date.now()}-device`; localStorage.setItem('shiyue-modern-device', stored); try { const result = await postJson('/api/auth/login', { ...values, deviceId: stored }); setAuthState('authenticated'); return result } catch (error) { messageApi.error(error.message || '登录失败'); throw error } }
  const register = async values => { try { const result = await postJson('/api/auth/register', values); messageApi.success('账号已创建，请前往邮箱完成验证'); return result } catch (error) { messageApi.error(error.message || '注册失败'); throw error } }
  const forgotPassword = async values => { try { const result = await postJson('/api/auth/forgot-password', values); messageApi.success('如果账号存在，重置邮件已发送'); return result } catch (error) { messageApi.error(error.message || '发送失败'); throw error } }
  const logout = async () => { try { await postJson('/api/auth/logout', {}); setCurrentUser(null); setAuthState('unauthenticated') } catch (error) { messageApi.error(error.message || '退出登录失败') } }
  const savePreferences = async values => { try { const result = await postJson('/api/preferences', values); setPreferences(current => ({ ...current, ...(result.preferences || result || values) })); messageApi.success('阅读偏好已保存') } catch (error) { messageApi.error(error.message || '阅读偏好保存失败'); throw error } }
  const mergePreferences = values => setPreferences(current => ({ ...current, ...values }))
  const requestDeletion = () => { Modal.confirm({ title: '确认申请注销账户？', content: '提交后会退出当前设备，并进入 7 天宽限期。宽限期内重新登录可以取消。', okText: '申请注销', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { try { await postJson('/api/account/deletion', { reason: '用户在新版工作台申请注销' }); setAuthState('unauthenticated'); messageApi.success('注销申请已提交') } catch (error) { messageApi.error(error.message || '注销申请失败'); throw error } } }) }
  const cancelDeletion = async () => { try { await postJson('/api/account/deletion/cancel', {}); await reloadWorkspace({ silent: true }); messageApi.success('注销申请已取消') } catch (error) { messageApi.error(error.message || '取消注销失败') } }
  const revokeOwnDevice = async deviceId => {
    Modal.confirm({ title: '确认撤销此设备？', content: '撤销后，该设备需要重新登录才能访问工作台。', okText: '确认撤销', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { try { const response = await fetchWithCsrf(`/api/auth/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '设备撤销失败'); await reloadWorkspace({ silent: true }); messageApi.success('设备已撤销') } catch (error) { messageApi.error(error.message || '设备撤销失败'); throw error } } })
  }
  const exportAdminSummary = async () => { try { const response = await fetch('/api/admin/exports/summary', { credentials: 'include' }); const data = await response.json(); if (!response.ok) throw new Error(data.error || '导出失败'); const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `shiyue-admin-summary-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(url); messageApi.success('运营摘要已导出') } catch (error) { messageApi.error(error.message || '导出失败') } }
  const checkIn = async () => { try { await postJson('/api/checkins', {}); await reloadWorkspace({ silent: true }); messageApi.success('签到成功，成长值已更新') } catch (error) { messageApi.error(error.message || '签到失败') } }
  const redeemReward = async code => { try { await postJson('/api/rewards/redeem', { code, idempotencyKey: `redeem-${code}-${crypto.randomUUID?.() || Date.now()}` }); await reloadWorkspace({ silent: true }); messageApi.success('奖励兑换成功') } catch (error) { messageApi.error(error.message || '奖励兑换失败') } }
  const filteredBooks = useMemo(() => books.filter(book => `${book.title} ${book.subtitle} ${book.author}`.toLowerCase().includes(query.toLowerCase()) && (filter === '全部' || book.source === filter)), [books, query, filter])

  const nav = [{ key: 'workspace', icon: <DashboardOutlined />, label: '学习空间' }, { key: 'catalog', icon: <ShopOutlined />, label: '首页 · 书城' }, { key: 'library', icon: <BookOutlined />, label: '我的书架' }, { key: 'stats', icon: <BarChartOutlined />, label: '学习记录' }, { key: 'vocab', icon: <StarOutlined />, label: '生词复习' }, { key: 'rewards', icon: <GiftOutlined />, label: '成长奖励' }, { key: 'membership', icon: <ThunderboltFilled />, label: '会员中心' }, { key: 'admin', icon: <AppstoreOutlined />, label: '运营后台' }, { key: 'platform', icon: <SettingOutlined />, label: '平台与部署' }].filter(item => !['admin', 'platform'].includes(item.key) || currentUser?.isAdmin)
  const settings = [{ key: 'settings', icon: <SettingOutlined />, label: '系统设置' }]
  const selectScreen = key => { setMobileOpen(false); if (key === screen) { if (pageLoading) reloadWorkspace({ targetScreen: key }).catch(error => messageApi.error(error.message || '页面刷新失败')); return } setPageLoading(true); setScreen(key); history.pushState({}, '', `${modernEntryPath()}?screen=${key}`) }
  const openReader = book => { const kind = book.source === '官方读物' || book.trial ? 'official' : 'workspace'; location.href = `${modernEntryPath()}?screen=reader&reader=${kind}&id=${encodeURIComponent(book.id)}${book.trial ? '&trial=1' : ''}` }

  const theme = { token: { colorPrimary: '#2f6f50', colorInfo: '#2f6f50', borderRadius: 12, fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif' }, components: { Layout: { siderBg: '#17392b', headerBg: '#fbfaf7' }, Menu: { darkItemBg: '#17392b', darkItemSelectedBg: '#2b5943', darkItemHoverBg: '#234b38', itemBorderRadius: 10 } } }
  if (['/verify-email', '/reset-password'].includes(location.pathname)) return <ConfigProvider theme={theme}><AntApp>{contextHolder}<AuthActionPage path={location.pathname} /></AntApp></ConfigProvider>
  if (authState === 'loading') return <ConfigProvider theme={theme}><AntApp>{contextHolder}<main className="modern-auth"><Card className="modern-auth-card"><Skeleton active avatar title paragraph={{ rows: 6 }} /></Card></main></AntApp></ConfigProvider>
  if (publicPage) return <ConfigProvider theme={theme}><AntApp>{contextHolder}<PublicSite authenticated={authState === 'authenticated'} page={publicPage} /></AntApp></ConfigProvider>
  if (purchaseRoute) return <ConfigProvider theme={theme}><AntApp>{contextHolder}<PageErrorBoundary key={routePath}><PurchasePage authenticated={authState === 'authenticated'} /></PageErrorBoundary></AntApp></ConfigProvider>
  if (routePath === '/login' || routePath === '/register') {
    const next = routeParams.get('next') || '/app'
    if (authState === 'authenticated') { location.replace(next); return null }
    return <ConfigProvider theme={theme}><AntApp>{contextHolder}<AuthPage loading={false} initialMode={routePath === '/register' ? 'register' : 'login'} next={next} onLogin={login} onRegister={register} onForgot={forgotPassword} /></AntApp></ConfigProvider>
  }
  if (authState !== 'authenticated') return <ConfigProvider theme={theme}><AntApp>{contextHolder}<AuthPage loading={false} next="/app" onLogin={login} onRegister={register} onForgot={forgotPassword} /></AntApp></ConfigProvider>
  return <ConfigProvider theme={theme}>
    <AntApp>{contextHolder}<Layout className={`modern-shell ${screen === 'reader' ? 'reader-shell' : ''}`}>
      <Sider className="modern-sider" width={248} breakpoint="lg" collapsedWidth={0} trigger={null} onBreakpoint={broken => { if (broken) setMobileOpen(false) }}>
        <Brand /><SidebarMenu nav={nav} settings={settings} screen={screen} selectScreen={selectScreen} />
        <div className="sider-bottom"><div className="plan-chip"><div><Text className="plan-label">{currentUser?.planVersion || '未登录'}</Text><Text className="plan-copy">{currentUser?.email || '正在读取账户'}</Text></div></div><Text className="sider-version">拾页商业版 · Workspace 1.0</Text></div>
      </Sider>
      <Drawer placement="left" open={mobileOpen} onClose={() => setMobileOpen(false)} closable={false} width={280} styles={{ body: { padding: 0, background: '#17392b' } }}><Brand /><SidebarMenu nav={nav} settings={settings} screen={screen} selectScreen={selectScreen} /></Drawer>
      <Layout><Header className="modern-header"><Button className="mobile-menu" type="text" icon={<MenuOutlined />} onClick={() => setMobileOpen(true)} /><div className="header-context"><Text className="eyebrow">WORKSPACE / {nav.find(n => n.key === screen)?.label || '设置'}</Text><Text className="header-status"><span className="status-dot" /> 服务正常</Text></div></Header>
        <Content className="modern-content"><PageErrorBoundary key={screen}><Page loading={pageLoading} screen={screen} books={filteredBooks} allBooks={books} catalogBooks={catalogBooks} libraryBooks={libraryBooks} importTasks={importTasks} learningDays={learningDays} membership={membership} membershipOrders={membershipOrders} rewardStatus={rewardStatus} vocabulary={vocabulary} rewardsCatalog={rewardsCatalog} rewardsLedger={rewardsLedger} adminData={adminData} currentUser={currentUser} devices={devices} preferences={preferences} deletionStatus={deletionStatus} query={query} setQuery={setQuery} filter={filter} setFilter={setFilter} selectScreen={selectScreen} openReader={openReader} openImport={() => setImportOpen(true)} messageApi={messageApi} health={health} onRefresh={() => reloadWorkspace({ silent: true, targetScreen: screen })} onCatalogAction={catalogAction} onCancelImport={cancelImport} onUpdateUserStatus={updateUserStatus} onCreateInvitation={createInvitation} onDeleteUnusedInvitations={deleteUnusedInvitations} onRevokeDevice={revokeDevice} onAdjustQuota={adjustQuota} onUpdateSubscription={updateSubscription} onCreateManualOrder={createManualOrder} onCreateCommerceProduct={createCommerceProduct} onCreateCommerceVersion={createCommerceVersion} onPublishCommerceVersion={publishCommerceVersion} onSetCommerceProductActive={setCommerceProductActive} onCreateConfiguredBenefit={createConfiguredBenefit} onUpdateConfiguredBenefit={updateConfiguredBenefit} onRevokeOwnDevice={revokeOwnDevice} onExportAdminSummary={exportAdminSummary} onCheckIn={checkIn} onRedeemReward={redeemReward} onSavePreferences={savePreferences} onPreferencesChange={mergePreferences} onLogout={logout} onRequestDeletion={requestDeletion} onCancelDeletion={cancelDeletion} /></PageErrorBoundary></Content>
      </Layout>
    </Layout><ImportModal open={importOpen} onClose={() => setImportOpen(false)} onResume={() => setImportOpen(true)} onCreated={() => reloadWorkspace({ silent: true })} messageApi={messageApi} /><MembershipLimitModal onRefresh={async () => { setMembership(await getJson('/api/membership/usage')); await reloadWorkspace({ silent: true }) }} /></AntApp>
  </ConfigProvider>
}

function Brand() { return <div className="modern-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name">拾页</Text><Text className="brand-subtitle">ENGLISH WORKSPACE</Text></div></div> }
function AuthPage({ loading, initialMode = 'login', next = '/app', onLogin, onRegister, onForgot }) {
  const [form] = Form.useForm()
  const [mode, setMode] = useState(initialMode)
  const [submitting, setSubmitting] = useState(false)
  const submit = async values => {
    setSubmitting(true)
    try {
      if (mode === 'login') { await onLogin(values); location.href = next }
      else if (mode === 'register') {
        await onRegister({ invitationCode: values.invitationCode, email: values.email, password: values.password })
        setMode('login')
        form.setFieldsValue({ invitationCode: undefined, password: undefined })
      } else {
        await onForgot({ email: values.email })
        setMode('login')
        form.setFieldsValue({ password: undefined })
      }
    } finally { setSubmitting(false) }
  }
  return <main className="modern-auth"><Card className="modern-auth-card"><div className="modern-auth-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name auth-brand-name">拾页</Text><Text className="brand-subtitle auth-brand-subtitle">ENGLISH WORKSPACE</Text></div></div><Text className="eyebrow">SHIYUE MEMBERS</Text><Title level={1}>{mode === 'login' ? '登录拾页' : mode === 'register' ? '创建账号' : '找回密码'}</Title><Paragraph>{mode === 'login' ? '登录后进入书城、学习空间和会员中心。未激活邮箱的账号需要先完成邮件验证。' : mode === 'register' ? '使用有效邀请码创建学习账号，完成邮箱激活后才能登录。' : '输入注册邮箱，我们会发送密码重置邮件。'}</Paragraph><Segmented block value={mode} onChange={setMode} options={[{ label: '登录', value: 'login' }, { label: '注册', value: 'register' }, { label: '找回密码', value: 'forgot' }]} /><Form form={form} layout="vertical" onFinish={submit} disabled={loading} className="modern-auth-form">{mode === 'register' && <Form.Item label="邀请码" name="invitationCode" rules={[{ required: true, message: '请输入邀请码' }]}><Input size="large" autoComplete="off" /></Form.Item>}<Form.Item label="邮箱" name="email" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}><Input size="large" autoComplete="email" /></Form.Item>{mode !== 'forgot' && <Form.Item label="密码" name="password" rules={[{ required: true, min: 10, message: '密码至少 10 位' }]}><Input.Password size="large" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></Form.Item>}<Button block type="primary" size="large" htmlType="submit" loading={submitting || loading}>{mode === 'login' ? '登录' : mode === 'register' ? '创建账号' : '发送重置邮件'}</Button></Form><Text type="secondary">继续即表示同意用户协议、隐私政策与内容声明。</Text></Card></main>
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
  const backToLogin = () => { location.href = '/' }
  if (path === '/verify-email') return <main className="modern-auth"><Card className="modern-auth-card"><div className="modern-auth-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name auth-brand-name">拾页</Text><Text className="brand-subtitle auth-brand-subtitle">EMAIL VERIFICATION</Text></div></div>{status === 'loading' ? <div className="auth-action-state"><Skeleton active title paragraph={{ rows: 4 }} /></div> : status === 'success' ? <div className="auth-action-state"><CheckCircleFilled className="auth-action-success" /><Title level={2}>邮箱已激活</Title><Paragraph>现在可以使用注册邮箱和密码登录拾页。</Paragraph><Button block type="primary" size="large" onClick={backToLogin}>返回登录</Button></div> : <div className="auth-action-state"><Alert type="error" showIcon message="邮箱验证失败" description={error} /><Button block size="large" onClick={backToLogin}>返回登录</Button></div>}</Card></main>
  const resetPassword = async values => {
    setSubmitting(true); setError('')
    try { await postJson('/api/auth/reset-password', { token, password: values.password }); setStatus('success') }
    catch (reason) { setError(reason.message || '密码重置失败') }
    finally { setSubmitting(false) }
  }
  return <main className="modern-auth"><Card className="modern-auth-card"><div className="modern-auth-brand"><div className="brand-mark-modern">拾</div><div><Text className="brand-name auth-brand-name">拾页</Text><Text className="brand-subtitle auth-brand-subtitle">PASSWORD RESET</Text></div></div>{status === 'success' ? <div className="auth-action-state"><CheckCircleFilled className="auth-action-success" /><Title level={2}>密码已重置</Title><Paragraph>旧设备会话已经失效，请使用新密码重新登录。</Paragraph><Button block type="primary" size="large" onClick={backToLogin}>返回登录</Button></div> : <><Text className="eyebrow">ACCOUNT SECURITY</Text><Title level={1}>设置新密码</Title><Paragraph>新密码至少需要 10 位。完成后请重新登录。</Paragraph>{!token && <Alert type="error" showIcon message="重置链接缺少必要参数" />}{error && <Alert className="auth-action-alert" type="error" showIcon message={error} />}<Form layout="vertical" onFinish={resetPassword} disabled={!token || submitting} className="modern-auth-form"><Form.Item label="新密码" name="password" rules={[{ required: true, min: 10, message: '密码至少 10 位' }]}><Input.Password size="large" autoComplete="new-password" /></Form.Item><Form.Item label="确认新密码" name="confirmPassword" dependencies={['password']} rules={[{ required: true, message: '请再次输入新密码' }, ({ getFieldValue }) => ({ validator(_, value) { return !value || getFieldValue('password') === value ? Promise.resolve() : Promise.reject(new Error('两次输入的密码不一致')) } })]}><Input.Password size="large" autoComplete="new-password" /></Form.Item><Button block type="primary" size="large" htmlType="submit" loading={submitting}>确认重置密码</Button></Form><Button block type="link" onClick={backToLogin}>返回登录</Button></>}</Card></main>
}
function SidebarMenu({ nav, settings, screen, selectScreen }) { return <div className="sidebar-menu-wrap"><Menu theme="dark" mode="inline" selectedKeys={[screen]} items={nav} onClick={({ key }) => selectScreen(key)} /><div className="menu-divider" /><Menu theme="dark" mode="inline" selectedKeys={[screen]} items={settings} onClick={({ key }) => selectScreen(key)} /></div> }

function Page({ screen, loading, ...props }) {
  if (loading) return <PageSkeleton reader={screen === 'reader'} />
  const pages = { workspace: <WorkspacePage {...props} />, catalog: <CatalogPage {...props} />, library: <LibraryPage {...props} />, stats: <StatsPageNew {...props} />, vocab: <VocabularyPage {...props} />, rewards: <RewardsPageNew {...props} />, membership: <MembershipPage {...props} />, admin: <AdminPage {...props} />, platform: <PlatformOperationsPage {...props} />, settings: <SettingsPage {...props} />, reader: <ReaderPage {...props} /> }
  return pages[screen] || pages.workspace
}

function PageIntro({ eyebrow, title, copy, action }) { return <div className="page-intro"><div><Text className="eyebrow">{eyebrow}</Text><Title level={1}>{title}</Title><Paragraph>{copy}</Paragraph></div>{action}</div> }
function Workspace({ allBooks, selectScreen, openReader, openImport, learningDays, rewardStatus }) { const recentDays = learningDays.slice(0, 7); const minutes = recentDays.reduce((sum, day) => sum + Number(day.payload?.reading_seconds || 0) / 60, 0); const streak = Number(rewardStatus?.streak || recentDays.filter(day => Number(day.payload?.reading_seconds || 0) > 0).length || 0); const goalPercent = Math.min(100, Math.round(minutes / 120 * 100)); const continueBook = allBooks.find(b => b.progress > 0) || allBooks[0]; return <div className="page-stack"><PageIntro eyebrow={`GOOD MORNING · ${new Date().toLocaleDateString('zh-CN')}`} title="继续你的英语阅读" copy="把碎片时间变成可积累的理解力。今天完成 12 分钟学习，就能保持连续记录。" action={<Button type="primary" size="large" icon={<PlusOutlined />} onClick={openImport}>导入新读物</Button>} /><Row gutter={[20, 20]}><Col xs={24} xl={16}><Card className="hero-card"><div><Text className="card-kicker">继续学习</Text><Title level={2}>{continueBook?.title || '还没有读物'}</Title><Paragraph>{continueBook?.subtitle || '导入第一本读物，开始你的学习记录。'}</Paragraph><Space><Button type="primary" onClick={() => continueBook ? openReader(continueBook) : openImport()}>{continueBook ? '继续阅读' : '导入读物'} <span className="arrow">→</span></Button><Button onClick={() => selectScreen('library')}>查看书架</Button></Space></div>{continueBook && <Cover book={continueBook} large />}</Card></Col><Col xs={24} xl={8}><Card className="streak-card"><Text className="card-kicker">本周学习目标</Text><Statistic value={goalPercent} suffix="%" valueStyle={{ color: '#17392b', fontSize: 42, fontWeight: 700 }} /><Progress percent={goalPercent} showInfo={false} strokeColor="#f08b67" trailColor="#f7e3da" /><Text type="secondary">{Math.max(0, 120 - Math.round(minutes))} 分钟达到本周目标 · 当前连续 {streak} 天</Text><div className="streak-days">{['一','二','三','四','五','六','日'].map((d, i) => <span className={i < Math.min(7, recentDays.length) ? 'done' : ''} key={d}>{i < Math.min(7, recentDays.length) ? '✓' : d}</span>)}</div></Card></Col></Row><SectionHeader title="你的阅读进度" action={<Button type="link" onClick={() => selectScreen('library')}>查看全部</Button>} /><Row gutter={[16, 16]}>{allBooks.slice(0, 3).map(book => <Col xs={24} md={8} key={book.id}><BookCard book={book} onClick={() => openReader(book)} /></Col>)}</Row><SectionHeader title="今天可以做什么" /><Row gutter={[16, 16]}><ActionCard icon={<ReadOutlined />} title="完成一次精读" copy="选一段未读内容，跟读并标记 3 个新词。" action="开始阅读" onClick={() => selectScreen('library')} /><ActionCard icon={<CustomerServiceOutlined />} title="复习生词" copy="查看你的真实复习队列和学习活动。" action="去复习" onClick={() => selectScreen('stats')} /><ActionCard icon={<CloudUploadOutlined />} title="导入个人内容" copy="支持 TXT、Markdown、PDF、MP3 与视频。" action="开始导入" onClick={openImport} /></Row></div> }
function LegacyCatalog({ ...props }) { const books = props.catalogBooks?.length ? props.catalogBooks : props.books; return <div className="page-stack"><PageIntro eyebrow="CURATED LIBRARY" title="首页 · 书城" copy="按难度、主题与学习目标挑选下一本读物。" action={<Button icon={<BookOutlined />} onClick={() => props.selectScreen('library')}>我的书架</Button>} /><Card className="filter-card"><Space wrap><Input allowClear prefix={<FileTextOutlined />} placeholder="搜索标题、作者或主题" value={props.query} onChange={e => props.setQuery(e.target.value)} style={{ width: 280 }} /><Segmented options={['全部', '官方读物', '私人读物']} value={props.filter} onChange={props.setFilter} /></Space></Card><Row gutter={[20, 20]}>{books.filter(book => `${book.title} ${book.subtitle} ${book.author}`.toLowerCase().includes(props.query.toLowerCase())).map(book => <Col xs={24} sm={12} xl={8} key={book.id}><BookCard book={book} onClick={() => book.inLibrary ? props.openReader(book) : props.onCatalogAction?.(book)} onAction={() => props.onCatalogAction?.(book)} actionLabel={book.inLibrary ? (book.inLibrary ? '已加入书架' : '开始阅读') : '加入书架'} catalog /></Col>)}</Row></div> }
function LegacyLibrary({ ...props }) { const books = props.libraryBooks?.length ? props.libraryBooks : props.books; const tasks = props.importTasks || []; const [sort, setSort] = useState('recent'); const visibleBooks = books.filter(book => `${book.title} ${book.subtitle} ${book.author}`.toLowerCase().includes(props.query.toLowerCase()) && (props.filter === '全部' || book.source === props.filter)).sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title) : sort === 'progress' ? b.progress - a.progress : (b.updatedAt || '').localeCompare(a.updatedAt || '')); return <div className="page-stack"><PageIntro eyebrow="YOUR LIBRARY" title="我的书架" copy="所有读物、导入任务与最近阅读，都在这里继续。" action={<Button type="primary" icon={<PlusOutlined />} onClick={props.openImport}>导入读物</Button>} /><Card className="filter-card"><Space wrap><Input allowClear prefix={<FileTextOutlined />} placeholder="搜索我的读物" value={props.query} onChange={e => props.setQuery(e.target.value)} style={{ width: 280 }} /><Select value={props.filter} onChange={props.setFilter} options={['全部', '官方读物', '私人读物'].map(v => ({ value: v, label: v }))} /><Select value={sort} onChange={setSort} options={[{ value: 'recent', label: '最近阅读' }, { value: 'progress', label: '阅读进度' }, { value: 'title', label: '标题排序' }]} /></Space></Card>{tasks.length > 0 && <Card title="导入任务" className="table-card"><List size="small" dataSource={tasks.slice(0, 3)} renderItem={task => <List.Item actions={['queued', 'uploading', 'processing'].includes(task.status) ? [<Button size="small" danger onClick={() => props.onCancelImport?.(task)}>取消</Button>] : []}><List.Item.Meta title={task.title || task.originalFilename} description={task.error || task.step || task.status} /><Progress percent={task.progress} status={task.status === 'failed' ? 'exception' : task.status === 'complete' ? 'success' : 'active'} /></List.Item>} /></Card>}<Card className="table-card"><List itemLayout="horizontal" dataSource={visibleBooks} locale={{ emptyText: <Empty description="还没有符合条件的读物" /> }} renderItem={book => <List.Item actions={[<Button type="primary" ghost onClick={() => props.openReader(book)}>{book.progress ? '继续阅读' : '开始阅读'}</Button>, <Button type="text" icon={<MoreOutlined />} />]}><List.Item.Meta avatar={<Cover book={book} />} title={<Space>{book.title}<Tag color={book.source === '官方读物' ? 'gold' : 'green'}>{book.source}</Tag></Space>} description={<><Text type="secondary">{book.author} · {book.level}</Text><Progress percent={book.progress} size="small" strokeColor="#2f6f50" /></>} /></List.Item>} /></Card></div> }
function Stats({ allBooks, learningDays, openReader }) { const dayMinutes = day => Number(day.payload?.reading_seconds || 0) / 60; const recent = learningDays.slice(0, 7).reverse(); const dayCount = learningDays.filter(day => dayMinutes(day) > 0).length; const weekMinutes = recent.reduce((sum, day) => sum + dayMinutes(day), 0); const sentences = recent.reduce((sum, day) => sum + Number(day.payload?.sentences || 0), 0); const maxMinutes = Math.max(1, ...recent.map(dayMinutes)); return <div className="page-stack"><PageIntro eyebrow="LEARNING INSIGHTS" title="学习记录" copy="看见每一次阅读如何沉淀成理解力。" action={<Button onClick={() => location.href = '/api/account/export'}>导出个人数据</Button>} /><Row gutter={[16, 16]}><Metric title="学习天数" value={dayCount} suffix="天" note="来自真实学习日记录" /><Metric title="近 7 天阅读" value={Math.round(weekMinutes)} suffix="分钟" note="按工作区活动计算" /><Metric title="完成句子" value={sentences || '—'} suffix="句" note="按活动事件累计" /><Metric title="掌握词汇" value="—" suffix="个" note="复习统计接口待接入" /></Row><Row gutter={[20, 20]}><Col xs={24} lg={15}><Card title="学习趋势"><div className="chart-placeholder"><div className="chart-bars">{(recent.length ? recent : [{ day: '—', payload: { reading_seconds: 0 } }]).map((day, i) => <div key={day.day || i} className="chart-column"><div style={{ height: `${Math.max(4, dayMinutes(day) / maxMinutes * 100)}%` }} /><span>{day.day ? new Date(day.day).toLocaleDateString('zh-CN', { weekday: 'short' }) : '—'}</span></div>)}</div></div></Card></Col><Col xs={24} lg={9}><Card title="下一步"><List dataSource={allBooks.slice(0, 3)} locale={{ emptyText: '暂无读物' }} renderItem={book => <List.Item><List.Item.Meta avatar={<Cover book={book} />} title={book.title} description={`${book.progress}% 已完成`} /><Button size="small" onClick={() => openReader(book)}>打开</Button></List.Item>} /></Card></Col></Row></div> }
function LegacyVocabularyPage({ vocabulary, allBooks, selectScreen }) { return <div className="page-stack"><PageIntro eyebrow="VOCABULARY REVIEW" title="生词复习" copy="你的生词来自真实阅读语境，复习记录会写回当前账号。" action={<Button onClick={() => selectScreen('library')}>回到书架</Button>} /><Row gutter={[16, 16]}><Metric title="待复习" value={vocabulary.length} suffix="个" note="来自工作区生词接口" /><Metric title="来源读物" value={new Set(vocabulary.map(item => item.bookId)).size} suffix="本" note="已保存语境" /></Row><Card title="生词列表"><List dataSource={vocabulary} locale={{ emptyText: <Empty description="还没有生词，去阅读中点击单词保存" /> }} renderItem={item => { const payload = item.payload || {}; const book = allBooks.find(bookItem => bookItem.id === item.bookId); return <List.Item><List.Item.Meta title={<Space><Text strong>{payload.word || payload.form || '未命名单词'}</Text><Tag>{payload.rating || '待复习'}</Tag></Space>} description={<>{payload.meaning || payload.translation || '暂无释义'} · {book?.title || item.bookId}</>} /><Text type="secondary">{payload.due_at || payload.dueAt || '待安排'}</Text></List.Item> }} /></Card></div> }
function RewardsPage({ rewardStatus, rewardsCatalog, rewardsLedger, onCheckIn, onRedeemReward }) { return <div className="page-stack"><PageIntro eyebrow="GROWTH REWARDS" title="成长奖励" copy="签到、阅读和复习会产生真实成长值，可兑换账号权益。" action={<Button type="primary" onClick={onCheckIn} disabled={rewardStatus?.checkedIn}> {rewardStatus?.checkedIn ? '今日已签到' : '今日签到'} </Button>} /><Row gutter={[16, 16]}><Metric title="成长值" value={rewardStatus?.balance ?? '—'} suffix="点" note={`本月获得 ${rewardStatus?.monthEarned ?? '—'} 点`} /><Metric title="连续学习" value={rewardStatus?.streak ?? 0} suffix="天" note={rewardStatus?.checkedIn ? '今日已完成签到' : '今日尚未签到'} /><Metric title="邀请额度" value={rewardStatus?.inviteAllowance ?? 0} suffix="个" note="可用邀请名额" /></Row><Row gutter={[20, 20]}><Col xs={24} lg={12}><Card title="可兑换奖励"><List dataSource={rewardsCatalog} locale={{ emptyText: '暂无可兑换奖励' }} renderItem={item => <List.Item actions={[<Button size="small" onClick={() => onRedeemReward?.(item.code)} disabled={(rewardStatus?.balance || 0) < item.costPoints}>兑换</Button>]}><List.Item.Meta title={item.title} description={`${item.description || '暂无说明'} · ${item.costPoints} 点`} /></List.Item>} /></Card></Col><Col xs={24} lg={12}><Card title="成长记录"><List dataSource={rewardsLedger} locale={{ emptyText: '暂无成长记录' }} renderItem={item => <List.Item><List.Item.Meta title={item.eventType} description={item.day || item.createdAt} /><Text type={item.points > 0 ? 'success' : 'secondary'}>{item.points > 0 ? `+${item.points}` : item.points} 点</Text></List.Item>} /></Card></Col></Row></div> }
function LegacyReaderPage({ preferences, messageApi }) {
  const params = new URLSearchParams(location.search), kind = params.get('reader') === 'official' ? 'official' : 'workspace', bookId = params.get('id') || ''
  const [book, setBook] = useState(null), [active, setActive] = useState(0), [loading, setLoading] = useState(true), [wordInfo, setWordInfo] = useState(null), [grammar, setGrammar] = useState(null)
  const mediaRef = useRef(null), startedAt = useRef(Date.now())
  useEffect(() => { const endpoint = kind === 'official' ? `/api/catalog/books/${encodeURIComponent(bookId)}/reader` : `/api/workspace/books/${encodeURIComponent(bookId)}/reader`; getJson(endpoint, null).then(data => { setBook(data?.book || null); setLoading(false) }) }, [bookId, kind])
  const assets = book?.mediaAssets || [], video = assets.find(item => String(item.contentType).startsWith('video/')), audio = assets.find(item => String(item.contentType).startsWith('audio/')) || assets.flatMap(item => item.variants || []).find(item => String(item.contentType).startsWith('audio/'))
  const selectSentence = index => { setActive(index); setGrammar(null); const sentence = book.sentences[index]; if (mediaRef.current && Number.isFinite(Number(sentence?.start))) mediaRef.current.currentTime = Number(sentence.start) }
  const lookup = async (sentence, wordIndex, word) => { setWordInfo({ loading: true, word }); try { const result = await postJson('/api/word-context', { bookId, sentenceId: sentence.id, wordIndex }); setWordInfo({ ...result, word }) } catch (error) { setWordInfo({ word, error: error.message }) } }
  const analyze = async sentence => { try { setGrammar({ loading: true }); setGrammar(await postJson('/api/sentence-grammar', { bookId, sentenceId: sentence.id })) } catch (error) { setGrammar({ error: error.message }) } }
  const saveWord = async () => { const sentence = book.sentences[active]; if (kind !== 'workspace' || !wordInfo?.word) return; try { await postJson('/api/workspace/vocabulary', { bookId, sentenceId: sentence.id, wordIndex: wordInfo.wordIndex || 0, payload: { word: wordInfo.word, meaning: wordInfo.meaning || wordInfo.explanation || '', context: sentence.text, rating: 'unknown', due_at: new Date().toISOString() } }); messageApi.success('已加入生词复习') } catch (error) { messageApi.error(error.message) } }
  const finish = async () => { const seconds = Math.max(1, Math.round((Date.now() - startedAt.current) / 1000)); try { if (kind === 'workspace') await postJson('/api/workspace/activity', { bookId, readingSeconds: seconds, sentences: Math.max(1, active + 1), sessions: 1, lastSentenceId: book.sentences[active]?.id, idempotencyKey: `modern-reader-${crypto.randomUUID?.() || Date.now()}` }); else await postJson('/api/rewards/activity', { readingSeconds: seconds, sentences: Math.max(1, active + 1), reviews: 0, idempotencyKey: `modern-official-${crypto.randomUUID?.() || Date.now()}` }); messageApi.success('本次学习记录已保存') } catch (error) { messageApi.error(error.message) } }
  if (loading) return <div className="reader-loading">正在加载阅读器…</div>
  if (!book) return <Empty className="reader-loading" description="无法读取该读物，请确认已加入书架或导入完成" />
  const current = book.sentences[active] || book.sentences[0]
  return <div className={`modern-reader density-${preferences?.density || 'comfortable'}`}><header className="reader-head"><Button onClick={() => history.back()}>← 返回</Button><div><Text className="eyebrow">{kind === 'official' ? 'OFFICIAL READER' : 'PRIVATE READER'}</Text><Title level={3}>{book.title}</Title></div><Button type="primary" onClick={finish}>完成学习</Button></header><div className="reader-grid"><section className="reader-main">{video && <video ref={mediaRef} className="reader-media" src={video.url} controls preload="metadata" />}{!video && audio && <audio ref={mediaRef} className="reader-audio" src={audio.url} controls preload="metadata" />}<div className="reader-sentences">{book.sentences.map((sentence, index) => <article key={sentence.id} className={`reader-sentence ${index === active ? 'active' : ''}`} onClick={() => selectSentence(index)}><small>{index + 1}</small><p>{(sentence.words?.length ? sentence.words.map((word, wordIndex) => <button key={wordIndex} className="reader-word" onClick={event => { event.stopPropagation(); setWordInfo({ loading: true, word: word.text || word.word || word.form, wordIndex }); lookup(sentence, wordIndex, word.text || word.word || word.form) }}>{word.text || word.word || word.form} </button>) : sentence.text)}</p>{sentence.translation && <Text type="secondary">{sentence.translation}</Text>}<Button size="small" type="link" onClick={event => { event.stopPropagation(); analyze(sentence) }}>句法分析</Button></article>)}</div></section><aside className="reader-inspector"><Card title="当前句子"><Paragraph>{current?.text}</Paragraph>{current?.translation && <Text type="secondary">{current.translation}</Text>}</Card><Card title="单词释义">{wordInfo?.loading ? '正在分析…' : wordInfo?.error ? <Text type="danger">{wordInfo.error}</Text> : wordInfo ? <><Title level={4}>{wordInfo.word}</Title><Paragraph>{wordInfo.meaning || wordInfo.explanation || wordInfo.contextExplanation || '已返回语境分析结果'}</Paragraph>{kind === 'workspace' && <Button onClick={saveWord}>加入生词</Button>}</> : <Empty description="点击正文中的单词查看语境释义" />}</Card><Card title="句法分析">{grammar?.loading ? '正在分析…' : grammar?.error ? <Text type="danger">{grammar.error}</Text> : grammar ? <Paragraph>{grammar.explanation || grammar.aiExplanation || JSON.stringify(grammar)}</Paragraph> : <Empty description="点击句子旁的句法分析" />}</Card></aside></div></div>
}
function LegacyMembership({ membership, membershipOrders }) { const plan = membership?.plan; const usage = membership?.usage || []; const ai = usage.find(item => item.feature === 'ai_context_generations'); const aiPercent = ai?.limit ? Math.min(100, Math.round((ai.used / ai.limit) * 100)) : 0; return <div className="page-stack"><PageIntro eyebrow="MEMBERSHIP" title="会员中心" copy="把内容、AI 学习和导入能力集中管理，按需升级。" action={<Button type="primary" disabled={!membership}>管理订阅</Button>} /><Card className="membership-hero"><Space align="start"><div className="membership-icon"><ThunderboltFilled /></div><div><Text className="card-kicker">当前方案</Text><Title level={2}>{plan?.name || '未登录或暂无套餐'}</Title><Text>{membership?.period?.endsAt ? `有效期至 ${new Date(membership.period.endsAt).toLocaleDateString('zh-CN')}` : '登录后读取真实会员周期'}</Text></div></Space><Progress percent={aiPercent} format={() => ai ? `本月 AI 额度 ${ai.available} 可用` : '暂无额度数据'} strokeColor="#f08b67" /></Card><Row gutter={[16, 16]}><Quota title="内容权益" items={[`官方解锁：${usage.find(item => item.feature === 'official_unlocks')?.available ?? '—'} 可用`, `私人容量：${usage.find(item => item.feature === 'official_library_capacity')?.available ?? '—'} 可用`, `设备：${usage.find(item => item.feature === 'devices')?.available ?? '—'} 可用`]} /><Quota title="AI 学习" items={[`词汇语境：${usage.find(item => item.feature === 'ai_context_generations')?.available ?? '—'} 可用`, `句法分析：${usage.find(item => item.feature === 'ai_grammar_generations')?.available ?? '—'} 可用`, '失败请求自动释放额度']} /><Quota title="导入能力" items={[`MP3：${usage.find(item => item.feature === 'mp3_imports')?.available ?? '—'} 可用`, `视频：${usage.find(item => item.feature === 'video_imports')?.available ?? '—'} 可用`, `YouTube：${usage.find(item => item.feature === 'youtube_imports')?.available ?? '—'} 可用`]} /></Row><Card title="订单记录"><List size="small" dataSource={membershipOrders || []} locale={{ emptyText: '暂无订单记录' }} renderItem={order => <List.Item><List.Item.Meta title={`${order.planVersion} · ${(order.amountCents / 100).toFixed(2)} ${order.currency || 'CNY'}`} description={order.note || '无备注'} /><Tag>{order.status}</Tag></List.Item>} /></Card></div> }
function Admin({ adminData, onUpdateUserStatus, onCreateInvitation, onRevokeDevice, onAdjustQuota, onUpdateSubscription, onCreateManualOrder, onExportAdminSummary }) {
  const [inviteOpen, setInviteOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState(null)
  const [auditQuery, setAuditQuery] = useState('')
  const [auditAction, setAuditAction] = useState('全部')
  const [auditItems, setAuditItems] = useState([])
  const [inviteForm] = Form.useForm()
  const [quotaForm] = Form.useForm()
  const [subscriptionOpen, setSubscriptionOpen] = useState(false)
  const [subscription, setSubscription] = useState(null)
  const [subscriptionForm] = Form.useForm()
  const [orderOpen, setOrderOpen] = useState(false)
  const [orderForm] = Form.useForm()
  const dashboard = adminData?.dashboard
  const users = adminData?.users || []
  const audit = adminData?.audit || []
  const invitations = adminData?.invitations || []
  const filteredAudit = auditItems.length || auditQuery || auditAction !== '全部' ? auditItems : audit
  const auditActions = ['全部', ...new Set(audit.map(item => item.action).filter(Boolean))]
  useEffect(() => { const timer = setTimeout(() => { const params = new URLSearchParams({ limit: '100' }); if (auditQuery.trim()) params.set('q', auditQuery.trim()); if (auditAction !== '全部') params.set('action', auditAction); getJson(`/api/admin/audit?${params.toString()}`, { items: [] }).then(data => setAuditItems(data.items || [])) }, 220); return () => clearTimeout(timer) }, [auditQuery, auditAction])
  const openDetail = async user => { setDetailOpen(true); setDetailLoading(true); try { const response = await fetch(`/api/admin/users/${encodeURIComponent(user.id)}`, { credentials: 'include' }); const data = await response.json(); if (!response.ok) throw new Error(data.error || '无法读取用户详情'); setDetail(data) } catch (error) { setDetail({ error: error.message }) } finally { setDetailLoading(false) } }
  const columns = [{ title: '用户', dataIndex: 'email', render: (value, row) => <Space direction="vertical" size={0}><Text strong>{row.displayName || '未设置昵称'}</Text><Text type="secondary">{value}</Text></Space> }, { title: '方案', dataIndex: 'planVersion', render: v => <Tag color="green">{v}</Tag> }, { title: '设备', dataIndex: 'devices' }, { title: '状态', dataIndex: 'status', render: v => <Tag color={v === 'active' ? 'success' : 'warning'}>{v === 'active' ? '正常' : v}</Tag> }, { title: '邮箱', dataIndex: 'emailVerified', render: v => v ? <Tag color="success">已验证</Tag> : <Tag>待验证</Tag> }, { title: '操作', key: 'actions', fixed: 'right', render: (_, row) => <Dropdown menu={{ items: [{ key: 'detail', label: '查看详情' }, ...(row.status === 'active' ? [{ key: 'suspended', label: '暂停账号', danger: true }] : [{ key: 'active', label: '恢复账号' }])], onClick: ({ key }) => key === 'detail' ? openDetail(row) : onUpdateUserStatus?.(row, key) }}><Button type="link">管理</Button></Dropdown> }]
  const count = key => dashboard?.users?.[key] ?? '—'
  const openSubscription = item => { setSubscription(item); subscriptionForm.setFieldsValue({ action: item.status === 'active' ? 'suspend' : 'activate', endsAt: item.endsAt || '', note: '' }); setSubscriptionOpen(true) }
  const submitSubscription = async values => { Modal.confirm({ title: values.action === 'suspend' ? '确认暂停订阅？' : values.action === 'extend' ? '确认延长订阅？' : '确认恢复订阅？', content: '该操作会立即影响用户的会员权益，并写入审计记录。', okText: '确认操作', cancelText: '取消', okButtonProps: { danger: values.action === 'suspend' }, onOk: async () => { await onUpdateSubscription?.({ subscriptionId: subscription.id, action: values.action, endsAt: values.action === 'extend' ? values.endsAt : undefined, note: values.note || '运营后台订阅管理' }); subscriptionForm.resetFields(); setSubscriptionOpen(false); if (detail?.user) openDetail(detail.user) } }) }
  const submitOrder = async values => { await onCreateManualOrder?.({ userId: values.userId, planVersion: values.planVersion, startsAt: values.startsAt, endsAt: values.endsAt, note: values.note || '运营后台创建人工订阅', amountCents: Number(values.amountCents || 0) }); orderForm.resetFields(); setOrderOpen(false) }
  const submitInvite = async values => { await onCreateInvitation?.({ code: values.code?.trim() || '', maxUses: Number(values.maxUses || 1), note: values.note?.trim() || '运营后台创建', channel: 'admin' }); inviteForm.resetFields(); setInviteOpen(false) }
  const detailDrawer = <Drawer title="用户详情" open={detailOpen} onClose={() => setDetailOpen(false)} width={Math.min(560, window.innerWidth - 24)}>{detailLoading ? <Text type="secondary">正在读取用户详情…</Text> : detail?.error ? <Empty description={detail.error} /> : detail && <Space direction="vertical" size={20} style={{ width: '100%' }}><Descriptions column={1} bordered size="small"><Descriptions.Item label="邮箱">{detail.user?.email}</Descriptions.Item><Descriptions.Item label="状态">{detail.user?.status}</Descriptions.Item><Descriptions.Item label="套餐">{detail.user?.planVersion}</Descriptions.Item><Descriptions.Item label="设备数">{detail.user?.devices}</Descriptions.Item><Descriptions.Item label="成长值">{detail.growthBalance ?? 0}</Descriptions.Item></Descriptions><Card size="small" title="设备"><List size="small" dataSource={detail.devices || []} locale={{ emptyText: '暂无设备' }} renderItem={device => <List.Item><List.Item.Meta title={device.label || '未命名设备'} description={device.userAgent || '未知客户端'} /><Space><Tag color={device.revoked ? 'default' : 'success'}>{device.revoked ? '已撤销' : '活跃'}</Tag>{!device.revoked && <Button size="small" danger onClick={() => onRevokeDevice?.(detail.user.id, device.id)}>撤销</Button>}</Space></List.Item>} /></Card><Card size="small" title="订阅"><List size="small" dataSource={detail.subscriptions || []} locale={{ emptyText: '暂无订阅' }} renderItem={subscription => <List.Item actions={[<Button size="small" onClick={() => openSubscription(subscription)}>管理</Button>]}><List.Item.Meta title={subscription.planVersion} description={subscription.note || '无备注'} /><Tag>{subscription.status}</Tag></List.Item>} /></Card><Card size="small" title="人工订单"><List size="small" dataSource={detail.orders || []} locale={{ emptyText: "暂无人工订单" }} renderItem={order => <List.Item><List.Item.Meta title={`${order.planVersion} · ${(order.amountCents / 100).toFixed(2)} ${order.currency || "CNY"}`} description={order.note || "无备注"} /><Tag>{order.status}</Tag></List.Item>} /></Card><Card size="small" title="调整额度"><Form form={quotaForm} layout="vertical" onFinish={async values => { await onAdjustQuota?.(detail.user.id, values); quotaForm.resetFields(); openDetail(detail.user) }}><Form.Item label="功能" name="feature" initialValue="ai_context_generations"><Select options={[{ value: 'ai_context_generations', label: 'AI 语境分析' }, { value: 'ai_grammar_generations', label: 'AI 句法分析' }, { value: 'mp3_imports', label: 'MP3 导入' }, { value: 'video_imports', label: '视频导入' }, { value: 'youtube_imports', label: 'YouTube 导入' }]} /></Form.Item><Form.Item label="调整数量" name="quantity" rules={[{ required: true, message: '请输入调整数量' }]}><InputNumber style={{ width: '100%' }} step={1} /></Form.Item><Form.Item label="操作原因" name="reason" rules={[{ required: true, message: '请输入操作原因' }]}><Input.TextArea rows={2} placeholder="例如：补偿失败任务额度" /></Form.Item><Button type="primary" htmlType="submit">提交调整</Button></Form></Card></Space>}</Drawer>
  return <div className="page-stack"><PageIntro eyebrow="OPERATIONS" title="运营后台" copy="用清晰的数据和可回溯的操作管理你的商业工作区。" action={<Space><Button icon={<FileTextOutlined />} onClick={onExportAdminSummary}>导出数据</Button><Button onClick={() => setOrderOpen(true)}>创建人工订阅</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setInviteOpen(true)}>创建邀请码</Button></Space>} /><Row gutter={[16, 16]}><Metric title="用户总数" value={count('total')} note={`活跃 ${count('active')} 人`} /><Metric title="已验证用户" value={count('verified')} note={`暂停 ${count('suspended')} 人`} /><Metric title="有效订阅" value={dashboard?.activeSubscriptions ?? '—'} note={`活动邀请码 ${dashboard?.activeInvitations ?? '—'}`} /><Metric title="书城内容" value={dashboard?.catalog?.published ?? '—'} note={`总内容 ${dashboard?.catalog?.total ?? '—'} 本`} /></Row><Card title="用户与订阅"><Table rowKey="id" columns={columns} dataSource={users} locale={{ emptyText: <Empty description="暂无可展示的用户数据，或当前账号没有管理员权限" /> }} pagination={{ pageSize: 8 }} scroll={{ x: 860 }} /></Card><Row gutter={[20, 20]}><Col xs={24} lg={12}><Card title="最近邀请码"><List size="small" dataSource={invitations.slice(0, 6)} locale={{ emptyText: '暂无邀请码' }} renderItem={item => <List.Item><Space direction="vertical" size={0}><Text code>{item.code}</Text><Text type="secondary">{item.usedCount}/{item.maxUses} 次使用 · {item.status}</Text></Space><Button size="small" onClick={() => navigator.clipboard?.writeText(item.code)}>复制</Button></List.Item>} /></Card></Col><Col xs={24} lg={12}><Card title="最近审计操作" extra={<Space wrap><Input allowClear size="small" placeholder="搜索操作" value={auditQuery} onChange={event => setAuditQuery(event.target.value)} /><Select size="small" value={auditAction} onChange={setAuditAction} options={auditActions.map(value => ({ value, label: value }))} /></Space>}><List size="small" dataSource={filteredAudit.slice(0, 20)} locale={{ emptyText: '暂无审计记录' }} renderItem={item => <List.Item><List.Item.Meta title={item.action} description={`${item.actor || '系统'} · ${item.reason || '未填写原因'}`} /><Text type="secondary">{item.createdAt ? new Date(item.createdAt).toLocaleString('zh-CN') : '—'}</Text></List.Item>} /></Card></Col></Row>{detailDrawer}<Modal title="创建人工订阅" open={orderOpen} onCancel={() => setOrderOpen(false)} onOk={() => orderForm.submit()} okText="创建订阅" cancelText="取消"><Form form={orderForm} layout="vertical" onFinish={submitOrder}><Form.Item label="用户" name="userId" rules={[{ required: true, message: "请选择用户" }]}><Select showSearch optionFilterProp="label" options={(users || []).map(user => ({ value: user.id, label: `${user.displayName || "未设置昵称"} · ${user.email}` }))} /></Form.Item><Form.Item label="套餐" name="planVersion" rules={[{ required: true, message: "请选择套餐" }]}><Select options={(adminData?.planVersions || []).map(plan => ({ value: plan.id, label: `${plan.name} (${plan.id})` }))} /></Form.Item><Form.Item label="开始时间" name="startsAt" rules={[{ required: true, message: "请输入开始时间" }]}><Input placeholder="2026-10-11T00:00:00+08:00" /></Form.Item><Form.Item label="结束时间" name="endsAt" rules={[{ required: true, message: "请输入结束时间" }]}><Input placeholder="2026-12-31T23:59:59+08:00" /></Form.Item><Form.Item label="金额（分）" name="amountCents" initialValue={0}><InputNumber min={0} style={{ width: "100%" }} /></Form.Item><Form.Item label="备注" name="note"><Input.TextArea rows={3} /></Form.Item></Form></Modal><Modal title="管理订阅" open={subscriptionOpen} onCancel={() => setSubscriptionOpen(false)} onOk={() => subscriptionForm.submit()} okText="保存" cancelText="取消"><Form form={subscriptionForm} layout="vertical" onFinish={submitSubscription}><Form.Item label="操作" name="action"><Select options={[{ value: 'suspend', label: '暂停订阅' }, { value: 'activate', label: '恢复订阅' }, { value: 'extend', label: '延长订阅' }]} /></Form.Item><Form.Item label="新的结束时间（仅延期需要）" name="endsAt"><Input placeholder="2027-01-31T23:59:59+08:00" /></Form.Item><Form.Item label="备注" name="note"><Input.TextArea rows={3} placeholder="填写本次订阅操作原因" /></Form.Item></Form></Modal><Modal title="创建邀请码" open={inviteOpen} onCancel={() => setInviteOpen(false)} onOk={() => inviteForm.submit()} okText="创建" cancelText="取消"><Form form={inviteForm} layout="vertical" onFinish={submitInvite}><Form.Item label="邀请码（可选）" name="code"><Input placeholder="留空则自动生成" /></Form.Item><Form.Item label="可使用次数" name="maxUses" initialValue={1} rules={[{ required: true, message: '请输入使用次数' }]}><Input type="number" min={1} max={10000} /></Form.Item><Form.Item label="备注" name="note" initialValue="运营后台创建"><Input.TextArea rows={3} /></Form.Item></Form></Modal></div>
}
function LegacySettings({ currentUser, devices, preferences, deletionStatus, onRevokeOwnDevice, onSavePreferences, onLogout, onRequestDeletion, onCancelDeletion }) { const [form] = Form.useForm(); useEffect(() => { form.setFieldsValue(preferences) }, [form, preferences]); return <div className="page-stack"><PageIntro eyebrow="WORKSPACE SETTINGS" title="系统设置" copy="管理账号安全、阅读偏好、通知和设备。" /><Row gutter={[20, 20]}><Col xs={24} lg={15}><Card title="阅读偏好"><Form form={form} layout="vertical" initialValues={preferences} onFinish={onSavePreferences}><Form.Item label="默认阅读模式" name="readerMode"><Segmented block options={[{ label: '精读', value: 'intensive' }, { label: '泛读', value: 'extensive' }, { label: '影子跟读', value: 'shadow' }]} /></Form.Item><Form.Item label="界面密度" name="density"><Segmented options={[{ label: '舒适', value: 'comfortable' }, { label: '紧凑', value: 'compact' }]} /></Form.Item><Form.Item label="学习提醒" name="reminder"><Select options={[{ value: 'off', label: '关闭' }, { value: 'daily', label: '每天 20:00' }, { value: 'weekdays', label: '工作日 20:00' }]} style={{ width: '100%' }} /></Form.Item><Button type="primary" htmlType="submit">保存设置</Button></Form></Card></Col><Col xs={24} lg={9}><Card title="账户与安全"><Descriptions column={1} size="small"><Descriptions.Item label="登录邮箱">{currentUser?.email || '当前会话未读取'}</Descriptions.Item><Descriptions.Item label="登录保护"><Tag color="success">已开启</Tag></Descriptions.Item><Descriptions.Item label="已连接设备">{devices?.length || 0} 台</Descriptions.Item></Descriptions><List size="small" dataSource={devices || []} locale={{ emptyText: '暂无设备信息' }} renderItem={device => <List.Item actions={!device.revoked ? [<Button size="small" danger onClick={() => onRevokeOwnDevice?.(device.id)}>撤销</Button>] : []}><List.Item.Meta title={device.label || '未命名设备'} description={device.userAgent || '未知客户端'} /><Tag color={device.revoked ? 'default' : 'success'}>{device.revoked ? '已撤销' : '活跃'}</Tag></List.Item>} /></Card><Card title="危险区域" className="danger-card"><Text type="secondary">导出数据或申请删除账户。操作前会要求二次确认。</Text><Space direction="vertical" style={{ width: "100%" }}><Button block onClick={() => location.href = "/api/account/export"}>导出账户数据</Button><Button block danger onClick={onLogout}>退出登录</Button>{deletionStatus?.status === "requested" ? <><Text type="warning">计划删除时间：{new Date(deletionStatus.scheduledFor).toLocaleString("zh-CN")}</Text><Button block onClick={onCancelDeletion}>取消注销申请</Button></> : <Button block danger onClick={onRequestDeletion}>申请注销账户</Button>}</Space></Card></Col></Row></div> }
function BookCard({ book, onClick, onAction, actionLabel, catalog }) { return <Card hoverable className="book-card" onClick={onClick}><div className="book-card-top"><Cover book={book} /><Tag>{book.level}</Tag></div><Title level={4} ellipsis={{ rows: 1 }}>{book.title}</Title><Text type="secondary" ellipsis>{book.subtitle}</Text><div className="book-card-meta"><Text>{book.progress ? `${book.progress}% 已完成` : '尚未开始'}</Text><Text>{book.minutes ? `${book.minutes} 分钟` : '准备开始'}</Text></div><Progress percent={book.progress} showInfo={false} strokeColor="#2f6f50" />{catalog && <Button block type={book.inLibrary && book.inLibrary ? 'default' : 'primary'} disabled={book.inLibrary && book.inLibrary} onClick={event => { event.stopPropagation(); onAction?.() }} style={{ marginTop: 14 }}>{book.inLibrary && book.inLibrary ? '已加入书架' : actionLabel || '加入书架'}</Button>}</Card> }
function SectionHeader({ title, action }) { return <div className="section-header"><Title level={3}>{title}</Title>{action}</div> }
function ActionCard({ icon, title, copy, action, onClick }) { return <Col xs={24} md={8}><Card className="action-card"><div className="action-icon">{icon}</div><Title level={4}>{title}</Title><Paragraph>{copy}</Paragraph><Button type="link" onClick={onClick}>{action} →</Button></Card></Col> }
function Metric({ title, value, suffix, note }) { return <Col xs={12} lg={6}><Card className="metric-card"><Statistic title={title} value={value} suffix={suffix} /><Text type="secondary">{note}</Text></Card></Col> }
function Quota({ title, items }) { return <Col xs={24} md={8}><Card title={title} className="quota-card"><List size="small" dataSource={items} renderItem={item => <List.Item><CheckCircleFilled className="check-icon" />{item}</List.Item>} /></Card></Col> }
function ImportModal({ open, onClose, onResume, onCreated, messageApi }) {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [file, setFile] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const source = Form.useWatch('source', form) || 'file'
  const submit = async values => {
    setSubmitting(true)
    try {
      const input = values.input?.trim()
      const kind = source === 'youtube' ? 'youtube' : /\.pdf$/i.test(file?.name) ? 'document' : /\.mp3$/i.test(file?.name) ? 'mp3' : /\.(mp4|mov|m4v|mkv|webm)$/i.test(file?.name) ? 'video' : 'text'
      if (source === 'file' && !file) throw new Error('请选择要上传的文件')
      const filename = source === 'youtube' ? '' : file.name
      const key = `${kind}-import-${crypto.randomUUID?.() || Date.now()}`
      const title = values.title?.trim() || (source === 'youtube' ? '' : file.name.replace(/\.[^.]+$/, ''))
      const created = await postJson('/api/workspace/imports', { kind, title, filename, sourceUrl: source === 'youtube' ? input : '', idempotencyKey: key })
      if (source === 'file') {
        await new Promise((resolve, reject) => {
          const request = new XMLHttpRequest()
          request.open('POST', `/api/workspace/imports/${encodeURIComponent(created.task.id)}/upload`)
          request.withCredentials = true
          const headers = csrfHeaders({ 'Content-Type': file.type || 'application/octet-stream', 'X-Upload-Filename': file.name })
          Object.entries(headers).forEach(([key, value]) => request.setRequestHeader(key, value))
          request.upload.onprogress = event => { if (event.lengthComputable) setUploadProgress(Math.round(event.loaded / event.total * 100)) }
          request.onerror = () => reject(new Error('网络中断，文件上传失败'))
          request.onload = () => {
            let data = {}; try { data = JSON.parse(request.responseText || '{}') } catch {}
            if (request.status < 200 || request.status >= 300) reject(Object.assign(new Error(data.error || '上传失败'), { code: data.code, payload: data }))
            else resolve(data)
          }
          request.send(file)
        })
      }
      const taskId = created.task.id
      onClose(); form.resetFields(); setFile(null); setUploadProgress(0); await onCreated?.(); messageApi.success('导入任务已提交，后台处理进度会自动更新')
      void postJson(`/api/workspace/imports/${encodeURIComponent(taskId)}/complete`, {}).then(async result => {
        await onCreated?.()
        if (result.task?.status === 'complete') messageApi.success('内容已导入学习空间')
      }).catch(async error => { await onCreated?.(); if (!handleMembershipLimit(error, { onContinue: onResume })) messageApi.error(error.message || '导入处理失败') })
    } catch (error) { if (!handleMembershipLimit(error, { onClose, onContinue: onResume })) messageApi.error(error.message || '导入失败') } finally { setSubmitting(false) }
  }
  return <Modal title="导入新的学习内容" open={open} onCancel={submitting ? undefined : onClose} onOk={() => form.submit()} confirmLoading={submitting} okText={uploadProgress > 0 && uploadProgress < 100 ? `上传 ${uploadProgress}%` : '创建导入任务'} cancelText="稍后再说"><Form form={form} layout="vertical" onFinish={submit}><Form.Item label="内容来源" name="source" initialValue="file"><Segmented block options={[{ label: '上传文件', value: 'file' }, { label: 'YouTube', value: 'youtube' }]} /></Form.Item><Form.Item label="读物标题" name="title"><Input placeholder="可选，默认使用文件名" /></Form.Item><Form.Item label={source === 'youtube' ? 'YouTube 链接' : '学习文件'} name="input" rules={[{ required: true, message: source === 'youtube' ? '请输入 YouTube 链接' : '请选择要上传的文件' }]}><Input size="large" type={source === 'youtube' ? 'url' : 'file'} prefix={source === 'youtube' ? <CloudUploadOutlined /> : null} onChange={event => source === 'file' && setFile(event.target.files?.[0] || null)} placeholder={source === 'youtube' ? '粘贴 YouTube 链接' : undefined} /></Form.Item>{submitting && source === 'file' && <Progress percent={uploadProgress} status={uploadProgress >= 100 ? 'success' : 'active'} />}<Text type="secondary">支持 TXT、Markdown、PDF、MP3、MP4、MOV、M4V、MKV、WebM。文件直接流式发送，不再在浏览器中复制成完整 ArrayBuffer；大型音视频会进入后台处理队列。</Text></Form></Modal>
}

createRoot(document.getElementById('root')).render(<App />)
