# 拾页 SaaS 商业化分阶段实施计划

最后更新：2026-10-09。此文档是本地实施记录；所有阶段先在本机验收，未经单独指令不部署远程服务器。

## 首发目标与边界

把现有单用户点读系统改造成面向 100～500 名邀请用户的多租户 SaaS，首发仍采用单体架构：邀请码注册、邮箱验证、邮箱密码登录；默认免费版；付费套餐由后台人工开通；SaaS 业务数据以 PostgreSQL 为正式来源；媒体首版保存在服务器文件系统并经鉴权接口访问。

现有 39 本内容默认归属管理员私人资源，逐本审核后方可进入官方书城。部署节点、SSH 密码与本机运维任务继续留在独立本机运维库，不进入 SaaS 用户库。YouTube 导入默认是用户私人内容，不自动进入书城。首发不做家庭、学校或团队工作空间，不接支付 Webhook、OSS、CDN、Redis 或独立 Worker。

## 默认套餐和计量规则

| 权益 | 免费版 | 进阶版 | Pro版 |
| --- | ---: | ---: | ---: |
| 官方书架容量 | 5 本 | 30 本 | 100 本 |
| 官方读物月度解锁 | 2 本 | 12 本 | 40 本 |
| AI 语境精讲 | 20 次 | 300 次 | 1500 次 |
| 智能句法分析 | 10 次 | 100 次 | 500 次 |
| MP3 智能导入 | 1 次 | 5 次 | 20 次 |
| 本地视频智能导入 | 1 次 | 3 次 | 10 次 |
| YouTube 学习内容导入 | 1 次 | 5 次 | 20 次 |
| 私人学习空间 | 1 GB | 20 GB | 100 GB |
| 同时登录设备 | 1 台 | 2 台 | 5 台 |
| 任务优先级 | 标准 | 优先 | 高优先级 |

参考价格：进阶版 ¥39/月、¥299/年；Pro版 ¥79/月、¥599/年。创始会员可设置优惠价，但不改变套餐版本。

官方读物仅首次解锁计数；同一账期删除后重新收藏同书不重复计数。AI 语境和句法仅对用户首次查看某个内容计数，缓存重复查看不计数。失败、取消的 AI 或导入任务归还预占额度。免费版每 30 天重置，付费版按订阅账期重置。导入采用“预占—成功结算—失败释放”；空间按原始文件和生成资源实际字节数计量。官方共享资源、生词、备注和学习记录不占私人空间。权益一律以不可变 `plan_version` 保存；调整时创建 `free-v2`、`advanced-v2` 等新版本。

## 阶段与验收

### 阶段 0：文档、备份和开发基线

创建实施文档，记录 SQLite、39 本资源、媒体量和环境；备份 SQLite、配置与媒体清单；保留脏工作区；添加 SaaS 功能开关和以下环境变量：`DATABASE_URL`、`SESSION_SECRET`、`APP_BASE_URL`、`SMTP_HOST/PORT/USER/PASSWORD`、`SMTP_FROM`、`BOOTSTRAP_ADMIN_EMAIL`、`MEDIA_ROOT`。功能未完成时保留单用户模式。

验收：原书架、阅读、导入、复习和部署功能的回归测试继续可运行。

### 阶段 1：PostgreSQL、账号和邀请注册

核心表为 `users`、`user_sessions`、`email_verifications`、`password_reset_tokens`、`invitations`、`invitation_uses`、`devices`、`roles`。邀请码是注册必填项，密码使用带盐 `scrypt` 哈希；注册默认 `free-v1`；邮箱验证后方可导入、收藏和使用 AI。会话使用高熵随机令牌且数据库仅存哈希；Cookie 使用 `HttpOnly`、`SameSite=Lax`，HTTPS 时 `Secure`；修改接口使用 CSRF 校验。支持登录、退出、验证、忘记与重置密码、设备查看与下线；超过设备上限提示用户移除旧设备，不静默踢出。

接口：`POST /api/auth/register`、`POST /api/auth/verify-email`、`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`、`POST /api/auth/forgot-password`、`POST /api/auth/reset-password`、`GET /api/auth/devices`、`DELETE /api/auth/devices/{id}`。

迁移时创建管理员，现有私人书籍、生词、备注与学习记录归管理员，旧 SQLite 作为只读备份保留。未登录 API 请求除认证、验证及未来公开书城外统一返回 401；部署管理仅管理员且服务器本机可用。验收覆盖无邀请码、失效/停用/超次邀请码、邀请码并发、未验证用户限制、跨用户隔离及管理员数据完整迁移。

### 阶段 2：套餐、订阅、额度和会员中心

建立 `plans`、`plan_versions`、`subscriptions`、`usage_periods`、`usage_ledger`、`quota_reservations`、`manual_orders`、`assets`。订阅状态为 `active`、`grace_period`、`expired`、`suspended`。管理员人工创建订单、选择套餐及起止日期和备注；立即生成账期额度；到期回退免费版；保留审计。统一权益键为 `official_library_capacity`、`official_unlocks`、`ai_context_generations`、`ai_grammar_generations`、`mp3_imports`、`video_imports`、`youtube_imports`、`storage_bytes`、`devices`。

