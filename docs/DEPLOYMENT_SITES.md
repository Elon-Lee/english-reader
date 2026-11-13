# 国内与国际入口部署

更新时间：2026-11-13。本文记录本轮实现约定；真实发布版本、外部域名验收结果以 `AI_CONTEXT/tasks/dual-entry-commerce/HANDOFF.md` 为准。

2026-11-13已完成国内 `rynenglish.com`、`learn.rynenglish.com` 的Let’s Encrypt证书与HTTP80→HTTPS443（308，保留路径/查询参数，ACME路径除外）。HTTPS入口转国内5174，国际仍由Cloudflare转5173。`sites.json` 已保存 `https_deferred:false`；后续普通升级不得传 `--defer-https`。这是入口配置操作，未发布业务代码。

证书有效至2027-02-11；续期脚本 `/var/lib/shiyue/https/57dfc879ad04/renew.sh`，定时器 `shiyue-https-renew-57dfc879ad04.timer` 每日03:00/15:00检查续期。证书/配置独立保存在 `/var/lib/shiyue/https/57dfc879ad04/`，不放入Git或应用发布目录。HTTP80的ACME验证路径须继续可用。

同一源码提交构建两份 React：`reader/site/` 为国内应用，`reader/site-intl/` 为国际应用；`reader/blog/` 为国内独立 Astro 博客。部署包同时包含三份构建产物与共享 Python 后端。国内构建单独检查商业接口残留，国际构建允许商业模块。

2026-11-12 用户已验收国内主页与 `10ye.cc` 流程，确认将双入口与博客调整合并至实际默认主分支 `main`（仓库没有 `master`）。该验收不替代真实支付渠道联调与国内域名HTTPS的既有待办。

## 后续修改如何划分

保持一个 `main` 主线，按需求创建短期分支；国内/国际通过构建入口组合差异，不建立长期分叉的业务代码。

| 修改范围 | 代码与判断依据 | 必须验证 |
| --- | --- | --- |
| 共享核心 | 两站共用的阅读器、书架、内容管理、学习记录、账号、资源；`frontend/src/` 中实际被两入口使用的组件/页面/hooks/utils，以及 `tools/saas_*.py` 中共享服务和数据模型 | 国内与国际的相关流程、权限与数据一致性；只改一次核心实现 |
| 国内扩展 | `frontend/src/sites/cn/index.jsx` 选出的国内页面/品牌/路由；目前也复用 `frontend/src/pages/PublicSite.jsx` 等目录外文件。`blog/` 是独立公开博客 | 国内博客/阅读入口、国内商业路径拒绝；共享调用未被破坏 |
| 国际扩展 | `frontend/src/sites/intl/`、`frontend/public-intl/` 和国际可信入口下的商业服务 | 国际首页/会员/订单/支付相关流程与权限；国内产物仍无国际商业依赖 |

开始修改时先声明范围并检查实际引用链，目录只是线索。Vite配置 `frontend/vite.config.js` 将 `@site` 指向 `sites/cn|intl/index.jsx`；共享页面通过这个接口组合站点能力。不要把国际模块直接导入共享核心，也不要复制共享业务到各站目录。后端仍是一套服务，站点专属行为须保留 `saas_sites.py` 等服务端门禁，数据迁移兼容两入口。

## 每次程序发布的固定约定

- 无论本轮改共享核心、某站扩展或博客，都以**同一源码提交、一个发布包、一个发布版本**同时交付国内前端、国际前端、博客与共享后端。
- `build_code_package()` 调用 `build_frontend_assets()` → `npm run build:sites`（依次构建国内/国际），再调用 `build_blog_assets()`。任一构建失败即停止，产物校验包含国内商业隔离与国际产物完整性。
- 双前端与共享后端先在候选端口验收，全部通过后统一更新 `current` 并重建两入口。这里是整体切换流程，不保证零停机；失败走整体回退，不能只留下一个入口的新版本。
- 日常命令是 `npm run deploy:jdcloud -- --identity-file <已授权私钥路径>`；已改为 `--upgrade` 保数据升级。该命令读取远端 `sites.json` 恢复双入口与端口，无需分别执行两次发布。完整 `--saas`/重装仅用于单独授权的初始化场景。
- 发布后核对两入口、博客、共享API及运行版本，并按改动验证相关业务。不要只验证本轮修改的首页。构建产物不手工提交，也不单独替换线上文件。

以下为当前网络与端口配置：

| 入口 | 域名 | 进程/容器 | 正式端口 | 候选回环端口 |
| --- | --- | --- | --- | --- |
| 国内博客与阅读应用 | `rynenglish.com`、`learn.rynenglish.com` | `shiyue-saas-frontend` | HTTP 5174 | HTTP 15174 |
| 国际应用 | `10ye.cc` | `shiyue-saas-frontend-intl` | HTTP 5173 | HTTP 15173 |
| 共享 API | 仅内部访问 | `shiyue-saas` | HTTP 8790 | HTTP 18790 |

