# 拾页 SaaS 开发进度

> 本文件保存历史里程碑。当前架构、完成项、未完成项和下一步以 `AGENTS.md`、`AI_CONTEXT/README.md` 及对应任务 `HANDOFF.md` 为准；关键里程碑仍可在同一轮追加到本文。

更新时间：2026-10-11（Asia/Shanghai）

## 当前结论

- 核心单体多租户 SaaS 已完成阶段 0–9 的本地代码实现。
- 旧单用户 SQLite 模式继续保留；旧音频和 YouTube 内容不会自动进入 SaaS。
- SaaS 总开关保持 `SHIYUE_SAAS_ENABLED=0`，尚未远程部署或正式开放。
- 完整本地调试已完成；正式本机 SaaS 调试服务当前仍运行在 `http://localhost:8790`。
- 上线仍需真实 SMTP 与平台 AI 凭据；本地调试 SMTP 已配置为文件捕获，不外发邮件。

## 阶段状态

| 阶段 | 状态 | 主要交付 |
|---|---|---|
| 0 | 已完成 | 实施计划、SQLite 基线备份、媒体清单、环境变量与功能开关 |
| 1 | 已完成 | PostgreSQL、邀请码注册、邮箱验证、登录、密码重置、设备与会话安全 |
| 2 | 已完成 | 免费/进阶/Pro 套餐、人工订单、订阅、账期、额度预占/结算/释放 |
| 3 | 已完成 | 官方书城、官方书架、首次解锁、版权与发布约束 |
| 4 | 已完成 | 签到、成长值、复习奖励、邀请里程碑与奖励兑换 |
| 5 | 已完成 | 运营后台、用户封禁、邀请码、人工订单、额度调整、审计与导出 |
| 6 | 已完成 | 媒体鉴权、Range、空间计量、安全头、注销、备份与恢复工具 |
| 7 | 已完成 | 私人学习空间、生词、标注、学习日、阅读进度与活动奖励 |
| 8 | 已完成 | TXT/Markdown/PDF/MP3/本地视频/YouTube PostgreSQL 原生导入 |
| 9 | 已完成并验收 | AI 语境/句法租户缓存、首次扣额、缓存免扣、失败释放与用户导出 |

## 数据与迁移

- migration 文件：13 个，最新为 `0013_workspace_ai.sql`。
- 正式本机数据库：`shiyue_saas_local`。
- 可销毁测试数据库：`shiyue_phase1_test`。
- 旧 SQLite 内容策略：
  - 普通图书：34 本，管理员私人可见。
  - 旧音频：2 本，`blocked`。
  - 旧 YouTube：3 本，`blocked`。
- 最新本机备份：`.local/saas-backups/20261010T105734Z`，13 个 migration，5,286 个媒体清单全部校验。
- 最新项目外备份：`/Users/x/SaaSBackups/20261010T110343Z`，数据库 dump 与 5,286 个媒体文件全部校验。

## 已实现的重要路径

- 私人文件导入：TXT、Markdown、PDF、MP3、MP4、MOV、M4V、MKV、WebM。
- YouTube：yt-dlp 下载最高 720p 视频和可用双语字幕，再复用视频处理器。
- 音视频：FFmpeg 派生音频和封面，Whisper 生成词级时间轴。
- 私人媒体：统一通过 `/api/media/{asset_id}` 和 `?variant=` 鉴权。
- 学习数据：SaaS 前端使用 `/api/workspace/*`，不访问旧 SQLite 学习接口。
- AI：`/api/word-context`、`/api/sentence-grammar` 使用用户级 PostgreSQL 缓存和套餐额度。

## 测试状态

此前已通过：

- 阶段 1：7 项
- 阶段 2：7 项
- 阶段 3：5 项
- 阶段 4：6 项
- 阶段 5：5 项
- 阶段 6：5 项
- 阶段 7：2 项，通过（含新增学习指标）
- 阶段 8：9 项，通过（含视频和 YouTube）
- 阶段 9：2 项，通过（AI 缓存、额度、隔离与失败重试）
- SaaS 展示测试：8 项
- 阅读性能测试：2 项
- 移动端展示测试：7 项
- 旧单用户书架：39 本正常

本轮本地调试待执行：

- [x] 启动并连接项目 PostgreSQL 16 集群
- [x] 应用 migration 0013
- [x] 阶段 1–9 PostgreSQL 集成测试
- [x] HTTP/HTTPS 服务健康检查
- [x] 登录、会员、书城、私人空间、管理后台权限 API smoke
- [x] TXT/PDF/MP3/视频/YouTube 非破坏性处理器与单元回归
- [x] 旧模式媒体 Range 与 SaaS 租户隔离
- [x] 生词、标注、学习记录、复习奖励
- [x] AI 缓存与额度失败释放（可控测试生成器 + HTTP 失败释放）
- [x] 前端桌面/移动端与静态资源检查
- [x] 旧 SQLite 单用户模式回归
- [x] 生成并验证 13 migration 新备份

## 当前环境阻塞项

- 生产 SMTP 主机、账号、密码和发件人尚未配置；本地调试 SMTP 已启用，邮件写入 `.local/smtp-outbox`。
- `SHIYUE_DIOCO_TOKEN`、`SHIYUE_DIOCO_EMAIL` 尚未配置，真实平台 AI 调用不可用；可控测试生成器可验证协议。
- `SAAS_BACKUP_ROOT` 已指向 `/Users/x/SaaSBackups`；生产环境仍建议改为异机或云端备份位置。
- 直接 shell 的就绪检查当前受 IPC/网络命名空间限制，报告 PostgreSQL 不可连接；此前已通过获准项目脚本连接 55432 并完成全部 PostgreSQL 验收，正式库 migration 和测试结果仍以该次验收为准。
- 已安装 Colima/Docker 作为备用本地容器环境；GitHub DNS 当前仍阻止首次虚拟机镜像下载，不影响现有 PostgreSQL 调试链路。
- 上述秘密不得写入本文件或提交到 Git。

## 本轮变更日志

### 2026-10-10 — 本地完整调试启动

- 创建本进度文件，并规定后续所有工作必须同步更新。
- 已确认本机安装 PostgreSQL 16、FFmpeg、mkcert、Node.js、yt-dlp、Whisper CLI 与 PDF OCR。
- 新安装 Colima 0.10.3、Docker CLI 29.9.0、Lima 2.2.1 与 Go 1.27.2；Colima 镜像下载因 GitHub DNS 限制未完成。
- HTTP `./start-reader.sh` 与 HTTPS `./start-reader-https.sh` 均可真实启动；早期临时监听 8765、8766、8775、8776 已在验收后停止。
- 新增 `tools/local_smoke.py` 以及启动脚本 `--smoke [port]` 模式，在同一执行上下文中启动、请求并自动停止服务。
- HTTP 与 HTTPS smoke 全通过：健康检查、39 本书架、首页与前端版本、安全响应头、读物 manifest、101 句正文、音频单 Range（32 字节）、生词、学习日、导入目录和设置接口。
- HTTP smoke 额外验证错误 TLS/畸形请求后服务保持存活。
- Chrome 真实渲染通过并生成截图：
  - `.local/debug/http-desktop.png`：1440×1000，约 192 KB。
  - `.local/debug/http-mobile.png`：390×844，约 159 KB。
- 人工查看桌面和移动截图：桌面书架、侧栏、书系与卡片布局正常；移动端使用横向书卡浏览，标题和菜单按钮正常显示。
- 修复后端缺陷：畸形请求在 `self.path` 尚未创建时调用 `end_headers()` 会抛出 `AttributeError`，现改为安全读取路径。
- 启动脚本支持可选端口参数及 `--smoke`，默认启动行为不变。
- 非 PostgreSQL 测试共 79 项通过，覆盖部署、导入规划、断句、语法、视频质量、YouTube 字幕/书系、远程界面、性能、移动端与 SQLite 数据。
- 修复两个过时测试夹具：远程页面允许 `<body>` 含多个 class；句法数据库测试先创建外键所需的测试书籍。
- 语法分析测试使用项目 `.local/forced-aligner/venv`，其中 Torch 2.2.2 与 Stanza 模型工作正常；无需在 SaaS venv 重复安装大型依赖。

### 2026-10-10 — PostgreSQL、SaaS API 与正式本地运行验收

