# 纸间微光博客与阅读子域名

更新时间：2026-11-14（Asia/Shanghai）

## 国内业务备案页脚与抓取策略（本轮）

- 2026-11-14：阅读页及其登录恢复骨架隐藏备案页脚，移除额外124px占位，避免全高阅读器撑开网页；登录/注册/工作台继续显示。仅国内 `SiteFrame` 样式扩展；双站Chrome验证正常/加载/失败和两种PC视口无额外页面高度，返回设置国内页脚恢复。两站/博客构建、隔离及基础检查通过，已统一发布#345。
- 国内扩展，已合入main；不复制共享业务。`@site.SiteFrame` 在国内登录/注册/工作台等非阅读页面底部居中展示 `蜀ICP备2026071122号-1` 并链接工信部，国际透传 children。页脚正常文档流，阅读页隐藏并保持全高布局。
- `saas_frontend_server.py` 仅国内 app Host 返回 `/robots.txt` 的 `User-agent: * / Disallow: /`，GET/HEAD及查询串有效；该入口页面、静态资源、API和错误响应均带 `X-Robots-Tag: noindex, nofollow`。不按 User-Agent 区分响应，不新增JS校验或抓取身份检测。主域博客/IP博客预览与国际站维持既有抓取策略。
- 标准抓取/索引指令不等于访问控制，不能保证所有爬虫遵守、已收录URL立即消失或不被检查。业务数据继续由既有鉴权保护。
- 本地已通过：两前端构建及源码/产物隔离、真实HTTP网关/Host/路由23项、双站浏览器fixture（国内登录/注册/已登录设置页备案号，国际套餐/支付状态与无国内页脚）、modern/UI/JS检查、博客51页19文章构建与审计。新增HTTP用例修改前失败，修改后通过。浏览器截图 `/private/tmp/english-reader-dual-entry-check/cn-{login,app}-record.png`。
- Python编译、JS语法及diff检查通过；已完成下述#25同步发布与公网验收，无本轮未完成代码事项。不得覆盖线上云猫配置或使用 `--defer-https`。

## 最新程序发布

- 2026-11-14 **#345 complete**：源码main `db3999f`（clean），`current=code-20261114-192419-b830b3d5`；国内/国际/博客/共享后端同步保数据升级。20项公网检查、双站资源哈希及真实三入口Chrome通过；线上静态资源配隔离API验证阅读页无备案/额外页面高度、非阅读页备案保留。账号/书籍/音频/配置升级前后只读核对一致；详见阅读器交接首节。

- 2026-11-13 **#25 complete**，源码 `4ab76c1`（clean），`current=code-20261113-120608-54bdf2ae`。保数据同步发布两前端/博客/共享后端，完成候选双入口、迁移0045、原音检查与整体切换；备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261113-120608-54bdf2ae.dump`，包SHA-256 `2f566eb6246e5491d641c82bf8f58f7dd529fce2c2f10038f67cb6ada9c8bd5b`。
- 严格TLS公网验证：learn根路径/登录/app/JS/API/404均有noindex,nofollow；robots GET/HEAD及两种UA正确，登录HTML对两种UA字节一致。博客首页和robots无该头，博客HTML与本地逐字一致且无业务域名；国际健康ok，两套餐cloudcat与原URL保留；国内两域HTTP308跳HTTPS。Chrome确认国内登录备案号居中及查询链接、博客隔离、国际购买弹窗要求登录且无国内页脚，页面异常0；未登录真实账号或创建支付。已登录应用页使用隔离fixture验收。报告 `/private/tmp/cn-icp-robots-production.json`，截图 `/private/tmp/cn-login-icp-production.png`，发布日志 `/private/tmp/cn-icp-robots-deploy.log`。沿用精确locale警告过滤包装，不改发布器源码。

- 2026-11-13 **#24 complete**，源码 `5da28cc`（clean），`current=code-20261113-111607-f7884945`。共享AI默认免Token修复随国内/国际/博客/后端同步发布，博客内容/样式保持#23；51页19文章审计、博客公网HTTPS200与80跳443、双站健康通过。国内 `https_deferred:false` 保留；详情见 [平台交接](../platform-operations/HANDOFF.md)。下方#23与HTTPS入口版本号为当时记录。

