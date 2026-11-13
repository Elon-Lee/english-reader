# 纸间微光 AI 共享上下文

更新时间：2026-11-13（Asia/Shanghai）

只读取与当前任务对应的交接文档。用户已确认国内/国际双入口：国内保留邀请制个人阅读空间，国际定向恢复原商业流程；两站都要求邀请码。详细边界与真实发布状态见 dual-entry-commerce，不得整站回退旧代码。

## 当前架构

- 维护约定：用户已验收国内主页与10ye.cc流程，确认统一归入主线 `main`。后续先区分共享核心/国内扩展/国际扩展；共享业务只改一份、两站回归，单站差异通过 `@site` 组合。每次程序发布从同一提交同时交付国内、国际、博客及共享后端，不单独发布某站。详见 `AGENTS.md` 与 `docs/DEPLOYMENT_SITES.md`；`npm run deploy:jdcloud` 默认保数据升级。

- 前端：React 18 + Ant Design 5 + Vite，共享 `frontend/src/` 阅读业务，`sites/cn|intl` 分别构建到 `reader/site/` 与 `reader/site-intl/`。两个前端进程代理同一 API。
- 双站：`blog/` 独立 Astro + Retypeset 构建到 `reader/blog/`；主域名 `rynenglish.com` 提供静态文章，阅读应用使用 `learn.rynenglish.com`，按 Host 隔离资源和 API。发布进度及外部条件见博客分站交接。
- 后端：Python HTTP 服务 `tools/reader_server.py`，业务模块 `tools/saas_*.py`，PostgreSQL、Redis、Java 旋转验证码。
- 身份：有效邀请码注册、邮箱验证、数据库会话 Cookie、CSRF、管理员权限及租户隔离。未登录不能读取书城。
- 资源：`saas_resources.py` 统一控制容量、设备和 AI 使用；有效付费权益跨入口一致。私人导入：免费禁导入、进阶1GiB/Pro5GiB，历史private存储底线不再绕过；其他资源规则保留。国内私人导入关闭、管理员官方导入保留。国内商业页面/API关闭；国际商业模块受可信入口、权限与渠道门禁控制。保留学习奖励。
- 媒体：鉴权原音与媒体变体；保留私人上传、官方内容审核、书架、阅读、学习记录和生词复习。
- 长任务：创建任务后轮询，不额外引入 WebSocket。
- 历史数据：迁移链、交易记录与用户媒体保留；0045增量区分原私人账号和新国际账号资源策略。不得删除 `.local/`、`books/` 或真实用户数据。
- 内部 `shiyue` Cookie、数据库、容器与目录标识继续兼容；域名以实际配置为准，改名不自动迁移域名。
- 本地唯一入口：`./start-reader.sh --saas-local`（无参数等同）。独立 PostgreSQL 55432、Redis 56379、验证码 18080、API 8790、SMTP 1025、Vite 4173。见 [本地开发指南](../docs/LOCAL_DEVELOPMENT.md)。
- 部署仅本地模式、回环来源、登录管理员可用，写入检查 CSRF。远程模式拒绝平台与部署管理。

## 跨任务状态

- 最新程序发布为2026-11-13 **#28 complete**：`current=code-20261113-175831-0b004ac5`、源码 `7750427`（clean），国内/国际/博客/共享后端同步保数据升级，迁移0047。国际套餐支持原价＋实际售价、自动一位小数折扣，通过独立版本调价保护历史交易和权益；国内隔离保持。公网22项检查、Chrome及配置/数据核对通过；后台已出现真实调价审计，未由发布脚本调价或付款。详见 [商业交接](tasks/public-commerce/HANDOFF.md)。

- 上一程序发布为2026-11-13 **#27 complete**：`current=code-20261113-154904-ef012c6b`、源码 `46649cb`（clean），国内/国际/博客/共享后端同步保数据升级，迁移0046。国内私人导入入口隐藏、API404，管理员官方导入保留；国际免费提示升级、进阶1GiB/Pro5GiB，旧套餐同受上限，已有文件保留。公网18项检查、Chrome真实套餐页、资源哈希及数据/支付配置核对通过；支付宝与云猫保留，未付款。详见 [导入交接](tasks/import-media/HANDOFF.md)。

- 上一程序发布为2026-11-13 **#26 complete**，`current=code-20261113-141503-c5f09bd8`、源码 `d2409ed`（clean），两前端/博客/共享后端同步保数据升级。国际站正式支付宝电脑网站支付已配置启用，保留云猫与兑换；网关RSA2验签、公开商品渠道和正式收银台¥19确认通过，国内支付API保持404。未付款，用户要求暂不进行实际付款测试，真实回调及自动权益闭环待后续验收。详见 [支付交接](tasks/payments/HANDOFF.md)。

