# 拾页 SaaS Context Handover

> 历史交接资料，内容可能已过期。后续 AI 必须先读取 `AGENTS.md` 和 `AI_CONTEXT/README.md`；只有追溯旧决策时再读取本文。

更新时间：2026-10-10（Asia/Shanghai）

本文件用于在新会话中继续开发。项目根目录：`/Users/x/Documents/english`。

## 1. 当前目标与架构决策

目标：将原本单用户、SQLite 驱动的本地英语点读系统升级为面向约 100～500 名邀请用户的单体多租户 SaaS，同时保持现有本机单用户阅读器可用。

已确定的关键决策：

- 首发仍是单体 Python 标准库 HTTP 服务，不拆微服务。
- SaaS 正式业务数据使用 PostgreSQL；旧 `.local/library.sqlite3` 保留为只读兼容库和迁移来源，绝不删除。
- 首发账号采用邀请码注册、邮箱密码登录、邮箱验证、数据库会话、CSRF。
- 套餐是 `free-v1`、`advanced-v1`、`pro-v1`；首发仅后台人工开通，不接支付 Webhook。
- 所有权益使用 PostgreSQL 账期快照、额度预占、成功结算、失败/取消释放和幂等键。
- 既有 39 本内容默认归管理员私人资源，不自动公开；官方书城仅允许 `public_domain` 或 `licensed` 且 `published` 的内容。
- 媒体首版保留文件系统存储，但 SaaS 访问只能通过 `/api/media/{asset_id}` 鉴权；旧 `/books/...` 在 SaaS 模式禁止公开。
- 本机部署节点、SSH 密码和部署任务继续使用旧本机运维库，不进入 SaaS 数据库。
- 未获单独指令前不部署远程服务器。
- `.env` 当前保持 `SHIYUE_SAAS_ENABLED=0`。这是有意的：旧单用户模式仍正常运行；SaaS 完整向真实用户开放前还要完成部分租户化、邮件和容量收尾。

## 2. 本机运行环境与数据

- macOS Intel，项目使用 Python 3.14；SaaS 依赖位于 `.local/saas-venv`，已安装 `psycopg 3.3.6`。
- PostgreSQL 16 已安装。项目独立测试集群数据目录：`.local/postgres-phase1/data`，监听 `127.0.0.1:55432`。
- 正式本机 SaaS 数据库：`shiyue_saas_local`。
- 可销毁测试库：`shiyue_phase1_test`；恢复演练库：`shiyue_restore_test`。
- 现有 SQLite：`.local/library.sqlite3`，仍有 39 本读物（34 本普通图书、2 本 audio、3 个 YouTube）。
- 既有媒体目录：`books/`，约 12GB。
- PostgreSQL 已登记媒体资产：5,286 个，`13,030,194,330` 字节；与 `storage_bytes` 账本一致。

## 3. 已完成阶段与核心代码

### 阶段 0：基线与备份

- 实施计划：[SAAS_COMMERCIALIZATION_PLAN.md](SAAS_COMMERCIALIZATION_PLAN.md)
- 初始基线备份：`.local/saas-baselines/20261009T230110/`
- 环境变量样例：[.env.example](.env.example)
- SaaS 依赖：[requirements-saas.txt](requirements-saas.txt)

### 阶段 1：账号、邀请和 PostgreSQL

核心文件：

- `tools/saas_auth.py`
- `tools/saas_migrate.py`
- `tools/saas_migrations/0001_accounts.sql`
- `tools/reader_server.py`

已完成：

- 用户、角色、邀请、验证、重置密码、设备、会话表。
- `scrypt` 密码哈希；数据库只保存 session/CSRF 哈希。
- Cookie：`HttpOnly`、`SameSite=Lax`，HTTPS 时 `Secure`。
- 注册、验证、登录、退出、忘记/重置密码、设备下线。
- 并发邀请码防超发。
- 用户、设备和管理员角色隔离。
- 启动时 SaaS 校验 `DATABASE_URL`、`SESSION_SECRET` 与已应用 migration。