## 国内 HTTPS 已启用（2026-11-13）

- 用户授权 Let’s Encrypt 与80自动跳443，使用现有 `--https-entry` 入口配置流程，为 `learn.rynenglish.com` 和 `rynenglish.com` 分别签发证书，有效至2027-02-11。国内HTTPS仍转5174；HTTP返回308并保留路径/查询参数，ACME验证路径除外。`sites.json` 已保存 `https_deferred:false`，后续升级不得再传 `--defer-https`。
- 未发布业务代码；`current` 保持#23的 `code-20261113-103129-858fe5ab`。国际5173/Cloudflare与API8790保持原拓扑。入口配置备份：`/var/lib/shiyue/https/57dfc879ad04/backups/entry-20261113-105721-02187a67`。
- 公网固定真实IP的严格TLS检查：博客200、learn健康正常，两域HTTP308；真实Chrome从HTTP登录页跳HTTPS后验证码生成200、旋转图片可见、匿名Cookie为Secure/HttpOnly/SameSite=Strict，未提交账号登录。博客备案显示正常，国际HTTPS健康正常。43项入口/集成/双入口部署测试通过。
- 续期定时器 `shiyue-https-renew-57dfc879ad04.timer` 已active/enabled，每日03:00/15:00运行，脚本 `/var/lib/shiyue/https/57dfc879ad04/renew.sh`。`--dry-run --run-deploy-hooks` 两域模拟续期及Nginx语法检查/重载均通过。入口日志 `/private/tmp/english-reader-https-entry.log`，续期日志 `/private/tmp/english-reader-https-renew.log`，浏览器截图 `/private/tmp/english-reader-https-captcha.png`。

## 本轮：AI英语工具主题

- **最新页脚发布#23 complete**：`current=code-20261113-103129-858fe5ab`，源码 `ce05402`（clean），同步保数据升级两前端/博客/后端。左侧站点介绍、中间备案号、右侧版权，删除底部归档/标签/RSS链接；小屏堆叠且版权右对齐。仅国内博客 `Footer.astro`/`paper.css` 改动。构建/51页19篇审计/diff-check通过，本地与公网Chrome测量备案中心及版权右边缘对齐，公网HTML匹配本地，国际HTTPS健康正常；截图 `/private/tmp/footer-layout-production.png`。构建产物已恢复，沿用#21临时locale过滤包装。

- 用户已提供备案号 `蜀ICP备2026071122号-1`，已填写国内博客 `blog/src/config.ts` 的 `icpRecord`，沿用公共页脚链接工信部备案查询；首页及博客各页面一致展示。仅国内博客扩展，沿当前 `feat/blog-ai-english-tools` 分支保留已发布主题。
- **备案号发布#22 complete**：双前端/博客/后端同步保数据升级至 `code-20261113-102413-ab033c51`，源码 `6d892f4`（clean）；备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261113-102413-ab033c51.dump`。博客构建0错误、51页/19篇审计通过，候选两入口/迁移/原音检查通过。公网IP5174首页逐字匹配本地，Chrome确认备案号可见且链接为 `https://beian.miit.gov.cn/`，国际HTTPS健康正常。首页SHA-256 `8a4e9881143702853d36366243a70454de8faa5c2186cc7c808529fc5acf575e`，截图 `/private/tmp/icp-production-footer.png`。沿用#21临时locale过滤包装，未修改发布器；构建产物已恢复不提交。

