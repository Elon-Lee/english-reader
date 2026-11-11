# 纸间微光双站 Implementation Plan

> **For agentic workers:** 使用 superpowers:subagent-driven-development 执行。只分派一个独立博客实现任务；协调者负责入口和部署，分别审查规格与代码质量。

**Goal:** 主域名提供 Markdown 静态博客，阅读应用迁移至 learn 子域名，并按用户授权发布京东云。

**Architecture:** `blog/` 独立 Astro/Retypeset 工程输出到 `reader/blog/`；Python 前台按 Host 分站，Nginx 提供双域名证书与续期，原后台和数据库保持独立。

**Tech Stack:** Astro、Retypeset、React、Python HTTP、Nginx、Docker、PostgreSQL。

## Task 1: 静态博客

- [x] 从已检查的 `.local/blog-theme-retypeset` 导入主题源码至 `blog/`，记录上游 commit 和 MIT 许可，禁止复制 `.git`、示例文章或环境秘密。
- [x] 定制 `blog/src/config.ts`、内容及必要布局；中文、米白、衬线字；禁用远端评论、统计、演示社交链接和图片依赖。
- [x] 新增 `blog/README.md` 记录 Markdown frontmatter、写文章、构建及预览命令。生产输出为 `reader/blog/`。
- [x] 使用独立 lockfile 安装，运行 `npm --prefix blog run build`，要求类型检查和构建无错误；审核全部输出无子站地址。

## Task 2: 分站和发布包

- [x] 在 `tools/test_saas_frontend_routes.py` 或独立测试中加入真实 HTTP 两个 Host、主域名 API/写方法拒绝、未知 Host、路径遍历、原应用兼容测试，先运行记录失败。
- [x] 修改 `tools/saas_frontend_server.py` 实现配置驱动的静态博客与原应用分站，保留代理身份头和租户鉴权；主站只读，未知公网 Host 拒绝。
- [x] 更新 `frontend/index.html` 的应用域名元信息。
- [x] `tools/deployment/manager.py` 构建博客并将资源加入发布包、为前台增加博客挂载/域名环境变量；配置恢复与应用基础地址分开，不改写现有密钥。
- [x] 运行相关 HTTP 测试、`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、Python 编译和 `git diff --check`。

## Task 3: 双域名 HTTPS 与部署

- [x] 在 `tools/deployment/https_entry.py` 增加双站配置和证书续期支持，保留单站兼容；通过现有单站测试并增加双域名生成/验证测试。
- [x] 只读检查目标服务器 current、容器、媒体和数据库；检查公共 DNS 与公网域名放行。用户确认先部署源站，稍后添加 learn DNS。
- [x] 生成并审核发布包；经已有备份和候选切换流程升级服务器，保留真实用户数据。任务 #16 源站升级完成，未调用重装。
- [x] 源站完整页面、主域名 API 404、子站鉴权、验证码、原音推理与后台健康通过；用户/书目保留核对通过。
- [ ] 公网双域名证书与 HTTPS：按用户确认暂缓，待 learn DNS 与京东云域名放行后单独补装。
- [x] 同轮更新 `AI_CONTEXT/tasks/blog-domains/HANDOFF.md`、全局任务索引和部署交接。
