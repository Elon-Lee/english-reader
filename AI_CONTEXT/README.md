# 拾页 AI 共享上下文

更新时间：2026-10-21（Asia/Shanghai）

这是后续 AI 的最小全局上下文。只读取与当前任务相关的任务文档。

## 当前架构

- 前端：React 18 + Ant Design 5 + Vite，源码在 `frontend/src/`。
- SaaS 入口：生产根路径 `/` 直接加载 `reader/site/`；`/modern.html` 和 `/modern-assets/*` 只保留 308 兼容跳转。开发入口仍由 Vite 提供。
- 后端：Python 单体 HTTP 服务 `tools/reader_server.py`，业务拆分在 `tools/saas_*.py`。
- SaaS 数据：PostgreSQL；正式本地库 `shiyue_saas_local`，隔离测试库 `shiyue_phase1_test`。
- 旧数据：`.local/library.sqlite3` 和 `books/` 继续保留，不能删除；SaaS 新页面不再使用旧 UI。
- 媒体访问：SaaS 使用鉴权 `/api/media/{asset_id}` 和媒体变体。
- 认证：数据库会话 Cookie + CSRF；未登录时 React 渲染登录页。
- 长任务：导入和部署使用任务 API + 前端轮询，不依赖 WebSocket。
- 当前服务：后台 `127.0.0.1:8790`；Vite `127.0.0.1:5173`。
- 京东云生产：`117.72.209.44:8765`，Docker 运行 `shiyue-saas`、PostgreSQL 16 和 Redis 7；PostgreSQL/Redis 只监听远程回环地址。

## 全局完成状态

- 2026-10-21 本地修复 YouTube 已下载中文字幕未接入阅读句子，并按实际译文显示翻译按钮；已有书籍读取时补充响应、不回填。官方/私人导入列表增加明确导入时间。隔离回归与 Chrome 实机验证通过，8790 已重启，未发布生产。详见 import-media、reader。

- 2026-10-21 按用户限定，本地实现新 YouTube 导入人工英文字幕声学 CTC 对齐与不匹配回退；自动字幕等其他路径保持原流程，已有书籍未处理。真实全片/第 11 句检查、错字幕/静音拒绝、真实原音短视频处理至隔离 PostgreSQL 入库及 15 项集成回归通过；确认用户导入结束后已重启 8790，后台与 5173 代理健康，未发布生产。详见 import-media。

- 2026-10-20 阅读媒体新导入词时间轴已本地修复；最新视频第 11 行复查又修正 v2 的 DTW 距离阈值误判及标点共享时间点引发的整句回退，现为 timingVersion 3。全片 1,884 词重跑、人工字幕区间交叉检查及隔离导入回归通过，8790 已重启；依用户要求不写回已有书籍，未发布生产。详见 import-media。

- 2026-10-20 PC 首页学习闭环已本地实现：账号计划、统一续读、复习断点恢复、真实今日成果、阅读结算到本次新词复习再回首页；奖励去除失效权益并区分签到/学习。已备份迁移 0040、重启 8790；46 项隔离库回归、独立库 HTTP smoke、构建及前端检查通过，Chrome 隔离账号主要闭环已验收。未发布生产，详见 pc-workspace、reader、vocabulary-review、backend-saas。

- 2026-10-20 PC 生词复习第一版已本地实现：今日计划、主动回忆、薄弱词巩固、真实结算、断点恢复及回原文；新增迁移 0039 和服务端原子幂等作答。本地已备份迁移、重启，24 项隔离库回归、HTTP smoke、构建及 PC 浏览器验收通过；未发布生产。详见 vocabulary-review。

- 2026-10-20 PC 商业化第二轮已在本地完成：套餐权益逐行对比、首次学习指引、跨页面购买恢复、注册验证提示及真实转化/次日留存报表；本地已备份并应用迁移 0038、重启后台。36 项隔离库回归、35 项 HTTP smoke、构建与前端检查通过，Chrome 已验收主要路径；未发布生产。详见 commercial-design-audit。

- 2026-10-19 本地实现私人/官方导入隔离、运营内容管理官方导入及审核、用户媒体占用只读汇总、读物永久删除清理媒体；新 YouTube 高清最高 480p、流畅最高 240p，历史文件不重编码。45 项隔离库回归及前端检查通过，本地迁移 0037 和后台重启已完成；旧 HTTP smoke 的首页断言仍不兼容 API-only 后台，尚未发布生产。

