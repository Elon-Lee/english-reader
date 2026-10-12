# 平台运营与部署交接

## 已完成

- React 管理页覆盖内容审核、媒体资产、注销清理、平台配置和部署节点。
- 人工订阅支持 1 周、1 月、1 季度、1 年快捷时长和日期时间范围控件。
- 邀请码支持空值自动生成、批量生成、查询和分页。
- 部署测试、同步、部署、升级和清理任务在 `queued/running` 时每 2 秒轮询。
- 代码/内容回滚保留二次确认。
- 超级管理员可在数据库中保存 AI 邮箱、Token 和 API 地址；完整 Token 不回传。
- 远程发布包在生成前强制执行 `npm run build:modern`，避免部署陈旧的 React 静态资源。
- 发布包包含 `.shiyue-release.json`（版本、Git 提交、构建时间、工作区状态），远程切换前校验 SHA-256 和关键文件完整性，健康检查失败会恢复上一代码版本。
- 新增命令行入口：`npm run package:remote` 只打包，`npm run deploy:jdcloud` 构建并升级“京东云服务器”节点，同时轮询输出任务状态与日志。
- 京东云节点 `117.72.209.44:22` 已于 2026-10-12 完成新版脚本实机升级；最终发布版本见下方“当前生产状态”。

## 当前生产状态

- 节点：`京东云服务器`（部署目标 ID 1，`/srv/shiyue`，HTTP 8765）。
- 2026-10-12 部署前版本：`code-20261007-233146-94f79ee3`。
- 2026-10-12 首次新版脚本部署：`code-20261012-140630-ab439846`，健康检查、39 本书与 Dioco 语境接口均通过。
- 当前生产版本：`code-20261012-140803-36d3e8e2`（2026-10-12 14:08 Asia/Shanghai）；已包含最终进度修正，SHA-256 校验、容器健康检查、39 本书和 Dioco 语境接口均通过。

## 未完成

- 京东云生产节点的连接和程序升级已实机验收；内容同步此前已有成功记录。代码回滚、内容回滚和卸载仍未在本轮生产节点执行高风险验收。
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
- `tools/reader_server.py`

## 验证命令

```bash
npm run package:remote
npm run deploy:jdcloud
PYTHONPATH=tools python3 -m unittest tools.test_deployment_release_pipeline tools.test_deployment_nodes tools.test_deployment_docker_install tools.test_deployment_content_paths tools.test_deployment_dioco_config tools.test_deployment_grammar_content
python3 -m py_compile tools/deployment/manager.py tools/deploy_remote.py tools/test_deployment_release_pipeline.py
git diff --check
```

## 安全原则

- 高风险动作必须确认并写审计。
- 未经用户明确要求不执行远程部署、回滚、卸载或清理。
- 不在文档、前端或日志中显示完整密码与 Token。
