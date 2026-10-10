# 拾页 · 本地英语点读

## 启动

在项目根目录运行：

```bash
./start-reader.sh
```

浏览器打开 `http://localhost:8765`。不要直接双击 `index.html`，浏览器会阻止读取本地 JSON。

## SaaS 开发开关（阶段性）

默认仍是现有单用户 SQLite 阅读器。`SHIYUE_SAAS_ENABLED=0` 时不需要 PostgreSQL，也不会改变书架、导入或本机部署流程。

要准备 SaaS 开发环境，先复制根目录 [`.env.example`](../.env.example) 为未提交的 `.env`，填写 `DATABASE_URL`、`SESSION_SECRET`、SMTP 与首次管理员变量；然后安装驱动并执行迁移：

```bash
python3 -m venv .local/saas-venv
.local/saas-venv/bin/python -m pip install -r requirements-saas.txt
.local/saas-venv/bin/python tools/saas_migrate.py --migrate --bootstrap-admin --import-legacy
```

迁移会把现有 SQLite 读物、生词、备注、学习记录和句法数据作为管理员的 `private` 内容复制至 PostgreSQL；不会删除或修改 `.local/library.sqlite3`。首次管理员创建后，应从 `.env` 删除 `BOOTSTRAP_ADMIN_PASSWORD`。只有迁移完成后才将 `SHIYUE_SAAS_ENABLED=1` 设为启用状态。

若需要在本机重设初始管理员密码，不要把密码作为命令参数传入。临时在当前 shell 中以静默方式设置 `BOOTSTRAP_ADMIN_PASSWORD`，再执行：

```bash
read -rs 'BOOTSTRAP_ADMIN_PASSWORD?新的管理员密码： '
export BOOTSTRAP_ADMIN_PASSWORD
.local/saas-venv/bin/python tools/saas_migrate.py --reset-admin-password
unset BOOTSTRAP_ADMIN_PASSWORD
```

该操作会撤销该管理员的现有会话。

当前是认证和迁移基础阶段：启用 SaaS 时，未完成多租户改造的旧内容接口会返回 `saas_content_migration_pending`，以防管理员旧数据泄露给邀请用户。请不要在此阶段把该开关用于正式读者服务。

本机阶段 1 测试使用独立 PostgreSQL 16 集群：数据位于 `.local/postgres-phase1/data`，仅监听 `127.0.0.1:55432`，正式本机迁移库为 `shiyue_saas_local`，可销毁的验收库为 `shiyue_phase1_test`。不要启用 Homebrew 默认的 `/usr/local/var/postgresql@16` 集群。测试集群的启停命令如下：

```bash
pg_bin="$(brew --prefix postgresql@16)/bin"
"$pg_bin/pg_ctl" -D .local/postgres-phase1/data -l .local/postgres-phase1/postgres.log \
  -o "-h 127.0.0.1 -p 55432 -k $PWD/.local/postgres-phase1/socket" start
"$pg_bin/pg_ctl" -D .local/postgres-phase1/data stop
```

执行真实阶段 1 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase1_integration.py
```

## 阶段 2：套餐、额度和会员中心

`0002_membership.sql` 提供不可变套餐版本 `free-v1`、`advanced-v1`、`pro-v1`，并保存对应的 9 项权益、参考价格和账期快照。套餐调整必须创建新版本，绝不能修改已产生账期的 `limits_json`。

权益服务使用事务、用户行锁和幂等键实现“预占—成功结算—失败释放”。`quota_reservations` 记录任务预占，`usage_ledger` 只记录已结算消耗或补发额度；相同用户、功能和幂等键不会重复扣减。人工开通创建 `manual_orders` 与 `subscriptions`，支持暂停、恢复和延期，过期订阅会自动回退免费版。

启用 SaaS 后可使用：

- `GET /api/membership`、`GET /api/membership/usage`、`GET /api/membership/orders`
- `POST /api/admin/manual-orders`
- `POST /api/admin/subscriptions`，`action` 为 `create`、`suspend`、`activate` 或 `extend`

会员中心已提供登录、邀请注册、找回密码、额度与订单展示；管理员人工开通接口需要管理员会话和 CSRF 令牌。完整用户/订单运营后台将在阶段 5 完成。阶段 3 的多租户内容工作区完成前，AI、导入和书城动作仍不会通过旧 SQLite 路由执行或扣除正式额度。

执行真实阶段 2 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase2_integration.py
```

