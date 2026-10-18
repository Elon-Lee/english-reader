# 平台运营与部署交接

## 已完成

- 2026-10-18 媒体资产移入运营后台独立 `MediaAssetsAdmin.jsx`，按 Tab 加载、服务端分页与范围筛选，保留标记删除/扫描/清理及二次确认，提供加载/失败重试/空状态；平台页不再请求媒体资产，账户注销清理保留在平台配置页。内容审核拆为“审核”“编辑”两个按钮：审核仅设置版权和发布状态，编辑仅改书目信息并保留审核状态。
- 修复“上传待审核内容”任务 #24545 报错：HTTP `/api/deployment/sync` 仍调用旧 `start_sync`，日志明确 `Error: No such object: shiyue-reader`。已切换 `start_saas_public_sync` 并新增路由回归；任务表新增失败原因列。本地真实内容导出验证 4 本、118 个媒体文件通过，部署相关 28 项、构建/modern/UI/JS、Python 编译及 diff 检查通过。本地后台已重启、前端及代理健康；本轮未重新执行远程上传或发布，线上重传待用户操作。
- 2026-10-18 内容审核已从平台与部署移至“运营后台 → 内容审核”，独立 `CatalogModeration.jsx` 按 Tab 加载，提供真实审核 API、状态筛选、错误重试、编辑、发布及停止公开确认；管理员书架入口直达该 Tab。平台页资源同步按钮改为“上传待审核内容”。本地前后端正常，尚未发布线上。
- 内容上传规则：仅上传已登记到 `catalog_books` 且为 draft/published、非 prohibited 的内容；不打包未登记的私人读物。导出与接收双侧强制新内容/变更内容为 `draft`（界面“未审核”），清空本地审核人及发布时间；首次初始化同样进入未审核。只有目标站管理员审核发布才进入首页书城。manifest 新增 `contentFingerprints`；未变更的重复同步保留线上审核状态、书目编辑及标签，有变更则重新审核；旧 manifest 首次同步按待审核处理。同步携带当前 apply 脚本，避免远程旧脚本绕过规则。未修改现有线上书目。
- 验证：前端构建/modern/UI/JS、Python 编译、diff 检查通过；部署套件原 26 项及新增初始化/接收脚本用例通过；独立临时 PostgreSQL 的 phase3 与上传审核共 13 项通过，覆盖待审核不可见、发布可见、重复同步保留线上编辑/标签、修改重新审核、旧包发布状态清除。临时库已清理。现有 HTTP smoke 仍假设后台 `/` 返回首页，与当前 API-only 后台冲突，在首页检查失败；本地前端 5173 返回 200，代理健康为 SaaS。
- 2026-10-18 远程 SaaS 部署改为前后台双容器：公网只暴露 `5173` 前台容器，前台将 `/api/*` 与 `/books/*` 反代到仅监听 `127.0.0.1:8790` 的 SaaS 后台容器；候选验收、生产切换、升级、公共资源同步、回滚和卸载均同步处理两个容器。部署目标服务端口固定为 `5173`，完整部署入口也改走 SaaS 流程。
- 2026-10-18 远程升级任务 `24508` 已完成，发布版本 `code-20261018-174855-80458285`。失败任务 `24489` 的原因是候选验收仍访问已改为 API-only 的后台根路径 `/`，已改为验收独立前台容器；升级前检查也兼容旧的单容器生产状态。远程实机确认 `shiyue-saas-frontend` 正常监听 `*:5173`、`shiyue-saas` 仅监听 `127.0.0.1:8790`、Redis/数据库健康、前台 `/` 和 `/api/health` 均返回 200，旧 `8765` 已关闭。公网从当前工作站访问 `117.72.209.44:5173` 仍超时，远程主机本机 iptables 为 ACCEPT，判断为京东云安全组尚未放行 TCP 5173，需要在云控制台开放该端口后才能公网访问。
- 2026-10-18 为修复视频导入 45% 假停滞，已对生产 `/srv/shiyue/current/tools/saas_imports.py` 做临时热修复并重启 `shiyue-saas`；FFmpeg/Whisper 端到端体检通过，后台健康和前台 200 通过。热修复备份为 `/srv/shiyue/backups/saas/saas_imports.py.20261018-210557.bak`；下一次正式 SaaS 升级必须包含仓库当前导入代码，避免覆盖该热修复。