接口：`GET /api/membership`、`GET /api/membership/usage`、`GET /api/membership/orders`、`POST /api/admin/subscriptions`、`POST /api/admin/manual-orders`。所有付费动作经统一权益服务；超额返回 `quota_exceeded`，含 feature、plan、used、limit、resetAt 与 recommendedPlan。会员中心展示套餐、有效期、八项额度、空间、重置时间、成长值、邀请码、订单与升级入口。并发不能超扣，重复任务只能预占一次，失败/取消归还，AI 缓存不重扣，到期回退且不影响既有内容阅读。

### 阶段 3：首页书城、详情页和我的书架

菜单改为：首页·书城、我的书架、学习记录、生词复习、导入内容、会员中心、系统设置；普通用户不显示部署管理。建立 `catalog_series`、`catalog_books`、`catalog_tags`、`catalog_book_tags`、`user_library`、`official_book_unlocks`。旧书均以管理员 `private` 导入，管理员逐本标记公版、已授权、私人或禁止上架；仅公版/已授权可发布，官方媒体只存一份。

书城支持中文/英文标题、作者、书系、标签搜索与筛选，展示继续阅读、本周推荐、最近上新、热门读物、按书系和难度浏览（首期采用后台规则排序）。详情展示封面、双语标题、作者、简介、书系/标签/等级、时长、句子数、词数和支持功能；第一次阅读前提示会消耗解锁。接口：`GET /api/catalog`、`GET /api/catalog/series`、`GET /api/catalog/tags`、`GET /api/catalog/books/{id}`、`POST /api/catalog/books/{id}/unlock`、`POST /api/library/items`、`DELETE /api/library/items/{id}`、`GET /api/library`。书系频道仅统计当前用户书架：全部、收藏官方书系、私人导入、MP3、视频、YouTube、稍后阅读。

### 阶段 4：签到、成长值和会员邀请

建立 `checkins`、`reward_ledger`、`reward_catalog`、`reward_redemptions`、`member_invites`、`member_invite_rewards`。成长值：每日签到 +1；当日阅读 10 分钟且点读 5 句 +2；连续 3/7/14/30 天额外 +2/+5/+10/+20；每日完成生词复习最多 +2；完成官方书 +10；受邀用户首次有效学习 +10、首次付费 +30；月上限默认 100。兑换：20 成长值换 10 次语境、30 换 5 次句法、80 换 1 次解锁、150 换 1 次 MP3 导入、20 换补签卡。

接口：`GET /api/rewards/status`、`POST /api/checkins`、`GET /api/rewards/catalog`、`POST /api/rewards/redeem`、`GET /api/rewards/ledger`。免费用户没有邀请名额；进阶/Pro 由后台或活动发放。奖励在受邀用户首次有效学习与首次付费后发放，并以设备、邮箱、支付账号和异常 IP 防套利。需验证幂等签到、时区一致的连续日、补签、原子兑换、邀请奖励不重复。

### 阶段 5：管理后台和商用运营

后台包含用户/设备、邀请码/渠道、套餐版本/人工订单、额度/明细、书城审核标签上下架、空间/大文件、导入任务失败率、成长值兑换、管理审计。管理员可开通、延期、暂停套餐，补发/扣减额度，创建渠道邀请码，审核官方资源，查看用量但不能读密码，封禁账号并记录原因，导出经营数据。普通设置仍保存阅读快捷键、护眼、听写与词提示。Dioco 令牌改为平台管理员配置，普通用户不可见。

### 阶段 6：媒体鉴权、存储核算和安全收尾

建立 `media_assets`、`asset_variants`、`asset_usage`，记录所有者、官方/私人类型、类型、原始/生成大小、SHA-256、路径、引用和创建/删除时间。可猜测 `/books/...` 路径逐步改为 `GET /api/media/{asset_id}`；后端验证所有者或已解锁官方内容，支持音视频 Range，阻断路径穿越，按引用关系删除，官方媒体不重复计入空间。

补齐登录/注册/邀请码/AI 限流、安全响应头、CSRF、用户导出、延迟注销、失败任务清理、数据库备份、媒体清单与恢复演练，以及协议、隐私、上传声明、退款、版权投诉入口。

## 迁移、兼容与总体验收

现有阅读、音视频同步、CTC 高亮、词典、语境、句法、生词、听写和部署必须保持可用；管理员数据与改造前一致；成品媒体不重新生成；39 本书不默认公开；`library.sqlite3` 在 PostgreSQL 验证成功前不得删除。导入 Worker 要携带 `user_id`、`workspace_id`、套餐版本和额度预占，避免任务运行中套餐变化错账。所有表使用外键、唯一约束和事务，不依赖前端防重。