### 阶段 2：套餐、订阅与额度

核心文件：

- `tools/saas_membership.py`
- `tools/saas_migrations/0002_membership.sql`

已完成：

- `free-v1`、`advanced-v1`、`pro-v1` 与 9 项额度。
- 人工订单、订阅、账期、用量账本、预占、结算、释放、补发/扣减。
- 套餐版本不可变；已产生账期使用 `limits_json` 快照。
- 订阅暂停/恢复/延期/到期回退。
- 设备数按当前有效套餐计算。

### 阶段 3：官方书城与官方书架

核心文件：

- `tools/saas_catalog.py`
- `tools/saas_migrations/0003_catalog.sql`

已完成：

- 官方书城、书系、标签、详情、官方书架、首次解锁。
- 版权/发布约束：只有 `public_domain` 或 `licensed` + `published` 可见。
- 书架容量与解锁额度有事务/并发保护；移除后重新收藏不重复扣解锁。
- 已解锁官方内容可从 PostgreSQL 读取正文。

正式库当前：`catalog_books=0`、`published_catalog_books=0`，没有旧书被自动公开。

### 阶段 4：成长值、签到与会员邀请

核心文件：

- `tools/saas_rewards.py`
- `tools/saas_migrations/0004_rewards.sql`
- `tools/saas_migrations/0005_member_invite_allowances.sql`

已完成：

- 签到、连续签到、有效阅读、复习、完成官方读物成长值。
- 每月正向成长值上限 100。
- 奖励兑换、补签卡、额度信用。
- 邀请里程碑奖励。
- 邀请码额度必须由后台/活动发放；付费用户不拥有无限自助邀请码。

### 阶段 5：运营后台

核心文件：

- `tools/saas_admin.py`
- `tools/saas_migrations/0006_admin_operations.sql`

已完成：

- 管理员用户/设备、封禁/恢复、渠道邀请码、人工订单、套餐版本、额度调整、邀请码额度、书城审核、审计和 JSON 导出。
- 普通用户访问 `/api/admin/*` 返回 `admin_required`。
- 管理操作写入 `admin_audit_logs`。
- Dioco 在 SaaS 模式设计为平台环境变量 `SHIYUE_DIOCO_TOKEN` / `SHIYUE_DIOCO_EMAIL`，后台仅显示是否配置，不返回秘密。

### 阶段 6：媒体、安全、备份与账户生命周期

核心文件：

- `tools/saas_media.py`
- `tools/saas_accounts.py`
- `tools/saas_backup.py`
- `tools/saas_backup_verify.py`
- `tools/saas_restore_drill.py`
- `tools/saas_media_inventory.py`
- `tools/saas_migrations/0007_security_media_accounts.sql`
- `tools/saas_migrations/0008_bootstrap_admin_subscription.sql`
- `tools/saas_migrations/0009_restore_bootstrap_admin_pro.sql`
- `reader/legal/`

已完成：

- `media_assets`、变体、使用统计和受鉴权 Range 流媒体。
- 私有媒体仅所有者可访问；官方媒体要求已发布、版权合规、已解锁。
- 逻辑删除媒体后释放私人空间，物理清理支持 dry run 和移入 `.local/media-trash`。
- 用户数据导出、30 天延迟注销、撤销注销、完成匿名化。
- CSP、安全响应头、内存限流。
- 法律页面：`/terms`、`/privacy`、`/content-policy`、`/refunds`、`/copyright`。
- 备份、清单校验、恢复演练工具和 launchd 示例。

重要备份：

- `.local/saas-backups/20261010T035159Z`：阶段 6 初始备份。
- `.local/saas-backups/20261010T042945Z`：阶段 7 备份。
- `.local/saas-backups/20261010T063936Z`：阶段 8 初始备份。
- `.local/saas-backups/20261010T072211Z`：12 个 migration 备份，已完整校验。

### 阶段 7：私人学习空间

核心文件：