- 新增 `./start-reader.sh --saas-test` 与 `tools/run_saas_debug.py`，在本机服务上下文中安全连接正式库和 `_test` 库。
- 正式库 `shiyue_saas_local` 已应用 `0013_workspace_ai.sql`；migration 共 13 个。
- 阶段 1–9 PostgreSQL 集成测试全部通过。
- PostgreSQL 集成共 48 项通过；加上 79 项非 PostgreSQL 回归，本轮累计 127 项自动测试通过。
- 正式库验收计数：用户 1、私人内容 39、媒体资产 5,286、导入任务 0、AI 缓存 0。
- 新增 `./start-reader.sh --saas-smoke`：真实验证未登录隔离、登录 Cookie/CSRF、会员、书城、文本导入、私人正文、媒体 Range、生词、标注、学习活动、成长奖励、AI 未配置失败释放、账号导出、后台权限和退出；全部通过。
- SaaS smoke 现使用临时 `MEDIA_ROOT`；早期两份 smoke 文件已移动至可恢复目录 `.local/media-trash/saas-http-smoke-20261010`。
- 新增 `./start-reader.sh --saas-ui-smoke`：真实 Chrome 生成 SaaS 登录页桌面与移动截图。
- 修复移动端 SaaS 登录卡片横向溢出；最新 `.local/debug/saas-login-mobile.png` 已人工确认完整显示。
- 修正文案：登录页不再显示“内容工作区将在书城阶段开放”，改为当前已开放的书城、私人学习空间和会员中心。
- 外部备份根目录已配置为 `/Users/x/SaaSBackups`，并生成、完整验证 `20261010T110343Z`。
- 新增 `./start-reader.sh --saas-local 8790` 与 `tools/run_local_saas.py`：启动正式本机 SaaS、文件型 SMTP 调试捕获器并执行 SMTP 自检。
- 当前持续运行：
  - Web：`http://localhost:8790`
  - 局域网：`http://192.168.1.45:8790`
  - SMTP 调试：`127.0.0.1:1025`
  - 邮件目录：`.local/smtp-outbox`
- 服务管理命令：启动 `./start-reader.sh --saas-local 8790`；停止 `./start-reader.sh --stop-saas-local`。
- 清理早期调试监听端口 8765、8766、8775、8776；保留 8790。
- 上线就绪检查当前仅剩两项生产阻塞：真实 SMTP、平台 AI 凭据。

### 2026-10-10 22:10 — 真实浏览器逐页审计与界面修复

- 使用管理员账号在真实 Chrome 中逐页检查 9 个 SaaS 页面，桌面和移动端各生成 9 张截图；审计目录：`.local/debug/walkthrough/20261010T135936Z`。
- 已检查页面：首页·书城、我的书架、私人学习空间、学习记录、生词复习、成长奖励、会员中心、运营后台、系统设置。
- 所有页面核心 API 均返回 200；账号登录、管理员后台、书城、私人读物、学习数据、奖励和会员数据可读取。
- 修复实际功能 Bug：SaaS 系统设置此前仍展示旧单用户 Dioco 邮箱/令牌，保存会被多租户保护层拒绝。现在改为真实登录账号与“平台统一管理”说明，阅读偏好保存在当前浏览器，保存按钮可用。
- 修复私人空间信息架构：私人读物提前到首屏；文件/YouTube 导入和任务列表折叠到“导入新内容”，有进行中任务时自动展开。
- 修复手机导航可理解性：顶部菜单按钮现在显示当前页面名称，并更新无障碍标签。
- 优化手机布局：会员权益、运营统计、奖励状态改为单列；书城详情在移动端改为单列；设置账号卡片单列。
- 优化书城：进入书城自动打开第一本详情，不再保留大块“选择一本读物”空白区。
- 优化请求性能：不再在所有页面启动时无条件加载书城和会员数据；书城筛选只在首次进入书城时加载，会员页避免重复初始化请求。
- 修复媒体连接日志：浏览器正常取消/重置媒体连接时不再打印完整 `ConnectionResetError`/`BrokenPipeError` 栈。
- 新增仅本机、仅随机密钥启用的浏览器审计登录跳转；正常 8790 服务未配置该密钥，外部不可用。
- 最新前端缓存版本：`styles.css?v=20261010-2`、`app.js?v=20261010-4`。
- 修复后再次通过 HTTP、HTTPS、SaaS API smoke，以及展示、性能、移动端、远程界面测试。
- 正式本机 SaaS 调试服务已恢复运行：`http://localhost:8790`；SMTP 捕获服务：`127.0.0.1:1025`。
- 当前明确不可用项：真实 AI 语境/句法调用仍缺少 `SHIYUE_DIOCO_TOKEN` 和 `SHIYUE_DIOCO_EMAIL`；页面会返回明确提示且不扣额度。这是配置阻塞，不是前端按钮失效。

### 2026-10-10 23:05 — 阅读主流程、书城弹层、后台 Tabs 与路由修复

- 学习空间读物不再进入简化正文页，现接入完整阅读器：句子高亮、音视频同步、单词侧栏、阅读模式和底部播放条全部恢复。
- 已用真实 Chrome 验证学习空间阅读器：受鉴权音频返回 206，桌面和移动端均显示底部播放条；移动端默认隐藏占位单词面板，点击单词后再弹出。
- 官方读物也接入同一完整阅读器；已用真实 Chrome 验证官方媒体资产返回 206，视频/音频可进入播放器。
- 修复官方媒体误报：官方阅读器会同时查找 `catalog_book_id` 官方资产和原 `content_book_id` 媒体；媒体网关允许“已发布 + 合法版权 + 用户已解锁”的原内容资产访问。
- 修复视频阅读器图片层与视频层同时显示的问题：视频模式现在隐藏页面图片层。
- 首页书城不再默认展示固定中间详情栏；点击书卡后使用弹出详情层，详情层提供“继续阅读/解锁并开始阅读”“收藏/移出书架”。
- 我的书架点击书籍不再跳转到书城页面，保持当前页面并打开同一个详情弹层。
- 移除“标记完成并领取成长值”按钮。官方读物阅读满 1 分钟且到达正文底部后，前端自动提交阅读活动并记录完成奖励；后端再次校验当天累计阅读时间至少 60 秒。
- “私人学习空间”用户可见名称已改为“学习空间”，包括左侧导航、页面标题、返回按钮和移动导航标签。
- “请求注销账号”已改为“申请注销账号”，“撤销注销请求”改为“撤销注销申请”。
- 运营后台重构为 5 个 Tabs：概览与用户、会员与额度、书城审核、媒体资产、审计与导出。
- 媒体资产接口新增 `limit + offset + total`，后台默认每页 20 项并提供上一页/下一页。
- 后台选择用户、选择审核内容等操作现在显示明确状态提示；原有表单按钮继续使用真实 API 和 CSRF。
- 左侧一级菜单、运营后台 Tabs、系统设置 Tabs、书籍详情弹层和完整阅读器均同步 URL 查询参数；刷新和浏览器前进/后退可恢复对应页面、Tab、详情或阅读器。
- 前端缓存版本更新为 `styles.css?v=20261010-4`、`app.js?v=20261010-6`。
- 阶段 1–9 PostgreSQL 集成再次全部通过，并生成/验证外部备份 `/Users/x/SaaSBackups/20261010T143940Z`。
- 修复后 HTTP smoke、SaaS API smoke、展示测试 9 项、移动端、性能和远程界面测试全部通过。
- 最新阅读器截图：
  - 学习空间桌面：`.local/debug/walkthrough/20261010T145454Z/desktop-workspace-reader.png`
  - 学习空间移动：`.local/debug/walkthrough/20261010T145845Z/mobile-workspace-reader.png`
  - 官方桌面：`.local/debug/walkthrough/20261010T145704Z/desktop-official-reader.png`
  - 官方移动：`.local/debug/walkthrough/20261010T145704Z/mobile-official-reader.png`
  - 后台 Tabs：`.local/debug/walkthrough/20261010T145952Z/desktop-admin.png`
- 后续复测确认：
  - 学习空间移动完整阅读器：`.local/debug/walkthrough/20261010T145845Z/mobile-workspace-reader.png`，正文优先显示、底部播放条可见。
  - 官方移动完整阅读器：`.local/debug/walkthrough/20261010T145704Z/mobile-official-reader.png`，视频与底部播放条可见。
  - 后台 Tabs 桌面/移动：`.local/debug/walkthrough/20261010T145952Z/desktop-admin.png`、`mobile-admin.png`。
- 后台所有操作新增全局状态栏；表单按钮会显示“处理中”，成功/失败结果不会再藏在审计 Tab 底部。
- 官方完成奖励后端新增 60 秒阅读校验，防止直接调用接口绕过前端条件。
- 学习空间完整阅读器中的生词评级和备注已切换到 `/api/workspace/vocabulary`、`/api/workspace/annotations`，不再误调用旧 SQLite 接口。
- 媒体资产清单分页接口及前端分页已完成，默认每页 20 项。
- 路由示例：`?screen=workspace`、`?screen=admin&tab=media`、`?screen=reader&reader=workspace&id=...`、`?screen=catalog&book=...`。

