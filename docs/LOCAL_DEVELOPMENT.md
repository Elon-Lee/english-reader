# RynEnglish 本地开发启动指南

更新时间：2026-11-08。此文档是本地开发环境的唯一有效操作说明；旧启动指南统一链接到这里。

## 1. 固定运行方式

本地调试运行完整的 SaaS 应用。PostgreSQL、Redis、验证码、Python API、调试邮箱和前端全部在当前电脑运行，数据存放在当前项目目录。启动不需要 SSH、远程服务器、生产账号、Docker、手动激活虚拟环境或临时 export 环境变量。

首次安装需要联网下载官方依赖；安装完成后，启动和本地登录不依赖远程节点。主动使用在线视频、外部 AI、购买链接或管理员部署服务器，仍会访问对应外部服务。

| 服务 | 本机地址 | 用途 |
| --- | --- | --- |
| React / Vite | `http://127.0.0.1:4173` | 唯一浏览器开发入口，包含登录、阅读和管理界面 |
| Python API | `http://127.0.0.1:8790` | SaaS API；直接访问后台根路径返回 404 是正常行为 |
| PostgreSQL 16 | `127.0.0.1:55432` | 独立本地正式库 `shiyue_saas_local` |
| Redis 7 | `127.0.0.1:56379` | 本地缓存、限流、验证码业务凭证；业务使用数据库 0 |
| Java 验证码 | `http://127.0.0.1:18080/health` | 本地 ROTATE 图像生成与轨迹校验；内部接口需要密钥 |
| 调试 SMTP | `127.0.0.1:1025` | 捕获邮件到 `.local/smtp-outbox/`，不实际发往邮箱 |

这些服务只监听回环地址。端口固定，不额外启动系统 PostgreSQL / Redis 服务，不运行 `brew services start`。

## 2. 当前这台 Mac：直接启动

本机依赖已安装。新终端、新会话或重启电脑后，直接执行完整命令：

```sh
cd /Users/elonlee/Documents/myporject/english-reader
./start-reader.sh --saas-local
./start-reader.sh --status-saas-local
```

成功时显示“独立本地 SaaS 已启动”，状态中 `redis`、`captcha`、`backend`、`frontend` 和所有 `listeners` 均为 `true`。然后打开 `http://127.0.0.1:4173`。

启动器会将服务放到后台，命令返回后可以关闭终端。重复执行启动命令会检查并复用已运行的服务。电脑重启后需要重新执行启动命令；没有配置开机自动启动。

## 3. 新电脑或重新克隆：首次安装

支持 macOS 的 Intel / Apple Silicon，以及 Linux 的 x86_64 / arm64。Linux 安装步骤以 Ubuntu 24.04 为基线；Windows 使用 Ubuntu 24.04 WSL2，并在 WSL 文件系统内放置项目。

下面的安装命令必须在**包含 `start-reader.sh`、`package-lock.json`、`tools/` 的项目根目录**运行。项目放在其他路径时，先用 `cd` 进入该项目根目录；不要照搬第 2 节的本机路径。

### 3.1 安装系统前置依赖

macOS：安装 Xcode Command Line Tools、Homebrew、Python 3.11+ 和 OpenSSL 3。已安装的依赖无需重复安装。

```sh
xcode-select --install
```

上面的系统安装窗口完成后再继续。尚未安装 Homebrew 时，执行官方安装命令并按提示完成系统授权（已安装则跳过此行）：

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

在当前安装终端识别 Homebrew，再安装 Python / OpenSSL：

```sh
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
brew install python@3.11 openssl@3
```

若当前 Mac 的 Homebrew 已不提供 PostgreSQL / Redis 二进制包，不影响后续安装；本项目安装器直接编译这两个服务。系统仍需可用的 C 编译器、Python 3.11+ 和 OpenSSL 3 开发文件。

Ubuntu 24.04 / WSL2 Ubuntu 24.04：

```sh
sudo apt-get update
sudo apt-get install -y git build-essential curl ca-certificates bzip2 perl pkg-config libssl-dev zlib1g-dev python3 python3-venv
```

不要以 root 身份运行本项目的安装器或服务，PostgreSQL 不允许以 root 启动。

### 3.2 安装项目依赖

在项目根目录执行：

```sh
sh tools/install_local_services.sh
```

安装器会下载并校验官方包，在项目忽略目录安装 PostgreSQL 16.15、Redis 7.4.7、Node.js 22.16.0 和 Corretto JDK 21，创建 `.local/saas-venv`，安装 `requirements-saas.txt`，按 `package-lock.json` 执行 `npm ci`，构建并测试验证码 JAR。PostgreSQL / Redis 编译过程的日志位于 `.local/local-dev/tools/`。

