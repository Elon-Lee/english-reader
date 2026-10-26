# 平台运营与部署交接

## 部署行为

- “程序升级”打包当前本机代码，先备份远程 PostgreSQL，再通过候选版本、迁移完整性和健康检查后切换；保留远端用户数据。
- “重新部署”是完整重装：先在安装目录外备份远程数据库，再移除远程服务和安装目录；安装时用当前本机数据库快照初始化，并同步本机公开内容。该操作会替换远端用户数据。
- “上传官方内容”只增量同步已登记的官方读物及关联媒体，不发布代码，也不覆盖远端用户数据。新增或变更内容需在线上审核后才公开。
- 远程部署、重新部署、回滚、卸载和清理均需管理员确认；除非用户明确要求，不执行远程变更。

## 当前实现（2026-10-25）

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
- `tools/deployment/saas_public_sync.py`：官方内容增量同步。

## 验证

```bash
npm run build:modern
npm run test:modern
npm run test:ui
PYTHONPATH=tools python3 -m unittest tools.test_deployment_release_pipeline
python3 -m py_compile tools/deployment/manager.py tools/test_deployment_release_pipeline.py
git diff --check
```

## 运维约束

- 程序升级与完整重新部署不可互换：升级保留远端数据；重新部署以本机数据库快照替换远端数据。
- 远程数据库备份存放于安装目录之外；失败后的数据库恢复需人工确认，避免覆盖备份后新增的数据。
- 不在文档、前端或日志中记录完整密码、Token 或密钥。
