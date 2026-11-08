# 独立本地开发环境

更新时间：2026-11-08（Asia/Shanghai）。用户要求本地调试不连接远程，并删除远程调试代码，完整记录可跨会话使用的启动流程。

## 目标与当前状态

- 唯一操作说明：[docs/LOCAL_DEVELOPMENT.md](../../../docs/LOCAL_DEVELOPMENT.md)；根 README 和旧 SAAS_DEPLOYMENT 指南均指向此文档。后续修改启动行为时同步更新该文档，不再复制另一份独立操作步骤。
- 当前 Mac 已安装项目内 PostgreSQL 16.15、Redis 7.4.7、Node 22.16.0、Python 3.11.18 venv 和 Corretto JDK21；数据库、缓存、验证码、API / SMTP、Vite 已启动，均只监听回环。
- 固定端口：PG55432，Redis56379，Java18080，API8790，SMTP1025，Vite4173。正式本地库 `shiyue_saas_local`，本地媒体 `.local/local-dev/media`，与线上用户/书籍/密钥完全独立。
- `start-reader.sh` 默认与 `--saas-local` 均启动完整本地栈；在读取 `.env` / `READER_PYTHON` 前分派到项目 venv。支持 `--status-saas-local`、`--stop-saas-local`、`--restart-saas-local`。无需激活 venv、临时PATH或SSH；后台进程可保留跨终端运行，电脑重启后需再次启动。
- `tools/run_remote_dev.py` 和其 SSH 监督/隧道测试已删除；Vite API / books / 媒体代理固定本机8790，远程覆盖入口已删除。三入口验证码浏览器脚本改为 `test_local_captcha_browser.cjs`。旧 `.local/remote-dev` 忽略目录仅保留既有资料，不再作为运行或安装依赖。
- 管理员主动服务器管理能力保留：SQLite节点/已有SSH密钥引用不改；查看远程版本、检测节点和升级会主动连接对应服务器。正常本地启动/登录/学习不访问节点。本轮未执行生产操作。

## 配置与生命周期

- 配置 `.local/local-dev/config.json` 权限0600、目录0700；自动生成本机 DB/Redis 密码、session/captcha secret 和本地管理员初始密码。禁止写进Git、日志或交接。日常启动仅白名单继承OS/工具链变量，排除旧远程/支付/SMTP/audit配置。
- 本地管理员 `admin@local.test`，初始凭据仅在 `.local/local-dev/admin-credentials.txt`（0600）。重启不重设密码。首次自动应用迁移并开启验证码，现有开关设置不被重启覆盖；没有恢复生产账号/书籍。
- PostgreSQL由pg_ctl维护项目私有集群；Redis开启AOF/RDB；PID核对归属后停止项目进程；停止保留DB/缓存/媒体，不杀其他服务。缺失配置但已有PG数据时拒绝初始化，避免覆盖。
- `install_local_services.sh` 支持macOS/Linux x86_64/arm64，官方SHA256校验PostgreSQL/Redis/Node/JDK；系统前置依赖/明确安装命令见操作说明。安装要求停止已有本地栈，按lockfile安装npm和项目venv依赖。仅当前Mac分支已实测。
- 验证码JAR使用固定时间戳，启动器按源码/JAR哈希检查是否需要重建；运行时源码变化先停止再启动。邮件由本机SMTP捕获到 `.local/smtp-outbox`，不外发。

## 关键文件

- `start-reader.sh`：统一公共入口。
- `tools/install_local_services.sh`：项目依赖安装。
- `tools/run_local_dev.py`：独立配置/初始化/进程管理/真实依赖检查；`exec -- <command>` 向检查进程注入同一套本地配置及工具路径。
- `tools/run_local_saas.py`：内部API/SMTP子进程启动；不是日常入口。
- `tools/stop_local_saas.py`：历史兼容入口，转到统一停止器，不再按端口盲杀进程。
- `frontend/vite.config.js`：4173 / strictPort，所有API和媒体固定代理8790。

## 已执行验证与限制

- 本机官方源码校验、PG/Redis编译安装、Java构建8项、前端生产构建、modern/UI22项/JS、Python编译和diff检查通过。
- 独立本地库/Redis15：验证码6项中5项通过，1项依赖固定测试Java secret的旧live用例跳过；phase9 PostgreSQL4项与完整HTTP smoke29项通过。真实业务Java出图另由启动器和Chrome独立验证，未关闭本地验证码。
- Chrome无mock验证登录/注册/找回密码三入口图片，以及真实旋转校验→本地管理员登录→工作区/平台权限/本地节点配置；浏览器无外部网络请求。测试凭据仅进程内读取，不写日志。
- 实际完整停止后全部监听关闭；再次启动后本地账号ID/密码哈希/迁移记录与Redis临时检查值保留；重复启动复用进程，JAR不重复构建。
- 删除远程入口后新增/保留本地启动8项、部署打包23项通过；清空终端环境的安装器和启动实测通过，注入旧远程DB/Redis/媒体/无效Python变量仍连接本机55432/56379。本地文档相对链接检查、shell/JS语法、Python编译及diff通过；原转发端口关闭，最后Chrome三入口与完整登录复验通过。当前服务全部保持运行。
- 当前Mac之外的Linux/Apple Silicon安装分支尚待对应机器验收。AI/支付等外部平台配置未迁移，需按具体调试任务在本地另行配置。

## 验证命令

```sh
./start-reader.sh --status-saas-local
.local/saas-venv/bin/python -m unittest discover -s tools -p test_run_local_dev.py
.local/saas-venv/bin/python tools/run_local_dev.py exec -- npm run build:modern
.local/saas-venv/bin/python tools/run_local_dev.py exec -- npm run test:modern
.local/saas-venv/bin/python tools/run_local_dev.py exec -- npm run test:ui
.local/saas-venv/bin/python tools/run_local_dev.py exec -- npm run check:js
git diff --check
```

浏览器用例额外需要playwright-core；完整旋转登录测试额外需 `.local/local-dev/test-venv` 中的Pillow/numpy，仅测试依赖。环境变量 `PLAYWRIGHT_MODULE` 指向实际安装模块，完整登录另需 `SHIYUE_LOCAL_BROWSER_TEST=1`。这些不是启动依赖，不应把临时测试工具路径写回启动器。