## 阶段 3：书城、官方书架和受解锁保护的正文

`0003_catalog.sql` 将官方书城与迁移的私人内容分离。`content_books` 中的旧内容不会自动进入书城；管理员必须通过 `POST /api/admin/catalog/books` 将某一本源内容标记为 `public_domain` 或 `licensed`，并设为 `published`。`private` 和 `prohibited` 内容不能发布。

公共书城接口为 `GET /api/catalog`、`GET /api/catalog/series`、`GET /api/catalog/tags` 和 `GET /api/catalog/books/{id}`。登录后可通过 `POST /api/library/items` 收藏、`POST /api/catalog/books/{id}/unlock` 首次解锁，以及 `DELETE /api/library/items/{id}` 移除。收藏容量依据当前套餐计算；解锁只在首次发生时消耗账期额度，移除后重新收藏或再次打开不会重复扣除。

`GET /api/catalog/books/{id}/reader` 只向已验证且已解锁的用户返回 PostgreSQL 中的正文文本，因此“开始阅读”可以进入受保护的文本阅读视图。音频、视频、原书页和封面仍不会经由旧 `/books/` 路径公开；它们将在阶段 6 的媒体资产和 Range 鉴权中接入。

管理员可先检查待审核源内容：

```bash
curl -b "shiyue_session=..." http://127.0.0.1:8765/api/admin/catalog/sources
```

本机现有 39 本迁移内容均保持管理员私人资源，当前没有任何官方书城发布条目。

执行真实阶段 3 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase3_integration.py
```

## 阶段 4：签到、成长值和会员邀请

`0004_rewards.sql` 和 `0005_member_invite_allowances.sql` 提供签到、成长值账本、兑换目录、补签卡、有效学习记录、邀请里程碑和邀请码额度。成长值的正向发放有每月 100 点上限；兑换扣减成长值后，对 AI、句法、官方解锁或 MP3 导入的奖励会作为当前账期的权益信用写入 `usage_ledger`。

规则已实现：每日签到 +1；当日累计阅读 10 分钟并点读至少 5 句 +2；连续第 3/7/14/30 天额外 +2/+5/+10/+20；完成生词复习每天 +2；完成一本已解锁官方读物 +10。相同事件均由幂等键或唯一约束保护，重复上报不会重复奖励。

奖励目录默认包含：20 点换 10 次 AI 语境、30 点换 5 次句法、80 点换一次官方解锁、150 点换一次 MP3 导入、20 点换一张补签卡。

会员邀请码遵循“后台或活动发放”原则：免费用户没有资格；进阶/Pro 用户也必须先获得 `member_invite_allowances`，每生成一个邀请码原子消耗一份额度。邀请用户完成首次有效学习奖励邀请人 +10，首次有效付费奖励 +30；相同设备或相同注册 IP 的邀请关系会被标记为不发奖。支付账号反作弊将在接入支付后补齐。

接口：

```text
GET  /api/rewards/status
POST /api/checkins
GET  /api/rewards/catalog
POST /api/rewards/redeem
GET  /api/rewards/ledger
POST /api/rewards/activity
POST /api/rewards/complete-book
POST /api/member-invites
```

执行真实阶段 4 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase4_integration.py
```

## 阶段 5：运营后台

管理员登录 SaaS 后会看到“运营后台”。后台仅展示运营必要数据，不返回密码哈希、会话令牌、SSH 凭据或 Dioco 令牌值。已提供：用户与设备、封禁/恢复、渠道邀请码、人工订单、订阅暂停/恢复/延期、额度补发或扣减、邀请码额度发放、书城源内容审核、套餐版本列表/新版本创建、管理审计与经营 JSON 导出。