Cloudflare 原国际回源 `http://localhost:5173` 保持不变；国内 Nginx 按已知 Host 转到 5174。国际前端只接受国际域名，国内博客不暴露应用 API，未知 Host 拒绝访问。两个前端共享账号、数据库、Redis、媒体与同一套后端；Cookie 在各注册域分别登录。

国内阅读子域名的抓取策略由 `tools/saas_frontend_server.py` 按入口站点与Host执行：`/robots.txt` 全站 `Disallow: /`，所有国内应用响应带 `X-Robots-Tag: noindex, nofollow`；博客与国际站不套用此规则。所有访客返回同一策略，规则不能代替鉴权或保证所有爬虫遵守。国内应用备案页脚通过 `@site.SiteFrame` 挂载；国际透传原布局，不引入国内专属文案和样式。

用户授权测试时，`sites.json` 中 `cn_public_preview:true` 令国内正式5174监听 `0.0.0.0`，并将部署节点的固定IP Host映射到静态博客。当前预览地址 `http://117.72.209.44:5174/`，不提供IP登录或API。域名分站保持原规则，国际5173和所有候选端口仍仅回环。后续升级恢复该设置；测试结束可删除该键或设为false后重建国内前端，恢复回环监听。公网是否可达还取决于实际云安全组和网络放行。

## 配置与凭据

`shared/config/sites.json` 保存 `public_domain`（阅读应用）、`blog_domain`、`intl_domain`、`frontend_port`、`intl_frontend_port` 与 `https_deferred`。后续普通升级先恢复该文件，不能被本地旧节点设置覆盖。旧版本没有 `intl_domain` 时保留原单前端 5173/TLS 行为，不自动开启国际入口。

共享后端使用权限 0600 的 `shared/config/saas.env`。双入口升级保留已有数据库、会话和支付凭据，并在远端进程内生成缺失的 `CN_GATEWAY_TOKEN`、`INTL_GATEWAY_TOKEN`；生成值不进入部署命令或日志。`CN_APP_BASE_URL` 与 `INTL_APP_BASE_URL` 分别使用已配置的可信 HTTPS 域名。

前端各自只读取 `shared/config/frontend-cn.env` 或 `frontend-intl.env`，其中仅包含本站 `FRONTEND_SITE_TOKEN`，权限 0600。前端容器不读取数据库、支付密钥或另一站入口凭据。令牌由入口覆盖注入，不能相信浏览器自报站点。

## 保数据升级

日常同时升级国内、国际、博客及共享后端：

```bash
PATH=/Users/elonlee/.nvm/versions/node/v24.14.0/bin:$PATH \
npm run deploy:jdcloud -- --identity-file <已授权私钥路径>
```

服务器当前已保存 `https_deferred:false`，普通升级保持国内HTTPS；该命令不会把初始化重装作为默认路径。若本机默认Python缺少项目依赖，直接用 `.local/saas-venv/bin/python tools/deploy_remote.py --target 1 --upgrade --identity-file <已授权私钥路径>`，与npm命令使用同一发布流程。

首次显式启用双入口：

```bash
PATH=/Users/elonlee/.nvm/versions/node/v24.14.0/bin:$PATH \
python3 tools/deploy_remote.py --target <节点ID> --upgrade \
  --app-domain learn.rynenglish.com --blog-domain rynenglish.com \
  --intl-domain 10ye.cc --defer-https --identity-file <已授权私钥路径>
```

普通后续升级可省略域名参数，继续使用远端保存的双入口配置。`--defer-https` 不申请证书、不建立正式 443；仅在存在且归属当前项目的 HTTP bootstrap 时，将其国内 Host 转到当前国内前端端口，并保留 ACME 路径。遇到已有 443 配置时拒绝把它降级为 HTTP。国内正式 TLS 仍依赖实际 DNS 与云商放行；补装 HTTPS 读取已保存的国内端口，国际端口不受影响。

升级先完成源码打包、远程数据库备份及配置备份，再以 18790/15174/15173 启动候选。检查两入口 Host、首页、健康、国内商业 API/页面拒绝和国际商业页面/未登录 API，并完成数据库迁移与原音对齐检查后切换。任一候选失败清理全部候选容器，保持正式入口；切换或最终验收失败时恢复原 current、原站点配置、入口凭据和 Nginx 配置，再恢复原前端拓扑。旧单站升级失败会恢复单前端 5173/TLS，不留国际容器。

只做兼容增量迁移，不自动恢复数据库备份覆盖正式库。用户账号、书目与媒体目录不因代码回退而删除。完整重装与卸载仍是独立的破坏性操作，不能替代本流程。

## 本地验证

```bash
PYTHONPATH=tools python3 -m unittest discover -s tools -p 'test_deployment*.py'
PYTHONPATH=tools python3 -m unittest tools.test_blog_deployment
python3 -m py_compile tools/deploy_remote.py tools/deployment/manager.py tools/deployment/https_entry.py
git diff --check
```

`test_deployment_dual_entry.py` 通过临时目录与替身 Docker 命令执行真实 Bash 故障路径，覆盖候选清理、切换失败恢复旧单站、最终配置整体回退、独立凭据文件权限与密钥不输出。测试不会连接远程 Docker 或正式数据库。
