# RynEnglish 品牌与源码同步

更新时间：2026-11-07（Asia/Shanghai）

## 目标与现状

- 网站统一为 `RynEnglish`，域名 `rynenglish.com`，标语 `Every Page, A Deeper Understanding.`。
- 正式 R/e 图标：松林绿 `#285c45`、纸白 `#faf8ef`、暖金 `#d7ba80`，e 位于 R 右上角。内部 Cookie、存储键、协议、容器/目录/数据库标识继续兼容原 `shiyue`。
- 品牌完整提交 `7b65f78` 已通过双亲合并提交 `d1ca8d9` 正式合入并推送 main；远程 `feat/rynenglish-brand` 已删除，本地原本无同名分支。合并保留 main 的上传完整性与 Linux 对齐部署修复；原工作区阅读器、分段补传及额外品牌打包门禁/回归改动独立保留，未纳入此次提交。
- 逐文件审计：42 个功能/资源文件中，38 个与原品牌提交完全一致；SettingsPage、package.json、部署 manager 和 reader_server 另保留当前阅读模式、依赖、对齐与导入补丁。审计清单 `/private/tmp/english-reader-ryn-sync/audit.json`。
- 原因：2026-11-06 品牌任务独立分支提交并上线，当时未合入 main；之后从 main 修导入/阅读器时仅在定向发布中保留生产品牌产物，未回合源码。上一轮局部替换标题/图标仍有遗漏；本轮按完整提交同步。

## 已同步范围

- 原版 `BrandLogo.jsx` / `BrandLogo.css` 与 `config/brand.mjs`，覆盖公开页头尾、工作区、登录/注册、邮箱验证/重置；移除上一轮临时 `brand-logo.css` 实现。
- 首页标语、标题、description / Open Graph、版本化 SVG/ICO/favicon/Apple touch 与全部 PNG 正式资产。
- 购买/会员/运营/新手引导、管理摘要下载文件名、五个法律源文档；法律 React 页面直接复用源文档，不再运行时替换品牌。
- 两张正式产品截图 `workspace-current.jpg` / `vocabulary-review-20261026.webp`，仍按内容哈希刷新 URL。
- 验证/密码重置邮件主题与标语签名、支付/业务错误提示、CLI/本地启动/安装升级提示、旧 reader 兼容图标。
- 原提交附带的账号操作调整：设置“账号操作”，移除“导出账户数据”入口，保留退出/注销；购买恢复“不再提醒”，沿用原 `clear_purchase` API。
- 只读核对生产：`saas_auth.py`、`saas_commerce.py`、`saas_payments.py`、`reader_server.py` 当前与生产逐字节一致；全部正式图标、法律文案与生产一致。本轮无需再次发布已有生产品牌。

## 安装与升级

- `manager.build_frontend_assets()` 在任何部署打包前构建，检查 RynEnglish 标题、三种入口图标引用、五个非空品牌资产；缺失中止。新安装/重装/升级共用此入口，`code_files()` 归档完整 reader 与 tools，邮件/品牌文件随包携带。
- modern smoke 检查 Open Graph、版本化图标引用和源/构建资产字节一致；部署测试覆盖缺图标、旧标题阻断和归档包含品牌。
- 后续定向修复须同步完整源码及交接，不得只保留线上产物而使当前分支缺失已上线品牌修改。

## 验证

- 本次 Git 合并在隔离工作区验证：构建、modern smoke、UI 22 项、邮件/部署/对齐/上传完整性 38 项、JS 检查、11 个变更 Python 文件编译和 diff 检查通过；两份交接文档冲突保留双方内容。切换 main 前后原工作区 673 个文件状态/内容指纹一致，随后仅更新本轮交接状态。
- 构建、modern smoke、UI 22 项、阅读器 Node 7 项/Python 15 项、JS 检查、相关 Python 编译、diff 检查通过。
- `PYTHONPATH=tools .local/saas-venv/bin/python -m unittest tools.test_saas_mail tools.test_deployment_release_pipeline`：19 项通过。邮件主题/签名/原令牌链接用 mock 验证，无真实发信。当前统一使用独立本地环境的 venv，启动见本地开发指南。
- `tools/test_brand_browser.cjs`：生产构建预览的首页/登录/注册/套餐/支持/五个法律页/重置/验证共 12 路由；正式标志/标语、标题、Open Graph、截图原字节、无旧文案/溢出通过。隔离业务 API 验证账号操作、“不再提醒”原 POST、失败重试，无真实账号写入。
- 本地真实登录/注册/找回验证码 SDK 出图通过；后台已重新加载，4173 前端及受监督 SSH 隧道保留。
- 合并后的生产构建另复验 EPUB 2/3/目录兜底/最新真实两章共四组，900ms 翻页、背景与页脚对齐、横竖原图两布局通过；临时 4176 构建预览已关闭。
- 截图/日志 `/private/tmp/english-reader-ryn-sync/`；旧 `output/branding/shiyue-icon-320.*` 仅作历史导出保留。

## 关键文件

- `frontend/src/components/BrandLogo.jsx` / `BrandLogo.css`、`frontend/src/config/brand.mjs`、`frontend/index.html`。
- `frontend/public/brand/`、`frontend/public/product/`、`reader/legal/`。
- `frontend/src/main.jsx`、`pages/PublicSite.jsx` / `SettingsPage.jsx` / `LegalPage.jsx`。
- `tools/saas_auth.py`、`saas_commerce.py`、`saas_payments.py`、`reader_server.py`、`deployment/manager.py`。
- `tools/test_brand_browser.cjs`、`test_modern_frontend.py`、`test_saas_mail.py`、`test_deployment_release_pipeline.py`。

## 未完成

- 品牌原始提交已合并 main 并清理分支，无阻塞。原工作区阅读器/导入与额外品牌门禁/回归改动尚未提交；本轮未修改生产数据、重新部署或重启生产服务。
