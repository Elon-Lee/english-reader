# 平台运营与部署交接

## 2026-11-12 国内/国际并行（当前优先）

- 用户已确认恢复国际完整流程并保数据发布，实施分支 `feat/dual-entry-commerce`。本轮发布进度以 [双入口交接](../dual-entry-commerce/HANDOFF.md) 为准；下方11月11日状态为发布前基线。
- 国际 `10ye.cc` 回环5173、国内主域博客/learn阅读回环5174、共享API8790；两个前端独立构建，同一数据库与公共业务。Cloudflare回源5173、国内Nginx改转5174。运维端口与升级约定见 `docs/DEPLOYMENT_SITES.md`。
- 后续升级从 `sites.json` v2 恢复三域与双端口，保留支付配置；国内商业关闭、国际按真实渠道就绪门禁开放。两站仍要求邀请码，原个人账号资源不降低。
- 双候选和正式检查失败整体恢复代码、配置、入口令牌、Nginx与前端拓扑；数据库只做兼容迁移，禁止用完整重装替代保数据升级。

## 2026-11-11 双站源站发布（本轮前基线）

- 用户授权先部署源站、稍后添加 DNS。任务 **#16 complete**，`current=/srv/shiyue/releases/code-20261111-152232-21f52fbd`，源码提交 `3c0c77b`，保留用户、媒体与密钥，迁移至 0044；6 个容器健康。数据库及站点配置备份见 [双站交接](../blog-domains/HANDOFF.md)。
- 主域 `rynenglish.com` 仅提供 Astro/Retypeset 静态博客；阅读应用为 `learn.rynenglish.com`，`APP_BASE_URL` 已对应修改。该日 `sites.json` 保存两域及 `https_deferred:true`；11月12日用户另授权国际恢复，以顶部双入口方案为准。
- 源站真实 Host 验收、用户/书目保留、验证码与原音 CPU 推理通过。主域 API/登录 404，阅读应用未登录会话 401。临时预览 `http://127.0.0.1:4331/` 经仅回环 SSH 转发访问实际京东云内容。
- 公网 learn DNS 仍 NXDOMAIN，主域 HTTP 仍为 JDTP 403，域名证书和 443 尚未开通。待用户新增 learn A=`117.72.209.44` 并完成京东云放行后，只执行 `tools/deploy_remote.py --target 1 --https-entry --domain learn.rynenglish.com --identity-file <已授权私钥路径>`，恢复双站并安装各自证书/续期，无需重新部署数据库。
- 节点 2 GB 内存，候选推理曾内存紧张并出现高 I/O 等待；已添加 `/var/lib/shiyue/paper-glow-deploy-20261111.swap` 的 1 GiB 临时 swap（0600），未配置开机启用，重启后需要恢复。失败任务 #14/#15 已回退，记录保留；#16 不跳过任何候选推理或分站检查。
- 以下 2026-11-08/09 记录为历史；当前域名、版本和待办以上文及双站交接为准。

## 2026-11-09 私域改造补充

- 当前分支已删除商业运营后台及对应支付、订单、订阅、套餐、兑换开通 API。旧商业记录不再代表当前实现；详见 [私域改造交接](../private-paper-glow/HANDOFF.md)。
- 本地部署入口先加载认证会话，再检查 local 模式、回环来源和管理员权限；写入继续检查 CSRF，远程模式拒绝管理。
- 打包前重新构建并检查纸间微光标题、新 SVG 与旧商业接口残留；归档排除旧 modern 包、源码映射、测试、Python 缓存及开发文档。后续升级清理旧支付渠道环境变量。
- 本轮仅本地代码与隔离验证，未连接或更改远端节点、正式数据库或真实用户媒体。

## 部署行为

- “程序升级”打包当前本机代码，先备份远程 PostgreSQL，再通过候选版本、迁移完整性和健康检查后切换；保留远端用户数据。
- “重新部署”是完整重装：按 2026-11-08 用户最新要求，不备份远程数据库；本机构建和初始化快照准备完成后，直接移除项目服务和安装目录并完整安装，用当前本机数据库快照初始化，并同步本机公开内容。该操作会删除原远端用户数据。
- “上传官方内容”只增量同步已登记的官方读物及关联媒体，不发布代码，也不覆盖远端用户数据。新增或变更内容需在线上审核后才公开。
- 远程部署、重新部署、回滚、卸载和清理均需管理员确认；除非用户明确要求，不执行远程变更。

## 2026-11-08 运行记录（历史）

