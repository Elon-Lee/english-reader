# 纸间微光博客与阅读子域名

更新时间：2026-11-11（Asia/Shanghai）

## 已确认范围

- 用户确认采用 Astro + Retypeset；主域名独立博客，阅读应用迁到 `learn.rynenglish.com`，主站不包含子站入口或业务资源。
- 已授权发布京东云，保留已有数据库与媒体。工作分支 `feat/paper-glow-blog-domains`，基线 `810f19a`。
- 设计与执行计划在 `docs/superpowers/specs/2026-11-11-paper-glow-domains-design.md` 和对应 plans 文件。

## 当前状态与外部条件

- 博客、Host 分站、双域名独立证书与续期、保数据升级集成已实现。用户已提供可用 SSH 私钥；凭据内容不得写入文档或日志。
- 用户明确选择稍后添加 DNS、先部署源站。公共 DNS 实测主域名指向京东云，learn 为 NXDOMAIN；主域名 HTTP 返回 JDTP 403，HTTPS 未连通。源站部署使用 `--upgrade --app-domain learn.rynenglish.com --blog-domain rynenglish.com --defer-https`，不能声称公网 HTTPS 已完成。
- 已验证 React 构建、modern/UI/JS、106 项部署回归、75 项域名/HTTPS/路由测试；额外覆盖切换后配置保存失败的回退路径。主域名不代理 API，未知 Host 拒绝，所有 User-Agent 返回一致。
- 当前准备执行远端升级，尚未修改远端。

## 关键文件与维护

- `blog/` 为独立 Astro + Retypeset 工程，MIT 来源、Markdown 写作和 Node 要求见 `blog/README.md`；根依赖未变。
- `reader/blog/` 为生成且忽略的静态产物；`npm --prefix blog run build` 和 `npm --prefix blog run verify` 生成并验证。部署包自动包含该目录，不直接修改。
- `tools/saas_frontend_server.py` 根据 `APP_DOMAIN`、`BLOG_DOMAIN`、`BLOG_ROOT` 精确分站；主站独立静态目录，应用保留原 API 与鉴权。
- `tools/deployment/manager.py` 构建双站、备份数据库与站点配置、候选检查、切换失败回退。`shared/config/sites.json` 持久化双域名与 `https_deferred`，后续升级优先恢复该配置。
- `tools/deployment/https_entry.py` 支持主/子域各自证书和续期；待两域 DNS 与京东云放行完成后，仅补装 HTTPS，不重装或导入数据库。
- 博客当前含三篇原创方法笔记，不虚构个人经历；备案号配置为空，取得真实号码后填写 `blog/src/config.ts` 的 `icpRecord` 并重新构建发布。
