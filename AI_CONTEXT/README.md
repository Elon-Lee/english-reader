# 拾页 AI 共享上下文

更新时间：2026-10-13（Asia/Shanghai）

这是后续 AI 的最小全局上下文。只读取与当前任务相关的任务文档。

## 当前架构

- 前端：React 18 + Ant Design 5 + Vite，源码在 `frontend/src/`。
- SaaS 入口：生产根路径 `/` 直接加载 `reader/site/`；`/modern.html` 和 `/modern-assets/*` 只保留 308 兼容跳转。开发入口仍由 Vite 提供。
- 后端：Python 单体 HTTP 服务 `tools/reader_server.py`，业务拆分在 `tools/saas_*.py`。
- SaaS 数据：PostgreSQL；正式本地库 `shiyue_saas_local`，隔离测试库 `shiyue_phase1_test`。
- 旧数据：`.local/library.sqlite3` 和 `books/` 继续保留，不能删除；SaaS 新页面不再使用旧 UI。
- 媒体访问：SaaS 使用鉴权 `/api/media/{asset_id}` 和媒体变体。
- 认证：数据库会话 Cookie + CSRF；未登录时 React 渲染登录页。
- 长任务：导入和部署使用任务 API + 前端轮询，不依赖 WebSocket。
- 当前服务：后台 `127.0.0.1:8790`；Vite `127.0.0.1:5173`。
- 京东云生产：`117.72.209.44:8765`，Docker 运行 `shiyue-saas`、PostgreSQL 16 和 Redis 7；PostgreSQL/Redis 只监听远程回环地址。

## 全局完成状态

- SaaS 阶段 1–9 后端、迁移、认证、会员、书城、奖励、工作区、导入、媒体、AI、管理后台均已实现并经过本地集成测试。
- PC React 页面已经覆盖登录、学习空间、书城、书架、学习记录、生词、奖励、会员、运营后台、平台部署、系统设置和阅读器。
- PC 主要 API 已真实接入；刷新路由、认证闪屏、分页、热力图、任务轮询、批量邀请码和数据库 AI 配置已修正。
- 阅读器已改为旧版语义的媒体/字幕/释义三栏交互，并保留快捷键、护眼和专注模式。
- 京东云旧 reader 服务已被根路径 React SaaS 替换；生产 PostgreSQL、Redis、SaaS 容器和已公开书籍增量同步已实机验收。
- 本地已增加公开产品官网、数据库套餐页、固定期限购买确认、不可变商品版本后台和面包多 Pay 订单/查单/回调开通；正式本地数据库已迁移，生产尚未部署。
- 最新构建与测试通过，最近 PC 浏览器验收目录：`.local/debug/modern-walkthrough/20261011T135345Z`。

## 全局未完成

- 移动端展示、底部操作区、手势和弹层交互尚未进入正式优化阶段。
- 面包多 Pay 支付闭环已实现并通过模拟集成测试；尚缺审核通过后的真实 `app_id/app_key` 和端到端实付验收。
- 大文件上传已避免 `arrayBuffer()` 内存复制，但尚未实现可恢复分片上传。
- 京东云 SaaS 完整部署和公开资源增量同步已验收；生产回滚、卸载等高风险动作尚未执行。
- Dioco 完整词典接口 `base_dict_getFullDict_8` 尚未按用户提供的请求正式接入；当前词汇 AI 走 `/api/word-context`。
- 旧 UI 文件仍物理保留用于兼容和行为参考；不能删除，SaaS 路由不得再使用它们。
- `frontend/src/main.jsx` 仍包含部分已停用的旧 React 内联组件，后续可在不改变行为的前提下清理。

## 任务索引

| 当前工作内容 | 必读任务文档 |
|---|---|
| PC 页面、路由、分页、工作台视觉 | `tasks/pc-workspace/HANDOFF.md` |
| 阅读器、媒体、字幕、快捷键、词典 | `tasks/reader/HANDOFF.md` |
| 账号、会员、数据库、API、安全 | `tasks/backend-saas/HANDOFF.md` |
| 公开产品官网、商品版本、套餐购买、面包多支付 | `tasks/public-commerce/HANDOFF.md` |
| 文件/YouTube 导入、任务进度、媒体处理 | `tasks/import-media/HANDOFF.md` |
| 运营后台、AI 配置、远程部署 | `tasks/platform-operations/HANDOFF.md` |
| 移动端适配与触摸交互 | `tasks/mobile/HANDOFF.md` |

如果任务跨多个领域，只读取实际涉及的几个文档。

新的独立任务使用 `TASK_TEMPLATE.md` 创建自己的 `tasks/<task-slug>/HANDOFF.md`。

## 默认验证

```bash
npm run build:modern
npm run test:modern
npm run test:ui
npm run check:js
python3 -m py_compile <本轮修改的 Python 文件>
git diff --check
```

涉及认证、写 API 或租户数据时，再运行：

```bash
./start-reader.sh --saas-smoke 8795
```