每阶段独立覆盖邀请/邮箱/设备、租户隔离、三档套餐、AI 缓存和退款、三类导入预占、空间、官方解锁/收藏、书城搜索、签到/奖励/邀请、人工订阅、Range 鉴权、迁移计数与路径一致、桌面与移动主流程，以及 100～500 用户并发登录、浏览、阅读和任务排队。完成一阶段后记录状态、迁移结果、测试和未解决项，本机验收后才进入下一阶段。

## 实施状态与迁移记录

### 阶段 0 — 已完成（2026-10-09）

- 创建本实施文档、[`.env.example`](.env.example) 和可关闭的 `SHIYUE_SAAS_ENABLED` 基线。
- 生成不可覆盖的本地备份：`.local/saas-baselines/20261009T230110/`。其中包含 SQLite 一致性备份、配置快照、启动脚本、SQLite schema/计数、SHA-256 清单和 5,261 条媒体路径/字节/mtime 记录。
- 基线统计：SQLite `books=39`（34 本书、2 个音频、3 个 YouTube）、`vocabulary=4`、`word_annotations=5`、`sentence_grammar=16,193`、`learning_daily=11`；媒体目录约 12GB，SQLite 约 144MB。
- 未修改或删除 `.local/library.sqlite3`、原始媒体、部署配置或当前工作区内容。

验收：备份目录已生成，SQLite 可读，基线统计与项目记录的 39 本读物相符。

回归记录：`tools/test_reader_performance.py`（2 项）和 `tools/test_mobile_reader_presentation.py`（7 项）通过；本机服务 smoke test 通过，健康接口及 39 本旧书架均可读取。`tools/test_remote_reader_presentation.py` 有 1 个既有断言失败：测试查找精确字符串 `class="runtime-pending"`，而当前 HEAD 的 `reader/index.html` 原本就是 `class="runtime-pending screen-shelf"`；本次未修改该 HTML 或该测试，故未将无关断言改写为本阶段变更。

### 阶段 1 — 已完成（2026-10-10）

- 安装 PostgreSQL 16 与项目私有 `.local/saas-venv`（`psycopg 3.3.6`）；未启用 Homebrew 默认数据库服务。测试集群为 `.local/postgres-phase1/data`，仅监听 `127.0.0.1:55432`。
- 实际应用 `0001_accounts.sql` 并建立本机正式迁移库 `shiyue_saas_local`。管理员以原有本机配置邮箱创建且已验证；迁移结果为：39 本书、4 条生词、5 条标注、11 天学习记录、16,193 条句法数据。全部内容以管理员所有、`visibility=private` 写入 PostgreSQL；原 SQLite 保持完整、未被修改或删除。
- 新增认证接口和控制：邀请码必填、过期/停用/耗尽拒绝、`scrypt` 密码哈希、哈希会话令牌、HttpOnly + SameSite=Lax Cookie、CSRF、忘记/重置密码、设备查看/下线和套餐设备上限。服务启用时要求迁移成功、`DATABASE_URL` 及至少 32 字符的 `SESSION_SECRET`。
- SaaS 标志启用时，尚未改造的旧 SQLite 内容接口会明确返回 `saas_content_migration_pending`；它们不会以“已登录即可访问”的方式暴露管理员的旧书籍、学习记录或媒体。因此 `.env` 仍保留 `SHIYUE_SAAS_ENABLED=0`，阶段 3 的书城/多租户内容适配完成前不对实际读者开启该开关。
- 验收通过：`tools/test_saas_phase1.py` 3 项、`tools/test_saas_phase1_integration.py` 7 项（真实 PostgreSQL migration、管理员、邀请码并发、失效邀请码、验证、Cookie/CSRF、设备上限、登出、用户和管理员密码重置、SQLite 导入和 HTTP 内容隔离）、原性能测试 2 项、移动端展示测试 7 项、旧模式 39 本书架 smoke test，以及真实管理员 SaaS HTTP 登录 smoke test。
- 未接入 SMTP 服务器：代码会在 SMTP 配置就绪后发送验证与重置邮件；当前验收使用直接生成的令牌验证其数据库与失效逻辑。未部署远程服务器。

### 阶段 2 — 核心权益层已完成（2026-10-10）