## 页面优化建议（后续迭代）

### P0：补齐真实外部服务

- 配置平台 AI 凭据，使“AI 语境精讲”和“句法分析”从受控降级状态变为真实生成。
- 配置生产 SMTP；当前本地 SMTP 仅写入 outbox，适合调试，不适合真实用户收信。

### P1：主要用户流程

- 将“导入新内容”从私人空间折叠区进一步拆成独立向导：选择类型 → 上传/地址 → 额度与空间预检 → 后台任务 → 完成读物。
- 导入任务改为服务端后台队列；当前同步 `/complete` 在长视频或 YouTube 场景中会让浏览器长时间等待。
- 私人阅读页增加目录、最近阅读位置和媒体/正文双栏快捷切换，降低长读物的定位成本。
- 官方书城补真实封面、简介质量和统一的主操作按钮；目前字母占位封面辨识度有限。

### P2：移动端与管理后台

- 为 SaaS 移动端增加固定底部主导航（书城、书架、私人空间、学习、我的），减少反复打开侧栏。
- 运营后台按“用户、会员、内容、媒体、审计”拆分标签页；当前单页纵向较长，手机上查找操作成本高。
- 会员中心将 9 项额度按“内容、AI、导入、空间/设备”分组，避免大量同级卡片。
- 空状态增加直接行动按钮，例如“去书城”“导入第一本”“创建邀请码”，减少只有说明文字的页面。

### P3：可观测性与体验

- 前端增加统一 Toast/错误中心，并显示请求 ID，便于定位失败任务。
- 为视频、YouTube、Whisper 和 AI 任务增加预计耗时、排队位置、可取消状态和失败重试按钮。
- 管理后台增加系统健康页：PostgreSQL、SMTP、AI、备份、磁盘、Worker 和最近错误。
- 上线前补真实手机 Safari/Chrome 手工验收；当前真实 Chrome 截图和响应式自动测试已经通过。

### 2026-10-10 19:20 — 进度同步

- 当前端口确认：
  - `8790`：本地 SaaS Web 调试服务，正在监听。
  - `1025`：本地 SMTP 捕获服务，正在监听。
- 当前本地调试服务没有停止；停止命令为 `./start-reader.sh --stop-saas-local`。
- 当前可复用的项目外备份仍为 `/Users/x/SaaSBackups/20261010T110343Z`；本机最新备份仍为 `.local/saas-backups/20261010T105734Z`。
- 最新就绪检查：数据库、13 个 migration、外部备份目录、FFmpeg、Node.js、yt-dlp、Whisper、PDF OCR 均配置/可用；真实 SMTP 和平台 AI 仍缺失。
- 直接运行 `./start-reader.sh --readiness` 时，当前 shell 因网络命名空间无法访问 55432，显示 PostgreSQL `OperationalError`；这不代表正式数据库验收回退，之前的 `./start-reader.sh --saas-test` 已在获准本机上下文完成阶段 1–9 和备份校验。
- 代码、测试和文档仍是未提交工作区变更，未执行远程部署或 Git 提交。

### 2026-10-10 23:46 — Product Design 当前界面审计

- 按 Product Design 截图审计流程重新采集当前版本证据，仅使用本轮新截图，不混用旧界面截图。
- 本轮覆盖：首页·书城、学习空间、学习空间阅读器、官方读物阅读器、学习记录、会员中心、运营后台、系统设置；每页均检查桌面与移动布局。
- 截图目录：
  - 书城：`.local/debug/walkthrough/20261010T153833Z`
  - 学习空间：`.local/debug/walkthrough/20261010T153912Z`
  - 学习空间阅读器：`.local/debug/walkthrough/20261010T153952Z`
  - 学习记录：`.local/debug/walkthrough/20261010T154030Z`
  - 会员中心：`.local/debug/walkthrough/20261010T154108Z`
  - 运营后台：`.local/debug/walkthrough/20261010T154144Z`
  - 系统设置：`.local/debug/walkthrough/20261010T154417Z`
  - 官方读物阅读器：`.local/debug/walkthrough/20261010T154448Z`
- 当前优点：奶油白、鼠尾草绿、深绿和珊瑚色形成统一的阅读品牌；衬线标题有编辑出版感；卡片、边框、圆角和留白规则较一致；后台 Tab 化后信息架构明显清晰；阅读器已有固定底部播放条。
- P0 体验问题：移动端多个页面仍出现内容超出视口并被右侧裁切；私人读物媒体区显示破图，官方视频首屏长期停留在加载占位；移动阅读器标题与正文被裁切；这些问题直接影响可用性和产品完成度。
- P1 体验问题：书城与学习空间使用重复的字母占位封面，识别效率低；学习空间 35 本读物缺少搜索、排序、筛选、最近阅读与进度入口；移动端主导航依赖顶部菜单；学习记录缺少周目标、连续学习、最近会话和下一步行动；会员额度未按内容、AI、导入、空间/设备分组。
- P2 体验问题：书城在内容较少时桌面首屏留白过大，移动筛选区占用过多纵向空间；卡片主操作弱；系统设置移动端信息行溢出且长页面缺少分区导航；运营后台移动 Tab 横向被裁切，应改成可滚动 Tab 并提供可见提示。
- 无障碍风险：需用代码和键盘实测确认文字对比度、可见焦点、弹层焦点圈定/返回、Tab 语义、状态播报以及至少 44×44 px 的触控目标；截图审计不能宣称达到完整 WCAG 合规。
- 本轮只完成设计审计和建议记录，没有直接修改前端实现。

### 2026-10-11 — 按审计结果完成第一轮 Bug 与体验优化

- 学习空间新增“继续学习”卡片，自动选择最近有阅读进度的私人读物；无进度时引导开始第一本读物。
- 学习空间新增标题、英文标题、书系和难度搜索，以及最近阅读、阅读进度、标题、最近导入排序；卡片显示进度条和“继续阅读/开始阅读”。
- 私人读物封面从单一字母占位改为带色彩和装饰纹理的轻量封面样式，仍保留无真实封面时的稳定降级。
- 学习记录新增连续学习天数、“下一步”继续阅读入口，并在移动端将指标卡固定为两列，避免桌面四列导致横向裁切。
- 会员中心额度按“内容权益、AI 学习、导入能力、账户资源”分组；套餐和有效期使用更适合用户阅读的中文日期/套餐名称。
- 阅读器增加原书页失败提示与重试按钮；视频增加加载较慢提示、重试入口，并在没有视觉媒体时隐藏空的图片元素，避免显示原生破图图标。
- 进一步将原书图片默认设为不可见，只有资源成功触发 `load` 后才显示；失败时显示产品化错误状态，避免浏览器原生破图图标闪现。
- 移动端增加全局宽度约束、卡片单列约束、搜索表单缩放、播放器安全宽度、阅读器正文/标题换行、后台 Tab 可横向滚动和设置页长文本换行。
- 前端缓存版本更新为 `styles.css?v=20261011-1`、`responsive.css?v=20261011-1`、`app.js?v=20261011-1`；展示测试同步更新版本断言。
- 验证通过：移动展示 7 项、会员展示 9 项、远程界面 3 项、性能 2 项；JavaScript 语法、Python 编译和 `git diff --check` 均通过。
- 本轮真实浏览器截图目录：
  - 学习空间：`.local/debug/walkthrough/20261010T230055Z`
  - 官方阅读器：`.local/debug/walkthrough/20261010T230514Z`
  - 会员中心：`.local/debug/walkthrough/20261010T230627Z`
  - 学习记录：`.local/debug/walkthrough/20261010T230823Z`

### 2026-10-11 — 主流 UI 框架引入方案

- 当前前端仍为原生 HTML/CSS/JavaScript，没有 `package.json`、React/Vue 组件树或构建入口；核心阅读器包含音频、视频、句子高亮、词典、路由和移动布局状态。
- 推荐采用低风险方案：引入 Bootstrap 5.3 的 CSS/基础组件能力，保留当前原生 JavaScript 和阅读器核心状态；用拾页自己的设计令牌覆盖默认蓝色、圆角、间距、阴影和交互状态。
- 暂不建议第一阶段迁移 React + Ant Design；这属于架构重写，容易影响阅读器、路由、媒体播放和已有 SaaS 功能。
- 组件迁移顺序：设计令牌 → 按钮/表单 → 卡片/徽章/进度条 → Tab/Offcanvas/Toast → 书城和学习空间 → 会员/学习记录 → 运营后台 → 阅读器外围控件。
- 交互规范：所有按钮统一支持 default、hover、focus-visible、pressed、loading、disabled、success/error 状态；危险操作使用二次确认；弹层、Tab、移动菜单和播放器不得混用两套互相冲突的状态管理。
- 本轮只完成框架选型与迁移方案记录，尚未安装 UI 框架或改造页面组件，等待进入实施阶段。

