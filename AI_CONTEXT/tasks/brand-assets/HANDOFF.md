# 纸间微光品牌

更新时间：2026-11-09（Asia/Shanghai）

## 当前状态

- 当前分支 `refactor/private-paper-glow` 已将网站名改为“纸间微光”，标语“一页一光，静读慢行。”。本轮未提交或部署。
- 统一图标 `frontend/public/brand/paper-glow-mark.svg`；页面标题、认证页、邮件主题与签名、四个法律页、CLI、安装升级默认发件名称同步。
- 已移除旧 RynEnglish SVG/ICO/PNG、支付图片、未使用营销截图；删除旧 modern 编译包，生产构建从源码生成。
- 内部 Cookie、数据库、容器、目录及部分 CSS 类名继续兼容原标识；实际域名未变更。
- 本任务属于 [私域改造](../private-paper-glow/HANDOFF.md)，原商业品牌交付已被取代，不恢复套餐/购买组件。

## 关键文件

- `frontend/src/config/brand.mjs`、`frontend/src/components/BrandLogo.jsx` / `BrandLogo.css`、`frontend/index.html`。
- `frontend/public/brand/`、`reader/legal/`、`reader/favicon.svg`。
- `tools/saas_auth.py`、`tools/deployment/manager.py`、`tools/test_brand_browser.cjs`。
- 部署打包必须重新构建，检查中文标题、新 SVG，并拒绝包含已撤除商业接口的 JS。

## 验证与后续

- 生产构建、modern smoke、UI 16 项、品牌浏览器验收通过；浏览器使用隔离 API，不发送真实邮件或改写正式账号。
- 邮件回归及部署打包验证记录统一见私域改造交接。
- 本轮仅本地源码与构建改造；备案审批与域名/远程发布由后续实际指令决定。