- 京东云 `117.72.209.44` 当前通过 **`https://10ye.cc` 的 Cloudflare Tunnel 提供服务**。原恢复任务 #89 因直连域名证书失败保持 failed；后续隧道恢复独立完成。当前指针 `/srv/shiyue/current` 指向 `code-20261108-092017-f197eeaa`。6 个容器运行：SaaS、前台、PostgreSQL、Redis、验证码及 HTTP bootstrap Nginx。API 的 SaaS/Redis、PG readiness、验证码健康、5173 首页与 TLS 均通过，数据库迁移至 0043。
- 直连域名证书问题已按用户要求移入备案后待办：Let's Encrypt HTTP-01 返回京东云 `JDTP 403`；服务器回环验证文件为 200。当前没有 `rynenglish.com` 的域名证书、443 监听或续期 timer；暂停申请。5173 自建证书与 Cloudflare 公网证书独立。
- 已恢复原 Cloudflare 隧道 `4017ec4f-b520-4559-9e29-b643601849a8`，沿用云端 `10ye.cc → http://localhost:5173` 回源。官方 cloudflared 2026.10.7 二进制按 GitHub 发布 SHA-256 校验后安装于 `/usr/local/bin/cloudflared`；`cloudflared.service` 为 active/enabled，`127.0.0.1:20241/ready` 返回 4 条可用连接，失败自动重启。凭据仅存远程 `/etc/cloudflared/rynenglish.token`（root:root、0600），不写代码、日志或文档。
- 隧道恢复任务 **#287 complete**：实际重启服务后重新连接成功，公网首页/7 项入口静态资源/健康接口 200、严格 TLS 通过，未登录认证接口 401，真实公网旋转验证码生成与 Secure/HttpOnly Cookie 通过；PG readiness 和验证码健康正常。本轮前端构建、modern smoke、18 项 HTTPS/入口集成、操作脚本 Python 编译与 diff 检查通过。
- 后台 `APP_BASE_URL` 已切换为 `https://10ye.cc`，以原镜像和当前代码重建 API 并通过健康检查，数据库与会话密钥保留。本地节点 #1 的直连 `public_domain` 暂置空，远程 `shared/config/https-deferred.json` 记录待备案域名；当前无 `https-entry.json`，后续程序升级跳过 Let's Encrypt 并保留已有 Cloudflare HTTPS 基础地址。网站入口字段会显示兼容的 IP:5173，实际当前公网入口为 `10ye.cc`。
- 清空前后差异已复核：2026-11-05 曾签发有效至 2027-02-03 的证书，但同日后续记录已出现公网 80/443 的 JDTP403/超时，因此不能将拦截认定为本次删除才发生。2026-11-08 全量清理同时移除证书、私钥及 ACME 账户，恢复必须重新申请并完成公网 HTTP-01 验证，当前拦截使该步骤失败。清理脚本没有修改 DNS、云安全组或云厂商域名策略；拦截发生时间及具体规则仍需京东云确认。
- 原任务 #71 在 36% 报“远程没有可导出的 RynEnglish 运行镜像”：旧脚本依赖已清掉的运行镜像，本机也无离线缓存。新增 `tools/deployment/runtime.py` 和 `deployment/docker/Dockerfile.runtime`，空节点上传 SHA-256 固定的 whisper.cpp 1.7.6 源码与最小构建上下文，目标 Linux 构建 Python/FFmpeg/静态 whisper-cli；探测 Debian 下载源并包含 Git 编译依赖。上下文不含本地账号、配置或书籍。
- 已存在的远程运行镜像立即复用，不再阻塞等待镜像回传；本机离线缓存仍可选，先完整 gzip 校验，再以 pipefail 上传加载。重部署保留无业务数据的基础运行镜像。#88 已实机源码构建并验证命令，真实 JFK 样本使用 base.en 在约 6 秒完成转写；非必要离线回传主动取消。#86/#87 失败验证记录保留。
- Whisper 模型在卸载前按固定 SHA-256 准备；新下载缓存于 `.local/deployment/runtime/models/ggml-base.en.bin`，有效 vendor 模型可复用，自定义 vendor 模型不覆盖。模型准备失败不会卸载远程项目。CPU 对齐包已校验并安装，候选版本通过真实原音 CPU 推理；首次缺失环境显示安装提示，部署进度分别展示验证码、对齐及 HTTPS 阶段。
- HTTPS 脚本签发失败返回专用错误标记/退出码 10，保留应用及既有 TLS 配置；后台明确提示 DNS、80 端口及云厂商放行检查，支持单独补装 HTTPS。错误识别只匹配实际输出标记，避免脚本文本中的标记误报。
- 用户已授权清空整个远程项目（数据库、书籍、音视频、配置及备份）。#62 清理完成，#71 失败后本轮按修复流程执行 #89 恢复；原业务数据已删除，用本机快照初始化。重新部署不做远程数据库备份，程序升级仍备份。旧版本/证书/隧道/备份记录均为历史，不能据此恢复。
- 本轮验证：95 项运行环境/节点/发布/HTTPS/Docker/对齐/验证码测试通过，包含真实隔离 bash 执行；前端生产构建和 modern smoke 通过，Python 编译、diff 检查通过。最终本地后台已重载，六项本地服务保持独立，不使用远程调试隧道。

## 未完成与接续

本节的单域名/Cloudflare 操作已由顶部 2026-11-11 双站待办替代，保留为历史记录，不直接执行。

1. **待用户完成 `rynenglish.com` 域名备案后再处理直连 HTTPS。** 届时核查京东云域名放行，确认公网 ACME 路径到达 Nginx；目前不再申请证书，不影响 Cloudflare 入口服务。
2. 备案及放行完成后，在节点设置重新填写公网域名 `rynenglish.com`，再在仓库根目录执行以下命令，只补装 HTTPS 和续期，不重新导入数据库：

```bash
.local/saas-venv/bin/python tools/run_local_dev.py exec -- \
  .local/saas-venv/bin/python tools/deploy_remote.py \
  --target 1 --https-entry --domain rynenglish.com
```

3. 验收公网域名严格 TLS、首页/API、443 监听、续期 timer 与 renew dry-run。需要 DNS 验证替代方案时，必须先具备 DNS 提供商授权；当前没有相关凭据。
4. #89 保持失败记录（应用可用、HTTPS 未完成），不会补写完整发布成功。日志 `.local/deployment/logs/89.log`；真实转写验收 `.local/local-dev/remote-whisper-probe.log`。本地开发唯一启动指南为 [docs/LOCAL_DEVELOPMENT.md](../../../docs/LOCAL_DEVELOPMENT.md)，管理员主动部署权限保留。