- 实际应用 `0002_membership.sql` 到本机正式 PostgreSQL 库。新增 `plans`、`plan_versions`、`subscriptions`、`usage_periods`、`usage_ledger`、`quota_reservations`、`manual_orders`、`assets` 与 `membership_audit`。预置 `free-v1`、`advanced-v1`、`pro-v1`，含计划中全部 9 项额度、30 天免费账期和进阶/Pro 的月付、年付参考价。
- 实现统一权益服务：账期额度快照、用户锁串行化、同幂等键只预占一次、成功结算、失败/取消释放、额度补发、订单/订阅审计、暂停/恢复/延期、到期标记 `expired` 并回退免费版。设备上限会在登录时读取有效套餐版本，不依赖旧的静态版本判断。
- 新增会员 API：`GET /api/membership`、`GET /api/membership/usage`、`GET /api/membership/orders`；管理员通过 CSRF 保护的 `POST /api/admin/manual-orders` 与 `POST /api/admin/subscriptions` 创建、暂停、恢复或延期人工订阅。非管理员返回 `admin_required`。
- 新增会员前端：SaaS 启用时提供登录、邀请码注册、找回密码、当前套餐、重置时间、9 项额度、空间、订单与退出登录界面；默认单用户模式不显示这些界面，也不改变原书架。
- 验收通过：`tools/test_saas_phase2_integration.py` 7 项，覆盖免费权益快照、25 并发预占（20 次成功、5 次超额）、幂等结算、释放、补发额度幂等、人工订单、暂停/恢复/延期、套餐设备上限、到期回退、真实 Cookie/CSRF 管理员 API 和会员 API；阶段 1 集成测试 7 项仍通过。
- 重要边界：为避免旧 SQLite 管理员内容泄露，SaaS 模式的 AI、导入、书架与媒体接口仍返回 `saas_content_migration_pending`。阶段 2 已提供可供这些动作调用的预占/结算服务与测试；真正将 AI 缓存、三类导入、官方收藏/解锁绑定到用户内容工作区，需要与阶段 3 多租户书城和阶段 6 媒体鉴权一起接入，因此本机 `.env` 继续保持 `SHIYUE_SAAS_ENABLED=0`。

### 阶段 3 — 核心书城与官方书架已完成（2026-10-10）

- 实际应用 `0003_catalog.sql` 到本机正式 PostgreSQL 库。新增 `catalog_series`、`catalog_books`、`catalog_tags`、`catalog_book_tags`、`user_library` 与 `official_book_unlocks`。迁移不会自动创建书城记录：正式库当前 `catalog_books=0`、`published=0`，因此原有 39 本管理员私人资源没有被意外公开。
- 实现书城和书架服务：公开搜索（中文/英文标题、作者、书系）、书系/等级/资源类型/标签筛选、详情、有限正文预览、用户独立书架、稍后阅读状态、管理员源内容审核与版权/发布状态。只有 `public_domain` 或 `licensed` 且 `published` 的读物可见；`private`、`prohibited` 和草稿不会出现。
- 收藏容量按当前有效套餐的 `official_library_capacity` 原子计算；首次官方解锁通过 `official_unlocks` 账期账本结算。用户锁确保并发收藏不超过容量，并发解锁不超额；同一用户移除后重加或重复开始阅读同一本书不重复扣解锁。
- 新增 API：`GET /api/catalog`、`GET /api/catalog/series`、`GET /api/catalog/tags`、`GET /api/catalog/books/{id}`、`POST /api/catalog/books/{id}/unlock`、`POST /api/library/items`、`DELETE /api/library/items/{id}`、`GET /api/library`，以及管理员审核用的 `GET /api/admin/catalog/sources`、`POST /api/admin/catalog/books`。解锁用户可通过 `GET /api/catalog/books/{id}/reader` 进入 PostgreSQL 正文阅读视图。
- 新增 SaaS 前端书城、详情、我的官方书架与受解锁保护的正文阅读。首次“开始阅读并解锁”自动收藏、结算一次解锁并进入文本阅读。现阶段不加载旧 `/books/` 文件路径，音视频、原书页、封面和 Range 流媒体将在阶段 6 接入。
- 验收通过：`tools/test_saas_phase3_integration.py` 5 项，覆盖默认不公开、版权发布约束、搜索/书系/标签、用户书架隔离、6 并发收藏容量、首次解锁/删除重加不重复扣费、3 并发解锁、受解锁正文阅读和完整 HTTP Cookie/CSRF 流程。`tools/test_membership_presentation.py` 3 项验证会员/书城阅读界面存在。
- `.env` 保持 `SHIYUE_SAAS_ENABLED=0`。阶段 3 已不再用 `saas_content_migration_pending` 阻止官方书城、官方书架和正文；但私人导入、原有学习记录、生词、AI、导入任务和媒体仍需在后续阶段按用户/资产迁移，不对 SaaS 用户开放。

### 阶段 4 — 核心签到、成长值与会员邀请已完成（2026-10-10）