### 2026-10-11 — UI 组件层第一批实施

- 已新增 `reader/components.css`，建立 Bootstrap 兼容的拾页组件层：主题令牌、按钮变体、按钮状态、表单控件、焦点环、卡片阴影、Tab 状态、Toast 和移动底部导航。
- `reader/index.html` 已接入组件层，并新增移动端五项主导航：书城、书架、学习空间、学习记录、我的。
- `reader/app.js` 已让移动底部导航复用现有 `showScreen` 和路由逻辑；阅读器状态下自动隐藏，SaaS 页面显示并同步当前激活项。
- 移动底部导航增加显式运行时同步：根据屏幕宽度、阅读器/专注模式和当前 SaaS 状态控制显示，避免仅依赖 CSS 媒体查询造成浏览器差异。
- 全局阅读 Toast 增加 `role="status"` 和 `aria-live="polite"`，显示时间从 1.4 秒调整为 2.2 秒，便于用户读完反馈内容。
- 新增根目录 `package.json`，声明未来可安装的 `bootstrap@5.3.3` 和 `bootstrap-icons@1.11.3` 依赖，以及 `npm run check:js`、`npm run test:ui` 脚本。
- 本机安装 Bootstrap 依赖时因 npm registry DNS `ENOTFOUND` 失败；因此当前运行版本使用自包含组件层，不依赖 CDN 或外网，网络恢复后可以安装官方包并继续替换底层 CSS。
- 2026-10-11 再次执行 `npm install`，仍因 `registry.npmjs.org` DNS `ENOTFOUND` 失败；未生成 `node_modules` 或 `package-lock.json`，未把不完整依赖接入运行时。
- 2026-10-11 网络复测：一次 `curl -I https://registry.npmjs.org/bootstrap` 成功返回 HTTP/2 200，但随后 `npm ping`、Node `dns.lookup` 和后续 curl 请求仍间歇性返回 `ENOTFOUND registry.npmjs.org`；确认是本机/沙箱 DNS 解析不稳定，不是 Bootstrap 包地址失效。
- 2026-10-11 再次重试 `npm install --fetch-retries=2 --fetch-timeout=15000`，仍失败；新增手动安装脚本 [tools/install_ui_deps.sh](tools/install_ui_deps.sh)，会自动在 npm 官方源与 npmmirror 之间选择，并验证两个依赖包。
- 用户手动执行 npm 安装成功：`bootstrap@5.3.3`、`bootstrap-icons@1.11.3` 已安装，`package-lock.json` 已生成，审计结果为 0 vulnerabilities。
- 已验证 `require.resolve("bootstrap/package.json")` 与 `require.resolve("bootstrap-icons/package.json")`，并将官方静态资源复制到 `reader/vendor/bootstrap`、`reader/vendor/bootstrap-icons`。
- `reader/index.html` 已接入官方 Bootstrap CSS、Bootstrap Icons CSS 和 Bootstrap Bundle JS；拾页自定义组件层仍在其后覆盖品牌颜色和交互样式。
- 官方资源真实浏览器复测返回 200；最新组件复测截图目录：`.local/debug/walkthrough/20261011T020244Z`。

### 2026-10-11 — 运营后台 Bootstrap 操作组件第二批

- 运营后台一级导航改为 Bootstrap `btn-group` 风格，当前 Tab 使用 `btn-primary`，其他 Tab 使用 `btn-outline-secondary`，并同步 `aria-selected`。
- 媒体资产清单改成表格化布局：类型、内容类型、大小、归属/状态、存储路径；移动端保持横向滚动，不再把每一行拆成无序卡片。
- 媒体资产分页改为 Bootstrap `pagination` 风格，上一页、当前页、下一页使用统一 `page-link` 间距和禁用状态。
- 后台表单提交按钮、刷新按钮、导出按钮和审核按钮统一使用 Bootstrap 兼容的高度、圆角、阴影、Hover 和 Focus 状态。
- `enhanceAdminMediaRows()` 将后台 API 返回的媒体卡片数据转换成表格列，保留现有分页接口和 API，不改变后端协议。
- 真实浏览器后台复测通过：`.local/debug/walkthrough/20261011T021533Z`；官方 Bootstrap CSS、Icons 和 Bundle JS 均返回 HTTP 200。
- 回归测试继续通过：移动展示 8 项、会员展示 9 项、远程界面 3 项、性能 2 项、JavaScript/Python 编译和 `git diff --check`。
- 回归通过：JavaScript 语法、移动展示 8 项、会员展示 9 项、远程界面 3 项、性能 2 项、Python 编译和 `git diff --check`。
- 新一轮真实浏览器学习空间截图：`.local/debug/walkthrough/20261010T235850Z`。

### 2026-10-11 — React + Ant Design 商业版界面第一轮重构

本轮目标：把现有原生 HTML/CSS/JS 界面迁移到可持续维护的 React + Ant Design 页面层，同时保留已有 Python API、媒体鉴权、阅读器和 SaaS 业务逻辑，采用“新工作台并行接入 → 页面逐个替换 → 阅读器外围最后迁移”的策略降低风险。

#### 已完成的工程改造

- 新增 React/Vite 前端工程：`frontend/index.html`、`frontend/src/main.jsx`、`frontend/src/styles.css`、`frontend/vite.config.js`。
- 新增商业版入口：`reader/modern.html`；构建产物输出到 `reader/modern-assets/`，由现有 `reader_server.py` 直接提供静态资源。
- 新增脚本：`npm run dev:modern`、`npm run build:modern`；依赖为 React 18、React DOM、Ant Design 5、Ant Design Icons、Vite 和 React 插件。
- 新版通过 `/api/health`、`/api/workspace/books` 读取真实后端数据；接口不可用时使用明确的演示降级数据，避免页面空白。
- 已完成构建验证：`npm run build:modern` 通过，Vite 产物包含固定入口 `reader/modern-assets/assets/index.js` 和样式文件。

#### 页面级调整方案与当前实现

| 页面 | 商业化布局调整 | 控件与交互调整 | 后续产品/功能调整 |
|---|---|---|---|
| 学习空间 | 用“继续学习”主卡 + 周目标 + 阅读进度 + 今日行动四段式首屏，突出一个主任务 | 主 CTA 统一为“继续阅读/导入读物”，阅读卡可直接进入阅读器 | 接入真实最近阅读、学习目标、连续天数和任务完成状态；支持团队/个人空间切换 |
| 首页·书城 | 搜索和筛选置于首屏，读物卡统一封面、难度、进度和主操作 | 书源 Segmented、搜索 Input、卡片 hover/focus、移动端单列 | 增加主题/难度/时长筛选、收藏、解锁、版权标签和推荐理由 |
| 我的书架 | 从卡片堆叠改为带进度、来源、作者、操作的 List，适合 35+ 本读物 | 搜索、来源 Select、排序 Select、继续阅读按钮、空状态 | 接入服务端排序/分页、批量归档、最近阅读和导入任务状态 |
| 学习记录 | 四项关键指标 + 趋势图 + 下一步行动，避免只有历史数据 | 时间范围 Select、导出报告、读物继续入口 | 接入真实学习日、句子数、生词复习、周/月目标和可分享报告 |
| 会员中心 | 方案状态置顶，额度按内容权益、AI 学习、导入能力分组 | 进度条、权益清单、订阅管理入口 | 接入真实套餐比较、升级/降级、订单、发票、额度预警与失败释放说明 |
| 运营后台 | 指标行 + 用户/订阅表格，统一后台工作台信息层级 | Table 横向滚动、搜索、导出、创建邀请码、查看操作 | 增加审计日志、批量用户操作、人工订单、内容审核和任务队列详情 |
| 系统设置 | 阅读偏好与账户安全分栏，危险操作单独隔离 | Segmented、Select、保存按钮、设备管理和注销入口 | 接入 CSRF/API 保存、设备撤销、通知渠道、数据导出和删除确认流程 |
| 导入弹窗 | 单一任务弹窗，先选来源再输入文件/链接，降低认知负担 | Modal + Form + Segmented + 校验 + 成功反馈；移动端全宽 | 接入真实上传进度、重复导入确认、失败重试、队列优先级与取消任务 |
| 阅读器 | 暂保留现有阅读器核心，将外围导航、设置、反馈逐步迁移 | 先复用 React 工作台导航与入口，避免破坏音频、视频和词汇状态 | 第二阶段迁移播放条、媒体面板、生词侧栏和键盘/触控快捷键 |