## Cloudflare 日常运维

- SSH 到节点后执行 `systemctl status cloudflared --no-pager` 查看状态，`systemctl restart cloudflared` 重启；`curl --noproxy '*' -fsS http://127.0.0.1:20241/ready` 应返回 status 200 和正数 readyConnections。
- 外部验证：`curl --noproxy '*' --fail https://10ye.cc/api/health`，应为 status=ok、saasEnabled=true、redisReady=true；使用正常证书校验，不加 `-k`。
- systemd 单元 `/etc/systemd/system/cloudflared.service` 使用 `--token-file /etc/cloudflared/rynenglish.token`，凭据不会出现在命令参数； metrics 仅回环。云端域名/回源路由未修改，没有新建临时隧道。
- 这次恢复入口使用已保留的原连接凭据；若再次清空上述凭据，必须从 Cloudflare 原隧道管理页取得连接凭据，不能只靠公开域名恢复。`.local/deployment/restore-cloudflare-20261108.py` 为本机本次操作脚本，不是无凭据安装器。

## 清理前历史参考

以下记录不代表当前在线状态；当前状态以上文及实际远程健康检查为准。

### 2026-11-07 程序升级 #6 本地 JDK 缺失修复

- 用户启动的 `saas_upgrade` #6 在本地构建验证码服务时失败：`Unable to locate a Java Runtime`。SSH和React构建已通过，但本机无JDK；失败前没有上传发布包、执行迁移或切换线上版本，原失败记录保留。
- 已在忽略目录 `.local/captcha-tools/` 下载官方Corretto21 macOS x64并按官方SHA256校验，`jdk`链接指向其Contents/Home，无系统全局Java变更。`services/captcha/build.sh` 增加Java/javac≥17检查、项目JDK自动发现和`--check`，缺失/旧版明确失败；部署错误直接展示缺失依赖原因。验证码构建置于React构建之前，避免依赖不全时浪费前端构建。
- 实际 `build_code_package` 验证通过：Java8项、React生产构建、26.8MiB完整包/JAR/品牌资产/metadata/SHA256检查；43项启动/部署回归、UI22项、modern、JS、Python编译、shell语法和diff通过。本轮当时已重载后台；现由独立本地环境替代。验证包 `.local/deployment/code-local-upgrade-preflight-20261107.tar.gz` 仅本地保存，未上传/激活；用户可重新启动“程序升级”。
- 关键文件：`services/captcha/build.sh`、`tools/deployment/captcha.py`、`manager.py`、`tools/test_deployment_captcha.py`、`test_deployment_release_pipeline.py`。线上current仍为 `code-20261106-113458-43116bfb`；后续真实升级与候选激活尚未执行。

### 本地部署管理与原性能问题

- 本地部署权限继续要求 `SHIYUE_DEPLOYMENT_MODE=local`、回环请求和已认证管理员；未放宽鉴权 / CSRF。SQLite 部署节点 #1 与用户既有 SSH 密钥引用保留，仅供主动节点管理使用。
- 原 API 延迟由跨网建连和多次 SQL 往返放大；远程数据库/缓存调试已撤除，不再恢复旧转发端口或旧启动器。历史远程升级任务保留，生产数据已按上述清空授权删除。

### 2026-11-07 品牌分支正式合并与清理

- 合并提交 `d1ca8d9`（父提交 `0a2f966`、`7b65f78`）已推送 main，远程 `feat/rynenglish-brand` 已删除，本地无同名分支。保留 main 的上传完整性和 Linux 对齐部署修复；隔离构建、modern/UI、38 项邮件/部署/对齐/上传回归、JS/Python/diff 通过。
- 原工作区 673 个文件内容/状态指纹保持，阅读器/导入和额外品牌门禁/测试改动仍未提交；仅交接状态在合并后更新。本轮不重新部署生产，不变更用户数据或现有本地服务。

### 2026-11-07 完整品牌源码同步

- 定位原品牌提交 `7b65f78` 在 `origin/feat/rynenglish-brand`，已上线但未合入 main；后续定向发布只保留线上产物，造成当前工作区遗漏。现按完整提交合入品牌组件/标语/SEO/邮件/法律/截图/运行提示及账号操作，保留本地导入、阅读器、对齐依赖等修复，详见 brand-assets。
- 只读对比生产，`saas_auth.py`、`saas_commerce.py`、`saas_payments.py`、`reader_server.py` 与本地逐字节相同；本轮无生产代码/数据更新。生产已有品牌，相关源码未同步的历史阻塞已解除。
- 安装/重装/升级共用的 `build_frontend_assets()` 新增五个品牌资产、RynEnglish 标题/图标引用检查；缺失中止。打包仍包含完整 reader、tools，新增回归覆盖缺图标/旧标题和品牌归档。无需增加 Linux 依赖或数据库迁移。
- 构建/modern/UI/阅读器回归、19 项邮件与部署测试、相关编译/diff 通过；构建预览 12 路由、隔离账号操作/提醒失败重试、真实三入口验证码通过。后台已重新加载，保留本地前端和受监督隧道；临时候选服务验收后关闭。日志 `/private/tmp/english-reader-ryn-sync/`。

### 2026-11-07 阅读界面细节发布