- 实际应用 `0004_rewards.sql`、`0005_member_invite_allowances.sql` 到本机正式 PostgreSQL 库。新增 `checkins`、`reward_ledger`、`reward_catalog`、`reward_redemptions`、`reward_daily_activity`、`reward_activity_events`、`member_invites`、`member_invite_rewards` 与 `member_invite_allowances`。正式库已预置 5 种兑换奖励；当前没有签到、邀请码额度或邀请关系。
- 实现成长值账本和月上限 100：每日签到 +1，有效阅读 +2，连续第 3/7/14/30 天额外 +2/+5/+10/+20，生词复习每天 +2，完成已解锁官方读物 +10。签到、阅读活动、复习、完成读物和账本奖励都有唯一事件键或事务锁，重复操作不会多发成长值。
- 实现奖励兑换与补签：20 点换 10 次 AI 语境、30 点换 5 次句法、80 点换官方解锁、150 点换 MP3 导入、20 点换补签卡。额度类奖励以负用量信用写入阶段 2 账期账本；补签卡在过去日期签到时原子消耗，不能重复补同一天。
- 实现会员邀请：免费用户没有资格；进阶/Pro 也必须具有后台/活动发放的 `member_invite_allowances` 才能生成邀请码，每次生成扣减一份额度。受邀用户注册后绑定邀请关系，首次有效学习和首次有效付费分别奖励邀请人 +10/+30；同设备或相同注册 IP 的关系不发奖励。支付账号和异常 IP 风控需要支付接入和运营后台数据，留待阶段 5/支付阶段补全。
- 新增奖励前端、签到、兑换、邀请状态和成长记录；官方文本阅读页面会在离开时上报阅读秒数和已点读句数，已解锁读物可手动标记完成。新增 API：`GET /api/rewards/status`、`POST /api/checkins`、`GET /api/rewards/catalog`、`POST /api/rewards/redeem`、`GET /api/rewards/ledger`、`POST /api/rewards/activity`、`POST /api/rewards/complete-book`、`POST /api/member-invites`。
- 验收通过：`tools/test_saas_phase4_integration.py` 6 项，覆盖连续签到、月度上限、补签卡、有效阅读、复习上限、兑换幂等与账期额度信用、完成读物幂等、邀请码额度消耗、首次有效学习、首次付费奖励以及完整 HTTP Cookie/CSRF 流程。阶段 1–3 集成与原单用户回归均继续通过。
- `.env` 继续保持 `SHIYUE_SAAS_ENABLED=0`，未部署远程服务。私人导入、既有 SQLite 学习记录/生词、AI 实际调用与媒体资产仍在后续阶段迁移范围内。

### 阶段 5 — 核心运营后台已完成（2026-10-10）

- 实际应用 `0006_admin_operations.sql` 到本机正式 PostgreSQL 库。新增 `admin_audit_logs`、`platform_settings`，并为 `invitations` 增加渠道字段和索引。正式库当前没有管理审计测试数据；迁移仅新增结构。
- 新增管理员运营服务和后台页面：用户/设备查询、账号封禁与恢复、渠道邀请码、人工订单和订阅管理、额度补发/扣减、邀请码额度发放、套餐版本查看与不可变新版本创建、书城源内容审核、运营审计和经营 JSON 导出。普通用户访问 `/api/admin/*` 一律返回 `admin_required`。
- 权益调整通过阶段 2 账期账本写入 `adjustment`，正数为补发、负数为扣减；封禁会撤销当前会话。封禁/恢复、额度调整、邀请码额度和人工订单均产生管理员审计记录，敏感操作要求理由。
- 平台级 Dioco 配置使用 `SHIYUE_DIOCO_TOKEN`、`SHIYUE_DIOCO_EMAIL` 环境变量；后台仅显示配置状态，不存储或返回令牌。现有 `.dioco.local.json` 保留给遗留单用户流程。部署节点、SSH 密码和本机部署任务继续不进入 SaaS 数据库。
- 验收通过：`tools/test_saas_phase5_integration.py` 5 项，覆盖运营汇总、用户列表不泄露密码、渠道邀请码、额度补发/扣减、邀请码额度、封禁撤销会话、恢复登录、套餐 `advanced-v2` 创建后旧账期快照不变、审计记录，以及普通用户后台拒绝/管理员 HTTP + CSRF 渠道邀请码流程。阶段 1–4 集成、展示测试和原单用户回归全部继续通过。
- `.env` 保持 `SHIYUE_SAAS_ENABLED=0`，未部署远程服务。多租户私人导入、媒体资产和 Range 鉴权仍由阶段 6 完成。

### 阶段 6 — 核心媒体鉴权、安全与恢复已完成（2026-10-10）

