# 纸间微光博客与阅读子域名

更新时间：2026-11-11（Asia/Shanghai）

## 已确认范围

- 用户确认采用 Astro + Retypeset；主域名独立博客，阅读应用迁到 `learn.rynenglish.com`，主站不包含子站入口或业务资源。
- 已授权发布京东云，保留已有数据库与媒体。工作分支 `feat/paper-glow-blog-domains`，基线 `810f19a`。
- 设计与执行计划在 `docs/superpowers/specs/2026-11-11-paper-glow-domains-design.md` 和对应 plans 文件。

## 当前状态与外部条件

- 正在接入博客和双站配置；用户已提供本机 SSH 私钥路径，凭据内容不得写入文档或日志。
- 公共 DNS 初查主域名指向京东云，learn 为 NXDOMAIN；主域名 HTTP 返回 JDTP 403，HTTPS 未连通。需继续核实最新状态，不能声称公网已发布。
- 当前尚未修改远端。