#### 商业使用标准的统一规范

- 信息架构：一级导航固定为学习空间、书城、书架、学习记录、会员中心、运营后台；系统设置独立放置，避免和内容入口混在一起。
- 交互状态：所有主操作需覆盖 default、hover、focus-visible、loading、disabled、success/error；危险操作必须二次确认，并通过 Toast/Inline 状态明确反馈。
- 移动端：侧栏转为 Drawer；首屏 CTA 保持全宽；筛选项允许换行；列表操作不依赖 hover；内容区禁止横向溢出；触控目标按至少 44px 设计。
- 视觉令牌：延续拾页的奶油白、深绿、鼠尾草绿、珊瑚色，但由 Ant Design token 统一管理，避免页面各自定义蓝色、间距和圆角。
- 无障碍：使用 Menu、Button、Form、Modal、List、Table 等语义组件；下一轮需用键盘实测焦点、弹层焦点返回、错误播报、对比度和屏幕阅读器状态。

#### 当前边界与下一轮

- 这轮是可运行的 React 商业版工作台第一阶段，不会直接删除旧入口；`reader/index.html` 仍是原有完整阅读器，`reader/modern.html` 是新的 React 工作台入口。
- 下一轮优先把真实 API 数据结构映射到书城/书架/学习记录，并将导入弹窗接到现有导入接口；随后再替换会员、后台和设置的演示数据。
- 当前构建产物约 1.1MB，已可用但需要下一轮做 Ant Design 按页面拆包/懒加载，降低首屏 JS 体积。

### 2026-10-11 — React 工作台真实数据与导入任务第二轮

- 工作台启动时并行读取 `/api/health`、`/api/workspace/books`、`/api/catalog`、`/api/library`、`/api/workspace/learning-days`、`/api/membership/usage` 和 `/api/workspace/imports`。
- 新增服务端数据归一化层：将私人读物、官方书城读物和书架读物统一映射为 React 卡片/列表模型，兼容真实字段 `englishTitle`、`estimatedMinutes`、`progress.readingSeconds`、`coverUrl`、`series` 和会员 `usage`。
- 书城现在使用真实 `/api/catalog` 数据；我的书架优先使用真实 `/api/library` 数据；工作台和学习记录使用真实工作区进度/学习日数据。
- 学习记录已从静态示例指标改为读取 `content_learning_daily.payload`，展示学习天数、阅读分钟数和句子数；词汇统计暂时保留清晰的“下一阶段接入”状态，避免伪造数据。
- 会员中心已读取真实套餐、周期和各项额度，AI 额度按 `available / limit` 生成进度；未登录或 SaaS 接口不可用时保留可识别的降级展示。
- 导入弹窗已接入 `/api/workspace/imports`、`/{taskId}/upload`、`/{taskId}/complete`：支持文本、PDF、MP3、视频和 YouTube；上传任务自动刷新书架和任务列表。
- 所有 React 写操作统一携带 `shiyue_csrf` Cookie 对应的 `X-CSRF-Token`；保留后端幂等键，避免重复提交产生重复导入任务。
- 我的书架新增导入任务区域，展示任务步骤、状态和进度；失败状态使用 Ant Design `exception` 样式，完成状态使用 `success` 样式。
- 验证通过：`npm run check:js`、`npm run build:modern`、`git diff --check`。
- 当前未做真实账号下的浏览器上传回归：现有本地服务受当前 shell 网络命名空间限制，下一轮需要在可访问 PostgreSQL 的本机调试上下文中完成桌面/移动截图和真实上传验证。

### 2026-10-11 — 目录、导入队列与运营后台第三轮

- 书城卡片接入真实目录状态：根据 `inLibrary` 和 `unlocked` 显示“加入书架 / 解锁阅读 / 已解锁”，分别调用 `/api/library/items` 和 `/api/catalog/books/{id}/unlock`。
- 书城操作按钮与卡片点击行为分离，点击加入书架不会误触发阅读器跳转；成功后自动刷新书城、书架和会员额度。
- 导入任务增加后台轮询：存在 `queued`、`uploading` 或 `processing` 任务时每 3 秒读取 `/api/workspace/imports`，任务列表会自动更新步骤、进度、完成和失败状态。
- 导入任务增加取消操作，调用 `/api/workspace/imports/{taskId}/cancel`，并在取消后刷新队列和额度状态。
- 运营后台接入 `/api/admin/dashboard` 与 `/api/admin/users`，真实展示用户数、活跃用户、已验证用户、有效订阅、书城内容和用户表格；无管理员权限时显示空状态，不再伪造用户数据。
- 继续使用 Ant Design Table 的横向滚动和分页，保证移动端后台表格不会撑破页面宽度。
- 验证通过：`npm run build:modern`、`npm run check:js`、`git diff --check`。
- 当前仍未在真实管理员账号的浏览器上下文完成目录解锁与任务取消截图回归；下一轮需要在可访问本地 PostgreSQL 的调试服务中验证 quota exceeded、权限不足、任务失败和移动端触控反馈。

### 2026-10-11 — 运营操作闭环第四轮

- 运营后台用户表增加“管理”下拉操作：活跃账号可暂停，暂停账号可恢复。
- 用户状态操作接入 `/api/admin/users/{userId}/status`，发送操作原因并在成功后刷新 Dashboard、用户列表和统计指标。
- 继续复用 CSRF 保护和 Ant Design Dropdown，危险操作以红色菜单项表达，不直接暴露破坏性按钮。
- 运营后台现在具备从数据查看到账号状态管理的最小闭环；后续将继续接入邀请码创建、人工订阅和审计日志。
- 验证通过：`npm run build:modern`、`npm run check:js`、`git diff --check`。

### 2026-10-11 — 邀请码与审计追溯第五轮

- 运营后台接入 `/api/admin/invitations`，新增创建邀请码弹窗，支持自定义邀请码、使用次数和备注；邀请码留空时由服务端生成。
- 邀请码创建沿用管理员权限检查、CSRF 校验和服务端审计记录，成功后自动刷新 Dashboard、邀请码列表和审计列表。
- 运营后台新增“最近邀请码”列表，展示使用次数、状态和复制操作；移动端保持单列布局。
- 运营后台新增“最近审计操作”列表，展示操作类型、操作者、原因和时间，形成“操作后可追溯”的最小闭环。
- 新增真实读取：`/api/admin/invitations?limit=20`、`/api/admin/audit?limit=20`。
- 验证通过：`npm run build:modern`、`npm run check:js`、`git diff --check`。
- 尚未在真实管理员账号上下文执行邀请码创建回归；需要下一轮验证邀请码冲突、使用次数边界、非管理员 403 和移动端复制反馈。

### 2026-10-11 — 运营用户详情第六轮

- 运营后台用户表新增“查看详情”操作，打开 Ant Design Drawer，不离开当前列表即可查看用户账号信息。
- 用户详情接入 `/api/admin/users/{userId}`，展示邮箱、状态、套餐、设备数、成长值、设备列表和订阅列表。
- 设备详情展示客户端信息、最近状态和是否已撤销；订阅详情展示套餐版本、状态和备注。
- Drawer 在移动端按视口宽度收缩，避免详情面板横向溢出；接口失败时显示明确空状态，不使用静态占位数据。
- 用户状态管理、邀请码创建和审计列表继续共享同一套权限与 CSRF 写入逻辑。
- 验证通过：`npm run build:modern`、`npm run check:js`、`git diff --check`。

### 2026-10-11 — 管理员设备安全操作第七轮