- 实际应用 `0007_security_media_accounts.sql`、`0008_bootstrap_admin_subscription.sql`、`0009_restore_bootstrap_admin_pro.sql` 到本机正式 PostgreSQL 库。新增媒体资产、变体、使用、账号注销请求和安全事件结构；恢复原本机管理员迁移前预期的 Pro 订阅，避免既有私人媒体因免费空间额度被拒绝。
- 现有 `books/` 已完成只读资产登记：5,286 个管理员私人媒体资产，合计 `13,030,194,330` 字节；每个登记项有相对存储路径、SHA-256、字节数和可选内容书关联。资产总字节数与 `storage_bytes` 账期账本完全一致；没有移动、重生成、删除或公开任何原始媒体。
- 实现 `GET /api/media/{asset_id}`（含 `?variant=`）和 `DELETE /api/media/{asset_id}`。私有媒体仅所有者可访问；官方媒体要求已发布、版权合规且用户已解锁。支持单 Range 请求；SaaS 模式继续阻断旧 `/books/...` 可猜测路径。逻辑删除释放私人空间，物理清理由 `MEDIA.purge_deleted` 先 dry run 后移入 `.local/media-trash`。
- 增加用户数据导出、注销请求/撤销和 30 天延迟删除；到期后会撤销设备/会话、匿名化账号、屏蔽私人内容并逻辑删除私人资产。增加安全响应头、CSP、登录/注册/找回密码/签到/AI 接口内存限流，以及用户协议、隐私政策、上传声明、退款规则和版权投诉页面。
- 新增 `saas_backup.py`、`saas_backup_verify.py`、`saas_restore_drill.py` 与 launchd 备份示例。首次备份位于 `.local/saas-backups/20261010T035159Z`，包含 custom PostgreSQL dump、5,286 文件 SHA-256 清单与元数据。全量清单校验通过；实际恢复演练已恢复至可销毁数据库 `shiyue_restore_test`，结果为 9 个 migration、1 个用户、5,286 个媒体资产。
- 验收通过：`tools/test_saas_phase6_integration.py` 5 项，覆盖私有媒体空间/越权/删除释放、官方解锁媒体、Range、路径穿越、变体、清理 dry run/移入回收区、数据导出、注销/撤销/到期清理、安全头、限流、法律页和备份清单。阶段 1–5 集成、展示测试和原单用户 39 本书架回归在最终验证中继续运行。
- 未部署远程服务。`.env` 仍为 `SHIYUE_SAAS_ENABLED=0`，因此现有单用户阅读不会切换到 SaaS；正式上线前仍需设置 SMTP、平台级 AI 环境变量、外部备份位置并完成一次人工运营和媒体恢复演练复核。

### 阶段 7 — 私人学习空间补充阶段已完成（2026-10-10）

- 在既定阶段 0–6 完成后补充 `0010_private_workspace.sql`，新增 `workspace_progress`、`workspace_settings`、`workspace_activity_events`，并为迁移生词记录补充 PostgreSQL sequence 默认值。该阶段解决“原管理员的既有私人内容只能作为迁移落地区、不能在 SaaS 访问”的缺口。
- 新增按 `owner_id` 强制隔离的私人工作区 API：私人读物列表/正文、关联受鉴权媒体、生词、标注、学习日和活动记录。未所有者访问返回 `workspace_book_not_found`；正文不返回旧 `/books/...` 可猜测路径，媒体继续使用阶段 6 的 `/api/media/{asset_id}`。
- 私人工作区活动会写入 PostgreSQL `content_learning_daily` 与 `workspace_progress`，并调用阶段 4 有效阅读奖励逻辑。当前管理员的 39 本迁移私人读物和 2,791 个按内容路径关联的私有媒体已可在工作区访问；其余私人资产仍可按所有者通过资产 API 使用。
- 新增 SaaS “私人学习空间”及文本阅读界面。普通邀请用户默认看到空空间；旧 SQLite 导入 Worker 不会被直接开放给他们，后续需要建设 PostgreSQL 原生导入任务/队列。
- 验收通过：`tools/test_saas_phase7_integration.py` 2 项，覆盖私人读物/媒体隔离、生词和标注保存、学习日、活动幂等、HTTP Cookie/CSRF、受鉴权 Range 媒体及有效阅读成长值。正式 SaaS smoke 确认管理员工作区包含 39 本私人读物且正文和关联媒体可读取。
- 生成并完整验证最新备份 `.local/saas-backups/20261010T042945Z`，包含阶段 7 schema dump、5,286 文件清单及 SHA-256。未部署远程服务，`.env` 继续保持 `SHIYUE_SAAS_ENABLED=0`。

### 阶段 8 — PostgreSQL 原生私人导入任务初版已完成（2026-10-10）

