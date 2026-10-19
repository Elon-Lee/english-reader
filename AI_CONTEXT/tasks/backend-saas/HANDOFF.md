# SaaS 后端交接

## 2026-10-19 内容管理调整

- 验证：隔离临时 PostgreSQL 的 phase3/6（排除旧页面断言）/7/8、权益并发与视频画质共 45 项通过；含真实 FFmpeg、管理员导入 HTTP 登录/CSRF/角色隔离及文件清理。构建、modern/UI/JS、Python 编译、diff 检查通过。旧 phase6 的 `/terms` 页面断言和完整 HTTP smoke 的后台 `/` 首页断言均仍因 API-only 架构返回 404，不属于本轮接口失败；未执行真实 YouTube 网络下载或浏览器人工验收。临时测试库均已删除。
- 本地已备份 `.local/backups/pre-content-management-20261019-083247.dump`，应用 `0037_private_import_ownership.sql`：3 本历史个人导入恢复私人，删除官方登记及收藏关联，保留所有者正文/媒体/学习数据；迁移可重复执行，官方导入不受影响。本地 8790 已重启、5173 API 代理健康；未发布生产。
- 2026-10-19 新增管理员官方导入 `/api/admin/content-imports`（沿用 create/upload/complete/retry/cancel/list/delete-invalid 任务协议），所有写请求保留 CSRF，服务端校验 admin 与任务归属。官方媒体允许管理员导入暂存，完成后绑定 draft catalog；官方导入不计私人字节及音视频收藏名额。私人书架、学习访问与 AI 私人查询排除已登记官方源，避免管理员绕过发布状态。
- 管理员 GET `/api/admin/media-assets` 返回 `{users,total}`；带 `ownerId` 返回 `{videos,total}`，支持 limit/offset，大小包含原文件和衍生文件。POST `/api/admin/catalog/delete` 要求 sourceBookId+准确 confirmTitle，事务删除官方正文/收藏并标记媒体，提交后清理文件；私人书架永久删除同样清理媒体。返回 removedFiles/pendingFiles，文件失败会保留待清理标记。直接 DELETE `/api/media/{id}` 返回 409，要求使用读物永久删除入口。


## 当前架构

- 主服务：`tools/reader_server.py`。
- PostgreSQL 服务模块：`tools/saas_auth.py`、`saas_membership.py`、`saas_catalog.py`、`saas_workspace.py`、`saas_imports.py`、`saas_ai.py`、`saas_admin.py` 等。
- 当前新增 migration：`0037_private_import_ownership.sql`（个人导入归属纠正，已应用本地）；此前 `0036_youtube_channel_series.sql`，回填 YouTube 历史默认系列为频道并同步书城默认分组，保留手工系列；2026-10-19 已应用本地正式库，启动 SaaS 后台及 Vite 代理健康检查通过。迁移前备份：`.local/backups/pre-local-start-20261019-065355.dump`。生产仍为 `0034`，尚未发布生产。
- 认证使用数据库会话 Cookie 和 CSRF；所有写接口必须校验 CSRF。
- 2026-10-18 修复已有会话缺失/失配 `shiyue_csrf` 时写 API 持续 403：认证读取会轮换当前 session 并补发配对 CSRF Cookie，使缺失 Cookie 同时撤销旧 session；前端收到一次 `csrf_failed` 后自动刷新认证并重试一次，写接口仍强制校验 CSRF。新增回归覆盖旧 session 失效、Cookie 恢复和后续安全登出；隔离 PostgreSQL 测试库当前未配置，尚未执行数据库集成测试。
- 测试库名称必须以 `_test` 结尾。
- 京东云生产运行 PostgreSQL 16 Bookworm、Redis 7 Bookworm 和 `shiyue-saas-runtime:20261012-1`；数据库和 Redis 端口仅绑定 `127.0.0.1`，应用通过 host network 访问。

## 已完成

- 2026-10-19 新增管理员部署历史删除 `/api/deployment/jobs/delete-invalid`，删除失败/取消状态并记录审计，审计失败回滚删除。部署及平台配置 API 限本地模式（`SHIYUE_DEPLOYMENT_MODE=local`）登录管理员、本机连接；后台默认 remote，远程部署容器明确 remote，本地启动脚本设 local。`/api/auth/me` 返回 `user.canManagePlatform` 供菜单和直接页面鉴权；写入仍校验 CSRF。32 项部署回归覆盖角色、模式、CSRF、审计失败及重复删除，本地已加载，未发布生产。无需数据库迁移。

