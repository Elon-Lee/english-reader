# 验证码开关与 DirectMail

## 目标与范围

- 用户已撤销密保方案。保留邮箱密码登录、邀请码注册、邮箱激活与邮件找回密码，不新增密保字段或账号迁移。
- 单一管理员开关控制天爱 ROTATE 验证码，覆盖注册、登录、换设备登录、找回密码；后端强制校验。
- 发信采用杭州 DirectMail：`smtpdm.aliyun.com:465`、`noreply@rynenglish.com`、显示名称 `RynEnglish`。SMTP 密码只存受保护配置，不能写入代码、Git、日志或文档。

## 当前状态

- 2026-11-08 本地验证码改为本机 Java + 本机 Redis + 本机 PostgreSQL，共享密钥由 `.local/local-dev/config.json` 自动生成并持久保存（0600）。旧 SSH 调试启动器与转发已删除，不再恢复远程连接。
- 全部服务统一由 `./start-reader.sh --saas-local` 启动；首装、跨会话启动和排错以 [本地开发指南](../../../docs/LOCAL_DEVELOPMENT.md) 为准。真实 Chrome 已验证登录/注册/找回密码三入口出图，并以真实旋转票据登录本地管理员，认证/管理员/CSRF限制保留。
- 当前测试：`tools/test_local_captcha_browser.cjs`（三入口出图），`tools/test_local_dev_browser.cjs`（完整本地验证码登录和管理员权限）；Java8项、Python验证码7项、本地独立库/Redis隔离集成与HTTP smoke通过。详细依赖和验证见 [local-development](../local-development/HANDOFF.md)。

- 开发分支 `feat/auth-security-captcha`，基线 `main` / `1887b0d`；交付目标为 `main` / `origin/main`，用户已授权本轮提交、合并与推送，实际提交状态以 Git 为准。用户已授权修改和远程测试发布，保留线上数据、HTTPS 和 Cloudflare 隧道。
- 已实现：Java 天爱 1.5.6 与同版本自托管 SDK，Python 一次性凭证、运营后台认证安全开关、React 验证弹窗、安装/升级/卸载集成。
- SMTP 新增 465 隐式 TLS 与发件人名称，587 保留验证证书的 STARTTLS。
- 2026-11-05 京东云图片恢复升级任务 #3 complete，当前版本 `code-20261105-173117-956a2f49`；数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261105-173117-956a2f49.dump`，保留现有数据。
- 生产验证码已开启，通过现有有效管理员身份记录配置审计；运营后台 → 认证安全可切换。开启前真实调用内部 ROTATE 生成接口检查可用性。
- DirectMail TLS/认证已通过，新容器已加载配置；向用户明确指定的测试邮箱发送一封测试邮件，`_send_mail` 返回 true，代表 SMTP 接受，实际收件待用户确认。

## 关键约束

- 验证码默认关闭；开启前检查服务与 Redis，开启后故障禁止绕过。
- 验证凭证绑定匿名 HttpOnly Cookie、操作和邮箱，短时有效且原子单次消费。
- Java 服务只监听回环，内部接口要求共享密钥；不使用公开演示服务。
- 管理配置沿用已有 platform_settings 与管理员/CSRF/审计，无需账号迁移。

## 验证与待确认