- 用户授权修改并发布国内博客；从 `main@05e92cc` 创建 `feat/blog-ai-english-tools`。仅国内博客扩展，国际与共享阅读/API/数据库无改动，发布仍同时交付两前端/博客/后端。
- 新增导航首位 `english-tools` 英语工具，4篇2026-11-13原创文章：词汇卡、情景口语、英文写作反馈、原音听力复盘。原 `prompt-notes` 栏目删除，3篇原文章移至 `ai-reading`，保留URL和发布日期。栏目当前4/3/9/3，共19篇。
- 首页、精选、英语工具箱、学习路线、插画、站点描述/标语、关于与页脚统一AI英语学习定位；公开内容是方法与模板文章。保留纸色版式与全本地资源，无新增业务接口。
- 构建和输出验证通过51页/19篇；验证脚本新增旧栏目输出不存在、迁移归属与英语主题断言。Chrome验证栏目4/3/9/3、归档19篇、3个迁移文章原URL/新归属、明暗/目录、390px无溢出，资源与页面无错误；20项博客/双入口部署回归通过。首页英语精选/工具箱与延伸阅读不重复展示文章。
- **最新发布#21 complete**：`current=/srv/shiyue/releases/code-20261113-095135-d559ce0c`，源码 `f55dbe9`（clean），包SHA-256 `3219b3fadf713dc8ca1c0fa754856d8b457a92d9264586894f34a4cdcaa8d708`。保数据同步升级国内/国际/博客/后端，完成双构建、候选、迁移及原音检查；备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261113-095135-d559ce0c.dump`。7容器运行、sites配置保持，发布前后仍1用户/2书目/2内容书/0支付订单/0订阅。
- 公网IP5174的50个正常页面HTTP200且SHA-256逐页匹配本地，旧栏目404/API404；Chrome首页→英语工具→文章/目录真实点击通过，无资源/pageerror，截图 `/private/tmp/english-tools-production.png`。首页SHA-256 `62aa601ba0614eb44643e2636851d12869c8180ff51d7ecb7036e2cf50ab1e26`。国际HTTPS健康status=ok、redisReady=true。浏览器首次点击检查因未等待导航而读到旧首页数量，补充URL/栏目就绪等待后重新验收通过。
- #20在切换前读取sites时失败：SSH输出的固定locale警告穿插JSON。#21仅在本次Python发布进程包装Remote.ssh，过滤精确匹配的 `bash|/bin/sh: warning: setlocale: LC_ALL: cannot change locale (C.UTF-8)` 行，日志仍保留原文且非零退出仍报错；未修改服务器/发布器源码。后续若复现，应修复输出分离或locale环境，不能据此把有效配置改成单站。下方#19为本轮前线上基线。

## 目标与边界

- 用户确认 Astro + Retypeset 独立博客和“纸色手记”改版；主域 `rynenglish.com` 展示公开文章，阅读业务在 `learn.rynenglish.com`。实施分支 `feat/dual-entry-commerce` 已获用户验收，2026-11-12本轮合并推送至默认主线 `main`；后续修改边界与双程序同步发布规则见根 `AGENTS.md` 及 `docs/DEPLOYMENT_SITES.md`。线上仍为下述#19，本轮文档/默认升级命令调整不重新发布业务。
- 主站不链接业务站、不代理API，不加载登录/支付业务资源；所有访客与User-Agent一致。域名分站不替代实际服务的备案和合规要求。
- 国内/国际双前端和共享后端详见 [双入口交接](../dual-entry-commerce/HANDOFF.md)；端口与升级配置见 `docs/DEPLOYMENT_SITES.md`。

## 原AI手记改版基线（本轮已在上方更新）

- 2026-11-12新增12篇原创AI文章，四个一级栏目各3篇：AI入门、提示词手记、AI与阅读、实践与思考。原3篇阅读随笔保留2026-11-11日期与地址，归入AI与阅读（合计6篇），全站15篇。不虚构作者经历、研究结果或旧发布日期。
- 首页采用米白纸色、墨绿/暖橘细节与中文衬线字体；横向导航、书页SVG插画、栏目卡片、精选文章、最新6篇双栏、个人小笺/阅读路线/RSS侧栏。保留暗色切换、正文目录和标签。
- 新增 `/categories/<slug>/` 四个栏目页和 `/archives/` 完整归档（含置顶）。计数按真实内容生成；schema要求每文属于一个栏目。关于页与站点描述同步AI手记定位。
- 参考链接仅允许验证脚本中的4个精确原始资料URL（Transformer/RAG论文、NIST风险资料、Anthropic工作流介绍），脚本/图片/字体等资源全本地。仍禁止业务域名/API与第三方集成。
- 设计与执行清单：`docs/superpowers/{specs,plans}/2026-11-12-ai-journal*.md`。