- `tools/saas_workspace.py`
- `tools/saas_migrations/0010_private_workspace.sql`

已完成：

- 所有者隔离的私人读物、正文、媒体、生词、标注、学习日、阅读进度。
- 私人活动同时写工作区学习数据和阶段 4 有效阅读奖励。
- SaaS UI 已有“私人学习空间”。

当前正式库：34 本普通图书在私人工作区可见。

### 阶段 8：原生私人导入

核心文件：

- `tools/saas_imports.py`
- `tools/saas_migrations/0011_workspace_imports.sql`
- `tools/test_saas_phase8_integration.py`

已完成：

- PostgreSQL 私人导入任务协议：用户、工作区、套餐版本、额度预占、源资产、输出读物、幂等键、任务进度、取消/失败释放。
- 实际可用导入类型：TXT、Markdown、PDF、MP3、本地视频、YouTube。
- PDF 使用 `.local/bin/pdf_ocr` 在临时目录 OCR，不写 SQLite。
- MP3 使用本机 `whisper-cli + base.en`，通过 `whisper_book()` 创建带词级时间戳和动态分句的私人音频读物；成功结算 `mp3_imports`。
- 本地视频支持 MP4、MOV、M4V、MKV、WebM；FFmpeg 生成 M4A 音频、JPEG 封面及临时 Whisper WAV，输出 PostgreSQL 私人视频读物并结算 `video_imports`。
- 源视频作为主资产，音频和封面作为同一资产的 `audio`、`cover` 变体，均受 `/api/media/{asset_id}` 所有者鉴权与私人空间计量保护。
- YouTube 使用 yt-dlp 下载最高 720p 视频和可用的原生英文、中文字幕，复用视频处理器，并将字幕作为 `subtitles-en`、`subtitles-zh-CN` 变体。只结算 `youtube_imports`，不额外扣 `video_imports`。
- 前端私人工作区已接受 `.txt`、`.md`、`.pdf`、`.mp3`、上述视频格式和 YouTube 地址。

### 用户要求：旧 SQLite 音视频不自动导入 SaaS

核心 migration：

- `tools/saas_migrations/0012_exclude_legacy_av_workspace.sql`

已执行结果：

```text
audio|blocked|2
youtube|blocked|3
book|private|34
```

含义：旧 SQLite 的 2 本音频和 3 个 YouTube 内容仍保留在 SQLite、PostgreSQL 落地区、媒体资产和原始文件中，但不显示在 SaaS 私人空间，也不自动进入官方书城。未来由管理员逐项人工审核发布。新上传 MP3 和本地视频不受影响。

## 4. 数据库 migration 状态

正式库 `shiyue_saas_local` 已应用：

```text
0001_accounts.sql
0002_membership.sql
0003_catalog.sql
0004_rewards.sql
0005_member_invite_allowances.sql
0006_admin_operations.sql
0007_security_media_accounts.sql
0008_bootstrap_admin_subscription.sql
0009_restore_bootstrap_admin_pro.sql
0010_private_workspace.sql
0011_workspace_imports.sql
0012_exclude_legacy_av_workspace.sql
0013_workspace_ai.sql
```

## 5. 测试现状

通过的测试：

- `tools/test_saas_phase1_integration.py`：7 项
- `tools/test_saas_phase2_integration.py`：7 项
- `tools/test_saas_phase3_integration.py`：5 项
- `tools/test_saas_phase4_integration.py`：6 项
- `tools/test_saas_phase5_integration.py`：5 项
- `tools/test_saas_phase6_integration.py`：5 项
- `tools/test_saas_phase7_integration.py`：2 项
- `tools/test_saas_phase8_integration.py`：视频阶段 7 项已通过；当前已扩展为 9 项，新增 YouTube 成功/失败路径，受 Codex 沙箱 PostgreSQL IPC 限制尚待普通终端复跑
- `tools/test_saas_phase1.py`：3 项
- `tools/test_membership_presentation.py`：8 项
- `tools/test_reader_performance.py`：2 项
- `tools/test_mobile_reader_presentation.py`：7 项

