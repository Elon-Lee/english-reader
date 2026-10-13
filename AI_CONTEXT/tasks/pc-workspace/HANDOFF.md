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
- 2026-10-13 已统一 PC 页面首次加载体验：认证恢复和各页面数据请求完成前只显示共享骨架；阅读器、平台部署、书城筛选、书籍详情和用户详情也使用骨架。已彻底删除 `fallbackBooks` 与 Atomic Habits 等示例书数据，真实接口返回空数组时进入正式空状态。Vite 共享分包改为内容哈希文件名，避免新入口与浏览器旧缓存分包不匹配。仅完成本地修改，未发布远程。
- 2026-10-13 修复侧栏快速切换偶发卡在骨架：加载显式绑定目标页面，只有最新前台加载负责收尾；登录成功后的页面接口失败不再错误退出账号；重复点击正在加载的当前菜单会主动重试。运营邀请码和审计数据改为 Tab 内按需加载，降低首次请求并发。

## 未完成

- 清理 `frontend/src/main.jsx` 中不再使用的内联旧组件，避免重复实现；清理时不得改变行为。
- 建议增加 React 组件级测试，目前主要依赖静态 smoke、API smoke 和浏览器截图。
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