## 上一版本#19发布与验证

- 京东云任务 **#19 complete**，`current=/srv/shiyue/releases/code-20261112-180050-05f3c3a1`，源码 `e8b1ccd3884361a302127f35d7fbd3c13e7e841c`，sourceDirty=false。发布包SHA-256 `887281f0e8166b1a1be33dc597e7835eb39628c2c49daecb6e60a8630581b67a`。
- 保数据升级完成双React/博客构建、验证码测试、候选双前端/迁移0045/真实原音CPU检查和正式切换。备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261112-180050-05f3c3a1.dump`。发布前后只读核对均为1用户/2书目/2内容书/0支付订单/0订阅，7容器运行。
- 公网预览 **`http://117.72.209.44:5174/`**。40个正常公网页面（含4栏目和15文章）HTTP200且逐页SHA-256与本地产物一致。首页SHA-256 `f212850fe9afbc5896f1434de0ef1bcf3fd515ce1527a5ea2545a4e8bbed8f97`；IP `/api/health` 404。
- 本地Astro检查0错误/警告/提示，构建和输出审计通过（41页面含404、15文章、Feed/sitemap/导航/本地资源）。Chrome验证4栏目数量3/3/6/3、归档15篇、目录展开/收起、暗色切换、390px无横向溢出；公网Chrome真实点击首页→栏目→文章/目录，资源无失败、无pageerror。截图 `/private/tmp/ai-journal-{home,dark,post,production}.png`。
- 国际 `https://10ye.cc/api/health` 严格TLS返回status=ok、saasEnabled/redisReady=true。本轮未更改阅读、国际商业、数据库结构或鉴权逻辑；构建生成的已跟踪React产物已恢复，未提交产物。

## 运行配置与外部待办

- `sites.json` v2保持 `blog_domain=rynenglish.com`、`public_domain=learn.rynenglish.com`、`intl_domain=10ye.cc`、`frontend_port=5174`、`intl_frontend_port=5173`、`cn_public_preview=true`、`https_deferred=false`。
- 国内5174为0.0.0.0固定IP静态博客预览，国内Nginx转5174；国际与API仍回环5173/8790，Cloudflare沿用5173。后续普通升级自动恢复该配置，不要完整重装。
- 国内两域解析与公网HTTPS已在2026-11-13实际验收，详见上方HTTPS状态；IP5174仍仅用于博客预览。
- `blog/src/config.ts` 的 `icpRecord` 已按用户提供填写 `蜀ICP备2026071122号-1`；备案号变更以用户提供的实际号码为准。
- 服务器2GiB，临时1GiB swap `/var/lib/shiyue/paper-glow-deploy-20261111.swap` 未写fstab，重启需恢复。

## 关键文件与接续命令

- `blog/src/categories.ts`：栏目slug、名称与描述；`content.config.ts`：强制栏目枚举；`content/posts/*.md`：文章。写作/主题来源/命令见 `blog/README.md`。
- `pages/[...lang]/index.astro`、`categories/[category].astro`、`archives.astro`；`components/PostCard.astro`、Header/Navbar/Footer；`styles/paper.css`、`public/images/paper-light.svg`。
- `reader/blog/` 为忽略的构建输出，不手改。Node24运行 `npm --prefix blog run build` 和 `npm --prefix blog run verify`，再 `git diff --check`。本轮无Python改动，无需Python编译。
- `tools/saas_frontend_server.py` 精确Host分站；`tools/deployment/manager.py` 负责保数据升级与回退，`https_entry.py` 负责独立证书/续期。后续升级沿用 `tools/deploy_remote.py --target 1 --upgrade --identity-file <已授权路径>`；不要添加 `--defer-https`，不要把密钥或令牌写入文档。