安装器自动查找 Python 3.11+；macOS 自动识别 `/usr/local` 和 `/opt/homebrew` 的 Python / OpenSSL。使用其他安装路径时，只在首次安装命令指定真实路径，例如：

```sh
LOCAL_PYTHON_BIN=/opt/python/bin/python3.11 LOCAL_OPENSSL_DIR=/opt/openssl sh tools/install_local_services.sh
```

此处两个路径仅为自定义安装的示例，必须替换为当前机器上实际存在的路径。日常启动无需这些变量。

如果服务已经运行，安装器会拒绝更改运行中的依赖。先执行 `./start-reader.sh --stop-saas-local`，再安装依赖，完成后重新启动。

### 3.3 首次初始化并启动

```sh
./start-reader.sh --saas-local
./start-reader.sh --status-saas-local
```

首次启动自动生成独立本地密钥、初始化项目私有 PostgreSQL 数据目录、创建 `shiyue_saas_local`、应用仓库迁移并创建已验证的本地管理员；启动 Redis、Java 验证码、API / SMTP 和 Vite。验证码默认在首次初始化时开启，开启前检查 Redis 和真实 ROTATE 出图。

初始数据不包含线上用户、线上书籍、生产 Token 或生产支付配置。正常页面中的空书架 / 空书城属于真实空数据状态，需要在本地导入资源。不会自动下载或恢复生产数据。

## 4. 登录与邮件

访问 `http://127.0.0.1:4173/login`。本地管理员邮箱为 `admin@local.test`，随机初始密码写在当前项目的：

```text
.local/local-dev/admin-credentials.txt
```

此文件权限为 `0600`。只在本机查看，不复制进 Git、日志或交接文档。真实旋转验证码照常校验；不会为本地调试绕过认证、管理员权限或 CSRF。

重启服务不会重设已存在的管理员密码。如果在页面修改了密码，后续使用新密码，凭据文件仅记录首次初始化的密码。

注册验证和找回密码邮件写入 `.local/smtp-outbox/*.eml`。用文本编辑器打开最新邮件，使用其中链接完成操作；收件人的真实邮箱不会收到这些调试邮件。

请统一使用 `127.0.0.1:4173`，不要在同一次登录流程中交替使用 `localhost`，两者的 Cookie 属于不同主机。

## 5. 日常启动、停止与更新

以下命令均在项目根目录执行：

```sh
# 启动全部本地服务；不加载 .env，不使用 READER_PYTHON 覆盖
./start-reader.sh --saas-local

# 查看项目进程归属和本机监听状态
./start-reader.sh --status-saas-local

# 停止全部项目服务；保留数据库、Redis 持久化文件、账号和媒体
./start-reader.sh --stop-saas-local

# 停止后重新启动，重新加载后端代码 / 验证码 / 前端配置
./start-reader.sh --restart-saas-local
```

默认 `./start-reader.sh` 等同于 `--saas-local`。不需要 `nohup`、单独启动 Vite、单独执行 `reader_server.py` 或先激活 Python venv。

React 组件修改由 Vite 热更新；Python 代码、验证码源码和 Vite 配置修改后执行重启。验证码构建按源码和 JAR 内容哈希检查，避免固定构建时间戳导致每次启动都重复编译。运行中的验证码源码变化时，先停止再重新启动以安全加载新包。

拉取代码后如果依赖清单、JDK 或前端依赖变化，按以下顺序更新：

```sh
./start-reader.sh --stop-saas-local
sh tools/install_local_services.sh
./start-reader.sh --saas-local
```

## 6. 数据、配置与换机器

| 路径 | 内容 / 处理规则 |
| --- | --- |
| `.local/local-dev/config.json` | 本机 DB / Redis 密码、会话 / 验证码密钥、初始管理员配置；`0600`，启动自动读取，禁止提交 |
| `.local/local-dev/postgres/` | PostgreSQL 16 本地数据目录；不要删除或手动修改 |
| `.local/local-dev/redis/` | Redis AOF / RDB 持久化数据 |
| `.local/local-dev/media/` | 本地 SaaS 新上传的原文件和衍生媒体 |
| `.local/local-dev/pids.json` | 当前项目后台进程记录；停止时核对命令，避免误停其他进程 |
| `.local/local-dev/tools/` | 此机器的数据库 / Redis / Node 工具，不作为跨机器安装包 |
| `.local/captcha-tools/` | 项目 JDK 和 Maven |
| `.local/saas-venv/` | 当前路径对应的 Python 虚拟环境 |
| `.local/library.sqlite3`、`.local/deployment/` | 保留的旧数据及管理员部署节点 / 密钥引用；本地 SaaS 业务数据库不使用 SQLite |

全部这些运行数据均由 Git 忽略。换机器或更换项目目录时，重新执行第 3 节安装，创建该机器独立的调试环境；不要复制 venv、编译工具或 `pids.json`。它们包含当前操作系统、CPU 和绝对目录路径信息。