关键管理接口：

```text
GET  /api/admin/dashboard
GET  /api/admin/users
GET  /api/admin/users/{id}
POST /api/admin/users/{id}/status
GET  /api/admin/invitations
POST /api/admin/invitations
POST /api/admin/quotas/adjust
POST /api/admin/member-invite-allowances
GET  /api/admin/plan-versions
POST /api/admin/plan-versions
GET  /api/admin/catalog/sources
POST /api/admin/catalog/books
GET  /api/admin/audit
GET  /api/admin/exports/summary
GET  /api/admin/platform-config
```

封禁、额度扣改、邀请码额度发放等具有影响用户权益的操作要求填写理由，并写入 `admin_audit_logs`。首次人工开通付费套餐会继续触发受邀用户的首次付费奖励逻辑。

Dioco 配置在 SaaS 模式下为平台级环境变量：`SHIYUE_DIOCO_TOKEN` 与 `SHIYUE_DIOCO_EMAIL`。后台仅显示是否已配置，绝不返回令牌内容；普通用户看不到也不能修改它。现有本机 `.dioco.local.json` 仍只服务于遗留单用户模式。

执行真实阶段 5 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase5_integration.py
```

## 阶段 6：媒体鉴权、安全和恢复

`0007_security_media_accounts.sql` 建立 `media_assets`、`asset_variants`、`asset_usage`、`account_deletion_requests` 与 `security_events`；`0008/0009` 保留原本机管理员的迁移后 Pro 权益，以容纳既有私人媒体。媒体始终使用 `MEDIA_ROOT` 下的相对路径，登记时计算 SHA-256，拒绝绝对路径和路径穿越。

SaaS 模式中，媒体只能通过以下接口访问：

```text
GET    /api/media/{asset_id}
GET    /api/media/{asset_id}?variant=low
DELETE /api/media/{asset_id}
```

私有媒体仅所有者可访问；官方媒体仅在读物已发布、版权合规且当前用户已解锁时可访问。音视频支持单 Range 请求；旧 `/books/...` 路径不会在 SaaS 模式公开。私有资产登记前会检查套餐空间，登记后计入 `storage_bytes`；逻辑删除释放空间，物理文件由清理工具先移到 `.local/media-trash`，支持 dry run。

将既有媒体登记为管理员私人资产（可重复运行，已登记路径会跳过）：

```bash
DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_saas_local \
MEDIA_ROOT="$PWD/books" \
  .local/saas-venv/bin/python tools/saas_media_inventory.py \
  --owner-email "管理员邮箱" --media-root "$PWD/books"
```

账号数据接口为 `GET /api/account/export`、`POST /api/account/deletion`、`POST /api/account/deletion/cancel`。注销请求会退出现有会话并保留 30 天撤销期，完成后账号匿名化、私人资产逻辑删除。

备份默认生成 PostgreSQL custom dump 与媒体 SHA-256 清单：

```bash
.local/saas-venv/bin/python tools/saas_backup.py \
  --database-url postgresql://127.0.0.1:55432/shiyue_saas_local \
  --media-root "$PWD/books" --output-root .local/saas-backups
.local/saas-venv/bin/python tools/saas_backup_verify.py \
  .local/saas-backups/<timestamp> --media-root "$PWD/books"
```

`tools/saas_restore_drill.py` 仅允许恢复到名称以 `_test` 结尾的数据库。可参考 `deployment/launchd/com.shiyue.saas-backup.plist.example` 设置本机定时备份；示例不自动安装或加载。

阶段 6 还为 SaaS 响应添加 `nosniff`、反嵌入、Referrer、跨源隔离与 CSP 安全头，对登录、注册、找回密码、签到和 AI 接口启用内存限流。法律页面位于 `/terms`、`/privacy`、`/content-policy`、`/refunds`、`/copyright`。

执行真实阶段 6 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase6_integration.py
```

## 阶段 7：私人学习空间

