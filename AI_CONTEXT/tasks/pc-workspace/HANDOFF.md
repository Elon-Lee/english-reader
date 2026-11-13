# PC 工作台交接

## 范围与架构

- PC SaaS 前端使用 React 18、Ant Design 5 和 Vite；页面源码位于 `frontend/src/`。
- 生产根路径 `/` 使用 `reader/site/` 构建产物。开发时由 Vite 提供前端，`/api` 和 `/books` 代理至本地 SaaS 后台。
- Vite API / 媒体代理固定为 `http://127.0.0.1:8790`，不允许环境变量覆盖为远程地址。开发入口为 `http://127.0.0.1:4173/`，统一由 `./start-reader.sh --saas-local` 启动；安装、登录和排错见 [本地开发指南](../../../docs/LOCAL_DEVELOPMENT.md)。
- 前端覆盖公开首页、学习空间、书城、书架、学习记录、生词复习、奖励、会员、运营后台、平台部署、设置和阅读器。业务数据通过真实 API 加载，不使用静态数据替代。
- 优先完成 PC 验收，再开始移动端优化。不要把 SaaS 操作改回旧 `reader/index.html` 或 `reader/app.js`。

## 当前状态（2026-11-13 更新）

- 2026-11-13国内入口通过 `@site.SiteFrame` 在登录/注册及应用页面底部增加居中备案号链接；国际 `SiteFrame` 透传原布局，业务组件继续共享。国内登录与已登录设置页已通过隔离浏览器验证；公网发布状态见 [博客分站交接](../blog-domains/HANDOFF.md)。阅读器页脚位于正常文档流，不固定覆盖播放控件。
- PC 主要页面与 API 流程已实现；移动端正式优化尚未开始。
- 本地开发服务已启动：Vite `4173`、SaaS 后台 `8790`，数据库、Redis、验证码均独立在本机。后台健康接口返回 200；未登录访问 `/api/auth/me` 返回 401 `authentication_required` 是预期行为。
- 已移除 Vite API / 媒体远程覆盖变量与远程调试启动器，避免旧会话环境影响本地请求；具体运行状态见 local-development 交接。

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