- 2026-10-19 导入历史操作改为“删除无效任务”，范围为当前账号 `failed` + `cancelled` 记录；前端按 `invalidCount` 启用按钮，确认与成功提示同步更新。POST 改为 `/api/workspace/imports/delete-invalid`，保留登录/CSRF/用户隔离与重复删除安全；有效任务和源媒体不删除。构建、modern/UI/JS、Python 编译、diff 检查与 phase8 的 11 项隔离库集成测试通过（含仅取消记录、混合状态、重复删除及 HTTP 鉴权）。本地后台已重启加载，未发布生产。

- 2026-10-18 书城视频封面优先使用源书的首帧，私人书目补返 `coverUrl`。已发布书城封面通过既有 `trialBook` 图片鉴权路由供未收藏用户读取，不扩大正文或原视频权限。新增当前用户失败导入记录批量删除 POST `/api/workspace/imports/delete-invalid`，GET 导入历史支持服务端分页；鉴权、CSRF、跨用户隔离、重复删除及图片试读访问已由隔离库真实 HTTP 回归覆盖。实现及验证详情见 import-media 和 pc-workspace。

- 2026-10-18 视频画质鉴权：以当前有效且已开始的非免费订阅判定高清资格，过期立即失效；私人/官方原视频、其他视频变体和官方试读原件均在媒体服务端返回 403，免费账号仅可获取 low 视频变体，音频/图片/文档仍按原权限访问。阅读接口和会员接口返回 canWatchHdVideo，公开商品按等级展示画质权益；不改写历史套餐版本或新增迁移。phase6 媒体直链 HTTP、phase7 试读、phase8 私人视频和 commerce 商品共 4 项隔离库回归通过；本地后台已重启，生产未发布。
- 2026-10-18 上传内容必须目标站审核：打包及接收端将新/变更书目设为 draft，移除本地审核人和发布时间；未变更重传保留线上审核。审核来源 API 返回书目实际标题、作者、简介、系列、等级、标签与排序，避免再次审核覆盖已编辑信息。沿用管理员/CSRF/审计校验，未新增接口与迁移。临时 PostgreSQL 的 phase3 + 内容上传共 13 项通过；后台已重启，尚未发布线上。详情见 platform-operations。
- 2026-10-18 修复 `CatalogService.add_or_unlock` 对已有收藏忽略 `shelf_state` 的问题：支持既有 `active/later` 状态双向更新，并返回 `shelfState`；更新仅作用于当前用户的收藏，保持鉴权、锁和容量检查，不新增迁移。phase3 归档/恢复/重复请求/阅读权限/用户隔离回归已在临时 PostgreSQL 通过。本地后台已加载，尚未发布生产。
- 2026-10-18 官方读物统一以 `user_library` 为收藏和访问事实来源：加入即能阅读，移出即撤销正文、原媒体、AI、进度/词汇写入和完成奖励访问，保留学习数据。历史 `official_book_unlocks` 不再授权；兼容字段 `unlocked` 仅等于 `inLibrary`，旧 `/unlock` 入口等价加入书架，不再产生独立记录。重复移出成功返回。
- 官方收藏和私人音视频导入最终入库共用用户行锁、合并数量检查；重新加入也必须通过当前套餐限制。YouTube 计入视频，归档/稍后收藏仍占容量；不自动删除既有超限内容，超限期间禁止新增。
- 权益并发修复：兑换先锁用户再查幂等记录；人工订阅/邀请码发放同事务保存回执并拒绝同键异参；订阅修改先锁用户再锁订阅、接受相同到期日重试，并支持显式幂等回执；管理端同一在途写请求合并，失败重试保留请求键。未带键的旧人工订阅/邀请码发放按请求内容生成兼容键。
- AI 同一内容使用 PostgreSQL 事务 advisory lock 合并生成，避免重复上游调用及一个失败请求释放另一请求的预占；成长值按奖励接收者锁定并严格限制月上限，邀请领取支持幂等键；奖励 AI 额度补发写入实际每日账期。媒体变体/删除、导入任务、旧支付回调统一相关锁顺序；Paddle/面包多重复通知及同用户续费并发不重复发放、不丢失天数。
- 商品版本创建按商品锁串行编号，发布也先锁商品再锁版本，确保同商品并发发布最终只有一个 published 版本，重复发布当前版本幂等。
- 新增 `tools/test_entitlement_concurrency.py`：真实 PostgreSQL 的 13 组并发回归（每组最多 12 请求），覆盖书架/旧解锁绕过、音视频合计、官方与私人争抢最后名额、额度结算释放、人工权益、邀请码、成长值与奖励、兑换码、上传/导入取消、存储、AI、旧支付回调及套餐版本创建/发布。阶段 1–9、commerce、支付回归通过；独立临时库 HTTP smoke 29 项、前端构建/modern/UI/JS、Python 编译及 diff 检查通过。本地服务 8790 已重启并健康。

