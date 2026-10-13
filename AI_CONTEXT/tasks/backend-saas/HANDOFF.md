# SaaS 后端交接

## 当前架构

- 主服务：`tools/reader_server.py`。
- PostgreSQL 服务模块：`tools/saas_auth.py`、`saas_membership.py`、`saas_catalog.py`、`saas_workspace.py`、`saas_imports.py`、`saas_ai.py`、`saas_admin.py` 等。
- 最新 migration：`0022_mbdpay_events.sql`；`0018`–`0022` 已应用正式本地库和隔离测试库，京东云生产库尚未应用。新增不可变商品版本、固定期限订单快照、年卡 30 天额度周期和面包多事件账本。
- 认证使用数据库会话 Cookie 和 CSRF；所有写接口必须校验 CSRF。
- 测试库名称必须以 `_test` 结尾。
- 京东云生产运行 PostgreSQL 16 Bookworm、Redis 7 Bookworm 和 `shiyue-saas-runtime:20261012-1`；数据库和 Redis 端口仅绑定 `127.0.0.1`，应用通过 host network 访问。

## 已完成

- 邀请注册、邮箱验证、登录、密码重置、设备撤销和管理员隔离。
- 套餐、订阅、账期、额度预占/结算/释放、人工订单和套餐变更申请。
- 官方书城、私人工作区、奖励、媒体鉴权、账户导出/注销。
- 完整阅读偏好保存。
- 邀请码支持后台自动生成、批量生成、查询和分页。
- AI 平台配置保存在 PostgreSQL `platform_settings`，不再依赖环境变量。
- 2026-10-12 已将旧版本地有效 Dioco 凭据通过 `AdminService.update_platform_config` 迁入 PostgreSQL，并留下管理员审计记录；连通性测试成功，未在日志或文档中记录完整 Token。
- `/api/auth/devices` 现在把设备时间转换为 ISO 字符串并返回前端使用的 camelCase 字段，修复系统设置页因 PostgreSQL datetime 无法 JSON 序列化而加载失败的问题。
- 生词服务支持已解锁官方读物：API 接收 catalog book ID，校验当前用户的 `official_book_unlocks`，以源 `content_book_id` 安全存储，并对前端继续返回 catalog book ID；未解锁用户不能读写该词汇记录。
- 新增鉴权与 CSRF 保护的 `/api/workspace/progress`，只更新最近句子；私人和已解锁官方读物都经过租户/解锁校验，不写活动事件、不累计学习时长或奖励。官方阅读接口会返回映射后的 `progress`。
- 生产根路径 `/` 已直接启用 React SaaS；健康接口同时校验 Redis。首次远程数据库从本地正式库恢复后，只保留合法已公开书籍的内容/媒体数据，并保留账号、订阅和平台配置。
- 2026-10-12 已完成 Resend 生产邮件配置：验证发送子域名 `auth.10ye.cc`，Cloudflare DNS 已配置 DKIM、SPF/Return-Path CNAME 和 DMARC；本地 `.env` 与京东云 `/srv/shiyue/shared/config/saas.env` 均使用受限于该域名的 Resend SMTP 密钥。京东云和本地均已向 Resend 官方测试地址真实发送成功，生产容器已重建并通过健康检查。密钥未写入代码、Git、日志或交接文档。
- 2026-10-12 已完成认证邮件流程加固并部署生产：`/verify-email` 与 `/reset-password` 直接返回 React 入口，重置页可提交新密码，激活页自动验证 token；注册和找回邮件发送成功后前端切回登录。未激活邮箱登录返回 `email_unverified`。每个邀请码最多产生 3 封激活邮件；同一账号连续申请 3 封重置邮件后停止继续发送，成功重置会清零计数。入口 JS/CSS 带构建版本查询参数，避免固定文件名的旧缓存继续加载过时认证页面。生产发布为 `code-20261012-235032-6d5d0c1a`。
- 2026-10-13 本地修复管理员用户详情查询：人工订单表字段应为 `plan_version_id`，此前错误查询 `plan_version` 会令存在人工订单的用户详情返回失败。阶段 5 测试和隔离浏览器验收均通过；未部署远程。
- 2026-10-13 已完成 Paddle Billing 本地第一版：新增 `tools/saas_billing.py` 和 migration `0018`；会员页可创建 Paddle Transaction、加载官方 overlay Checkout、展示 Paddle/人工订单，并通过客户门户更新付款方式或取消自动续费。`/api/billing/webhooks/paddle` 保留原始请求体验签，按 Paddle event ID 幂等处理交易与订阅生命周期，只在 `transaction.completed` 或有效订阅状态同步后创建/更新本地会员权益。API Key、webhook secret 仅从环境变量读取，浏览器只获取 Paddle client-side token。已完成 webhook 单元测试、隔离 PostgreSQL 自动开通/重复事件测试和现有阶段 2 回归。Paddle 正式账号已由用户注册；切换 sandbox 时 Paddle 要求为沙盒账号单独重置密码，目前等待用户完成邮件中的沙盒密码设置，然后才能创建沙盒产品、价格、API Key、客户端 Token 和 webhook。
- 2026-10-13 已实现面包多固定期限支付闭环：本地不可变商品订单、官方 MD5 签名、支付宝安全表单、webhook 幂等、服务端主动查单、金额核验、同套餐顺延或新开会员、前端订单轮询。未配置密钥时不创建订单或展示可点击支付按钮。长期会员按套餐 `period_days` 重置额度，当前付费套餐每 30 天生成新 `usage_period`。

## 未完成

- Paddle 半成品代码保留用于 provider 抽象和历史测试，但公开 UI 已停用 Paddle 与自动续费。
- 面包多真实账号审核、`MBDPAY_APP_ID`、`MBDPAY_APP_KEY`、正式 webhook 和真实支付宝付款验收尚待外部条件。
- 自动退款后台操作尚未实现；当前可先在面包多控制台退款，应用已具备订单与权益状态基础。
- 2026-10-13 已完成面包多 Pay 准入导向审查（仅分析，未改代码）：面包多官方当前个人可申请支付宝、微信 JSAPI、微信 H5，但公开说明其审核较严格；微信 H5 还需要在控制台审核 H5 域名，微信官方 H5 域名配置要求 ICP/经营性网站资质，因此未备案域名阶段不把 H5 作为准入或主支付路径。后续若改接面包多，会员产品必须从“自动续费订阅”改为“单次购买固定期限权益”，优先支付宝/微信 JSAPI，付款成功 webhook + 查单双重核验后开通，不承诺自动扣费。当前会员页、退款页和公开入口截图证据保存于 `.local/debug/product-design/mbdpay-admission-audit-20261013/`；需要先调整套餐文案、支付方式、退款规则、版权/内容声明、客服与交易凭证，再实现面包多 provider。
- 100～500 用户的并发和容量压测。
- AI Token 数据库字段目前是普通 JSONB；如进入生产，应评估应用层加密或外部密钥管理。

## 安全原则

- 不输出 `.env`、Token、密码或 `.dioco.local.json`。
- 管理员写操作要写审计日志。
- 不允许 SaaS API 回退到旧 SQLite 学习数据。
- 新接口必须验证 tenant owner 或 admin 权限。

## 关键验证

```bash
./start-reader.sh --saas-smoke 8795
python3 -m py_compile tools/reader_server.py tools/saas_*.py
python3 tools/test_paddle_billing.py
SHIYUE_SAAS_TEST_DATABASE_URL=... .local/saas-venv/bin/python tools/test_saas_billing_integration.py
```