`0010_private_workspace.sql` 将已迁移的 `content_books`、生词、标注、学习日数据和阅读进度通过所有者权限重新接入 SaaS。私人读物不会出现在官方书城；只有 `owner_id` 相同的用户能列出、阅读、更新生词/标注或记录学习活动。

```text
GET  /api/workspace/books
GET  /api/workspace/books/{id}/reader
GET  /api/workspace/vocabulary?bookId={id}
POST /api/workspace/vocabulary
GET  /api/workspace/annotations?bookId={id}
POST /api/workspace/annotations
GET  /api/workspace/learning-days
POST /api/workspace/activity
```

工作区正文绝不会返回旧 `/books/...` URL；关联媒体继续走 `/api/media/{asset_id}`。阅读活动会同时写入该用户的 PostgreSQL 学习日记录和成长奖励的有效阅读判定。

本机管理员的 39 本迁移私人读物已经可在 SaaS“私人学习空间”读取；其他用户会看到空空间，直至其内容由下一轮 PostgreSQL 原生导入任务创建。旧 SQLite 导入 Worker 仍不会在 SaaS 模式直接对邀请用户开放。

执行真实阶段 7 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase7_integration.py
```

## 阶段 8：PostgreSQL 原生私人导入任务

`0011_workspace_imports.sql` 增加 `workspace_import_tasks`。任务会记录创建用户、工作区、导入类型、套餐版本快照、额度预占、源资产、输出读物、进度、错误和幂等键。它不再调用旧 SQLite Worker。

当前已经完成的实际导入路径是 **TXT / Markdown / PDF / MP3 / 本地视频 / YouTube**：上传文件或提交 YouTube 地址后会登记为受鉴权私人源资产、提取并分句、创建 PostgreSQL 私人读物，并显示在“私人学习空间”。PDF 使用项目本机 `.local/bin/pdf_ocr` 在隔离临时目录进行 OCR；MP3 使用项目本机 `whisper-cli + base.en` 生成带词级时间戳的正文；视频使用 FFmpeg 提取 M4A 音频与 JPEG 封面，并用隔离的 16kHz WAV 执行 Whisper；YouTube 使用 yt-dlp 下载最高 720p 视频及可用的原生英文、中文字幕，再复用相同视频处理器。所有结果都写入 PostgreSQL 与受鉴权媒体资产，不写入 SQLite。支持的 API：

```text
GET  /api/workspace/imports
POST /api/workspace/imports
POST /api/workspace/imports/{id}/upload
POST /api/workspace/imports/{id}/complete
POST /api/workspace/imports/{id}/cancel
```

MP3、视频和 YouTube 创建任务时分别预占 `mp3_imports`、`video_imports`、`youtube_imports`；成功完成后结算，失败或取消自动释放额度与私人源资产空间。当前 MP3 原生处理器接受 `.mp3`，视频原生处理器接受 `.mp4`、`.mov`、`.m4v`、`.mkv`、`.webm`。源视频、派生音频、封面和可用字幕使用同一个资产 ID，可分别通过 `/api/media/{id}`、`?variant=audio`、`?variant=cover`、`?variant=subtitles-en`、`?variant=subtitles-zh-CN` 鉴权访问。YouTube 只结算 `youtube_imports`，不会额外消耗 `video_imports`，也不会回退到遗留 SQLite 导入器。

私人视频阅读页会直接使用受鉴权的源视频播放器，并提供派生音频与封面入口；这些变体的字节数计入同一私人资产的 `generated_bytes` 和空间账本。

历史 SQLite 中已有的音频、视频和 YouTube 读物不会自动进入 SaaS 私人学习空间或官方书城；它们保留在本机旧库、PostgreSQL 落地区和媒体资产清单中，供管理员以后逐项人工审核并导入官方书城。新上传的 MP3 和本地视频不受这个规则影响。

上传或下载会先按私人空间额度预检，媒体登记和派生变体登记时再以用户锁进行最终校验。TXT、Markdown、PDF、MP3、本地视频和 YouTube 导入都可通过 SaaS“私人学习空间”界面完成。

SaaS 模式的“学习记录”和“生词复习”使用 PostgreSQL 工作区接口，不再访问旧 SQLite 学习表。私人阅读页可点击单词，手工保存私人释义和备注；复习评分、查词、阅读时长、句子数和学习会话写入当前账号的工作区学习日。浏览器英文朗读用于替代旧 `/api/word-tts`。平台词典的完整释义接口仍待后续单独租户化。

AI 语境精讲和句法分析现已通过 `0013_workspace_ai.sql` 租户化。首次生成分别使用 `ai_context_generations`、`ai_grammar_generations` 的预占—结算—失败释放协议；同一用户、读物和内容哈希命中 PostgreSQL 缓存后不重复扣额。平台凭据仅来自 `SHIYUE_DIOCO_TOKEN`、`SHIYUE_DIOCO_EMAIL`。私人阅读页的单词面板与逐句句法按钮会调用对应 SaaS API；平台词典的完整释义仍留待后续单独接入。

执行阶段 9 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase9_integration.py
```