- 新增管理员设备撤销后端能力：`DELETE /api/admin/users/{userId}/devices/{deviceId}`。
- `AdminService.revoke_device` 会校验目标用户和设备归属，重复撤销保持幂等，并同步撤销该设备的活跃会话。
- 每次成功撤销都会写入 `admin_audit_logs`，动作类型为 `device_revoked`，包含目标用户、设备 ID 和操作原因。
- 用户详情 Drawer 的设备列表新增“撤销”按钮；已撤销设备不会重复显示操作按钮，成功后自动刷新详情相关数据。
- 后端接口要求管理员会话和 CSRF Token，非管理员返回 `403 admin_required`，不存在设备返回明确 `404 device_not_found`。
- 验证通过：`npm run build:modern`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py`、`git diff --check`。
- 现有 UI 回归也通过：`npm run test:ui`（移动展示 8 项、会员展示 9 项、远程界面 3 项、性能 2 项）。
- 尚未在真实管理员账号中执行设备撤销浏览器回归；下一轮需验证当前设备保护、重复撤销幂等和移动端 Drawer 操作反馈。

### 2026-10-11 — 高风险确认与审计筛选第八轮

- 设备撤销现在必须经过二次确认，明确提示“活跃会话会立即失效”，确认按钮使用危险色，取消操作不会调用后端。
- 审计日志增加关键词搜索，可匹配操作类型、操作者、目标用户和操作原因。
- 审计日志增加操作类型筛选，筛选项根据当前真实返回数据动态生成，不引入不存在的固定操作类型。
- 审计列表移动端使用可换行的筛选区域，结果继续限制在最近 20 条，避免后台首屏过长。
- 继续保留后端审计写入、权限校验、CSRF 校验和设备撤销幂等行为。
- 验证通过：`npm run build:modern`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py`、`git diff --check`。

### 2026-10-11 — 运营额度调整第九轮

- 用户详情 Drawer 新增额度调整表单，支持 AI 语境、AI 句法、MP3、视频和 YouTube 导入等功能项。
- 调整表单要求填写数量和操作原因，调用已有 `/api/admin/quotas/adjust`，自动生成幂等键，避免重复提交造成重复额度变更。
- 成功调整后刷新工作台、会员额度、用户详情和审计列表；失败时保留后端额度不足、功能无效和权限错误信息。
- 额度调整继续受管理员权限、CSRF、服务端额度边界和审计原因校验保护。
- 用户详情中现在形成“账号状态、设备安全、订阅、额度”四类运营信息的统一入口。
- 验证通过：`npm run build:modern`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py`、`git diff --check`。
- 当前仍需真实管理员账号回归验证正负额度调整、额度为零、非法功能和移动端表单提交反馈。

### 2026-10-11 — 订阅运营闭环第十轮

- 用户详情 Drawer 的订阅列表新增“管理”操作，接入暂停订阅、恢复订阅和延长订阅。
- 订阅操作调用已有 `/api/admin/subscriptions`，延期时要求填写新的结束时间；暂停和恢复保留当前结束时间。
- 订阅操作支持填写备注，服务端会写入会员审计记录；成功后自动刷新会员额度、用户详情和运营审计列表。
- 运营后台现在可以在同一个用户详情入口完成账号状态、设备安全、额度和订阅四类操作。
- 验证通过：`npm run build:modern`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py`、`git diff --check`。
- 当前仍需真实管理员账号验证延期时间格式、已过期订阅恢复、重复提交和订阅权限边界。

### 2026-10-11 — 人工订阅与订单第十一轮

- 运营后台新增“创建人工订阅”入口，接入 `/api/admin/manual-orders`。
- 支持选择真实用户、套餐版本、开始时间、结束时间、金额（分）和备注。
- 启动时读取 `/api/admin/plan-versions`，套餐选项不再硬编码；用户选项来自真实 `/api/admin/users`。
- 创建成功后自动刷新 Dashboard、会员额度、用户详情、订阅列表和审计日志。
- 人工订阅沿用服务端订单创建、套餐校验、时间格式校验、管理员权限和审计写入。
- 验证通过：`npm run build:modern`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py`、`git diff --check`。
- 当前仍需真实管理员上下文验证无套餐、无用户、结束时间早于开始时间、金额边界和重复提交。

### 2026-10-11 — 审计服务端筛选第十二轮

- `AdminService.audit` 新增服务端关键词和操作类型筛选，避免审计数据增长后只在前端筛选最近一小段结果。
- `/api/admin/audit` 新增查询参数：`q` 可匹配操作、原因、操作者和目标用户；`action` 可精确匹配操作类型。
- 查询继续使用参数化 SQL，保留管理员权限、审计数据隔离和最大返回条数限制。
- 前端现有搜索和操作类型控件仍可继续工作，后续将把控件改为服务端查询并增加分页。
- 验证通过：`npm run build:modern`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py`、`git diff --check`。

### 2026-10-11 — 审计查询与订单追溯收尾轮

- 审计日志前端已切换为服务端查询：输入关键词或选择操作类型后，经过轻量防抖调用 `/api/admin/audit`，不再只对当前页面内存数据筛选。
- 订阅暂停、恢复和延期现在统一经过二次确认，明确说明会立即影响用户会员权益并写入审计记录。
- 用户详情新增人工订单列表，展示套餐版本、金额、币种、状态、起止时间和备注。
- `AdminService.user_detail` 新增读取用户最近 20 条人工订单，人工订阅创建后的订单与订阅状态可以在同一详情抽屉追溯。
- 验证通过：`npm run build:modern`、`npm run check:js`、`npm run test:ui`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py`、`git diff --check`。

### 2026-10-11 — 架构升级调试轮

- 前端生产构建通过：`npm run build:modern`；React + Ant Design 产物可正常生成。
- 原有前端脚本检查通过：`npm run check:js`。
- 现有 UI 回归通过：`npm run test:ui`，共通过移动展示 8 项、会员展示 9 项、远程界面 3 项、性能 2 项。
- 本轮新增后端文件定向编译通过：`tools/reader_server.py`、`tools/saas_admin.py`、`tools/saas_membership.py`。
- 全量 `python3 -m compileall -q tools` 被仓库已有 `tools/vendor/ECDICT/dictutils.py` 和 `tools/vendor/ECDICT/linguist.py` 的 Python 2 语法阻断；这些文件未被本轮修改，已保留为历史 vendor 兼容性问题。
- `test_saas_phase5_integration.py` 在当前 shell 中主动拒绝运行，因为 `SHIYUE_SAAS_TEST_DATABASE_URL` 没有指向名称以 `_test` 结尾的专用数据库；未对任何非测试数据库执行写操作。
- `git diff --check` 通过；当前代码变更未发现空白或 Python/JavaScript 语法回归。

### 2026-10-11 — 生产构建拆包优化轮

- Vite 新增稳定 vendor 拆包：`react.js`、`antd.js`、`icons.js` 和 `vendor.js`，避免 React、Ant Design 和图标库全部进入单一入口。
- React 工作台入口从约 1.16MB 降至约 36.7KB（未压缩），Ant Design 及其依赖按独立缓存块输出；入口 gzip 约 12.6KB。
- `reader/modern.html` 继续使用固定 `assets/index.js`，拆分后的 vendor 块由 Vite 入口自动加载，现有静态服务无需额外路由改动。
- 构建产物仍保留 Ant Design 约 525KB 的独立缓存块，后续可按页面做动态 import；当前首屏入口已不再携带整套 UI 框架。
- 验证通过：`npm run build:modern`、`npm run test:ui`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py tools/saas_admin.py tools/saas_membership.py`、`git diff --check`。

### 2026-10-11 — 现代前端产物 Smoke Test 轮

- 新增 `npm run test:modern` 和 [tools/test_modern_frontend.py](tools/test_modern_frontend.py)。
- Smoke test 检查 `reader/modern.html` 固定入口、入口 chunk、React/Ant Design/Icons vendor chunk 是否存在，以及入口引用的 chunk 是否都位于安全的 `reader/modern-assets/assets` 目录内。
- 防止构建产物存在但静态部署缺少 vendor chunk、入口引用 hash 失效或路径越界。
- 验证通过：`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、Python 定向编译、`git diff --check`。

### 2026-10-11 — 工作台会话闭环轮

- React 工作台启动时读取 `/api/auth/me`，顶部用户菜单优先展示当前登录邮箱，不再使用固定账户文案。
- 新增安全退出流程：退出菜单调用 `/api/auth/logout`，携带当前 CSRF Token，成功后返回旧阅读器入口；失败时保留错误反馈。
- 账户菜单保留“账户与安全”入口语义，并将退出操作标为危险项，降低误触风险。
- 会话读取失败时工作台仍保持可渲染的降级状态，不把未登录接口错误显示为白屏。
- 验证通过：`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、Python 定向编译、`git diff --check`。

### 2026-10-11 — 调试服务器与账户安全页收尾轮

- 系统设置页接入真实 `/api/auth/me` 和 `/api/auth/devices`，显示当前登录邮箱、设备数量、客户端信息和活跃/撤销状态。
- 普通用户可以在系统设置页撤销自己的设备；操作经过二次确认，调用现有 `DELETE /api/auth/devices/{deviceId}` 并自动刷新设备列表。
- 修正 Vite 配置根目录为 `frontend`，开发服务器现在可以直接访问 `/modern-assets/`，不再出现开发模式 404。
- 已启动 React + Ant Design 调试服务器：`http://127.0.0.1:5173/modern-assets/`。
- 调试服务器实测返回：现代入口 HTML 200、`src/main.jsx` 200、`src/styles.css` 200。
- 生产构建、现代前端 Smoke、UI 回归、JavaScript 检查、Python 定向编译和 `git diff --check` 全部通过。
- 当前调试服务器由本轮启动，停止方式为对应终端发送 `Ctrl-C`；未执行远程部署或 Git 提交。