- 已完成本地源码和生产基线组装候选验证后，定向发布入口 `index-source-7b99f4600df6.js`、模块 `source-reader-72d99f5ab867.js`、CSS `source-reader-51f9ee5047df.css`；翻页 900ms、原书连续底色、紧凑页码/居中保存状态、精读原图铺满列宽。沿用生产 React/Ant Design，43 个导出 AST 校验一致；5 个新增资产 + HTML，248 个保留文件哈希一致，无服务重启、数据库或后台变更。
- 生产基线仍为 `code-20261106-113458-43116bfb`；备份 `backups/saas/reader-polish-20261107/{original-index.tar,manifest.json}`，执行目录 `shared/.local/reader-polish-20261107/`，清单 `manifests/history/reader-polish-20261107.json`。先版本化资产后原子切 HTML，发布前后哈希/严格源站 HTTPS/SaaS/Redis 健康通过。
- 本地构建、modern/UI 22 项、阅读器 Node 7 项/Python 15 项、JS/编译/diff 通过；候选 Chrome 覆盖原 EPUB/PDF、真实两章与目录兜底、纸色/页码/保存状态/900ms 动画、横竖原图/两布局、音频补传；本地真实登录/注册/找回验证码出图通过。实际生产静态文件的四组目录/真实原书、页脚/动画、图片、PDF 原页/空白页/查词/恢复均复验通过，真实未登录入口品牌/验证码开关/401/全部新增资产 200 通过，无页面异常；业务写 API 均在浏览器上下文拦截。日志/截图 `/private/tmp/english-reader-polish/deploy/`，临时候选服务与验收隧道已结束，用户本地 4173/8790/受监督隧道保留。
- 本地标题/图标使用 `frontend/public/brand/` 官方 RynEnglish 资产，详见 brand-assets。保留生产已有品牌/验证码/上传模块，本轮没有发布本地旧官网等无关变化。原品牌提交现已完整同步至当前工作区，见 brand-assets 交接。

### 2026-11-07 本地远程数据调试与阅读交互发布

- 该轮使用过临时远程数据调试，现已删除相关启动器与代理；当前调试统一使用独立本地环境，阅读器的既有生产发布结果保留。
- 阅读器修复精读名称、原文件目录/同文件锚点、词背景/指针和翻书动效；详见 reader。实时生产基线组装候选并完成本地浏览器/构建/相关测试后，定向发布入口 `index-source-596c367b06f6.js`，模块 `source-reader-093be4088218.js`；新增 7 个静态资产 + HTML，241 个原文件哈希保持，保留 RynEnglish/验证码/音频补传。无需后台更新、迁移或重启。
- 发布目录 `shared/.local/reader-interactions-20261107/`；备份 `backups/saas/reader-interactions-20261107/{original-index.tar,manifest.json}`，清单 `manifests/history/reader-interactions-20261107.json`；基线/发布/保留哈希和严格源站 HTTPS 首页、SaaS/Redis 健康通过。仅前端发布，未写生产书籍/账号/学习数据。发布候选与验收日志 `/private/tmp/english-reader-interactions/deploy/`；发布后实际静态文件经隔离 Chrome 复验最新原书两章节、EPUB 2/3/缺失目录、词悬停/翻书、PDF 原页/空白页/查词/恢复、系统设置改名均通过；真实未登录入口的品牌/验证码/401 与全部新资产 200 通过，无页面异常。

### 2026-11-07 原文件泛读定向发布