- 2026-10-18 SaaS 升级任务 #24389 complete，发布 `code-20261018-081452-67a2d629`，数据库预备份、候选根页面/JS、migrations 至 `0034`、生产 SaaS/Redis 和版本挂载检查全部通过。CLI `tools/deploy_remote.py` 默认/`--upgrade` 入口也已改为 `start_saas_upgrade`，补行为测试。此前 CLI 任务 #24388 误入旧 reader 流程失败，已移除旧容器并恢复指针后完成正式发布；未覆盖生产数据库。
- React 管理页覆盖内容审核、媒体资产、注销清理、平台配置和部署节点。
- 人工订阅支持 1 周、1 月、1 季度、1 年快捷时长和日期时间范围控件。
- 邀请码支持空值自动生成、批量生成、查询和分页。
- 部署测试、同步、部署、升级和清理任务在 `queued/running` 时每 2 秒轮询。
- 代码/内容回滚保留二次确认。
- 超级管理员可在数据库中保存 AI 邮箱、Token 和 API 地址；完整 Token 不回传。
- 远程发布包在生成前强制执行 `npm run build:modern`，避免部署陈旧的 React 静态资源。
- 发布包包含 `.shiyue-release.json`（版本、Git 提交、构建时间、工作区状态），远程切换前校验 SHA-256 和关键文件完整性，健康检查失败会恢复上一代码版本。
- 新增命令行入口：`npm run package:remote` 只打包；`npm run deploy:jdcloud` 完整部署根路径 SaaS/PostgreSQL/Redis；`npm run sync:jdcloud:public` 只增量同步合法已公开书籍及相关正文、语法和媒体。
- 发布包不再包含 `reader/modern.html` 或 `reader/modern-assets/`；生产前端构建到 `reader/site/` 并直接接管根路径，旧路径仅返回 308 到 `/`。
- 内容同步只选择已登记书目中的可传输内容及关联媒体，上传后的审核规则见上；不覆盖远程用户、订阅、会话和学习数据。
- 2026-10-13 本地修复“用户与订阅 → 查看详情”在存在人工订单时失败：`AdminService.user_detail` 读取 `manual_orders` 时误用了不存在的 `plan_version` 列，已改为真实列 `plan_version_id`，并补充带人工订阅/订单的阶段 5 回归测试。已在隔离测试库通过浏览器确认用户详情、设备和订阅记录正常展示；按用户要求尚未发布远程。
- 2026-10-13 本地前端构建将 React/Ant Design/vendor/icons 共享分包改为内容哈希文件名，入口 JS/CSS 仍带构建版本参数，避免发布后新入口加载浏览器缓存中的旧分包。该变更随下次用户手动发布生效，尚未远程部署。
- 2026-10-17 修复“程序升级”误走旧 reader 部署流程：`/api/deployment/upgrade` 与 `/api/deployment/saas-upgrade` 现在进入 `start_saas_upgrade`。升级只打包本机工作区并替换 SaaS 代码，不导入本地数据库或同步内容；要求远端现有 SaaS/PostgreSQL/Redis 健康，先对远程 PostgreSQL 做私有权限备份，再启用候选容器。候选启动应用自动 migrations 后，必须 `ensure_migrated()` 确认发布包含的所有 schema/data migrations 已登记，且根页面 JS 可加载、SaaS/Redis 健康，才切换线上版本。切换后再核对 `current` 与 SaaS 容器挂载版本；管理页版本读远端 release 的 `current` 标记。发布包会在前端构建前记录 Git 提交和工作区状态。
- 2026-10-17 修复前本地任务 #3665、#3785 记录了 `program_upgrade` 使用旧 reader 容器命令替换 SaaS 服务；#3785 指针切换至 `code-20261017-232959-d894ff4d` 且健康接口成功，但旧流程没有迁移完整性校验。
- 2026-10-17 #4530 使用 SaaS 专用升级流程，代码切换与 migrations 均已生效；任务因挂载源软链接未规范化误报失败。已只读确认当前生产版本 `code-20261017-235121-c35c7a4a`、健康状态和 migrations。后端校验修正本地完成，未重跑生产升级。