- 2026-10-19 确认待审核内容采用媒体增量传输与 PostgreSQL 书目合并；移除仅适用旧 SQLite/reader 的失效内容回滚入口、接口和脚本，保留代码回滚。构建及 33 项部署回归通过，完整 HTTP smoke 受测试库缺少 migration 0036 阻断；尚未发布生产。详见 platform-operations。

- 2026-10-19 “平台与部署”限制为本地模式登录管理员：远程隐藏菜单且拒绝部署/平台配置 API，本地启动启用 `SHIYUE_DEPLOYMENT_MODE=local`，后台默认及远程容器为 remote；部署历史增加删除失败/取消任务。验证通过、本地已加载，尚未发布云服务器；详见 platform-operations。

- 2026-10-18 本地统一视频首帧/文字封面与书城按钮，导入历史增加分页和删除失败记录，YouTube 默认系列改频道并新增历史回填迁移 0036；构建入口缓存版本由时间戳改内容哈希。构建、相关回归和 PC 浏览器验收通过，尚未发布生产；2026-10-19 已备份本地正式库并应用 0036，本地调试服务健康。详见 pc-workspace、import-media、backend-saas、platform-operations。

- 2026-10-18 本地视频画质按有效套餐控制：免费版阅读/试读仅流畅，进阶与 Pro 可切换高清；媒体直链同步拦截免费账号，套餐公开页、会员中心与运营说明已更新。构建及隔离库回归通过，本地后台已重启，尚未发布生产。详见 reader、backend-saas、public-commerce 交接。
- 2026-10-18 本地内容审核移入运营后台；本地打包上传的新/变更书目强制未审核，必须由目标站管理员审核发布后才进入首页书城。重复同步未变更内容保留线上审核；本地构建及隔离 PostgreSQL 回归通过，尚未发布生产。详见 platform-operations、pc-workspace 交接。
- 2026-10-18 本地套餐触限已接入同页升级闭环：书城/试读收藏、导入额度及阅读器 AI 额度触限展示可升级商品，云猫购买兑换成功刷新权益并提供继续原操作；最高档显示释放名额/额度恢复说明。构建与浏览器模拟接口验证通过，尚未发布生产；详见 public-commerce、pc-workspace 交接。
- 2026-10-18 本地官方读物已统一为书架收藏状态：取消“已解锁”展示，阅读及原媒体权限跟随当前书架；官方与私人音视频合计严格检查套餐收藏上限。权益并发/幂等已扩展修复并新增 PostgreSQL 回归，新增 migration `0035`；尚未发布生产，详见 backend-saas、pc-workspace、import-media 交接。
- 2026-10-18 本地修复已登录但 CSRF Cookie 丢失导致所有写 API 403：认证读取轮换 session 并补发会话绑定 CSRF Cookie，前端对 `csrf_failed` 自动恢复并单次重试；旧 session 失效。待浏览器旧会话验收，尚未发布生产，详见 backend-saas 与 pc-workspace 交接。
- 2026-10-18 本地修复 YouTube 导入长时间停在 45%：Whisper 关闭并丢弃进度输出；已接入阶段进度、转写百分比和遗留任务恢复，卡住的任务已恢复完成。代码及测试通过，运行中的 8790 服务需重启后生效；详见 import-media 交接。
- 2026-10-18 已实机检查并热修复京东云视频处理：FFmpeg/Node/yt-dlp/Whisper/模型、媒体挂载和 3 秒端到端处理均通过；生产后台已加载导入进度修复版并重启，后续正式 SaaS 升级需带入该代码，详见 import-media 与 platform-operations 交接。