### 2026-10-11 — 集成测试与验收轮

- 已运行 `./start-reader.sh --saas-test`：阶段 1–9 全部通过，测试库为 `shiyue_phase1_test`，13 个 migration 完整校验通过。
- 正式本地库 `shiyue_saas_local` 的 migration 无新增待应用项；验收统计为 users 1、content_books 40、media_assets 5287、workspace_import_tasks 1、workspace_ai_results 0。
- 备份验收通过：项目外备份 `/Users/x/SaaSBackups/20261011T045417Z`，数据库 dump 校验通过，5,290 个媒体文件清单校验通过。
- 已运行 `./start-reader.sh --saas-smoke 8795`：SaaS health、CSP、未登录隔离、登录、CSRF、会员额度、目录、文本导入、私人阅读器、媒体 Range、生词、标注、学习活动、AI 失败额度释放、账号导出、管理员隔离和退出登录全部通过。
- 已运行 `./start-reader.sh --saas-ui-smoke 8792`：登录页桌面截图和移动截图通过，截图保存为 `.local/debug/saas-login-desktop.png`、`.local/debug/saas-login-mobile.png`，并已人工检查无空白、裁切或加载错误。
- 修复 SaaS UI smoke 的历史版本号硬编码：资源断言改为检查 `app.js?v=` 和 `styles.css?v=`，避免前端缓存版本更新后误报失败。
- 当前调试服务：React Vite `http://127.0.0.1:5173/modern-assets/` 仍在运行；SaaS smoke 服务为测试脚本临时启动并已自动停止。
- 验收结论：核心 SaaS 后端、认证隔离、导入/阅读/媒体、AI 额度、备份恢复链路和登录页桌面/移动入口均通过；完整已登录 React 工作台截图仍需带真实管理员凭据的浏览器 walkthrough 才能最终确认。

### 2026-10-11 — 最终调试状态复核轮

- 当前环境未配置 `SHIYUE_BROWSER_AUDIT_EMAIL` / `SHIYUE_BROWSER_AUDIT_PASSWORD`，也没有可安全读取的管理员 walkthrough 密码；未尝试猜测或写入凭据，因此不强行执行已登录管理员截图验收。
- React 调试服务器仍正常运行，`http://127.0.0.1:5173/modern-assets/` 实测返回 200。
- 现代前端 Smoke、移动/会员/远程/性能 UI 回归、JavaScript 检查、Python 定向编译和 `git diff --check` 再次通过。
- 当前剩余唯一验收项是：在提供真实管理员测试凭据后，执行已登录 React 工作台的桌面/移动 walkthrough，覆盖书城、学习空间、会员中心、运营后台和系统设置；后端集成验收已完成，不受该凭据缺失影响。

### 2026-10-11 — React 工作台 API 真接入修正轮

- 学习空间不再固定显示 68% 和 6 天，改为读取 `/api/workspace/learning-days` 与 `/api/rewards/status`，根据真实阅读秒数、句子数和连续学习数据计算周目标、学习天数和趋势。
- 学习记录趋势图改为使用真实学习日数据绘制；无数据时显示空状态/零值，不再使用静态柱状图数值。
- 会员中心读取 `/api/membership/usage` 和 `/api/membership/orders`，权益卡按真实额度展示；订单列表显示真实套餐、金额、币种、状态和备注。
- 运营后台“导出数据”按钮接入 `/api/admin/exports/summary`，生成真实 JSON 文件下载；不再是无动作按钮。
- 我的书架排序控件真正生效，支持最近更新、阅读进度和标题排序；导入任务仍由 `/api/workspace/imports` 轮询并支持取消。
- 系统设置读取 `/api/auth/me`、`/api/auth/devices`，普通用户可以真实撤销自己的设备；退出登录调用 `/api/auth/logout`。
- 保留真实 API 为空或未登录时的明确降级状态；不再把静态演示指标冒充为真实业务数据。
- 验证通过：`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、Python 定向编译、`git diff --check`。

### 2026-10-11 — 本地后台 API 启动与接口探测轮

- 已停止占用旧端口的后台进程，并用当前工作区代码重新启动本地 SaaS API：`http://localhost:8790`。
- `/api/health` 返回 200，确认 `saasEnabled=true`、运行模式为 `full`。
- 公开书城 `/api/catalog` 返回 200 和真实目录 JSON。
- 认证接口 `/api/auth/me`、设备、工作区、书架、会员、奖励、导入、后台、账户接口在未登录状态均正确返回 401。
- 未登录写操作也全部正确拒绝：退出登录、创建导入任务、创建邀请码和设备删除均返回 401。
- 已在专用测试库通过认证 HTTP smoke，覆盖登录、CSRF、工作区导入、阅读器、媒体 Range、词汇、标注、学习活动、AI 额度释放、账户导出和管理员隔离。
- 当前 8790 后台 API 进程仍在运行；React Vite 调试服务仍在 5173 运行。

### 2026-10-11 — Vite API 代理修复轮

- 修复 5173 调试前端访问 `/api/*` 返回 404 的问题：Vite 开发服务器新增 `/api` → `http://127.0.0.1:8790` 代理。
- 同时代理 `/books` 资源路径，确保新版前端通过 5173 调试时可以读取后台媒体/书籍资源。
- 修复后实测：`http://127.0.0.1:5173/api/health` 返回 200，`/api/catalog` 返回 200，`/api/auth/me` 正确返回 401（未登录鉴权），不再由 Vite 返回 404。
- 当前调试地址仍为 `http://127.0.0.1:5173/modern-assets/`，后台 API 仍运行在 `http://127.0.0.1:8790`。

### 2026-10-11 — 老架构功能对齐联调轮