上线前可运行不泄露秘密值的只读检查：

```bash
.local/saas-venv/bin/python tools/saas_readiness.py --env-file .env
```

该工具检查 PostgreSQL 与最新 migration、SMTP、平台 AI、外部备份目录以及 FFmpeg、Node.js、yt-dlp、Whisper、PDF OCR，不会打印数据库地址、密码或令牌内容。

执行真实阶段 8 验收：

```bash
SHIYUE_SAAS_TEST_DATABASE_URL=postgresql://127.0.0.1:55432/shiyue_phase1_test \
  .local/saas-venv/bin/python tools/test_saas_phase8_integration.py
```

## 数据存储

动态导入的数据不写入前端源码：

- `.local/library.sqlite3`：书籍清单、正文、句子与单词时间轴、OCR数据、Whisper转写、对齐数据、词典、系统设置和导入任务状态。
- `.dioco.local.json`：Dioco邮箱与令牌等本机配置，权限为 `600`。
- `books/`：用户原始PDF/MP3以及导入后必须由浏览器读取的二进制媒体。生成页面放在每本书的 `.reader/pages/`；单MP3书籍使用符号链接，多MP3书籍才生成合并音频。
- `.cache/dioco/`：可重新生成的词典、TTS和语境接口缓存。

导入完成后，OCR、Whisper和图书JSON等结构化中间文件会写入SQLite并从书籍目录删除。前端书架和阅读数据通过本地数据库API动态读取。

## 已实现

