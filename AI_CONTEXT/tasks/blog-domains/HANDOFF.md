# 纸间微光博客与阅读子域名

更新时间：2026-11-12（Asia/Shanghai）

## 国内/国际入口变更

- 2026-11-12 AI手记改版：用户确认纸色手记方案，分支 `feat/dual-entry-commerce`。新增4个一级栏目（AI入门/提示词手记/AI与阅读/实践与思考）、12篇当日原创文章，原3篇阅读随笔保留URL并归入AI与阅读，共15篇。首页改为横向导航、书页SVG首屏、栏目卡片、精选、最新6篇及个人侧栏；新增完整归档与分类路由，关于页同步定位。
- 分类定义 `blog/src/categories.ts`，内容schema强制category枚举。文章正文保留目录和标签、暗色切换；资源全本地。参考资料仅允许验证脚本中4个精确原始资料URL，主站仍无业务链接/API或访客差异。
- 本地Astro类型检查0错误/警告，静态构建及输出验证通过（41页面/15文章），Chrome验证4栏目、阅读栏目6篇、归档15篇、目录展开/暗色切换及390px无横向溢出，无pageerror。截图 `/private/tmp/ai-journal-{home,dark,post}.png`。源码完成后按现有保数据升级发布；本次线上状态待验收后填写。

- 用户已确认国际恢复原完整流程；国内博客和learn继续保持本任务边界。双前端共享同一业务后端，国际回环5173、国内回环5174，国内Nginx随发布改转5174。
- 本轮实际发布状态优先看 [双入口交接](../dual-entry-commerce/HANDOFF.md)，端口与升级配置见 `docs/DEPLOYMENT_SITES.md`。下方11月11日数据为本轮前基线。
- 主站不链接阅读子站，不代理API；所有User-Agent返回一致，不按爬虫或访客差异呈现。域名拆分不替代备案和实际服务合规要求。
- 京东云#17已保数据发布 `code-20261112-113233-fafb1495`，国内回环5174/Nginx80和国际5173均通过真实Host验收；国内主域当前SHA-256 `4539c3b4c116d31c0e08a0e582118a152b5b65748c30df7e11c8ddccfa45939b`。11月12日服务器侧主域HTTP200，本机固定真实IP外部HTTP仍JDTP403；learn未解析、国内443未启用。外部条件仍待完成，不复用下方旧预览断言。

## 已确认范围

- 用户确认采用 Astro + Retypeset；主域名独立博客，阅读应用迁到 `learn.rynenglish.com`，主站不包含子站入口或业务资源。
- 已授权发布京东云，保留已有数据库与媒体。工作分支 `feat/paper-glow-blog-domains`，基线 `810f19a`。
- 设计与执行计划在 `docs/superpowers/specs/2026-11-11-paper-glow-domains-design.md` 和对应 plans 文件。

## 当前状态与外部条件

- 博客、Host 分站、双域名独立证书与续期、保数据升级集成已实现。用户已提供可用 SSH 私钥；凭据内容不得写入文档或日志。
- 用户明确选择稍后添加 DNS、先部署源站。公共 DNS 实测主域名指向京东云，learn 为 NXDOMAIN；主域名 HTTP 返回 JDTP 403，HTTPS 未连通。源站部署使用 `--upgrade --app-domain learn.rynenglish.com --blog-domain rynenglish.com --defer-https`，不能声称公网 HTTPS 已完成。
- 已验证 React 构建、modern/UI/JS、106 项部署回归、75 项域名/HTTPS/路由测试；额外覆盖切换后配置保存失败的回退路径。主域名不代理 API，未知 Host 拒绝，所有 User-Agent 返回一致。
- 实现提交 `3c0c77b`；京东云任务 **#16 complete**，实际版本 `code-20261111-152232-21f52fbd`，源码快照干净。此前 #14/#15 的传输与候选检查失败记录保留，已完成回退后重试，不冒充成功。
- 数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261111-152232-21f52fbd.dump`；配置备份同目录 `settings-code-20261111-152232-21f52fbd/`。迁移已到 0044，升级前后只读核对均为 1 用户、2 书目。数据库、Redis、媒体目录和会话密钥保留。
- 实测节点内存约 2 GB、无 swap，候选推理时出现高 I/O 等待与 SSH 握手超时；已添加 `/var/lib/shiyue/paper-glow-deploy-20261111.swap` 的 1 GiB 临时交换空间（0600），未写入 fstab。启用后候选真实原音 CPU 推理和正式切换均通过；交换空间在服务器重启后需要重新启用。
- 临时传输包装 `.local/deployment/deploy-origin-resume.py` 增加 SSH 保活与大包分段/前缀 SHA-256 校验，仅本轮进程使用；未改动部署业务逻辑或运行源码。

## 源站验收与待办

- 6 容器运行，`current`、发布包 SHA-256、应用挂载和健康检查通过。`APP_BASE_URL=https://learn.rynenglish.com`，`sites.json` 保存两域及 `https_deferred:true`。
- 实际源站主域首页/文章/关于/RSS 为 200，API 与登录地址为 404，自定义缺页为 404；learn 登录页面和健康接口为 200、未登录会话为 401；未知 Host 为 421，验证码健康与配置通过。
- 主域首页 SHA-256 `a5139f33b2c8ad90f5567a3dd203bac3a9e46e7db6971398842414ec9e05c27b`，与本机构建及经 SSH 转发的源站预览完全一致。Chrome 已实际打开源站首页，纸色主题显示正常。
- 临时源站预览 `http://127.0.0.1:4331/`：仅本机回环，代理脚本 `.local/deployment/preview-blog-origin.py`，经 SSH 回环 4332 固定主域 Host 访问已部署站点。本地生产构建预览 4321 另存；4331 才是京东云实际源站。
- 2026-11-11 公共 DNS 再验：learn 仍 NXDOMAIN，主域 A 为 `117.72.209.44`；公网 HTTP 返回 `Server: JDTP` 的 403。**尚未开通两域公网 HTTPS**，没有申请失败的证书冒充可用。
- 用户稍后添加 `learn` A 记录到 `117.72.209.44`，并完成京东云域名放行后，仅补装入口：`tools/deploy_remote.py --target 1 --https-entry --domain learn.rynenglish.com --identity-file <已授权私钥路径>`；该流程读取远端双站配置并为两域各自签证、安装续期，再严格验收公网 HTTPS。不要用主域覆盖应用域名，不要执行 `--saas` 或重装。

## 关键文件与维护

- `blog/` 为独立 Astro + Retypeset 工程，MIT 来源、Markdown 写作和 Node 要求见 `blog/README.md`；根依赖未变。
- `reader/blog/` 为生成且忽略的静态产物；`npm --prefix blog run build` 和 `npm --prefix blog run verify` 生成并验证。部署包自动包含该目录，不直接修改。
- `tools/saas_frontend_server.py` 根据 `APP_DOMAIN`、`BLOG_DOMAIN`、`BLOG_ROOT` 精确分站；主站独立静态目录，应用保留原 API 与鉴权。
- `tools/deployment/manager.py` 构建双站、备份数据库与站点配置、候选检查、切换失败回退。`shared/config/sites.json` 持久化双域名与 `https_deferred`，后续升级优先恢复该配置。
- `tools/deployment/https_entry.py` 支持主/子域各自证书和续期；待两域 DNS 与京东云放行完成后，仅补装 HTTPS，不重装或导入数据库。
- 博客当前共15篇手记，不虚构个人经历；写作与栏目维护见 `blog/README.md`。备案号配置为空，取得真实号码后填写 `blog/src/config.ts` 的 `icpRecord` 并重新构建发布。
