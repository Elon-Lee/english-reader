# Dual Entry Commerce Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for integration, and superpowers:dispatching-parallel-agents for the separate frontend and commercial backend file scopes.

**Goal:** 国内与国际前端并行，共享最新阅读业务与数据，国际恢复商业流程。

**Architecture:** 单主线、两份前端产物、单后端。回环端口国际 5173/国内 5174/API 8790；入口可信凭据与后端白名单共同隔离商业功能。

**Tech Stack:** 当前 React/Ant Design/Vite、Python HTTP、PostgreSQL/Redis、Astro、Docker/Nginx/Cloudflare。

### Task 1: 可信站点和前端代理（主代理）

- [ ] 在 `tools/test_saas_sites.py` 和前端服务测试中先验证国内拒绝商业路由、伪造头拒绝、国际 Host 限制、可信站点基础地址，再实现 `tools/saas_sites.py` 和 `tools/saas_frontend_server.py`。
- [ ] `PYTHONPATH=tools python3 -m unittest tools.test_saas_sites tools.test_saas_frontend_routes`：新增用例先失败，再通过。
- [ ] 合同：`current_site()` 返回 `cn`/`intl`；`app_base_url(environment)` 返回可信站点配置；`request_site(headers, peer, environment)` 识别站点并拒绝无效凭据；入口覆写 `X-Shiyue-Site`/`X-Shiyue-Site-Token`。配置键为 `CN_GATEWAY_TOKEN`、`INTL_GATEWAY_TOKEN`、`CN_APP_BASE_URL`、`INTL_APP_BASE_URL`。

### Task 2: 国际商业后端（独立文件范围）

- [ ] 先补商业路由鉴权/国内拒绝以及私人资源兼容测试；迁回 `saas_membership.py`、`saas_commerce.py`、`saas_redemptions.py`、`saas_payments.py` 和所需计费模块及原相关测试。
- [ ] 修改 `reader_server.py`、`saas_auth.py` 和 `saas_resources.py`，通过可信站点上下文提供商业 API，使用单一共享权益模型；增量 SQL 保留现有私人账号额度，新国际账号免费规则，旧迁移不动。
- [ ] 支付仅恢复有效原流程，退役渠道保持禁用；支付配置不输出私钥，生产模拟支付始终关闭；回调验签、金额、订单与幂等保留。
- [ ] 专用 `_test` 库运行恢复模块集成，绝不让测试清理正式库；执行 Python 编译。

### Task 3: 国际前端与双构建（独立文件范围）

- [ ] 先补国际路由、国内商业依赖隔离测试；`frontend/src/sites/cn` 与 `intl` 分别导出站点组件，Vite 构建别名选择模块。
- [ ] 定向恢复首页、会员、商业运营和支付组件/样式，保留当前阅读代码。`frontend/src/main.jsx` 只调用站点扩展；输出国内 `reader/site/` 和国际 `reader/site-intl/`。
- [ ] 增加 `build:intl` 与 `build:sites`，共享依赖不升级，国际资源置于独立 public 目录，不污染国内产物；运行两次构建和 UI/modern 检查。

### Task 4: 部署与配置（主代理）

- [ ] 先补两前端容器、配置持久化、Nginx 5174、双候选与回退测试。
- [ ] 修改 `tools/deployment/manager.py`、`https_entry.py` 和 `tools/deploy_remote.py`，保存国际域名与端口，生成各入口环境，升级保留支付凭据，候选前端 15173/15174 共用候选 API 18790。
- [ ] 保留旧部署配置兼容；双前端任一失败整体回退；数据库先备份、仅增量迁移、不重装。

### Task 5: 集成、发布与交接（主代理）

- [ ] 执行双站构建、博客 check/build/verify、modern/UI/JS、相关 Python 测试及编译、`git diff --check`；独立复核站点身份、额度和支付边界。
- [ ] 提交清晰的源代码快照；保数据升级京东云，核实 Cloudflare 配置及实际 HTTPS/静态资源/未登录认证/验证码。仅在外部条件满足时启用国内 TLS。
- [ ] 更新 `docs/DEPLOYMENT_SITES.md`、当前任务、blog-domains、platform-operations 和商业任务交接，记录实际版本、端口、测试和真实外部待办。
