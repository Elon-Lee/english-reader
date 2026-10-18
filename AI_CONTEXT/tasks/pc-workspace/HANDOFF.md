# PC 工作台交接

## 目标

在开始移动端优化前，保证所有 PC 页面使用 React + Ant Design、真实 API、真实交互，并且刷新和浏览器前进/后退正常。

## 已完成

- 2026-10-18 书架失败导入任务的“重试”改为调用原任务重试 API，保留源文件并直接重新执行当前任务，不再打开新的导入确认弹窗；失败处理不再删除源文件，缺失源文件时返回明确错误。已通过构建、modern/UI smoke、Python 编译和 `git diff --check`，本地 SaaS 后台已重启加载新接口。
- 2026-10-18 本机导入报“Whisper 处理器或模型未安装”已修复：运行 `tools/install_whisper.sh` 构建 `tools/vendor/whisper.cpp/build/bin/whisper-cli` 并下载 `tools/vendor/whisper.cpp/models/ggml-base.en.bin`，后台已重启，Whisper CLI 与模型文件均已验证存在。
- 2026-10-18 修复 YouTube 失败任务重试时的“该媒体路径已经登记”：如果第一次下载已登记源媒体，后续重试会复用现有源媒体和字幕变体，不重复登记同一路径；普通文件导入仍按原流程处理。SaaS 导入集成测试因当前环境未设置安全的 `_test` 数据库 URL 未能启动，Python 编译和 `git diff --check` 已通过；本地后台已重启。

- 2026-10-18 权益触限不再仅弹错误：通过 `api/membershipLimit.js` 与全局 `MembershipLimitModal` 接入同页升级、云猫购买/兑换、成功刷新权益和继续原操作。书城关闭详情后显示可升级套餐，免费可选进阶/Pro、进阶仅 Pro，最高档显示无可升级说明；加载、失败重试、空状态均具备。仅本地，尚未发布生产。
- 新前端页面：学习空间、书城、书架、学习记录、生词、奖励、会员、运营后台、平台部署、设置。
- Vite 地址保持 `/modern-assets/?screen=...`；生产保持 `/modern.html?screen=...`。
- 认证恢复期间显示启动页，不闪现登录页。
- 学习空间本周目标按真实自然周活动判断；继续学习封面固定在卡片右侧。
- 书架 8 本/页分页；生词支持列表/卡片和平铺分页；成长记录分页。
- 2026-10-18 书城取消“已解锁”展示，仅按 `inLibrary` 显示“已加入书架”及开始阅读；加入只调用书架 API，移出后的收藏状态及阅读权限跟随书架记录。卡片/详情加入提供加载与防重复提交；目录刷新同步本地列表，过期筛选响应不能覆盖写入后的状态。移除确认说明释放名额、保留学习数据及重新加入的套餐限制。管理员权益写入合并在途请求，失败重试沿用幂等键。仅本地，尚未发布生产。
- 2026-10-18 书城未收藏卡片改为“查看详情”，详情可“开始试读”或加入书架；试读沿用完整阅读器布局，音视频限制为总时长前 10%，纯文本限制为前 10% 句数（向上取整，至少一句），不写阅读进度/偏好。书城展示真实收藏总数与有阅读记录的独立用户数。仅本地，尚未发布生产；试读 API/媒体边界回归已通过；尚需浏览器实机验收。
- 2026-10-18 试读入口 `trial` 强制使用官方 reader；热度条收藏数字改为红色实心心形，底色改为浅暖白并增加细边框。
- 2026-10-18 修复已有登录会话缺失 CSRF Cookie 时加入书架等写操作失败：后端认证读取轮换当前 session 并补发 CSRF，前端对明确的 `csrf_failed` 自动恢复并重试一次；旧 session 同步失效。浏览器旧会话恢复待实机验收。
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