- 合并前复验：前端生产构建（输出 `.local/captcha-merge-build`）、modern/UI 22 项/JS 检查、Java 8 项、部署 71 项、验证码 7 项、SMTP 3 项，以及 14 个 Python 文件编译与 diff 检查通过；构建产物及本地配置不纳入源码提交。
- 2026-11-05 本轮反馈修复：去掉外层 Ant Design Modal，使用挂载到 body 的原生 modal dialog，仅保留 SDK 自有 318×318 面板，相对视口居中；保留加载/失败/重试/取消和 Escape。提示改为“拖动滑块，将图片转正”。
- 根因：官方 SDK 发送页面绝对坐标，而 BasicTrackCaptchaInterceptor 要求零起点；Java 适配层按 pointer-down 归一化坐标，保留角度容差、轨迹、期限和单次消费检查。新增页面偏移 socket 回归先失败（code50001）再通过，Java 测试现 8 项。先前零起点测试漏掉此场景。
- 用户反馈书籍图片难识别，已恢复原 Tianai 动物图（实际为猫咪），随 JAR 部署 `captcha/animal-default.jpg`；来源见 `services/captcha/src/main/resources/captcha/README.md`。单层居中与坐标修复保留，图片恢复版已发布；前端构建、Java 8 项、Python 验证码 7 项、Python 编译和 diff 检查通过，JAR 原图字节一致性检查通过。恢复原动物图后，线上独立 Chrome 真实拖动校验成功，弹窗居中，找回密码接口返回 200；截图 `.local/captcha-production-animal.png`，未向真实账号发信。
- 独立无头 Chrome 的真实 SDK → Python → Java → Redis/PG 验收通过：两种视口中心偏差 <2px，无额外 AntD 窗口；错误角度拒绝并刷新；正确旋转后找回密码提交200、无效邀请码注册返回业务400、测试账号登录200并进入/app。截图 `.local/captcha-browser-centered.png`。未操作用户当前浏览器。
- 修复版已发布；独立 Chrome 通过现有 Cloudflare 公网入口完成真实旋转 → 一次性票据 → 找回密码200，单层面板中心偏差 <2px，生产截图 `.local/captcha-production-centered.png`。使用不存在的合成测试邮箱，不发送真实账号邮件。SaaS/Redis/Java 健康、Cloudflare active；标准 HTTPS 的部署检查通过，原本机网络 80/443 限制仍未修改。
- 已通过：前端构建、modern/UI 22 项/JS 回归，Python 验证码 7 项、SMTP 3 项、隔离 PostgreSQL/Redis HTTP 6 项（设置 `SHIYUE_CAPTCHA_LIVE_TEST=1`，含真实 Java 图片生成）、部署 71 项、旧 Phase1 契约 3 项、Phase9 PostgreSQL 4 项、完整 HTTP smoke 29 项、Python 编译与 diff 检查；Java `build.sh` 的 8 项覆盖真实 HTTP 生成与正确轨迹、页面偏移、错误轨迹、重放、过期、内部鉴权和体积限制。本轮修复额外重跑前端构建/modern/UI/JS、Python 13 项相关单测、6 项集成及 Chrome E2E（1 项含三流程）。
- Java 默认本地缓存发现官方过期检查有清理窗口，已替换为严格期限与原子消费缓存；无网络图片依赖。SDK 来源/校验和见 `frontend/public/tianai/README.md`。
- 生产实测：验证码开启配置、四入口无票据拒绝、真实 ROTATE 图像、Secure/HttpOnly/SameSite Cookie、首页和 4 个 SDK 资源均通过；18080 仅回环监听、Java 非 root/只读根目录/512 MiB 限制，saas.env 与 captcha.env 均为 0600。5173 原入口严格信任原根证书访问 200，Cloudflare 公网 API 及本机回源均 200。
- 服务器侧访问域名 HTTPS/HTTP→HTTPS 正常；本机公网域名检查出现京东云 JDTP “网页禁止访问”403，HTTPS 超时。指定真实 IP 后 80/443 仍超时，5173 可用；本机 DNS 为代理映射地址。外部网络/代理/云侧拦截原因待确认，不得据服务器自访问宣称公网 80/443 已验收。
- 修复版独立 Chrome 自动化已通过，用户环境的旋转手感与测试邮箱最终到达待用户确认。

## 关键文件与运维

- `tools/saas_captcha.py`：platform_settings `auth.captcha`、Redis 验证凭证、内部服务调用；`tools/reader_server.py`：`/api/auth/config`、`/api/auth/captcha/gen|check`、`/api/admin/auth-config` 和四个认证入口。
- `frontend/src/components/AuthCaptcha.jsx`、`AuthSecuritySettings.jsx`，`frontend/src/main.jsx` 和 `pages/AdminPage.jsx`。
- `services/captcha/build.sh` 运行 `clean verify`，固定 Maven 3.9.9 SHA512 校验并选择 Java21；JAR 不提交。`tools/deployment/captcha.py` 构建容器并在 18081 候选健康检查后切换 18080。Java 只用专属 `shared/config/captcha.env`。
- 部署：`tools/deploy_remote.py --target <节点> --upgrade --identity-file <私钥> --smtp-config <0600配置文件>`。未提供 SMTP 配置时保留远端现有值；不提交凭据。
- Python 验证：`PYTHONDONTWRITEBYTECODE=1 .local/auth-venv/bin/python -m unittest discover -s tools -p test_saas_captcha.py`；集成另需隔离 `_test` PostgreSQL 和专用 `SHIYUE_CAPTCHA_TEST_REDIS_URL`。
- 环境配置按字面值读取，不再 source `saas.env`；仅导出 PG/Redis 白名单，支持 SMTP 名称空格和密码特殊字符，不在部署日志中输出秘密。
- 浏览器验收：`SHIYUE_CAPTCHA_BROWSER_TEST=1`、专用 `_test` PostgreSQL、隔离 Redis 与测试 Java secret，前端先构建至 `.local/captcha-fix-build`，执行 `PYTHONPATH=tools .local/auth-venv/bin/python -m unittest tools.test_auth_captcha_browser`。需隔离测试环境的 playwright/Pillow/numpy，不新增生产依赖；读取已知照片匹配旋转仅用于测试，不暴露正确答案接口。