- 用户授权“部署到线上我看一下”。当前入口 `/assets/index-source-abd3103b9d5f.js?v=abd3103b9d5f`，阅读器模块 `source-reader-095d7575ec22.js`，新增 EPUB/原文范围/PDF 模块及作用域 CSS 共 7 个静态文件；release 指针仍为 `code-20261106-113458-43116bfb`。PDF 原页与新 EPUB 原 XHTML/CSS/字体/图像直接加载，旧书不回填；具体产品行为见 reader、import-media。
- 从实时生产归档构建候选，仅替换已发布入口的 reader import，原 ImportModal/LibraryPage/CatalogModeration 等字节保持；43 个 Ant Design 导出实现 AST 校验后映射，复用生产 React/主题。237 个保留文件哈希通过，包含原品牌/CSS/验证码/音频补传、旧入口和代理/对齐 helper。
- 后端更新 `epub_document.py`、`reading_document.py`、`saas_imports.py`、`saas_catalog.py`、`saas_workspace.py`，新增 `source_reading.py`；`reader_server.py` 只改进度路由的 readingLocation 参数，保留线上较新品牌内容。正常安装/升级会打包全部 tools/*.py 与 reader 静态资源；无新 Linux 运行依赖和 schema 迁移。原品牌提交现已完整同步至当前工作区。
- 发布前确认无活动导入，备份 `/srv/shiyue/backups/saas/source-reader-20261107/{database.dump,database.list,original-code.tar,deployment-manifest.json}`；pg_restore 列表验证通过。宿主机原子放置版本化资源与后端，仅重启 SaaS，健康通过再切 HTML；失败只恢复代码，不回滚数据库。清单 `/srv/shiyue/manifests/history/source-reader-20261107.json`，执行目录 `shared/.local/source-reader-publish-20261107/`。首次解包因容器路径测试符号链接失败、未改生产；重命名该夹具后成功发布。
- 实际候选后端 Linux Python 3.11 隔离库/单元 61 项通过；候选及真实生产静态文件 Chrome 覆盖原 EPUB 字体/插图/排版/固定画布/精确位置/切章、PDF 原页查词与空白页恢复、资源限制、音频补传、失败重试，无页面异常。交互业务 API 使用隔离拦截，真实生产另核实 RynEnglish 登录、验证码开启、未登录接口 401、全部新增资源 200。
- 源站严格 HTTPS 首页/API、SaaS/Redis、发布和保留文件哈希验收通过，生产导入状态仍 complete 5/cancelled 8，未写生产书籍或学习数据。专用 `source_reader_publish_20261107_test` 已删除。开发机公网域名 TLS 仍需区分既有网络限制，SSH 隧道验收正常。

### 2026-11-07 配套原音可恢复上传定向发布

- 用户报告线上再次停 15%；定位文档已到达、音频请求被完整性校验拒绝，后端未启动。已发布配套 MP3 的 256 KiB 分段校验、重试、断点补传及私人/官方列表恢复入口。具体业务/API/恢复状态见 `../import-media/HANDOFF.md`；不接受残缺音频，不改其他媒体处理策略。
- release 指针仍为 `code-20261106-113458-43116bfb`，当前入口 `/assets/index-import15-206bdef9aa05.js?v=206bdef9aa05`，模块 `/assets/import-upload-6cf1568944cf.js`。只替换入口的 ImportModal、LibraryPage、CatalogModeration，复用原 React / Ant Design；官方组件变更前与基线做 AST 一致性检查，保留已上线泛读、品牌、验证码及 232 个既有静态文件哈希。
- 后端新增 `import_audio_upload.py`，更新 `saas_imports.py`，reader_server 只移植两个导入路由方法、前台服务只移植 `_proxy`，避免覆盖线上较新代码。正常安装/升级的 `tools/*.py` 与完整 reader 归档自动包含新 helper 与构建结果，无新增依赖、配置或 schema 迁移。原品牌提交现已完整同步至当前工作区。
- 备份 `/srv/shiyue/backups/saas/import15-20261107/` 包含通过 `pg_restore --list` 的生产 dump 和原文件；清单 `/srv/shiyue/manifests/history/import15-20261107.json`。先校验基线/候选哈希，宿主机原子替换，重启 SaaS 与前台服务，健康通过后切 HTML；发布文件与保留文件最终核验通过，源站严格 HTTPS 首页和 API 正常。未修改 current、数据库结构或旧书数据。
- Linux 隔离测试 26 项、客户端 4 项、构建/modern/UI 22 项/JS/Python/diff 及候选 Chrome 私人/官方补传与泛读检查通过。新任务已恢复完成，完整原音 8,159,161 字节/1,011.947378 秒、词覆盖 98.81%、206 句/89 原文块；结果 `shared/.local/import15-20261107/recovery-result.json`。真实生产 SSH 隧道 Chrome 验证入口、品牌登录页、私人/官方 401 及零页面异常通过，线上 HTTPS/SaaS/Redis 与发布哈希复查正常。专用 `companion_upload_20261107_test` 已删除。

### 2026-11-07 泛读模式定向发布

- 用户明确授权“部署远程我看一下”。保留数据的定向升级已完成，release 指针仍为 `code-20261106-113458-43116bfb`；前端入口 `/assets/index-extensive-73a8f1652388.js?v=73a8f1652388`，阅读器模块 `/assets/extensive-reader-1345b43bb194.js`，新增作用域 CSS 与本地 PDF.js/字体/CMap/WASM。旧入口、CSS、RynEnglish 登录/品牌、验证码、上传修复及其他现有资产全部按原哈希保留。只替换生产入口中的 ReaderPage 与设置项文字；阅读器通过独立模块复用生产 React / Ant Design，43 个 Ant Design 导出实现经 AST 核对后映射，避免主题上下文分裂。
- 后端只合入 `saas_imports.py`、`epub_document.py`、`saas_catalog.py`、`saas_workspace.py` 并新增 `reading_document.py`；4 个原文件与本地 HEAD 一致才应用改动。安装/升级的 `code_files()` 已使用 `tools/*.py` 并归档完整 reader 目录，新文件及 PDF 资源会随正常构建入包；原品牌提交现已完整同步至当前工作区。无 schema 迁移，既有书籍与学习记录不修改。
- 发布前检查没有进行中的导入任务。备份 `/srv/shiyue/backups/saas/extensive-reader-20261107/database.dump`（`pg_restore --list` 可读取）及 `original-code.tar`；清单 `/srv/shiyue/manifests/history/extensive-reader-20261107.json`，含 210 个发布文件与 31 个保留文件的哈希。发布脚本/验证/回归日志在 `shared/.local/extensive-reader-20261107/`。第一次写入因 `/app` 代码只读挂载被拒绝，自动恢复原代码；修正为宿主机原子替换后成功。先放入版本化资产和后端、健康通过后原子切换 HTML；失败只回退代码，不自动恢复数据库。
- Linux Python 3.11 隔离 PostgreSQL 回归与单元检查 18 项通过，包括真实 EPUB 导入持久化、真实 PDF OCR（含空白页）及 TXT/MP3/视频原路径。构建、modern smoke、UI 22 项、Python 编译、diff 与候选 Chrome 验收通过。实际生产登录页的品牌、验证码开启、未登录 API 401 与原 CSS 已检查，无页面异常；阅读交互用生产静态文件和隔离模拟 API 验证，不写入生产用户数据。
- 源站标准 HTTPS 首页/API 200、后台与 Redis 健康，原前台/验证码/HTTPS 容器不需要重启；发布文件与保留文件的最终哈希一致，业务导入任务仍为完成 4/取消 8。通过 SSH 隧道服务真实生产静态文件的全套泛读浏览器检查通过（模拟 API，仅测试上下文），零页面异常；专用 `extensive_reader_20261107_test` 已删除。开发机公网域名 443 仍有既有 TLS 超时，外部网络访问需用户确认。

### 2026-11-07 Linux 安装与升级补齐原音对齐

- 首次部署、完整重装、程序升级共用 `ensure_remote_aligner`，不受可选 Whisper 录音开关影响。已通过校验的 `shared/.local/forced-aligner` 复用；缺失/损坏时，由部署端下载目标 Linux CPython 3.11 的 CPU wheels 和固定 SHA-256 模型，校验缓存、打包并上传，远程禁网离线安装，避免远端慢速模型下载导致导入卡住。
- `tools/forced_aligner_setup.py` 与 `tools/install_forced_aligner.sh` 支持在线安装、`--offline-dir`、`--check`；固定 numpy 1.26.4、torch/torchaudio 2.2.2（Linux x86_64 为 +cpu），模型与当前生产一致。安装有文件锁、新环境通过后才替换 venv 链接，失败保留旧环境；模型下载/复制先校验再原子替换。发布包包含安装器和检查工具。
- 候选服务上线前检查实际运行环境（含自定义 CTC 路径）、模型 SHA-256、FFmpeg 16kHz 解码、numpy/Torch 兼容、wav2vec2 CPU 推理与原生 forced_align 扩展。任一步失败即停止，不切换 current、不停旧站；无需额外 WebSocket 或新业务接口。
- 验证：Linux x86_64 隔离目录首次离线安装、真实推理、实际部署 helper 复用检查通过；完整 CPU 依赖解析/593,930,240 字节模型包校验通过。Python 3.11 下 79 项部署、34 项上传/对齐/隔离 PostgreSQL 导入回归全部通过；构建、modern smoke、UI 22 项、JS、Python 编译与 diff 检查通过。ARM64 已提供平台包选择，尚无 ARM64 实机验收；未对任何生产节点执行完整重装。开发机默认 Python 3.9 的完整部署测试有 3 项因既有 `Path | None` 导入不兼容而失败，已在 Linux Python 3.11 全部重跑通过。
- 新文件：`tools/deployment/alignment.py`、`tools/forced_aligner_setup.py`、`tools/test_deployment_alignment.py`、`tools/test_upload_integrity.py`。首次部署端下载需可访问 Python 包源/PyTorch，之后复用经校验缓存；远端安装本身不依赖公网包源。

### 2026-11-07 导入故障定向修复

- 实机基线为 `code-20261106-113458-43116bfb`。本轮按用户授权备份 PostgreSQL（pg_restore --list 校验）与原代码后，定向热修复导入上传启动、部分原音校验和前端导入组件；保留线上数据、RynEnglish 品牌、验证码与现有 CSS。备份 `/srv/shiyue/backups/saas/import-recovery-20261107/`。
- 当前 release 目录未切换。后续定向修复加入前台代理/后端上传完整性校验，并撤回接受部分音频的临时方案；前端仅替换 ImportModal/LibraryPage 组件。线上 11 月 6 日品牌提交现已完整同步至当前工作区。
- CPU 对齐环境与模型在既有持久化 `shared/.local/forced-aligner/`，不改容器挂载或全局配置。最终上传完整性修复已发布，前端入口 **`c03008a13c69`**；原任务已更正为完整音频 8,159,161 字节/1,011.947378 秒，2,073/2,098 词实测时间，原书 ID/学习记录保留。备份 `backups/saas/upload-integrity-20261107/` 含可读取 pgdump 和原代码，清单 `manifests/history/upload-integrity-20261107.json`；实际前台短读请求返回 400，后台/前台/Redis 健康。恢复详情见 `../import-media/HANDOFF.md`。

### 2026-11-05 验证码与 DirectMail 已发布

- 用户授权程序升级及图片恢复任务 #3 complete，当前版本 `code-20261105-173117-956a2f49`；远程数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261105-173117-956a2f49.dump`，保留线上数据。
- 新增 `shiyue-captcha` Java 内部服务（回环 18080，候选 18081），独立权限 0600 的 `shared/config/captcha.env`；非 root、只读根目录、512 MiB、pids 128。安装/升级自动构建与探测，卸载/重装清理容器和镜像。
- CLI 新增 `--identity-file` 与可选 `--smtp-config`，配置仅白名单合并；不再执行环境文件，保留字面值与原密钥。
- 生产验证码已开启，DirectMail 已加载且测试邮件 SMTP 接受。服务器侧标准 HTTPS、原公网 5173 和 Cloudflare 回源/公网 API 均正常；本机公网域名 80/443 出现 JDTP403/超时，待核实外部网络或云侧限制。详见 `../auth-captcha/HANDOFF.md`。
- 修复版单层居中弹窗、SDK 坐标归一化已发布；按用户最新反馈恢复原动物图片。Cloudflare 公网入口真实 Chrome 旋转校验成功并提交找回密码200（不存在的测试邮箱）。

### 2026-11-05 标准 HTTPS 入口已上线

- 用户确认现用域名为 `rynenglish.com`，解析到京东云 `117.72.209.44`。已按用户确认实施 Docker Nginx + Certbot，仅调整入口和后台 `APP_BASE_URL`，现有程序版本仍为 `code-20261027-151445-6f1c16a2`，应用镜像 SHA 未变；数据库、Redis、媒体及 Cloudflare Tunnel 保留。
- 标准入口为 `https://rynenglish.com`。80 普通请求返回 308 到固定域名并保留路径/查询参数，IP 的 HTTP 请求也跳转到域名；HTTP `/.well-known/acme-challenge/` 独立 webroot，缺失文件 404。443 使用 Let's Encrypt YE1 证书，当前有效至 **2027-02-03 02:11:59 UTC**；不需要用户安装自建根证书。原 5173 自建证书入口保留兼容，后端 8790、PostgreSQL 5432、Redis 6379 仍仅回环。
- 运行环境为 CentOS 7、Docker 26.1.4、systemd 219。Nginx 容器 `shiyue-https` 使用 `nginx:1.28-alpine`（实机 1.28.3），Certbot 使用 `certbot/certbot:v5.4.0`；按项目既有方式支持 m.daocloud.io 镜像拉取及官方源回退，不改宿主 Docker 仓库配置。代理上传上限与应用视频上限对齐为 20 GiB，关闭代理请求/响应缓冲。
- 证书、账户、Nginx 配置及续期脚本持久化于 `/var/lib/shiyue/https/57dfc879ad04/`（安装目录 SHA-256 前 12 位），在应用安装目录之外。重新安装应用不删除该目录；共享配置清单为 `/srv/shiyue/shared/config/https-entry.json`。
- `shiyue-https-renew-57dfc879ad04.timer` 已 enabled/active，每天服务器本地时间 **03:00、15:00** 检查并按需续期，`Persistent=true`；续期成功后校验并重载 Nginx。安装和续期共用 flock，失败保留有效配置/重载标记。实际执行 `renew.sh --dry-run --run-deploy-hooks` 成功并验证重载；未覆盖生产证书。
- `APP_BASE_URL=https://rynenglish.com` 已生效；更新前的 env 与容器配置备份位于 `/var/lib/shiyue/https/57dfc879ad04/backups/entry-20261105-111036-5cf36450/`，权限 600。后台以原镜像及原代码重建，失败时恢复旧容器和 env。未发布本地业务程序或重新初始化数据库。
- 本地源码已同步：`tools/deployment/https_entry.py` 负责入口生成与续期，`manager.py` 的首次安装/升级共用入口流程；升级前从远端清单恢复域名，避免旧本地节点回退旧域名。节点持久化 `public_domain` 并校验，平台表单显示域名及内部应用端口；无域名的旧节点兼容原路径。仅当前仓库涉及改动，已检查指定 idea/webstorm 源码目录，无跨仓依赖。
- `tools/deploy_remote.py --https-entry` 可独立配置入口，支持 `--target` 或 `--host` + `--identity-file`；`--domain` 指定域名，`--acme-email` 可选。显式私钥模式复用默认 known_hosts 并严格校验，不读取/保存私钥内容；本次 ACME 账户未设置联系邮箱。
- 验证：前端构建、modern smoke、UI 22 项、JS 检查、Python 编译、diff 检查通过；部署/HTTPS/节点/发布流程 44 项、入口模块 16 项、其他部署/路由 10 项全部通过。独立规格与质量审查通过；发现的 1 GiB 入口上传限制已修为 20 GiB。构建后还原已跟踪生成物，仅保留源码改动。
- 实机验收：公网域名/IP HTTP 跳转及路径参数正确；HTTPS 首页/API 为 200，本机指定公网 IP 的严格 TLS 校验结果为 0；运行镜像及 current 指针未变、SaaS/Redis 健康，续期 dry-run 成功，timer active，实际 systemd 续期服务 `Result=success/ExecMainStatus=0`。未登录 `/api/auth/me` 返回 401，HTTP 验证路径缺失文件返回 404。既有真实 TLS/双 Secure Cookie 代理回归通过；未使用生产用户登录。当前无阻塞，源码、测试及部署架构文档一同交付；开发分支为 `feat/https-standard-entry`，合并目标为本地 `main`，提交与合并结果以 Git 历史为准。

### 已部署实现（2026-10-27）

- 本地 Vite 默认端口从 5173 改为 **4173**（`http://127.0.0.1:4173/`），`strictPort: true` 避免端口占用时静默漂移；本地 API 仍为 8790，远端前台继续使用 **HTTPS 5173**。本地已启动且首页/API 代理 200；启动命令 `npm run dev:modern`，后端为 `./start-reader.sh --saas-local 8790`。日志分别为 `.local/logs/vite-4173.log`、`.local/logs/saas-local-8790.log`；布局检查脚本默认地址同步更新到 4173 根路径。
- SaaS 首次部署、重新部署和程序升级统一启用公网 `https://<节点 host>:5173`，后台仍仅监听回环 `8790`；旧节点保存的 HTTP/8765 配置会在本次任务内按 HTTPS/5173 执行，成功后回写节点配置。CLI `--upgrade` 或平台“程序升级”可保留远端数据并切换 HTTPS，无需重装。
- 升级补齐 `ensure_remote_tls` 和 `ensure_remote_saas_config`，先准备证书与入口配置，再以 HTTPS 验收候选端口 15173 和正式端口 5173。已有 HTTPS 自定义域名 `APP_BASE_URL` 保留，HTTP/缺失或与节点 host 相同的地址改为 `https://host:5173`；数据库/会话密钥保留，配置更新使用现有运行镜像，无需宿主 Python。
- 完成结果增加 `frontendUrl`、本机 `rootCertificate` 路径。使用自建 CA，新生成证书补齐 CA/服务端约束、密钥用途和 AKI/SKI；浏览器需安装并信任返回的根证书才能正常受信任直连。新签发流程不再上传 CA 私钥；复用前用本机新版 OpenSSL 严格验证证书链、有效期和 host，避免远端 OpenSSL 1.0.2 放行旧证书。无效本机缓存先改名备份再换发。跨主机回源使用 HTTPS；同机 Tunnel 兼容方式见下一条。
- 已核对京东云 Cloudflare Tunnel 现有回源为 `http://localhost:5173`。`saas_frontend_server.py` 的 TLS 监听支持同端口仅回环 HTTP，保留现有 Tunnel 回源；公网非 TLS 连接拒绝。TLS/本机 HTTP 共用原前台代理与鉴权逻辑，不关闭 Secure Cookie。新增真实 TLS + 本机 HTTP 共存和拒绝公网明文/清理握手失败连接的回归。
- 2026-10-27 已按用户授权执行京东云程序升级，最终任务 **#26157 complete**，生产版本 **`code-20261027-151445-6f1c16a2`**。数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261027-151445-6f1c16a2.dump`，保留远端数据，候选/正式容器、迁移、current 指针和挂载验收均通过。
- 公网 `https://117.72.209.44:5173/` 与 `/api/health` 在显式信任根证书并开启严格验证时返回 200，SaaS/Redis 健康；公网 HTTP 拒绝；未登录 `/api/auth/me` 正常 401。Cloudflare `https://10ye.cc/api/health` 和本机 Tunnel HTTP 回源均 200。根证书为 `.local/deployment/certificates/117.72.209.44-rootCA.pem`，需访问设备自行安装并信任；未改系统证书信任或使用生产账号登录。
- 验证：构建、modern smoke、UI 22 项、JS/布局脚本语法、Python 编译、diff 检查和 45 项部署/路由回归通过，包含旧 HTTP 节点切换、保留 HTTPS 域名/密钥、旧证书换发、严格 TLS 验证、真实代理传递双 Secure Cookie 后 `/me` 返回 200（隔离假 API，非生产账号）。Vite 实际加载配置确认 4173/strictPort。

- 平台页面位于 `frontend/src/pages/PlatformOperationsPage.jsx`。已部署节点的“重新部署”使用橙色描边警示样式，并排在节点操作区最后；首次部署保持普通按钮样式。重部署确认框说明数据来源及替换范围。
- 重新部署包在本地构建 React 前端后归档 `reader/`。首页引用的三张产品截图必须存在于构建产物，缺少任一张时打包失败：
  - `reader/site/product/reader-word-panel.jpg`
  - `reader/site/product/workspace-current.jpg`
  - `reader/site/product/learning-insights.png`
- 本机前端构建和数据库快照先于远端卸载执行；本地构建失败时不会先拆除远端服务。重新部署不备份远端数据库，程序升级仍备份。截图来源为 `frontend/public/product/`。
- 线上静态服务对图片返回一年 `immutable` 缓存。首页截图 URL 现带图片内容 SHA-256 前 12 位作为 `v` 参数；图片变更会同时生成新 URL 和新入口版本，避免浏览器继续使用旧截图缓存。只需运行“程序升级”发布该前端修复，无需完整重新部署。
- 2026-10-25 只读核对：生产当前版本 `code-20261025-104352-3e65cccf` 的三张图片哈希与本地相同，证明截图文件已经随近期发布到达生产；但生产响应仍为一年 `immutable` 缓存。部署记录中最近任务类型为 `saas_upgrade`，不是 `saas_redeploy`。内容哈希 URL 修复目前仅在本地，未执行生产发布。

## 关键文件

- `AI_CONTEXT/tasks/platform-operations/DEPLOYMENT_ARCHITECTURE.md`：京东云生产访问链路、容器/端口、配置与数据目录、证书续期及常用运维命令（2026-11-05 实机核实）。
- `frontend/src/pages/PlatformOperationsPage.jsx`：部署操作、顺序、确认文案。
- `frontend/vite.config.js`：首页截图 URL 内容版本化及入口缓存版本。
- `tools/deployment/manager.py`：前端构建、发布包、SaaS 部署任务。
- `tools/deployment/https_entry.py`：标准入口、ACME 验证、持久证书及自动续期脚本生成。
- `tools/deploy_remote.py`：命令行打包与部署入口。
- `tools/test_deployment_release_pipeline.py`：发布包、截图与部署流程回归。
- `tools/test_deployment_https.py`：HTTPS 配置、旧节点升级和真实 TLS/Cookie 代理回归。
- `tools/test_deployment_https_entry.py`、`tools/test_deployment_https_integration.py`：入口重复安装/失败回滚/续期和节点/CLI/应用重建集成回归。
- `tools/deployment/saas_public_sync.py`：官方内容增量同步。

## 验证

```bash
npm run build:modern
npm run test:modern
npm run test:ui
PYTHONPATH=tools python3 -m unittest tools.test_deployment_release_pipeline
PYTHONPATH=tools python3 -m unittest tools.test_deployment_alignment tools.test_upload_integrity tools.test_book_audio_alignment
PYTHONPATH=tools python3 -m unittest tools.test_deployment_https_entry tools.test_deployment_https_integration
PYTHONPATH=tools python3 -m unittest tools.test_deployment_https tools.test_deployment_nodes tools.test_deployment_docker_install tools.test_deployment_dioco_config tools.test_deployment_content_paths tools.test_deployment_grammar_content tools.test_saas_frontend_routes
python3 -m py_compile tools/deployment/manager.py tools/deploy_remote.py tools/test_deployment_https.py tools/test_deployment_release_pipeline.py
git diff --check
```

## 运维约束

- 程序升级与完整重新部署不可互换：升级保留远端数据；重新部署以本机数据库快照替换远端数据。
- 重新部署不创建远程数据库备份。程序升级等保留数据操作按对应流程备份；失败后的数据库恢复需人工确认，避免覆盖备份后新增的数据。
- 不在文档、前端或日志中记录完整密码、Token 或密钥。
