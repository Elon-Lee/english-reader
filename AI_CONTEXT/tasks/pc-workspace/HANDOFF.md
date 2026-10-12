# PC 工作台交接

## 目标

在开始移动端优化前，保证所有 PC 页面使用 React + Ant Design、真实 API、真实交互，并且刷新和浏览器前进/后退正常。

## 已完成

- 新前端页面：学习空间、书城、书架、学习记录、生词、奖励、会员、运营后台、平台部署、设置。
- Vite 地址保持 `/modern-assets/?screen=...`；生产保持 `/modern.html?screen=...`。
- 认证恢复期间显示启动页，不闪现登录页。
- 学习空间本周目标按真实自然周活动判断；继续学习封面固定在卡片右侧。
- 书架 8 本/页分页；生词支持列表/卡片和平铺分页；成长记录分页。
- 学习记录使用旧版方格热力图，支持周/月/年。
- 会员当前方案排版和套餐变更申请已实现。
- 系统设置为精读、泛读、影子跟读提供 Tooltip。

## 未完成

- 清理 `frontend/src/main.jsx` 中不再使用的内联旧组件，避免重复实现；清理时不得改变行为。
- 建议增加 React 组件级测试，目前主要依赖静态 smoke、API smoke 和浏览器截图。
- 空数据时仍有少量 `fallbackBooks` 兼容数据；商业页面不得把这些数据当成真实用户数据，后续应彻底改为空状态。
- 等 PC 功能正式验收后再开始移动端任务。

## 关键文件

- `frontend/src/main.jsx`
- `frontend/src/styles.css`
- `frontend/src/pages/WorkspacePage.jsx`
- `frontend/src/pages/LibraryPage.jsx`
- `frontend/src/pages/StatsPage.jsx`
- `frontend/src/pages/VocabularyPage.jsx`
- `frontend/src/pages/RewardsPage.jsx`
- `frontend/src/pages/MembershipPage.jsx`
- `frontend/src/pages/AdminPage.jsx`
- `frontend/src/pages/SettingsPage.jsx`
- `frontend/vite.config.js`

## 验收重点

- 直接刷新 `/modern-assets/?screen=library` 不出现 Vite base URL 提示。
- 已登录访问不闪现登录页。
- 所有分页、筛选、排序、空状态和按钮均真实工作。
- 页面不能导航回旧 UI。