- 2026-10-18 按用户明确要求清除生产 `liyuntaogege@gmail.com` 的所有付费套餐信息并恢复 `free-v2`：删除 2 个订阅、1 个人工订单、1 个变更申请、5337 条用量账本、82 个预占和 2 个旧账期；保留管理员角色、账号会话、4 本私人内容、3 条书架/解锁记录、生词及学习记录。解锁记录账期关联转至免费账期以保留阅读权限。写入 `admin_audit_logs` 的 `membership_reset_to_free`；备份 `/srv/shiyue/backups/saas/pre-upgrade-account-membership-reset-20261018-0818.dump`。重新查询订阅为空、订单为 0、免费视频 4/2 和音频 1/5（现有书籍保留，超限后不能继续新增视频）。
- 2026-10-18 会员权益修复已发布 `code-20261018-081452-67a2d629`（任务 #24389 complete）：迁移 `0034` 为旧进阶补视频 20/音频 50、旧 Pro 补视频 100/音频 200，同时补齐已有非 AI 日账期缺失字段；保留明确额度（含 0）、原空间权益、用量和到期时间。发布后生产核验旧 Pro 视频 4/100、音频 1/200、空间 100 GB；随后该账号按用户要求恢复免费。验证：phase 2 10 项、commerce 12 项、phase 9 4 项、部署 26 项、HTTP smoke 29 项，前端构建/检查、Python 编译、diff 检查通过。
- 2026-10-17 按用户请求，通过生产 `AdminService.revoke_device` 清理指定账号的 1 个有效设备及其 1 个有效会话，保留历史并写管理员审计；执行后有效设备/会话均为 0，账号保持已验证、正常状态。本轮无业务代码或套餐变更。
- 2026-10-17 默认进阶月卡等级修正为 1（Pro 为 2）。云猫首批进阶/Pro 各 20 个库存码哈希已安全同步至生产，两环境购买链接已回填并审计；实际支付及发码待本人购买验收。详见 public-commerce 交接。
- 2026-10-17 增加会员变更闭环：`membership_change_orders` 记录首次开通/续费/升级/降级、状态、生效时间、结转天数和兑换来源；`membership_events` 记录变更事件。`/api/membership/change-preview` 提供变更预览，`/api/membership/change-orders` 查询记录，DELETE `/api/membership/change-orders/:id` 取消未生效排期；兑换支持幂等键并返回 `changeOrder`。现有 `subscriptions` 继续作为权益事实来源。
- 2026-10-17 会员规则收紧：只允许同等级续费或向更高等级升级，低等级卡密直接返回 `membership_downgrade_not_allowed` 且不核销。进阶升级 Pro 时按剩余权益价值折算：剩余进阶时长 × 19/49，向上取整到小时，再叠加新购 30 天；`0033` 增加 `carry_seconds` 保留小时精度。
- 2026-10-17 续费流程去排期：同级兑换直接延长当前订阅 `ends_at`，订单立即 `applied`；升级同样立即生效并将折算时长加到 Pro 到期日。新兑换不再创建未来开始订阅，会员页不再显示未来排期区块。旧排期在下一次有效兑换时并入当前订阅或被升级替换。
- 2026-10-16 migration `0025`–`0029` 已应用本地正式库和隔离测试库。Free/进阶/Pro 三档默认商品已发布；付费卡暂缺云猫链接，前台禁用购买。原价、折扣和折后价按版本存储。
- 公版/授权材料解锁不再按次数扣减；视频/音频导入不扣月次数额度。兑换码以 SHA-256 哈希持久化，管理员生成批次明文只返回一次；兑换接口要求已验证用户、会话和 CSRF，支持同人幂等、升级结转及订单记录。