- 对照旧版导航补齐 React 工作台的“生词复习”和“成长奖励”入口。
- 生词复习接入 `/api/workspace/vocabulary`，展示真实生词、释义、来源读物和复习时间；无数据时显示真实空状态。
- 成长奖励接入 `/api/rewards/status`、`/api/rewards/catalog`、`/api/rewards/ledger`，支持真实签到和奖励兑换，分别调用 `/api/checkins`、`/api/rewards/redeem`。
- 学习空间、学习记录、会员中心、运营后台、系统设置、书城、书架和导入任务均继续使用真实 API 数据；前端新增 API 代理后，5173 调试地址不再把 API 请求发给 Vite 自身。
- 真实 API 联调覆盖：公开 health/catalog、未登录 401 隔离、认证写操作拒绝，以及 `_test` 专用库 HTTP smoke 的登录、导入、阅读、媒体、词汇、标注、学习活动、奖励、AI 额度、导出和管理员隔离。
- 验证通过：`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、Python 定向编译、`git diff --check`。

### 2026-10-11 — PC 全功能迁移第一阶段（移动端暂缓）

- 按最新优先级改为仅推进 PC：先完成桌面功能迁移与联调，移动端视觉和手势交互在 PC 验收完成后单独进行。
- React 前端开始从单体 `main.jsx` 拆分：新增统一 API 客户端、阅读偏好配置、独立阅读器、书城、书架、生词复习、系统设置和平台运维页面；现有 SaaS 页面不再跳回旧阅读器。
- PC 阅读器补齐商业可用核心闭环：逐句上一句/复读/下一句、播放暂停、时间轴、倍速、媒体错误重试、句子同步定位、快捷键、句末自动暂停、左右/上下布局、护眼模式、专注模式、原始媒体视图、单词语境、私人释义、生词保存、单词标注、四档复习评分、句法分析、影子跟读录音、学习活动计数与完成保存。
- 修复私人阅读器 API 丢失时间信息：工作区 reader 现在返回 `start/end/page/section`，与官方 reader 保持逐句媒体同步所需的数据契约。
- 阅读偏好从 3 项扩展为账号级完整设置并写入 PostgreSQL：阅读模式、密度、提醒、布局、护眼、专注、句末暂停、4 个快捷键、单词工具栏时长、复习页大小、听写重复次数/停顿、高亮提前量、热力图范围和默认倍速；服务端执行枚举、范围和快捷键重复校验。
- 书城补齐 PC 多维筛选（难度、系列、标签、资源类型）、读物详情、有限预览、版权/阅读说明、加入书架、解锁并进入 React 阅读器。
- 书架补齐官方读物移出/归档与恢复、私人读物二次确认永久删除、完整导入任务历史、失败任务重新导入入口；新增 `DELETE /api/workspace/books/{id}`，验证租户归属、标题确认、官方书城源保护和媒体待清理标记。
- 生词页补齐真实到期队列、困难/掌握筛选、搜索、分页、四档复习评分、下次复习时间写回、复习活动计数及按偏好执行的听写朗读流程。
- 新增 React“平台与部署”管理页：内容版权/发布审核、媒体资产列表与标记删除、媒体清理预扫描/执行、到期注销账户清理、平台 AI 配置状态、远程节点新增/编辑、连接测试、资源同步、首次部署、程序升级、旧版本清理、代码/内容回滚和部署任务记录。SaaS 部署写操作新增 CSRF 校验。
- 修复桌面 walkthrough 的 `library` 路由白名单，旧别名不再把新版“我的书架”验收错误导向书城；测试库浏览器验收会先撤销过期验收设备，避免单设备套餐造成假失败，并支持仅运行 PC/指定页面。
- 已登录 1440px PC 浏览器验收通过：学习空间、书城、书架、学习记录、生词复习、成长奖励、会员中心、运营后台、系统设置、React 阅读器；输出 `.local/debug/modern-walkthrough/20261011T112505Z`。修正后书架、平台与部署、阅读器复核通过；输出 `.local/debug/modern-walkthrough/20261011T113557Z`。
- 认证 HTTP smoke 扩展并通过：完整阅读偏好持久化、导入/媒体 Range、生词、标注、学习活动、AI 失败额度释放、账户导出、私人读物删除及删除后 404、管理员面板和退出登录。
- 当前 PC 剩余工作：会员自助升级/支付仍缺少真实支付提供方与客户订单 API；导入仍是单请求上传，后端虽然允许大文件但浏览器端尚未实现可恢复分片；平台部署高风险动作需继续做真实节点沙箱验收。移动端仍按要求暂缓。

### 2026-10-11 — PC 商用闭环补强轮

- 新增迁移 `0015_membership_change_requests.sql`，已应用到 `shiyue_saas_local` 与 `shiyue_phase1_test`；增加用户侧套餐变更申请记录及单用户待处理申请唯一约束。
- 新增会员 API：`GET /api/membership/plans`、`GET /api/membership/requests`、`POST /api/membership/requests`；会员中心“管理订阅”不再是禁用按钮，现可查看免费版/进阶版/Pro 版真实配额与价格，并提交可审计的变更申请。正式支付仍需后续接入支付提供方，当前明确不会自动扣款。
- 导入上传不再使用 `file.arrayBuffer()` 整体复制文件；改为 `XMLHttpRequest.send(file)` 直接发送浏览器文件对象并显示真实上传进度，降低大型音视频上传时的浏览器内存峰值。可恢复分片上传仍属于后续增强项。
- 部署管理写操作补充 SaaS CSRF 校验；平台与部署 GET 接口、内容审核、媒体清单和平台配置均加入认证 smoke。
- 会员中心 1440px PC 浏览器复核通过，输出 `.local/debug/modern-walkthrough/20261011T124335Z`。
- 重新启动正式本地后台 `http://127.0.0.1:8790`；Vite 调试前端继续运行在 `http://127.0.0.1:5173/modern-assets/`。
- 最新验证通过：`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、Python 定向编译、`git diff --check`、扩展认证 HTTP smoke、PC 已登录 walkthrough。
- PC 阶段尚未声称完成的外部依赖/增强：真实支付网关与回调、可恢复分片上传、生产远程节点高风险部署/回滚实机演练。移动端仍未进入优化阶段。

### 2026-10-11 — PC 交互问题集中修正与阅读器对齐轮

- 修复 Vite 调试地址刷新路由：新版内部导航根据入口自动保持 `/modern-assets/?screen=...` 或 `/modern.html?screen=...`，不再在 5173 下跳到 `/modern.html` 并触发 Vite 的 public base URL 提示；实测 `http://127.0.0.1:5173/modern-assets/?screen=library` 刷新返回 200 并正常渲染。
- 修复已登录首页闪现登录页：认证状态为 `loading` 时显示独立工作区启动页，只有 `/api/auth/me` 明确返回 401 后才渲染登录表单。
- 首页本周目标圆点改为按自然周日期和每天真实学习活动判断，不再按接口数组长度从周一开始批量打勾；目标百分比与日期完成状态现在使用同一周数据。继续学习卡片改为固定左右布局，封面位于标题和操作区右侧。
- 导入流程改为“上传完成即关闭弹窗、后台处理请求异步继续、书架每 3 秒轮询”；轮询状态补齐 `running` 与 `awaiting_processor`。因此无需 WebSocket，也不再等待长时间转写/OCR 请求结束后才能返回页面。
- 我的书架新增 8 本/页分页；筛选、排序和删除后会自动重置或修正当前页。
- 学习记录改为旧版风格的方格学习热力图，支持周/月/年切换，按阅读时长、句数、查词和复习综合计算 0～4 级色阶，不再使用柱状图。
- 生词复习增加列表/卡片平铺切换，保留单词复习/听写模式、筛选、搜索和真实分页；卡片平铺支持发音入口和四档复习评分。
- 成长记录增加分页展示。
- 会员当前方案排版修正：方案名称与“当前方案”同一行，有效期在其下方左对齐。
- 运营后台改为独立 React 页面：人工订阅支持 1 周、1 月、1 季度、1 年快捷时长以及带时间的起止时间控件；邀请码留空由后台生成；支持一次批量生成 1～100 个、每码独立使用次数、过期时间；最近邀请码支持服务端查询与分页。
- 邀请码后台兼容单个旧接口返回结构，同时新增批量返回 `invitations/count`；HTTP smoke 已验证空码批量生成和查询。
- 部署任务增加 2 秒自动轮询，只要存在 `queued/running` 任务就持续刷新任务进度和节点状态；测试连接、同步、部署和升级不再要求手工刷新。
- 平台 AI 配置改为管理员从“平台与部署 → 平台配置”直接保存邮箱、Token 和 API 地址到 PostgreSQL `platform_settings`；AI 请求即时读取数据库配置，不再依赖 `SHIYUE_DIOCO_*` environment，完整 Token 不回传浏览器，并支持清除 Token。
- 系统设置为精读、泛读和影子跟读增加逐项 Tooltip，解释查词/句法、连续阅读和原音跟读录音的区别。
- PC 阅读器再次按旧版交互重构：顶部只保留媒体位置切换图标（带 Tooltip），支持媒体左侧/上方布局；右侧固定为“单词 / 句法 / 跟读”；媒体面板无内容边框、支持视频清晰度切换、关闭及按左侧布局恢复；字幕区独立滚动，依据原始音视频时间动态定位句子和高亮单词，缺少词级时间时按句子时长分配高亮区间；播放、复读和跟读均使用上传的原始音视频，不使用系统 TTS；句法面板恢复句型、主谓宾、从句、语法点和中文讲解；护眼和专注模式按旧版语义处理；快捷键监听使用捕获阶段，在普通、护眼、专注及媒体布局切换后均保持有效，并补回 Q 切换句末暂停。
- 使用 CDP 修复桌面验收工具稳定性。最新 1440px 登录态验收覆盖学习空间、书架、学习记录、生词、成长奖励、会员、运营后台、平台配置、系统设置和阅读器，全部通过；输出 `.local/debug/modern-walkthrough/20261011T135345Z`。
- 调试刷新页单独截图通过：`.local/debug/pc-parity/refresh-library.png`。最终构建、现代前端 smoke、旧版 UI 回归、JavaScript/Python 编译和 `git diff --check` 全部通过。

### 2026-10-11 — AI 共享交接文档规范化

- 新增根目录 `AGENTS.md`，规定 Codex 必读顺序、开发原则、文档维护规则和简洁交付格式。
- 新增 `AI_CONTEXT/README.md`，仅保存当前架构、全局完成/未完成状态、任务索引和默认验证命令。
- 按任务拆分交接目录：`pc-workspace`、`reader`、`backend-saas`、`import-media`、`platform-operations`、`mobile`；后续 AI 只读取当前任务对应文档，避免加载无关历史。
- 新增 `AI_CONTEXT/TASK_TEMPLATE.md`，新的独立任务必须建立自己的 `tasks/<task-slug>/HANDOFF.md`。
- `PROGRESS.md` 继续作为历史里程碑记录，但不再作为新会话默认全文上下文；任务当前状态以对应 `HANDOFF.md` 为准。