- 新增 `0011_workspace_imports.sql` 与 `workspace_import_tasks`。任务在创建时保存 `user_id`、工作区、导入类型、套餐版本、额度预占、源资产、输出读物、进度、错误和幂等键；取消/失败会释放导入额度预占，取消后也会逻辑删除私人源资产并释放空间。
- 实现无旧 SQLite 依赖的 TXT/Markdown/PDF/MP3 私人导入：上传前空间预检、受鉴权源资产登记、文本/音频分句、创建 PostgreSQL 私人读物、关联源资产并完成任务。PDF 通过本机 `pdf_ocr` 在隔离临时目录提取文本；MP3 通过本机 `whisper-cli + base.en` 生成词级时间戳和动态分句；两者均不把处理结果写回旧 SQLite。用户可在“私人学习空间”直接上传并得到可阅读的私人读物。
- 视频和 YouTube 保留相同原生任务协议，分别预占 `video_imports`、`youtube_imports` 并捕获套餐版本；目前会进入 `awaiting_processor`，明确等待 PostgreSQL 原生字幕、Whisper、音视频处理器迁移，不会调用或写入遗留 SQLite Worker。按用户要求，既有 SQLite 的 2 本音频和 3 个 YouTube 落地记录已标记为 `blocked`，不进入 SaaS 私人空间或官方书城；原始文件和落地记录保留，后续可手动审核导入官方书城。
- 验收通过：`tools/test_saas_phase8_integration.py` 5 项，覆盖文本任务幂等、上传、完成、PDF 原生 OCR、MP3 原生 Whisper 词级读物、私人读物创建、非所有者拒绝、MP3 预占/结算/取消释放、源资产空间释放以及 HTTP Cookie/CSRF 全流程；另对现有 81 页 PDF 做只读本机 OCR 探测，得到 1,133 行文本，对 12 秒临时 MP3 片段做真实 Whisper 探测，得到 13 个转写段、3 个句子、11 个词。阶段 1–7 全部集成、展示测试和旧单用户 39 本书架回归继续通过。
- 已生成并完整验证阶段 8 最新备份 `.local/saas-backups/20261010T063936Z`，包含 11 个 migration 的数据库 dump、5,286 文件媒体清单和 SHA-256。
- `.env` 继续保持 `SHIYUE_SAAS_ENABLED=0`。下一步是把现有 PDF OCR、MP3、视频和 YouTube 子处理器抽成只读源资产输入、PostgreSQL 输出的原生 Worker，再开启对应导入能力。

### 阶段 8.1 — MP3 原生处理器与旧音视频排除已完成（2026-10-10）

- MP3 不再进入 `awaiting_processor`：任务上传 `.mp3` 后运行本机 `whisper-cli + base.en`，使用现有 `whisper_book()` 分句逻辑生成带词级时间戳的 PostgreSQL 私人音频读物；成功后结算 `mp3_imports`，失败或取消释放预占与源资产空间。TXT、Markdown 和 PDF 路径保持不变；视频和 YouTube 继续等待原生处理器。
- 按用户明确要求，新增 `0012_exclude_legacy_av_workspace.sql`：此前从 SQLite 落地复制的 2 本音频和 3 个 YouTube 内容标记为 `blocked`，不再出现在 SaaS 私人学习空间，也不会自动进入官方书城。它们的 PostgreSQL 记录、资产清单、原始 SQLite 和媒体文件均保留，可由管理员日后手动审核并导入官方书城。当前可见私人读物为 34 本普通图书。
- 验收通过：阶段 8 集成测试增至 5 项，包含模拟 Whisper 的词级 MP3 私人读物、额度结算以及取消释放；对现有 MP3 剪出 12 秒临时片段运行真实 Whisper 探测，得到 13 个转写段、3 个句子、11 个词。阶段 1–7 集成、展示测试和旧单用户 39 本书架回归继续通过。
- 已生成并完整验证最新备份 `.local/saas-backups/20261010T072211Z`，包含 12 个 migration 的数据库 dump、5,286 文件媒体清单与 SHA-256。

### 阶段 8.2 — 本地视频原生处理器已完成（2026-10-10）

- 本地视频不再进入 `awaiting_processor`：支持 MP4、MOV、M4V、MKV、WebM，通过 FFmpeg 提取 M4A 音频、JPEG 封面和仅供转写使用的临时 16kHz WAV，再由 `whisper-cli + base.en` 生成词级时间戳与动态分句，最终创建 PostgreSQL 私人视频读物。
- 源视频继续作为私人主资产；音频与封面以 `audio`、`cover` 变体附加到同一资产 ID。变体登记会锁定用户并再次校验私人空间，将生成文件字节追加到 `generated_bytes` 和空间账本。所有媒体通过 `/api/media/{asset_id}` 及 `?variant=` 鉴权访问，其他租户不能读取。
- `video_imports` 使用预占—成功结算—失败释放协议。FFmpeg、Whisper、格式校验或最终发布失败时，任务标记失败、释放预占并逻辑删除源资产及已登记变体；未完成登记的派生文件会立即清理。用户取消沿用相同的额度和空间释放规则。
- SaaS 私人学习空间上传界面已开放本地视频类型，并明确 YouTube 仍等待 PostgreSQL 原生下载器。`.env` 继续保持 `SHIYUE_SAAS_ENABLED=0`，没有部署远程服务。
- 验证：真实 FFmpeg 生成 2 秒 MP4，并成功派生 AAC/M4A 音频与 JPEG 封面；原生视频方法结合可控 Whisper 输出生成带词级时间轴的私人视频读物及 `audio`、`cover` 两个媒体变体。阶段 8 PostgreSQL 集成测试已扩展至 7 项并在本机测试库全部通过，覆盖成功结算、空间计量、变体 Range 鉴权、租户隔离、损坏视频失败与额度/空间释放。阶段 1–7、展示测试及旧单用户 39 本书架回归继续通过。

### 阶段 8.3 — YouTube PostgreSQL 原生处理器已实现（2026-10-10）