- 邀请注册、邮箱验证、登录、密码重置、设备撤销和管理员隔离。
- 套餐、订阅、账期、额度预占/结算/释放、人工订单和套餐变更申请。
- 官方书城、私人工作区、奖励、媒体鉴权、账户导出/注销。
- 完整阅读偏好保存。
- 邀请码支持后台自动生成、批量生成、查询和分页。
- AI 平台配置保存在 PostgreSQL `platform_settings`，不再依赖环境变量。
- 2026-10-12 已将旧版本地有效 Dioco 凭据通过 `AdminService.update_platform_config` 迁入 PostgreSQL，并留下管理员审计记录；连通性测试成功，未在日志或文档中记录完整 Token。
- `/api/auth/devices` 现在把设备时间转换为 ISO 字符串并返回前端使用的 camelCase 字段，修复系统设置页因 PostgreSQL datetime 无法 JSON 序列化而加载失败的问题。
- 生词服务支持当前书架的官方读物：API 接收 catalog book ID，校验当前用户的 `user_library`，以源 `content_book_id` 安全存储，并对前端继续返回 catalog book ID；移出后不能继续读写该词汇记录。
- 新增鉴权与 CSRF 保护的 `/api/workspace/progress`，只更新最近句子；私人和已解锁官方读物都经过租户/解锁校验，不写活动事件、不累计学习时长或奖励。官方阅读接口会返回映射后的 `progress`。
- 生产根路径 `/` 已直接启用 React SaaS；健康接口同时校验 Redis。首次远程数据库从本地正式库恢复后，只保留合法已公开书籍的内容/媒体数据，并保留账号、订阅和平台配置。
- 2026-10-12 已完成 Resend 生产邮件配置：验证发送子域名 `auth.10ye.cc`，Cloudflare DNS 已配置 DKIM、SPF/Return-Path CNAME 和 DMARC；本地 `.env` 与京东云 `/srv/shiyue/shared/config/saas.env` 均使用受限于该域名的 Resend SMTP 密钥。京东云和本地均已向 Resend 官方测试地址真实发送成功，生产容器已重建并通过健康检查。密钥未写入代码、Git、日志或交接文档。
- 2026-10-12 已完成认证邮件流程加固并部署生产：`/verify-email` 与 `/reset-password` 直接返回 React 入口，重置页可提交新密码，激活页自动验证 token；注册和找回邮件发送成功后前端切回登录。未激活邮箱登录返回 `email_unverified`。每个邀请码最多产生 3 封激活邮件；同一账号连续申请 3 封重置邮件后停止继续发送，成功重置会清零计数。入口 JS/CSS 带构建版本查询参数，避免固定文件名的旧缓存继续加载过时认证页面。生产发布为 `code-20261012-235032-6d5d0c1a`。
- 2026-10-13 本地修复管理员用户详情查询：人工订单表字段应为 `plan_version_id`，此前错误查询 `plan_version` 会令存在人工订单的用户详情返回失败。阶段 5 测试和隔离浏览器验收均通过；未部署远程。
- 2026-10-13 套餐版本改为从服务器权益注册表创建：内置权益只包含 9 个现有运行时真实受控功能；运营勾选并设置限制后，后台自动创建独立不可变 `plan_version`，发布时激活。存储 GB 转换为字节，AI/导入/解锁/书架/设备限制继续由现有运行时校验。配置权益另存为版本快照，只用于展示，不进入额度账本。
- 2026-10-13 邀请码改为批次模型：每次创建只产生一条批次摘要，详情查看单码和注册邮箱；未使用且未关联会员邀请奖励的邀请码可批量删除，已使用邀请码由服务端拒绝删除并记录管理员审计。

## 未完成

- 云猫上架、商品链接、库存上传及生产升级已完成；真实付款、发码及账号兑换仍需商户本人做一笔购买验收。
- 100～500 用户的并发和容量压测。
- AI Token 数据库字段目前是普通 JSONB；如进入生产，应评估应用层加密或外部密钥管理。

## 安全原则

- 不输出 `.env`、Token、密码或 `.dioco.local.json`。
- 管理员写操作要写审计日志。
- 不允许 SaaS API 回退到旧 SQLite 学习数据。
- 新接口必须验证 tenant owner 或 admin 权限。

## 官方试读 API（2026-10-18，本地未发布）

- `GET /api/catalog/books/{id}/reader?trial=1` 保留已验证账号检查，返回前 10% 内容及 `trialPercent/trialEndSeconds/trialLimit`；普通 reader 仍要求当前书架记录。
- 试读媒体 `/api/media/{assetId}?trialBook={catalogId}`（可带 variant）校验账号、发布/授权状态和资产关联，只输出裁剪原媒体，不放开完整资产权限；PDF 不支持试读全文。片段在 `.local/trial-clips` 缓存，依赖 ffmpeg。
- 隔离库 phase3 与 phase7 已覆盖未收藏试读、完整阅读拒绝、10% 时间边界、原视频裁剪、错书与下架拒绝。

## 关键验证

```bash
./start-reader.sh --saas-smoke 8795
SHIYUE_SAAS_TEST_DATABASE_URL=... .local/saas-venv/bin/python tools/test_entitlement_concurrency.py
python3 -m py_compile tools/reader_server.py tools/saas_*.py
python3 tools/test_paddle_billing.py
SHIYUE_SAAS_TEST_DATABASE_URL=... .local/saas-venv/bin/python tools/test_saas_billing_integration.py
```

- 集成测试会清空隔离库的用户和关联商品。HTTP smoke 需要包含已发布默认商品与已验证 `ai-owner@local.test` 的独立测试库；不要把阶段测试结束后的残留库误当作 smoke 固定夹具。正式库和销售兑换码禁止用于测试。
