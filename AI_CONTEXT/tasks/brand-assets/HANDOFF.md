# RynEnglish 品牌与网站图标

## 目标与设计

- 网站名称统一为 `RynEnglish`，域名 `rynenglish.com`。
- Slogan：`Every Page, A Deeper Understanding.`（保留大小写、逗号和句号）。
- 沿用纸白、松林绿主题：`#285c45` 绿底、`#faf8ef` 米白 R、`#d7ba80` 暖金小写 e；按用户最新方向将 e 独立置于 R 的右上角，图标不依赖外部字体或图片服务。
- 用户已要求直接修改并发布。当前分支 `feat/rynenglish-brand`，基线 `main` / `bd846f0`；用户已授权提交并推送当前分支；未要求合并主分支。

## 当前实现

- 统一 `BrandLogo` 覆盖公开页头/页脚、工作台侧栏、登录/注册、邮箱激活和重置密码页；slogan 接入首页首屏及品牌组件。
- 页面标题、SEO/Open Graph、SVG/ICO favicon、Apple touch icon、购买/兑换、运营说明、新手引导、截图替代文本、法律文案、邮件主题/签名与运行提示同步更新。
- 首页两张真实产品截图只替换旧品牌区域，保留业务画面；URL 延续构建时内容哈希缓存策略。
- 内部 `shiyue_*` 标识、Cookie/localStorage 键、容器、目录、数据库和兑换码协议保留，确保现有会话与数据兼容。历史任务文档与旧构建文件不批量重写。
- 旧 reader 图标路径保留并更新图形；SaaS 页面继续走 React，不增加旧 UI 跳转。
- 第二轮调整同步导出全部 PNG/ICO 与产品截图；站内标记及 favicon/Apple touch URL 加 `v=20261106-re2`，避免首版 immutable 缓存。

## 关键文件与素材

- `frontend/src/components/BrandLogo.jsx` / `BrandLogo.css`：统一品牌组件与各场景尺寸。
- `frontend/src/config/brand.mjs`：名称、slogan、标记路径。
- `frontend/public/brand/`：SVG 源文件、512/320 PNG、180 Apple touch PNG、16/32/48 ICO。静态资源为 immutable 缓存，后续更新需变更文件名或 URL 版本。
- `frontend/index.html`：初始标题、分享信息和图标引用。
- `frontend/src/main.jsx` / `pages/PublicSite.jsx`：页面标题、品牌组件、首页 slogan。
- `reader/legal/*.html`：React 法律页面共用文本。
- `tools/saas_auth.py`：验证/重置邮件主题与签名；DirectMail 发件名已有 RynEnglish，无需改凭据。
- `frontend/public/product/workspace-current.jpg`、`vocabulary-review-20261026.webp`：更新品牌区域的真实产品截图。
- 先前 `output/branding/shiyue-icon-320.*` 为旧版历史导出，当前站点不再使用。

## 验证与发布

- 第二轮已通过构建、modern smoke、UI 22 项、JS/Python 编译、SVG XML 与 diff 检查；隔离 Chrome fixture 验证账号操作文案、移除导出入口、保留退出/注销，以及“不再提醒”的原 `clear_purchase` POST 与失败重试，无生产账号写入。京东云任务 #5 complete，当前版本 `code-20261106-113458-43116bfb`，备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261106-113458-43116bfb.dump`；健康与 Cloudflare active。
- 第二轮公网 Chrome 首页/登录验收通过：版本化 Logo 与本地字节 SHA256 一致、favicon 引用新版本、无渲染异常；线上 bundle 含“不再提醒”“账号操作”，不含旧按钮文案与导出入口。截图 `.local/rynenglish-re2-production-{home,login}.png`；登录后设置交互使用隔离 fixture 验收，未操作生产账号。
- 已通过前端构建、modern smoke、22 项 UI、JS 检查、SMTP 3 项、部署 71 项、前端路由 2 项、验证码 7 项、Java 8 项、11 个 Python 文件编译及 diff 检查；两类邮件主题/签名/令牌 URL 用 mock 验证，无真实发信。
- 独立 Chrome 已检查首页、登录/注册、套餐、支持、五个法律页和重置密码页：标题/Logo/slogan 正常、无旧中文品牌、无横向溢出及渲染异常。首次预览后台未启动，随后通过 SSH 隧道连接真实远端只读 API 复验通过，无连接提示。
- SVG XML 与 PNG/ICO 导出已验证并目视检查。浏览器截图 `.local/rynenglish-*.png` 为临时产物，不提交。
- 2026-11-06 京东云升级任务 #4 complete，当前版本 `code-20261106-111413-2385a2c5`；数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261106-111413-2385a2c5.dump`（非空），保留原数据与入口。
- Cloudflare 公网入口 `https://10ye.cc` 独立 Chrome 上述 11 个路由均通过；首次图标断言因网络尚未加载完成失败，改为等待真实图片加载后通过，非服务端资源错误。生产截图 `.local/rynenglish-production-{home,login,terms}.png`。
- 正式域名在服务器侧严格 TLS 返回新品牌页面，公网 IP:5173 严格信任原 CA 返回200，SaaS/Redis/验证码配置与 Cloudflare active；Logo 与邮件代码远端 SHA256 均和本地一致。
- 已知外部条件：本机直连 `rynenglish.com:443` 仍为既有 SSL 连接超时，未将服务器自访问当作公网域名验收；Cloudflare 公网已验收。源码交付分支 `feat/rynenglish-brand`，提交与推送状态以 Git 为准。

## 验证和发布命令

```bash
npm run build:modern
npm run test:modern
npm run test:ui
npm run check:js
PYTHONDONTWRITEBYTECODE=1 .local/auth-venv/bin/python -m unittest discover -s tools -p test_saas_mail.py
git diff --check
```

发布复用 `tools/deploy_remote.py --target 京东云服务器 --upgrade --identity-file <本机私钥路径>`，保留数据、标准 HTTPS 和 Cloudflare/5173 入口。