- 最新程序发布为2026-11-13 **#25 complete**，`current=code-20261113-120608-54bdf2ae`、源码 `4ab76c1`（clean）。国内业务登录/应用增加备案页脚，learn入口robots全站Disallow与响应noindex,nofollow；所有访客一致，博客/国际抓取策略不变。两前端/博客/后端同步保数据升级，公网HTTP/Chrome验证、国际健康与两条云猫配置保留通过，国内HTTPS/308保持。详见博客分站交接。#24的共享AI免Token修复继续保留，详见平台运营交接。

- 2026-11-13国内两域Let’s Encrypt HTTPS及HTTP308跳443已启用，`https_deferred:false`；业务版本仍#23。严格TLS、浏览器真实验证码生成、国际健康验证通过，续期定时器active/enabled；详情见博客分站交接。此前国内DNS/HTTPS待办已解除，后续升级不得再加 `--defer-https`。

- 页脚微调已随京东云#23首次发布，源码 `ce05402`：国内备案号居中、版权靠右、移除页脚导航；后续#24包含该修改。以下#22为备案号首次上线记录。

- 国内/国际并行在 `feat/dual-entry-commerce` 实施并经用户验收，本轮归入主线 `main`：国际回环5173、国内5174、共享回环API8790。用户已授权国内5174监听0.0.0.0供IP博客预览，配置 `cn_public_preview:true`；实际发布状态以 [双入口交接](tasks/dual-entry-commerce/HANDOFF.md) 为准，端口文档见 `docs/DEPLOYMENT_SITES.md`。
- 私域改造 `810f19a`、博客分站 `3c0c77b` 与后续双入口/AI博客改版均包含在本轮主线合并范围；原 `refactor/private-paper-glow`、`feat/paper-glow-blog-domains` 为历史实施分支，后续不作为独立业务主线。本地栈入口 `http://127.0.0.1:4173`。
- 国内品牌为“纸间微光”，标语“一页一光，静读慢行。”；国际恢复RynEnglish首页与商业素材，通过独立构建隔离。
- 京东云#22为备案号首次发布，随后#23完成页脚布局，迁移0045。国内博客以AI英语工具为主题，4栏目/共19篇；页脚展示用户提供的 `蜀ICP备2026071122号-1` 并链接工信部查询。实现分支 `feat/blog-ai-english-tools`，尚未合并main。详见博客分站交接；支付最新状态见上方#26与支付交接。
- PC 优先，移动端视觉优化仍待后续独立任务；保留原音播放，不以浏览器 TTS 替代。

## 任务索引

| 工作内容 | 必读任务文档 |
|---|---|
| 独立静态博客、主域名与阅读子域名、双站发布 | `tasks/blog-domains/HANDOFF.md` |
| 私域邀请制、商业功能移除、纸间微光更名 | `tasks/private-paper-glow/HANDOFF.md` |
| 品牌与网站图标 | `tasks/brand-assets/HANDOFF.md` |
| PC 页面、路由、分页、工作台 | `tasks/pc-workspace/HANDOFF.md` |
| 书城搜索、筛选、发现（待评审） | `tasks/catalog-discovery/HANDOFF.md` |
| 生词复习、学习结算 | `tasks/vocabulary-review/HANDOFF.md` |
| 阅读器、媒体、字幕、快捷键、词典 | `tasks/reader/HANDOFF.md` |
| 账号、资源、数据库、API、安全 | `tasks/backend-saas/HANDOFF.md` |
| 验证码、DirectMail | `tasks/auth-captcha/HANDOFF.md` |
| 文件与 YouTube 导入、媒体处理 | `tasks/import-media/HANDOFF.md` |
| 本地安装、启停、登录与排错 | `tasks/local-development/HANDOFF.md` |
| 运营后台、AI 配置、远程部署 | `tasks/platform-operations/HANDOFF.md` |
| 国内/国际入口并行、共享业务与国际商业功能恢复 | `tasks/dual-entry-commerce/HANDOFF.md` |
| 移动端适配 | `tasks/mobile/HANDOFF.md` |
| 国际商业与支付、国内关闭边界 | `tasks/public-commerce/HANDOFF.md`、`tasks/payments/HANDOFF.md` |

历史商业设计审计不再代表当前需求。新独立任务创建 `tasks/<task-slug>/HANDOFF.md`，不要把详细历史堆回全局索引。

## 默认验证

```sh
npm run build:modern
npm run test:modern
npm run test:ui
npm run check:js
python3 -m py_compile <本轮修改的Python文件>
git diff --check
```

涉及账号、资源或租户写入时，用专用 `_test` PostgreSQL 运行相关集成及 `./start-reader.sh --saas-smoke 8795`；先明确隔离测试 URL，不得以正式库运行清理数据的测试。