- `kind=youtube` 不再进入 `awaiting_processor`。服务仅接受 `youtube.com` 与 `youtu.be` 的 HTTP(S) 地址，使用项目本机 yt-dlp 与 Node.js 读取元数据、下载最高 720p 视频，并尝试保存原生英文和中文字幕。
- 下载的视频登记为用户私人主资产，再复用阶段 8.2 的 FFmpeg + Whisper 处理器。派生音频、封面、英文字幕和中文字幕作为 `audio`、`cover`、`subtitles-en`、`subtitles-zh-CN` 变体登记；YouTube ID、频道、字幕来源、轨道、下载和翻译状态写入 PostgreSQL 读物 JSON。
- YouTube 任务只预占和结算 `youtube_imports`，不会额外扣 `video_imports`。下载、重封装、Whisper、空间校验或最终发布失败时释放预占并逻辑删除私人源资产；尚未登记的字幕与派生文件立即清理。旧 SQLite 的 YouTube 内容继续保持 `blocked`，不会被扫描或自动导入。
- 私人学习空间新增 YouTube 地址导入表单。无数据库端到端探测使用可控 yt-dlp、真实 FFmpeg 和可控 Whisper 成功得到私人视频、英文/中文字幕、词级正文和四个受保护变体；阶段 8 数据库测试扩展为 9 项，新增 YouTube 成功、租户隔离、字幕元数据和失败释放用例。受当前 Codex 沙箱 PostgreSQL IPC 限制，新增数据库用例需在普通本机终端复跑后再生成新备份。

### 阶段 8.4 — SaaS 学习数据前端切换已完成（2026-10-10）

- SaaS 导航重新开放“学习记录”和“生词复习”，但数据源改为 `/api/workspace/vocabulary`、`/api/workspace/annotations`、`/api/workspace/learning-days`、`/api/workspace/activity`；单用户模式继续使用原 SQLite 接口。账号退出或切换时会清空浏览器内存中的工作区生词、学习日和读物状态，避免跨账号残留。
- 私人阅读页将正文拆为可点击单词，支持手工填写私人释义、加入 PostgreSQL 生词本、保存私人备注和浏览器本地英文朗读。查词次数、阅读时长、句子数、复习数和学习会话写入账号学习日；复习评分更新 `content_vocabulary`，并继续触发阶段 4 的每日复习成长奖励。
- 工作区生词和标注列表现在通过 `content_books` 联表过滤，只返回当前用户且可见性为 `private`/`draft` 的读物；旧 SQLite 音视频被标记为 `blocked` 后，其历史词条不会重新暴露到 SaaS 复习页面。
- 前端不再在 SaaS 模式请求旧 `/api/word-tts`，复习和听写改用浏览器 `speechSynthesis`。平台词典、AI 语境和句法接口仍保持关闭，留待下一阶段按用户额度和 PostgreSQL 缓存租户化。

### 阶段 9 — AI 语境与句法租户化已实现（2026-10-10）

- 新增 `0013_workspace_ai.sql` 与 `workspace_ai_results`，按用户、私人读物、结果类型、内容键和输入哈希保存 AI 缓存。私人内容所有权和句子/单词索引均由 PostgreSQL 正文重新校验，不信任浏览器提交的上下文文本。
- `/api/word-context` 与 `/api/sentence-grammar` 在 SaaS 模式改由 `WorkspaceAIService` 处理；旧单用户模式继续走原 SQLite/本机配置逻辑。平台 AI 只读取 `SHIYUE_DIOCO_TOKEN`、`SHIYUE_DIOCO_EMAIL`，不会读取或返回用户本机 `.dioco.local.json` 秘密。
- 首次缓存未命中分别预占 `ai_context_generations`、`ai_grammar_generations`；AI 返回有效内容并写入 PostgreSQL 后才结算。生成、上游或入库失败会释放预占；相同内容哈希重复查看直接返回用户缓存，不再扣额度。失败释放后的同一内容允许重新预占并重试。
- 私人阅读页增加“AI 语境精讲”和逐句“句法分析”，结果明确显示缓存命中或本次生成，并在实际扣额后刷新会员额度。用户数据导出包含 AI 结果；账号延迟删除完成时清除其 AI 缓存。
- 新增 `tools/test_saas_phase9_integration.py` 2 项数据库验收，覆盖语境/句法首次扣额、缓存不重复扣额、结构数据合并、所有者隔离、失败释放与成功重试。受当前 Codex 沙箱 PostgreSQL IPC 限制，需在普通本机终端执行后再生成包含 13 个 migration 的新备份。
- 新增只读 `tools/saas_readiness.py`，仅输出配置是否就绪，不输出任何秘密值。当前审计阻塞项为 SMTP、平台 AI 凭据、项目外部备份目录和 PostgreSQL 可访问性；FFmpeg、Node.js、yt-dlp、Whisper、PDF OCR、13 个 migration 文件和本机备份均已就绪，SaaS 总开关继续保持关闭。
