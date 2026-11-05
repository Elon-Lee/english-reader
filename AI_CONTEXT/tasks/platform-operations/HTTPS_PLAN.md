# rynenglish.com 标准 HTTPS 入口实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 在当前会话逐项实施。用户已确认 Docker Nginx + Certbot 方案和实机安装，无需再次请求同一操作授权。

**Goal:** 京东云提供 80 → 443 跳转、rynenglish.com 的 Let's Encrypt 证书和自动续期，安装与升级不会丢失入口配置。

**Architecture:** 公网 Nginx 代理既有回环 HTTP 前台 5173，应用后端保持 8790。Certbot 使用独立 HTTP-01 webroot；ACME 状态放在安装目录外的持久目录，systemd timer 触发续期并在签发成功后校验、重载 Nginx。仅入口命令不打包或发布业务代码；变更 APP_BASE_URL 时使用既有镜像重建后台容器并提供失败回退。

**Tech Stack:** Python 标准库、Docker Nginx、Docker Certbot、systemd、现有 React/Ant Design 节点设置。

## 1. 配置与回归

- [x] 新建 `tools/test_deployment_https_entry.py`：域名校验、节点保存、旧节点配置保持、HTTP 验证路径和跳转、持久化证书目录、续期失败不重载、入口命令不发布业务代码。
- [x] 运行失败用例后，新增 `tools/deployment/https_entry.py`，导出 `normalize_domain(value)`、`frontend_url(target)`、`install_script(target)`。
- [x] `tools/library_db.py` 为节点增量增加 `public_domain`，`manager.save_target()` 保存校验后的域名，未提供字段时保留原值。

```bash
PYTHONPATH=tools /usr/local/bin/python3.13 -m unittest tools.test_deployment_https_entry
```

## 2. 安装和升级共用入口

- [x] `manager.ensure_remote_saas_config()` 在明确配置新域名时精确写入 `APP_BASE_URL=https://<domain>`；没有新域名时兼容旧逻辑。
- [x] 在 `start_saas_upgrade()`、`start_saas_deploy()` 的应用验收后调用 `ensure_remote_https_entry()`，返回正确公网地址。远端已有入口配置时发现并恢复域名，防止旧本地节点配置覆盖新入口。
- [x] `tools/deploy_remote.py` 增加 `--https-entry`、`--domain`、`--host`、`--identity-file` 等仅入口参数，复用 SSH 认证和安装逻辑；不运行完整部署。
- [x] 平台节点表单增加域名字段，明确显示公网 80/443 与内部 5173 的区别；空域名兼容既有自建证书节点。
- [x] 后台配置变更时先保存权限受限的配置/容器备份，保留旧容器以便失败后恢复；同一镜像重新启动并验收后删除旧容器。

## 3. 本地验证

- [x] 检查生成的安装/续期脚本 `bash -n`；测试配置失效保留旧 Nginx 文件。
- [x] 运行部署 HTTPS、节点、发布流程相关回归。
- [x] 安装 lockfile 中已有依赖，运行构建、modern/UI/JS 检查。
- [x] Python 编译及 `git diff --check`。

```bash
npm ci
npm run build:modern
npm run test:modern
npm run test:ui
npm run check:js
PYTHONPATH=tools /usr/local/bin/python3.13 -m unittest tools.test_deployment_https_entry tools.test_deployment_https tools.test_deployment_nodes tools.test_deployment_release_pipeline
/usr/local/bin/python3.13 -m py_compile tools/deployment/https_entry.py tools/deployment/manager.py tools/deploy_remote.py tools/library_db.py tools/test_deployment_https_entry.py
git diff --check
```

## 4. 实机实施与验收

- [x] 用用户指定私钥执行仅入口命令，保留当前业务版本和数据。
- [x] 核对公网 HTTP 带路径/查询参数的 308、443 受信任证书链及域名、首页/API、后台 APP_BASE_URL、定时器。
- [x] 执行续期 dry-run，使用真实 ACME staging 验证 HTTP-01 与重载钩子。
- [x] 同轮更新 `HANDOFF.md` 和全局索引中的生产入口状态，记录已执行验证及任何外部阻塞。
