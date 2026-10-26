# PC 工作台交接

## 范围与架构

- PC SaaS 前端使用 React 18、Ant Design 5 和 Vite；页面源码位于 `frontend/src/`。
- 生产根路径 `/` 使用 `reader/site/` 构建产物。开发时由 Vite 提供前端，`/api` 和 `/books` 代理至本地 SaaS 后台。
- Vite 默认代理目标为 `http://127.0.0.1:8790`，可由 `SHIYUE_API_PROXY_TARGET` 覆盖。开发入口是 `http://127.0.0.1:5173/`，不要把生产兼容路径 `/modern.html` 或 `/modern-assets/` 当成 Vite 开发入口。
- 前端覆盖公开首页、学习空间、书城、书架、学习记录、生词复习、奖励、会员、运营后台、平台部署、设置和阅读器。业务数据通过真实 API 加载，不使用静态数据替代。
- 优先完成 PC 验收，再开始移动端优化。不要把 SaaS 操作改回旧 `reader/index.html` 或 `reader/app.js`。

## 当前状态（2026-10-25）

- PC 主要页面与 API 流程已实现；移动端正式优化尚未开始。
- 本地开发服务已启动：Vite `5173`、SaaS 后台 `8790`。后台健康接口返回 200；未登录访问 `/api/auth/me` 返回 401 `authentication_required` 是预期行为。
- 本次排查发现 Vite 进程曾带有过时的 `SHIYUE_API_PROXY_TARGET=http://127.0.0.1:8765`，请求因此落到旧后台并返回 `saas_disabled`。已将 Vite 以 `SHIYUE_API_PROXY_TARGET=http://127.0.0.1:8790` 重启并验证代理返回正确后台的 401。仓库配置无需修改；若问题复现，先检查 Vite 进程启动环境并重启，不要先改 API 路由。

## 后续事项

- 清理 `frontend/src/main.jsx` 中停用的内联旧组件时，保持现有行为不变。
- PC 功能验收完成后再规划移动端适配。
- 组件级测试覆盖仍有限；继续沿用现有 smoke、回归和浏览器验收，并按变更风险补充测试。

## 关键文件

- `frontend/vite.config.js`：开发服务器及 API 代理。
- `frontend/src/main.jsx`：应用入口、认证恢复和路由状态。
- `frontend/src/api/client.js`：前端 API 请求。
- `frontend/src/styles.css`：全局与页面样式。
- `frontend/src/pages/`：各 SaaS 页面。

## 常用验证

```bash
npm run build:modern
npm run test:modern
npm run test:ui
npm run check:js
git diff --check
```

验证代理时，可检查 `http://127.0.0.1:5173/api/auth/me`：未登录应由后台返回 401 `authentication_required`，而不是 Vite/代理的 404，也不应返回 `saas_disabled`。
