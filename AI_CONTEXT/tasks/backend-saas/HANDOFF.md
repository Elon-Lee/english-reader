# SaaS 后端交接

## 当前架构

- 主服务：`tools/reader_server.py`。
- PostgreSQL 服务模块：`tools/saas_auth.py`、`saas_membership.py`、`saas_catalog.py`、`saas_workspace.py`、`saas_imports.py`、`saas_ai.py`、`saas_admin.py` 等。
- 最新 migration：`0033_membership_upgrade_carry_seconds.sql`；本地正式库与隔离测试库已应用至 `0033`，生产需在下一次发布前执行迁移。
- 认证使用数据库会话 Cookie 和 CSRF；所有写接口必须校验 CSRF。
- 测试库名称必须以 `_test` 结尾。
- 京东云生产运行 PostgreSQL 16 Bookworm、Redis 7 Bookworm 和 `shiyue-saas-runtime:20261012-1`；数据库和 Redis 端口仅绑定 `127.0.0.1`，应用通过 host network 访问。

## 已完成

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
- 生词服务支持已解锁官方读物：API 接收 catalog book ID，校验当前用户的 `official_book_unlocks`，以源 `content_book_id` 安全存储，并对前端继续返回 catalog book ID；未解锁用户不能读写该词汇记录。
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

## 关键验证

```bash
./start-reader.sh --saas-smoke 8795
python3 -m py_compile tools/reader_server.py tools/saas_*.py
python3 tools/test_paddle_billing.py
SHIYUE_SAAS_TEST_DATABASE_URL=... .local/saas-venv/bin/python tools/test_saas_billing_integration.py
```
