# 国内与国际入口部署

更新时间：2026-11-12。本文记录本轮实现约定；真实发布版本、外部域名验收结果以 `AI_CONTEXT/tasks/dual-entry-commerce/HANDOFF.md` 为准。

同一源码提交构建两份 React：`reader/site/` 为国内应用，`reader/site-intl/` 为国际应用；`reader/blog/` 为国内独立 Astro 博客。部署包同时包含三份构建产物与共享 Python 后端。国内构建单独检查商业接口残留，国际构建允许商业模块。

| 入口 | 域名 | 进程/容器 | 正式端口 | 候选回环端口 |
| --- | --- | --- | --- | --- |
| 国内博客与阅读应用 | `rynenglish.com`、`learn.rynenglish.com` | `shiyue-saas-frontend` | HTTP 5174 | HTTP 15174 |
| 国际应用 | `10ye.cc` | `shiyue-saas-frontend-intl` | HTTP 5173 | HTTP 15173 |
| 共享 API | 仅内部访问 | `shiyue-saas` | HTTP 8790 | HTTP 18790 |

Cloudflare 原国际回源 `http://localhost:5173` 保持不变；国内 Nginx 按已知 Host 转到 5174。国际前端只接受国际域名，国内博客不暴露应用 API，未知 Host 拒绝访问。两个前端共享账号、数据库、Redis、媒体与同一套后端；Cookie 在各注册域分别登录。

用户授权测试时，`sites.json` 中 `cn_public_preview:true` 令国内正式5174监听 `0.0.0.0`，并将部署节点的固定IP Host映射到静态博客。当前预览地址 `http://117.72.209.44:5174/`，不提供IP登录或API。域名分站保持原规则，国际5173和所有候选端口仍仅回环。后续升级恢复该设置；测试结束可删除该键或设为false后重建国内前端，恢复回环监听。公网是否可达还取决于实际云安全组和网络放行。

## 配置与凭据

`shared/config/sites.json` 保存 `public_domain`（阅读应用）、`blog_domain`、`intl_domain`、`frontend_port`、`intl_frontend_port` 与 `https_deferred`。后续普通升级先恢复该文件，不能被本地旧节点设置覆盖。旧版本没有 `intl_domain` 时保留原单前端 5173/TLS 行为，不自动开启国际入口。

共享后端使用权限 0600 的 `shared/config/saas.env`。双入口升级保留已有数据库、会话和支付凭据，并在远端进程内生成缺失的 `CN_GATEWAY_TOKEN`、`INTL_GATEWAY_TOKEN`；生成值不进入部署命令或日志。`CN_APP_BASE_URL` 与 `INTL_APP_BASE_URL` 分别使用已配置的可信 HTTPS 域名。

前端各自只读取 `shared/config/frontend-cn.env` 或 `frontend-intl.env`，其中仅包含本站 `FRONTEND_SITE_TOKEN`，权限 0600。前端容器不读取数据库、支付密钥或另一站入口凭据。令牌由入口覆盖注入，不能相信浏览器自报站点。

## 保数据升级

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
