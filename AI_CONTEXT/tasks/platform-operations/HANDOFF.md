# 平台运营与部署交接

## 部署行为

- “程序升级”打包当前本机代码，先备份远程 PostgreSQL，再通过候选版本、迁移完整性和健康检查后切换；保留远端用户数据。
- “重新部署”是完整重装：先在安装目录外备份远程数据库，再移除远程服务和安装目录；安装时用当前本机数据库快照初始化，并同步本机公开内容。该操作会替换远端用户数据。
- “上传官方内容”只增量同步已登记的官方读物及关联媒体，不发布代码，也不覆盖远端用户数据。新增或变更内容需在线上审核后才公开。
- 远程部署、重新部署、回滚、卸载和清理均需管理员确认；除非用户明确要求，不执行远程变更。

## 当前实现（2026-11-07 核实）

### 2026-11-07 Linux 安装与升级补齐原音对齐

- 首次部署、完整重装、程序升级共用 `ensure_remote_aligner`，不受可选 Whisper 录音开关影响。已通过校验的 `shared/.local/forced-aligner` 复用；缺失/损坏时，由部署端下载目标 Linux CPython 3.11 的 CPU wheels 和固定 SHA-256 模型，校验缓存、打包并上传，远程禁网离线安装，避免远端慢速模型下载导致导入卡住。
- `tools/forced_aligner_setup.py` 与 `tools/install_forced_aligner.sh` 支持在线安装、`--offline-dir`、`--check`；固定 numpy 1.26.4、torch/torchaudio 2.2.2（Linux x86_64 为 +cpu），模型与当前生产一致。安装有文件锁、新环境通过后才替换 venv 链接，失败保留旧环境；模型下载/复制先校验再原子替换。发布包包含安装器和检查工具。
- 候选服务上线前检查实际运行环境（含自定义 CTC 路径）、模型 SHA-256、FFmpeg 16kHz 解码、numpy/Torch 兼容、wav2vec2 CPU 推理与原生 forced_align 扩展。任一步失败即停止，不切换 current、不停旧站；无需额外 WebSocket 或新业务接口。
- 验证：Linux x86_64 隔离目录首次离线安装、真实推理、实际部署 helper 复用检查通过；完整 CPU 依赖解析/593,930,240 字节模型包校验通过。Python 3.11 下 79 项部署、34 项上传/对齐/隔离 PostgreSQL 导入回归全部通过；构建、modern smoke、UI 22 项、JS、Python 编译与 diff 检查通过。ARM64 已提供平台包选择，尚无 ARM64 实机验收；未对任何生产节点执行完整重装。开发机默认 Python 3.9 的完整部署测试有 3 项因既有 `Path | None` 导入不兼容而失败，已在 Linux Python 3.11 全部重跑通过。
- 新文件：`tools/deployment/alignment.py`、`tools/forced_aligner_setup.py`、`tools/test_deployment_alignment.py`、`tools/test_upload_integrity.py`。首次部署端下载需可访问 Python 包源/PyTorch，之后复用经校验缓存；远端安装本身不依赖公网包源。

### 2026-11-07 导入故障定向修复

- 实机基线为 `code-20261106-113458-43116bfb`。本轮按用户授权备份 PostgreSQL（pg_restore --list 校验）与原代码后，定向热修复导入上传启动、部分原音校验和前端导入组件；保留线上数据、RynEnglish 品牌、验证码与现有 CSS。备份 `/srv/shiyue/backups/saas/import-recovery-20261107/`。
- 当前 release 目录未切换。后续定向修复加入前台代理/后端上传完整性校验，并撤回接受部分音频的临时方案；前端仅替换 ImportModal/LibraryPage 组件。后续完整升级必须保留线上 11 月 6 日源码变更，不能直接用本地旧品牌构建覆盖。
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
- 本机前端构建和数据库快照现在先于远端备份/卸载执行；本地构建失败时不会先拆除远端服务。截图来源为 `frontend/public/product/`。
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
- 远程数据库备份存放于安装目录之外；失败后的数据库恢复需人工确认，避免覆盖备份后新增的数据。
- 不在文档、前端或日志中记录完整密码、Token 或密钥。