- 本地书架和阅读进度保存
- 原版 MP3 自动朗读、进度拖动、0.75–1.5 倍速
- 句子级高亮、点击句子跳转、上一句/下一句
- 鼠标悬浮单词时自动暂停，移开继续
- 精读、泛听、跟读三种学习模式
- 跟读停顿、麦克风录音、录音回放；受支持的浏览器可显示语音文本匹配度
- 40 个互动故事段落和 `Go to …` 剧情跳转
- 点击单词查看中文释义、上下文用法并单独发音
- 点击正文单词会直接调用 Dioco TTS 接口播放独立单词发音，不再截取原书 MP3，因此不会串读相邻单词
- “认识 / 模糊 / 不认识”评级和间隔复习
- 本地学习记录：进度、听读时间、剧情选择、模式使用次数
- 原书扫描页和重排点读版双视图
- 阅读区自动使用约 88%–94% 的可用宽度；专注模式、隐藏原书页和隐藏词典时会重新分配栏宽
- 播放跨页时自动切换左侧原书扫描页，泛听模式也会持续高亮并滚动到当前句
- 阅读快捷键支持在“系统设置”中修改；默认 `A` 上一句、`S` 复读当前句、`D` 下一句、空格播放/暂停
- 单词高亮使用 `requestAnimationFrame` 按屏幕刷新帧同步；`timeupdate` 只负责低频保存进度
- Whisper 导入默认启用 `base.en + DTW`，对齐后自动消除相邻词重叠并切开吸收停顿的异常长时间片
- Whisper/DTW之后使用英文 wav2vec2 CTC强制对齐获得字符和单词声学边界；无法可靠对齐的句子自动保留DTW时间戳
- 任一单词开始后，高亮持续停留到下一个单词开始，不会在词间停顿时消失；句末停顿和自动暂停期间也保持最后一个词高亮
- 书架支持平铺和紧凑列表视图，并保存上次视图选择
- 左下角书系选择器可在多个已导入书系之间切换
- 点击单词显示可配置停留时间的浮动工具栏，可加入生词本、订正OCR和保存个人备注
- 生词、OCR订正、备注与复习历史写入SQLite；复习卡先主动回忆再显示答案
- 学习记录按天统计阅读时长、句子、查词、复习和跟读，使用GitHub式年度热力图展示
- 书架默认按最近阅读排序，从未读的新导入书籍排在已阅读书籍之后
- 系统设置支持护眼模式和单词工具栏停留时间
- 离开阅读页面会自动退出专注模式并恢复左侧菜单
- OCR订正和单词备注使用贴近工具栏的内联编辑卡，不打开独立窗口
- 生词复习支持昨日、当日、明日、全部筛选，以及听写模式
- 生词卡点击单词即可显示答案；答案尽量接在原句句末，空间不足时自动换行
- 生词分页数量可在系统设置中调整，默认10条；复习页支持 `A` 上一页、`D` 下一页、`E` 尾页、`F` 首页
- 生词列表增加独立发音按钮；普通复习点击单词只在当前词条内显示答案
- 听写由“开始”按钮启动，每个单词按系统设置重复朗读，完成后按设置秒数停顿；支持暂停/继续、重新开始、上一个、下一个、点击重听，并在结束后统一揭示全部答案
- 听写中点击已经播报的遮挡词，会在右侧栏显示单词、音标、完整释义、当前句用法、例句和备注

本地释义来自项目内的 ECDICT 英汉离线词典；当前《生存游戏》正文中的 237 种英文词形已全部建立词典索引。导入新书时，导入器会重新生成合并后的本地词典。
变形词会继承原形音标；词典中的多条释义会按真正的换行显示，不再显示字面量 `\\n`。

## Dioco 单词接口

阅读器现在通过本地后端分别代理三个接口：

- `/api/word-dictionary`：查询中文释义和例句。
- `/api/word-tts`：获取单词 MP3 发音；点击正文单词和右侧喇叭都使用该发音。
- `/api/word-context`：结合当前句和前后句生成中文语境解释。

在左侧“系统设置”填写账号邮箱、令牌和阅读快捷键。浏览器只提交给本机后端；后端仅在调用 Dioco 上下文接口时转发。完整令牌保存于项目根目录 `.dioco.local.json`，文件权限为 `600`，并已加入 `.gitignore`；浏览器读取设置时只能看到掩码。词典、TTS和语境结果会缓存在本机 `.cache/dioco`。接口失败时自动回退到ECDICT和本地语境规则。

《生存游戏》当前已经使用 Whisper 词级时间戳，不再使用最初的正文长度估算时间轴。导入器仍保留静音辅助估算作为未运行 Whisper 时的后备方案。

本项目已经在 `tools/vendor/whisper.cpp` 安装本地 `whisper.cpp`，并下载 `base.en` 英语模型。Whisper 只在本机运行，不上传书籍或录音。

Whisper 增强包括：

- 原书单词随 MP3 逐词变色
- 点击词典面板中的“听原书中的发音”播放该词的真实书籍录音
- Whisper 转写与原书正文强制对齐，正文仍以原书 OCR 校对文本为准
- 跟读录音发送到本机 `/api/transcribe`，由本地 Whisper 识别后计算文本匹配度

## 导入更多书籍

推荐直接使用左侧“导入书籍”：

1. 选择系列。
2. 勾选一本或多本书，也可“全选未导入”。
3. 点击“按顺序导入”。
4. 后台严格串行处理：一本完成或失败后才开始下一本，不会并发运行OCR/Whisper。
5. 页面逐本显示排队、当前进度、成功和失败原因。
6. 全部结束后自动刷新书架。

