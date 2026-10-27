# 平台运营与部署交接

## 部署行为

- “程序升级”打包当前本机代码，先备份远程 PostgreSQL，再通过候选版本、迁移完整性和健康检查后切换；保留远端用户数据。
- “重新部署”是完整重装：先在安装目录外备份远程数据库，再移除远程服务和安装目录；安装时用当前本机数据库快照初始化，并同步本机公开内容。该操作会替换远端用户数据。
- “上传官方内容”只增量同步已登记的官方读物及关联媒体，不发布代码，也不覆盖远端用户数据。新增或变更内容需在线上审核后才公开。
- 远程部署、重新部署、回滚、卸载和清理均需管理员确认；除非用户明确要求，不执行远程变更。

## 当前实现（2026-10-27）

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
- 本机前端构建和数据库快照现在先于远端备份/卸载执行；本地构建失败时不会先拆除远端服务。截图来源为 `frontend/public/product/`。
- 线上静态服务对图片返回一年 `immutable` 缓存。首页截图 URL 现带图片内容 SHA-256 前 12 位作为 `v` 参数；图片变更会同时生成新 URL 和新入口版本，避免浏览器继续使用旧截图缓存。只需运行“程序升级”发布该前端修复，无需完整重新部署。
- 2026-10-25 只读核对：生产当前版本 `code-20261025-104352-3e65cccf` 的三张图片哈希与本地相同，证明截图文件已经随近期发布到达生产；但生产响应仍为一年 `immutable` 缓存。部署记录中最近任务类型为 `saas_upgrade`，不是 `saas_redeploy`。内容哈希 URL 修复目前仅在本地，未执行生产发布。

## 关键文件

- `frontend/src/pages/PlatformOperationsPage.jsx`：部署操作、顺序、确认文案。
- `frontend/vite.config.js`：首页截图 URL 内容版本化及入口缓存版本。
- `tools/deployment/manager.py`：前端构建、发布包、SaaS 部署任务。
- `tools/deploy_remote.py`：命令行打包与部署入口。
- `tools/test_deployment_release_pipeline.py`：发布包、截图与部署流程回归。
- `tools/test_deployment_https.py`：HTTPS 配置、旧节点升级和真实 TLS/Cookie 代理回归。
- `tools/deployment/saas_public_sync.py`：官方内容增量同步。

## 验证

```bash
npm run build:modern
npm run test:modern
npm run test:ui
PYTHONPATH=tools python3 -m unittest tools.test_deployment_release_pipeline
PYTHONPATH=tools python3 -m unittest tools.test_deployment_https tools.test_deployment_nodes tools.test_deployment_docker_install tools.test_deployment_dioco_config tools.test_deployment_content_paths tools.test_deployment_grammar_content tools.test_saas_frontend_routes
python3 -m py_compile tools/deployment/manager.py tools/deploy_remote.py tools/test_deployment_https.py tools/test_deployment_release_pipeline.py
git diff --check
```

## 运维约束

- 程序升级与完整重新部署不可互换：升级保留远端数据；重新部署以本机数据库快照替换远端数据。
- 远程数据库备份存放于安装目录之外；失败后的数据库恢复需人工确认，避免覆盖备份后新增的数据。
- 不在文档、前端或日志中记录完整密码、Token 或密钥。
