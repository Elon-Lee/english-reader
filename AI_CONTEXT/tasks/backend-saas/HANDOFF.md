# SaaS 后端交接

## 当前架构

- 主服务：`tools/reader_server.py`。
- PostgreSQL 服务模块：`tools/saas_auth.py`、`saas_membership.py`、`saas_catalog.py`、`saas_workspace.py`、`saas_imports.py`、`saas_ai.py`、`saas_admin.py` 等。
- 最新 migration：`0015_membership_change_requests.sql`；正式库和测试库均已应用。
- 认证使用数据库会话 Cookie 和 CSRF；所有写接口必须校验 CSRF。
- 测试库名称必须以 `_test` 结尾。

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

## 未完成

- 真实支付提供方、支付回调、退款和自动订阅开通。
- 生产 SMTP 的真实发送验收。
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