导入器默认扫描项目根目录的 `books/`。当前扫描到7个系列、151个书籍目录，其中138本同时具有PDF和MP3。

## 导入 MP4 视频

在“导入内容”页面切换到“视频文件”，可以上传 MP4、MOV 或 M4V，并可选上传 SRT/VTT 字幕。

选择视频后，会用文件名自动填写英文标题；中文标题在未手动修改前会自动跟随英文标题。用户可以随后单独修改中文标题。

视频进度条展示总体进度，而不是只有上传进度：视频和字幕上传约占前20%，音频提取、关键帧、Whisper、字幕对齐、词典和SQLite写入占后80%。只有后台任务真正完成后才显示100%。

字幕策略按以下优先级执行：

1. 外部 SRT/VTT 字幕；
2. MP4 内嵌英文字幕；
3. 无字幕时使用 `base.en + DTW` 自动生成正文。

后台会自动提取 MP3、每15秒一张关键帧、Whisper词级时间戳和本地词典索引，并写入 SQLite。视频书籍会在阅读页左侧提供“关键帧 / 视频”切换；正文点读、生词、备注、跟读、听写、快捷键和学习记录继续复用现有逻辑。

局域网上传使用流式写入，视频不会整体读入内存。原始视频保存在：

```text
books/<所属系列>/video.<标题>-<ID>/source.mp4
```

生成资源保存在该目录的 `.reader/`，正文、时间轴和Whisper数据进入 `.local/library.sqlite3`。

## 通过 YouTube 地址导入

“导入内容”页面提供“YouTube 地址”入口。粘贴单个视频地址后先点击“解析地址”，系统会读取标题、频道、时长、缩略图，以及人工英文字幕和自动英文字幕状态。

确认标题和标签后点击“下载并导入”。后台使用项目本地 `.local/bin/yt-dlp`，默认只下载当前视频、最高720p，优先下载英文人工字幕，并以自动英文字幕作为后备。下载完成后自动进入现有视频流程：提取音频和关键帧、Whisper `base.en + DTW`、字幕对齐、词典和SQLite。

YouTube总体进度包括地址解析、视频和字幕下载、音频、关键帧、Whisper、对齐与数据库写入。任务按现有导入锁严格串行。普通公开视频无需登录；登录、年龄或区域受限视频目前会提示需要Cookie，不会绕过访问控制。默认不导入播放列表。

扫描整个书库：

```bash
python3 tools/import_books.py --scan
```

扫描版 PDF 先运行本地 OCR：

```bash
swiftc tools/pdf_ocr.swift -o /tmp/pdf_ocr -framework PDFKit -framework Vision -framework AppKit
/tmp/pdf_ocr "书.pdf" "ocr.json" "页面图片目录" 1.6
```

再导入：

```bash
python3 tools/import_books.py \
  --book-dir "书籍文件夹" --ocr "ocr.json" \
  --slug book-slug --title "中文书名" \
  --page-start 7 --page-end 31 --audio-start 39.8 \
  --section-fixes "section-fixes.json"
```

为新书生成 Whisper 词时间戳：

```bash
tools/transcribe_book.sh \
  "reader/assets/book-slug/audio.mp3" \
  "reader/data/book-slug/book.json" \
  "reader/data/book-slug/whisper/full"
```

如果已经有 Whisper 完整 JSON，也可以在导入时增加：

```bash
--whisper-json "whisper/full.json"
```

不同版本的前言、练习页位置不一：

- `page-start/page-end` 指定正文页。
- `audio-start` 是正文朗读开始的秒数。
- `section-fixes` 是可选的段落修正规则，用于跨页时 OCR 没识别出故事编号的情况。

段落修正规则示例：

```json
[
  {
    "startsWith": "正文开头的一段文字",
    "untilStartsWith": "下一段开头",
    "section": 6
  }
]
```

导入器会把估算边界吸附到 MP3 的真实静音位置，并在书籍数据旁生成 `quality-report.json`。导入后打开应用中的“导入质检”进行复核。
