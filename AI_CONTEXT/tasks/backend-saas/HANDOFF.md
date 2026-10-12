# SaaS 后端交接

## 当前架构

- 主服务：`tools/reader_server.py`。
- PostgreSQL 服务模块：`tools/saas_auth.py`、`saas_membership.py`、`saas_catalog.py`、`saas_workspace.py`、`saas_imports.py`、`saas_ai.py`、`saas_admin.py` 等。
- 最新 migration：`0017_auth_email_limit_backfill.sql`；正式本地库、隔离测试库和京东云生产库均已应用。`0016` 增加认证邮件计数与重置锁定字段，`0017` 把历史邀请码使用次数回填到激活邮件上限。
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

## 未完成

- 真实支付提供方、支付回调、退款和自动订阅开通。
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
```
