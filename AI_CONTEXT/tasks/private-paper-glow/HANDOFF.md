# 纸间微光：私域邀请制与商业功能移除

更新时间：2026-11-09（Asia/Shanghai）

## 目标与边界

- 工作分支 `refactor/private-paper-glow`，从干净本地 `main` 创建；用户已授权提交并推送至 `origin` 同名分支，实际提交与同步状态以 Git 为准；未合并或远程部署。
- 用户明确选择保留邀请码注册、关闭无邀请注册。网站名“纸间微光”，标语“一页一光，静读慢行。”。
- 实际删除线上商品、购买、付款、订阅、会员、兑换开通及关联后台和服务端代码，不设置临时隐藏或备案开关；没有新增线下收款引导。
- 保留账号认证、邮箱验证、CSRF、幂等、管理员权限、租户隔离、原音阅读、私人资料、书架和学习记录。
- 不删除正式数据库、历史交易或用户媒体。已执行 SQL 迁移链与历史交易表保留，运行代码不再读写商业记录。
- 本技术改造不代表备案审批通过。后续申报及运营范围须与实际内容一致。

## 已完成

- 前端删除商业页面、组件、API、状态、购买恢复、触限升级弹窗和运营入口；首页改为受邀个人空间。邀请字段必填，登录跳转只接受已支持的站内应用路径。
- 服务端删除 `saas_membership.py`、`saas_billing.py`、`saas_commerce.py`、`saas_payments.py`、`saas_redemptions.py`、`saas_mbdpay.py` 与对应 HTTP 路由、支付通知、模拟支付、人工订单/订阅、退款及付费推荐。
- 旧商业 API 返回 404。React 路由与生产前端服务器均拒绝 `/pricing`、`/purchase/*`、`/refunds` 及旧会员页面。
- 注册服务端强制校验邀请码并原子计数，未登录且未验证邮箱不能读取书城。统一资源服务替代会员等级；原音和媒体访问继续由所有权/书架权限控制。
- 品牌标题、SVG、邮件、四个法律页、CLI 和部署默认发件名称已更新。移除旧支付图标、旧品牌资产、未使用营销截图、旧 modern 编译包和过时商业计划。
- 本地部署 GET/POST 先认证，再限制 local 模式、回环来源和管理员；POST 保留 CSRF。升级脚本清理旧支付渠道环境变量。
- 打包门禁检查中文标题、新 SVG 和商业接口残留；归档排除旧 modern 包、源码映射、测试、Python 缓存与开发说明。
- 全局索引及商业、支付、品牌、后端和部署交接已更新，历史商业任务不再作为当前待办。

## 资源规则与迁移

`tools/saas_resources.py` 使用独立技术额度，无商品、订阅或到期升级：

| 资源 | 默认限制 |
|---|---|
| 私人媒体空间 | 20 GiB |
| 视频/音频收藏（公版与私人合计） | 100 / 200 |
| AI 语境/语法生成 | 每日 50 / 20，Asia/Shanghai 重置 |
| 普通账号有效设备 | 5；管理员沿用最近 5 条会话管理 |
| 已授权视频画质 | 不按会员等级拦截 |

媒体和 AI 可用 `RESOURCE_<FEATURE大写>` 环境变量配置正整数；设备固定 5，不接受 `RESOURCE_DEVICES` 覆盖。学习成长值、签到及非现金学习奖励保留，不发行会员邀请码或付费推荐奖励。

新迁移 `0044_private_resources.sql` 解耦用户/用量周期/导入任务的旧套餐引用，增加独立资源审计。已在独立测试 PostgreSQL 验证；2026-11-09 按用户本地启动要求，在当前目录首次初始化独立本地库并应用至 0044，无已有此栈数据库需要迁移或覆盖。远端库未操作。

## 验证

- `npm run build:modern`、`npm run test:modern`、`npm run test:ui`（16 项）、`npm run check:js` 通过。
- 前端 Node 41 项及 Chrome/Playwright 品牌、受邀注册、账号、后台、退役路由验收通过，无商业请求；截图 `/private/tmp/paper-glow-browser/`。
- 真实隔离 PostgreSQL HTTP smoke 33 项通过，覆盖邀请必填、登录、CSRF、统一资源、私人文本导入、媒体 Range、学习/生词、AI 失败释放、账户导出/删除与管理员拒绝。
- HTTP/部署权限/生产前端实际路由 25 项通过；部署打包/邮件/HTTP 离线回归 33 项通过。
- 最终空测试库完成全部迁移，phase1–9、资源并发、生词复习、配套原音分段上传共 137 项：136 项直接通过，新增邀请码到期测试唯一失败为 UTC 与 +08:00 字符串差异；改为比较同一时间点后 phase5 全部 8 项通过，无剩余失败。
- 补齐管理员带有效期发码的时间解析导入，覆盖单码/批量发码、有效码注册、过期拒绝及非法时间。删除无调用的原额度手工补发/调整、操作回执方法与闲置新表；删除原支付独占 cryptography 依赖。
- 实际归档内容审计 431 条目：新资源模块/迁移/图标存在，旧商业模块/品牌/支付图/营销图/缓存/map 不存在；此次只验证归档内容，构建步骤使用已完成的前端构建，未触发发布。
- 51 个变更/新增 Python 文件编译、运行模块全局名称检查、旧/新 CSS 解析和 `git diff --check` 通过。
- 收尾离线回归（部署、邮件、HTTP、资源及认证契约）41 项通过；本轮临时 PostgreSQL 55439 已停止，正式 55432 未操作。

隔离 HTTP 命令（须先具备独立临时 PostgreSQL，不能指向正式 55432）：

```sh
env PYTHONPATH=tools \
 DATABASE_URL=postgresql://paper_glow_test@127.0.0.1:55439/paper_glow_http_test \
 SHIYUE_SAAS_TEST_DATABASE_NAME=paper_glow_http_test \
 READER_PYTHON=.local/auth-venv/bin/python \
 ./start-reader.sh --saas-smoke 8795
```

## 关键文件与后续

- 前端：`frontend/src/main.jsx`、`pages/PublicSite.jsx`、`pages/AdminPage.jsx`、`utils/privateRoutes.mjs`。
- 后端：`tools/reader_server.py`、`saas_auth.py`、`saas_resources.py`、`saas_admin.py`、`saas_frontend_server.py` 及资源调用方。
- 品牌/交付：`frontend/src/config/brand.mjs`、`frontend/public/brand/`、`reader/legal/`、`tools/deployment/manager.py`。
- 当前独立本地栈已启动，入口 `http://127.0.0.1:4173`；API/Redis/验证码健康、前端代理、未登录 401、旧会员 API 404 与 0044 迁移记录已核实。本地管理员 `admin@local.test`，初始密码仅见 `.local/local-dev/admin-credentials.txt`，初始书籍为空。停止用 `./start-reader.sh --stop-saas-local`。
- 本次启动 Chrome 首页实际渲染通过，显示新名称、登录和受邀注册；无 JS 错误或请求失败。未执行登录后的业务操作，留给用户本地验收。
- 未来切换已有数据的其他目标环境前应先备份目标库并应用迁移。远端与域名配置未变更。
- 本次提交与推送已获用户授权；合并与远程发布仍须等待用户实际指令，无需恢复旧商业功能。