运行 PostgreSQL 集成测试的方式：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase8_integration.py
```

旧单用户回归仍通过：`./start-reader.sh` 可读取 39 本 SQLite 书架内容。

## 6. 未完成工作：按优先级

### P0：复跑 YouTube PostgreSQL 集成验收

视频阶段 7 项数据库测试已由前一轮完整通过。YouTube 处理器现已实现，并通过可控 yt-dlp + 真实 FFmpeg + 可控 Whisper 的无数据库端到端探测、Python/JavaScript 语法和展示测试。当前 Codex 沙箱既不能连接已有 PostgreSQL TCP/Unix socket，也不能创建 PostgreSQL 所需 System V shared memory，因此新增的两个 YouTube 数据库用例尚未运行。下一次在普通本机终端先执行阶段 8 的 9 项集成测试；若通过，再生成新的备份。

### P1：复跑阶段 7–9 PostgreSQL 验收并生成新备份

当前 Codex 沙箱禁止连接既有 PostgreSQL TCP/Unix socket，也禁止创建 PostgreSQL 所需共享内存。视频阶段 7 项数据库测试已由前一轮通过；此后新增了阶段 7 学习指标、阶段 8 YouTube 两项和阶段 9 AI 两项。应在普通本机终端依次复跑阶段 7、8、9，再生成包含 13 个 migration 的备份。

### P2：上线准备与容量验证

可先运行：

```bash
.local/saas-venv/bin/python tools/saas_readiness.py --env-file .env
```

当前只读审计阻塞项：SMTP 未配置、`SHIYUE_DIOCO_TOKEN/EMAIL` 未配置、`SAAS_BACKUP_ROOT` 未指向项目外部目录、当前 Codex 沙箱无法连接 PostgreSQL。工具链和本机备份正常，SaaS 开关仍为关闭。

- 配置真实 SMTP 并实际验证邮件流程。
- 配置 `SHIYUE_DIOCO_TOKEN`、`SHIYUE_DIOCO_EMAIL`。
- 将备份目录转移至外部/异机位置，并安装 launchd 定时任务（仅示例存在，尚未安装）。
- 100～500 用户并发登录、浏览、阅读、Range 媒体、任务排队压力测试。
- 再决定是否设为 `SHIYUE_SAAS_ENABLED=1`。

## 7. 工作区与安全注意事项

- 当前 Git 工作区是未提交的大型改造；不要假设有干净工作树，也不要 `git reset --hard` 或覆盖现有修改。
- 使用 `apply_patch` 编辑文件。
- `.env` 被忽略且权限为 `0600`；不要输出或提交里面的密钥。
- 不要输出 `.dioco.local.json` 中的秘密。
- 不要部署远程服务器。
- 对旧音频/YouTube 的 `blocked` 可见性不要恢复为 `private`，除非用户明确要求。
- 视频处理器只能处理新用户上传的私有源资产；不可扫描或导入旧 SQLite 视频/音频/YouTube 内容。

## 8. 推荐继续命令

检查 PostgreSQL：

```bash
pg_bin="$(brew --prefix postgresql@16)/bin"
"$pg_bin/pg_isready" -h 127.0.0.1 -p 55432 -d shiyue_saas_local
```

运行所有 SaaS 集成测试：

```bash
test_url=postgresql://127.0.0.1:55432/shiyue_phase1_test
for phase in 1 2 3 4 5 6 7 8 9; do
  SHIYUE_SAAS_TEST_DATABASE_URL="$test_url" \
    .local/saas-venv/bin/python "tools/test_saas_phase${phase}_integration.py"
done
```

运行旧模式：

```bash
./start-reader.sh
```

生成并验证备份：

```bash
DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_saas_local \
MEDIA_ROOT="$PWD/books" \
  .local/saas-venv/bin/python tools/saas_backup.py \
  --database-url "$DATABASE_URL" --media-root "$MEDIA_ROOT" \
  --output-root .local/saas-backups
```