需要保留已有本地业务数据时，另行进行 PostgreSQL 逻辑备份 / 恢复，并同步对应媒体和受限配置；不能把 PostgreSQL 数据目录当成通用可执行环境复制。缺失 `config.json` 但检测到数据库目录时，启动器会停止，防止生成新密码后误用原库。

远程调试启动器和远程媒体代理已删除。管理员“平台与部署”仍可主动连接已配置服务器；打开节点版本列表、检测连接或执行升级属于远程管理操作。未主动使用这些功能时，本地调试不连接部署节点。

## 7. 启动成功的检查标准

```sh
./start-reader.sh --status-saas-local
curl --fail http://127.0.0.1:8790/api/health
curl --fail http://127.0.0.1:18080/health
curl --fail http://127.0.0.1:4173/api/auth/config
```

预期：状态全部为 `true`；API 健康包含 `runtimeMode: "saas"`、`saasEnabled: true`、`redisReady: true`；Java 健康为 `status: "ok"`；首次初始化后的认证配置包含 `captchaEnabled: true`。管理员主动关闭验证码后，最后一项按真实设置返回。

浏览器登录时应出现真实旋转验证码，验证成功后进入 `/app`，管理员可看到“平台与部署”。启动器已执行 PostgreSQL 实际连接、Redis PING 和共享密钥认证的真实验证码出图；状态命令本身只展示进程和端口，不替代功能验证。

在不激活虚拟环境、不配置 PATH 的情况下运行常用检查：

```sh
.local/saas-venv/bin/python tools/run_local_dev.py exec -- npm run build:modern
.local/saas-venv/bin/python tools/run_local_dev.py exec -- npm run test:modern
.local/saas-venv/bin/python tools/run_local_dev.py exec -- npm run test:ui
.local/saas-venv/bin/python -m unittest discover -s tools -p test_run_local_dev.py
git diff --check
```

集成测试只能使用以 `_test` 结尾的隔离 PostgreSQL 库，验证码集成另外使用 Redis 数据库 15。不要把正式本地库或线上库传给会清空数据的测试。`--saas-smoke` 依赖既有隔离测试夹具，不是首次启动或健康检查命令。

## 8. 常见故障

| 现象 | 明确处理步骤 |
| --- | --- |
| 提示缺少 Python / Node / Java / PostgreSQL / Redis | 按第 3 节安装系统前置依赖，再执行项目安装器；不要临时使用 `/private/tmp` 中的工具 |
| 某端口被其他进程占用 | 先执行本项目停止命令；仍冲突时用 `lsof -nP -iTCP:端口号 -sTCP:LISTEN` 确认归属，由对应程序释放端口后重试；启动器不会擅自杀其他服务 |
| 安装失败 | 查看 `.local/local-dev/tools/postgresql-install.log` 或 `redis-install.log`；确认编译器、OpenSSL 开发文件、网络下载正常；修复后重跑安装器，已有数据不会重建 |
| 启动中途失败 | 查看下述各服务日志，修复原因后重新启动；已启动的项目进程有 PID 记录，可以统一停止；不要删除数据库目录 |
| 验证码暂不可用 | 先查 API 健康和 Java 健康，再查 `redis.log` / `captcha.log` / `backend.log`；执行完整重启。不要关闭验证码规避连接错误 |
| 本地登录原线上账号失败 | 本地数据库与线上独立；使用第 4 节的本地账号。线上书籍不会自动出现在本地 |
| 找回密码收不到邮件 | 查看 `.local/smtp-outbox/` 中最新 `.eml`；本地 SMTP 只捕获，不外发 |
| 页面还是旧版本或 API 报错 | 确认浏览器使用 `127.0.0.1:4173`，执行完整重启，再刷新页面；4173 以外的旧端口不是本指南入口 |
| 提示验证码源码变化 | 先停止再启动，或执行 `--restart-saas-local`；需要重建后再启动 Java |
| 数据库存在但配置缺失 | 恢复原 `.local/local-dev/config.json`；不生成替代密码，不删除原库 |

运行日志固定为 `.local/local-dev/postgres.log`、`redis.log`、`captcha.log`、`backend.log`、`frontend.log`。日志目录由本机用户独占；不要把密钥、密码、会话 Cookie 或整个配置文件贴进日志和问题描述。

本机已验证：macOS 15.7.8 Intel，PostgreSQL 16.15、Redis 7.4.7、Node 22.16.0、Python 3.11.18、JDK 21.0.13；完整启停后账号、密码哈希、迁移记录与 Redis 数据保留；真实 Chrome 验证码登录和管理员权限通过。其他操作系统 / CPU 的安装分支需要在对应机器执行验收，不将本机结果视为跨平台实测。