- SaaS 阶段 1–9 后端、迁移、认证、会员、书城、奖励、工作区、导入、媒体、AI、管理后台均已实现并经过本地集成测试。
- PC React 页面已经覆盖登录、学习空间、书城、书架、学习记录、生词、奖励、会员、运营后台、平台部署、系统设置和阅读器。
- PC 主要 API 已真实接入；刷新路由、认证闪屏、分页、热力图、任务轮询、批量邀请码和数据库 AI 配置已修正。
- 阅读器已改为旧版语义的媒体/字幕/释义三栏交互，并保留快捷键、护眼和专注模式。
- 京东云旧 reader 服务已被根路径 React SaaS 替换；生产 PostgreSQL、Redis、SaaS 容器和已公开书籍增量同步已实机验收。
- 本地和生产已切换云猫寄售套餐：Free/进阶/Pro 三档公开展示；进阶 ¥19、Pro ¥49/30 天，预设 6 折。两款云猫商品已上架、首批库存各 20 张，购买链接已回填两环境，40 个兑换码哈希已同步生产。会员规则为同级立即续费延长有效期、只允许向上升级并按剩余价值折算、不允许降级；本地实现待发布生产。
- 2026-10-18 京东云生产当前代码版本 `code-20261018-081452-67a2d629`，SaaS 升级任务 #24389 complete；SaaS/Redis、根页面、运行挂载与 migrations 至 `0034` 均通过。旧付费套餐缺失的音视频收藏权益及已有账期已修复；指定生产管理员账号随后按用户要求恢复免费，详见 backend-saas 交接。
- 2026-10-17 云猫购买到兑换闭环发布 `code-20261017-103944-212bb675`：套餐先进入拾页购买说明页，云猫新标签支付，购买页直接兑换码开通，登录后回跳到原购买页。
- 2026-10-17 按用户反馈，本地公开套餐页及会员中心续费/升级均改为当前页购买兑换弹窗，避免中间页面；隔离账号验证通过，尚未发布生产。
- 2026-10-17 修复平台“程序升级”路由误用旧 reader 部署流程，改为 SaaS 专用候选升级，包含远程 PostgreSQL 备份、SQL migrations 完整性核验、候选健康验收和远端 current 版本展示；本地验证完成，尚未发布生产。详见 `tasks/platform-operations/HANDOFF.md`。
- 2026-10-17 已确认并在本地实现 AI 分析新口径：免费用户按 `Asia/Shanghai` 自然日限制词汇语境 50 次、句法分析 20 次；进阶/Pro 两项不限次数，不扣额度。服务端使用独立每日 usage period，尚未发布生产。
- 最新构建与测试通过，最近 PC 浏览器验收目录：`.local/debug/modern-walkthrough/20261011T135345Z`。

## 全局未完成

- 移动端展示、底部操作区、手势和弹层交互尚未进入正式优化阶段。
- 云猫商品上架、库存与购买链接配置已完成；真实资金支付 → 云猫自动发码 → 正式账号兑换的整链路尚需商户本人完成一笔购买验收。
- 大文件上传已避免 `arrayBuffer()` 内存复制，但尚未实现可恢复分片上传。
- 京东云 SaaS 完整部署和公开资源增量同步已验收；生产回滚、卸载等高风险动作尚未执行。
- Dioco 完整词典接口 `base_dict_getFullDict_8` 尚未按用户提供的请求正式接入；当前词汇 AI 走 `/api/word-context`。
- 旧 UI 文件仍物理保留用于兼容和行为参考；不能删除，SaaS 路由不得再使用它们。
- `frontend/src/main.jsx` 仍包含部分已停用的旧 React 内联组件，后续可在不改变行为的前提下清理。

## 任务索引

| 当前工作内容 | 必读任务文档 |
|---|---|
| 品牌图标、网站图标导出 | `tasks/brand-assets/HANDOFF.md` |
| PC 页面、路由、分页、工作台视觉 | `tasks/pc-workspace/HANDOFF.md` |
| PC 商业化改版、布局配色、购买流程与验收 | `tasks/commercial-design-audit/HANDOFF.md` |
| 生词复习、练习会话、学习结算与复访闭环 | `tasks/vocabulary-review/HANDOFF.md` |
| 阅读器、媒体、字幕、快捷键、词典 | `tasks/reader/HANDOFF.md` |
| 账号、会员、数据库、API、安全 | `tasks/backend-saas/HANDOFF.md` |
| 公开官网、商品版本、折扣、云猫寄售、套餐兑换 | `tasks/public-commerce/HANDOFF.md` |
| 文件/YouTube 导入、任务进度、媒体处理 | `tasks/import-media/HANDOFF.md` |
| 运营后台、AI 配置、远程部署 | `tasks/platform-operations/HANDOFF.md` |
| 移动端适配与触摸交互 | `tasks/mobile/HANDOFF.md` |

如果任务跨多个领域，只读取实际涉及的几个文档。

新的独立任务使用 `TASK_TEMPLATE.md` 创建自己的 `tasks/<task-slug>/HANDOFF.md`。

## 默认验证

```bash
npm run build:modern
npm run test:modern
npm run test:ui
npm run check:js
python3 -m py_compile <本轮修改的 Python 文件>
git diff --check
```

涉及认证、写 API 或租户数据时，再运行：

```bash
./start-reader.sh --saas-smoke 8795
```