## 当前生产状态

- 节点：`京东云服务器`（部署目标 ID 1，`/srv/shiyue`，HTTP 8765）。
- 2026-10-12 部署前版本：`code-20261007-233146-94f79ee3`。
- 2026-10-12 首次新版脚本部署：`code-20261012-140630-ab439846`，健康检查、39 本书与 Dioco 语境接口均通过。
- 当前生产版本：`code-20261018-174855-80458285`（2026-10-18 17:49 Asia/Shanghai），升级任务 #24508 complete。前后台双容器、SaaS/Redis、候选前台/后台、migrations 至 `0035` 和规范化挂载路径检查均通过。升级备份：`/srv/shiyue/backups/saas/pre-upgrade-code-20261018-174855-80458285.dump`。
- 生产容器：`shiyue-saas`、`shiyue-postgres`（PostgreSQL 16 Bookworm）、`shiyue-redis`（Redis 7 Bookworm）；旧 `shiyue-reader` 已停止并替换。
- 当前公共内容版本：`public-20261012-180520-66dc4804`；4 本已公开书、4 本内容、110 条媒体资产、261 条语法数据、118 个媒体文件（533,915,615 字节）。
- 实机重复同步结果：新增/修改 0、删除 0、上传 0 字节，证明后续走增量同步。
- 公网验收：`/` 加载 `/assets/*`，`/assets/index.js` 返回 200；`/modern.html` 和 `/modern-assets/*` 的 GET 返回 308 到 `/`；健康接口为 `runtimeMode=saas`、`saasEnabled=true`、`redisReady=true`。

## 未完成

- 2026-10-13 用户详情修复及哈希分包已随 2026-10-17 生产升级发布。
- SaaS 程序升级会先生成 `/srv/shiyue/backups/saas/pre-upgrade-<release>.dump`。候选失败后的数据库恢复仍需运维人工确认后执行，避免自动恢复覆盖备份后产生的新写入。
- 完整 SaaS 首次部署入口仍要求本地 `tools/vendor/whisper.cpp/models/ggml-base.en.bin`；不要用完整首次部署替代程序升级，因为首次部署可能初始化数据或同步公共内容。
- 京东云生产节点的完整 SaaS 替换和公共资源增量同步已实机验收。代码回滚、公共内容回滚和卸载仍未执行高风险生产验收。
- 部署日志目前在任务刷新后展示有限，后续可增加增量日志 Drawer。
- AI 配置尚未实现独立的“测试连接”按钮。
- 管理员身份目前只有 `isAdmin`，没有独立的“超级管理员”角色层级；当前配置权限等同管理员权限。如果业务要求严格区分，需要新增角色/权限。

## 关键文件

- `frontend/src/pages/AdminPage.jsx`
- `frontend/src/pages/PlatformOperationsPage.jsx`
- `tools/saas_admin.py`
- `tools/deployment/manager.py`
- `tools/deploy_remote.py`
- `tools/test_deployment_release_pipeline.py`
- `tools/deployment/saas_public_sync.py`
- `tools/saas_cache.py`
- `deployment/docker/Dockerfile.saas`
- `tools/reader_server.py`

## 验证命令

```bash
npm run package:remote
npm run deploy:jdcloud
npm run sync:jdcloud:public
PYTHONPATH=tools python3 -m unittest tools.test_deployment_release_pipeline tools.test_deployment_nodes tools.test_deployment_docker_install tools.test_deployment_content_paths tools.test_deployment_dioco_config tools.test_deployment_grammar_content
python3 -m py_compile tools/deployment/manager.py tools/deploy_remote.py tools/test_deployment_release_pipeline.py
git diff --check
```

## 安全原则

- 高风险动作必须确认并写审计。
- 未经用户明确要求不执行远程部署、回滚、卸载或清理。
- 不在文档、前端或日志中显示完整密码与 Token。
