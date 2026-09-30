# 拾页（Shiyue）英语点读系统项目上下文

> 给后续开发会话使用的接手文档。最后更新：2026-09-29。
> 不要把Dioco令牌写入代码、Git或本文档；完整令牌只在项目根目录`.dioco.local.json`中保存。

## 1. 项目定位

这是一个本地优先的英语阅读、点读、视频学习、手动听写和间隔复习系统。原始内容是Oxford Bookworms分级读物，也支持本地MP4和YouTube视频。

核心业务：

- 从本地书库按系列和书籍进入阅读。
- PDF/字幕/Whisper生成英文正文。
- 音频、视频、正文保持句子级和单词级同步。
- 鼠标悬浮单词暂停，离开后继续；点击单词调用Dioco词典、TTS和上下文解释。
- 生词本、OCR订正、个人备注和间隔复习。
- 普通复习与手动听写。
- 学习热力图、阅读进度、最近阅读排序。
- 所有结构化数据使用SQLite；原始媒体留在`books/`。

## 2. 当前运行方式

```bash
./start-reader.sh
```

本机：

```text
http://localhost:8765
```

局域网：启动脚本会打印当前Mac地址，例如：

```text
http://192.168.1.45:8765
```

服务默认监听：

```text
0.0.0.0:8765
```

只允许本机访问：

```bash
READER_HOST=127.0.0.1 ./start-reader.sh
```

换端口：

```bash
READER_PORT=9000 ./start-reader.sh
```

## 3. 当前数据状态

截至2026-09-29，SQLite中有：

- `book`：9本
- `video`：2本
- `youtube`：2本
- 总书籍数：13本
- 词典词形：约2546个
- 生词、备注、OCR订正和学习统计均已建表。

已导入内容包括：

- 0级《生存游戏》
- 0级《明星记者》
- 0级《摩托女孩》
- 0级《时空异客》
- 1级部分书籍
- TED/TEDx视频
- YouTube视频

当前主要内容均已使用：

```text
wav2vec2-ctc-forced-alignment
```

CTC无法可靠对齐的句子自动保留DTW时间戳。

## 4. 运行环境与安装

开发机：

- macOS Intel x86_64
- 内存约16GB
- Python 3.14：本地服务和普通脚本
- Python 3.11.16：CTC强制对齐环境
- Node.js：yt-dlp的JavaScript运行时
- FFmpeg/FFprobe：音视频处理
- CMake + Apple Clang：编译whisper.cpp
- SQLite：macOS自带
- 7-Zip：提取CHM电子书正文

关键版本：

```text
yt-dlp       2026.08.19
whisper.cpp  1.9.4-dev
torch        2.2.2
torchaudio   2.2.2
Python       3.11.16
```

正文与Whisper时间轴匹配固定使用CTC环境中的Python 3.11，而不是主服务的Python 3.14。对齐子进程发生非业务异常时会自动重试一次，并将完整返回码、stdout和stderr写入：

```text
.local/align-<job-id>.log
```

已经完成OCR和Whisper、但在88%对齐阶段失败的任务，可以复用中间文件恢复：

```bash
python3 tools/import_worker.py <job-id> '<books相对路径>' --resume-alignment
```

恢复模式不会重新执行OCR或Whisper。

安装本地Whisper：

```bash
./tools/install_whisper.sh
```

模型：

```text
tools/vendor/whisper.cpp/models/ggml-base.en.bin
```

安装CTC对齐环境：

```bash
./tools/install_forced_aligner.sh
```

环境位置：

```text
.local/forced-aligner/venv
```

声学模型：

```text
.local/forced-aligner/models/hub/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth
```

安装yt-dlp：

```bash
./tools/install_yt_dlp.sh
```

安装CHM支持：

```bash
./tools/install_chm_support.sh
```

脚本支持检测`7zz`、`7z`或`extract_chmLib`。macOS默认通过Homebrew安装`sevenzip`。

二进制：

```text
.local/bin/yt-dlp
```

安装记录：

- `tools/whisper-installation.json`
- `tools/forced-aligner-installation.json`
- `tools/yt-dlp-installation.json`

## 5. 目录结构

```text
books/                         原始PDF、MP3、MP4、YouTube视频和生成媒体
reader/index.html              前端页面
reader/app.js                  前端交互和播放逻辑
reader/styles.css              前端样式
reader/README.md               使用说明
.local/library.sqlite3         主数据库
.local/bin/yt-dlp              本地yt-dlp
.local/forced-aligner/         Python 3.11、PyTorch和wav2vec2模型
.local/*.log                   导入、Whisper、CTC日志
.cache/dioco/                  Dioco词典、TTS、上下文缓存
.dioco.local.json              本地邮箱和Dioco令牌，不提交Git
tools/vendor/whisper.cpp        whisper.cpp源码和编译文件
start-reader.sh                启动脚本
```

`.gitignore`已忽略：

```text
.dioco.local.json
.cache/
.local/
books/.reader/
tools/__pycache__/
```

## 6. 技术架构

### 前端

- 原生HTML/CSS/JavaScript，无React/Vue构建步骤。
- `Audio`播放主音频。
- `requestAnimationFrame`逐帧同步单词高亮。
- 鼠标悬浮单词自动暂停，离开恢复。
- `MediaRecorder`用于跟读录音。
- 书架、导入、系统设置、生词复习和学习统计都是同一单页应用中的screen。

### 后端

- Python `ThreadingHTTPServer`。
- 同时提供静态文件服务和本地JSON API。
- 监听`0.0.0.0:8765`，便于局域网访问。
- SQLite保存所有结构化数据。
- 导入任务使用串行锁，避免多个Whisper/OCR/CTC任务同时占用CPU和内存。

### 目录书籍对齐链

```text
PDF + MP3
  ↓
macOS Vision OCR
  ↓
正文页识别和句子生成
  ↓
Whisper base.en + DTW
  ↓
OCR正文与转写文本匹配
  ↓
wav2vec2 CTC强制对齐
  ↓
字符合并成单词边界
  ↓
SQLite books.data_json
```

目录扫描会展示`books`下全部二级书籍目录，不再只展示同时具有PDF和MP3的目录。支持以下组合：

```text
PDF + 音频       → PDF OCR + Whisper + CTC
DOC/DOCX/TXT + 音频 → 权威正文 + Whisper + CTC
CHM + 音频       → 7-Zip提取HTML正文；错版时自动降级为仅音频
仅音频           → Whisper直接生成正文和词级时间轴
```

来源选择优先按书名匹配PDF，其次DOC/DOCX、CHM、TXT，最后使用正文规模、音频时长和PDF页数兜底。多章节音频按章节执行Whisper并支持断点复用。

长书阅读性能策略：

- 导入时按英文标点拆分正文，无空格标点也可识别；单句最多60词，超长内容按分号、冒号、逗号或词边界继续拆分。
- 已导入书可用`tools/resegment_book.py --book-id <id>`保留词级时间并重新分句，同时迁移生词和注解坐标。
- 阅读页只渲染当前句前后各45句，并在播放接近窗口边缘时自动切换窗口。
- 生词和注解使用Map索引，标记刷新只处理当前可见窗口。
- 句子DOM节点按索引缓存；播放时间和进度条限制为每秒10次，单词高亮仍使用逐帧同步。
- 导入worker使用较低系统优先级；Whisper默认3线程，wav2vec2 CTC默认3线程，避免后台处理占满整机CPU。

### 视频对齐链

```text
MP4 + 可选SRT/VTT
  ↓
FFmpeg提取16kHz单声道MP3
  ↓
每15秒生成关键帧
  ↓
外部字幕 → 内嵌字幕 → Whisper
  ↓
Whisper base.en + DTW
  ↓
wav2vec2 CTC强制对齐
  ↓
SQLite
```

字幕视频的导入策略：

```text
本地上传SRT/VTT         → 跳过Whisper → 字幕时间 → wav2vec2 CTC
视频内嵌英文字幕        → 跳过Whisper → 字幕时间 → wav2vec2 CTC
YouTube人工英文字幕     → 跳过Whisper → 字幕时间 → wav2vec2 CTC
YouTube自动英文字幕     → Whisper校准 → wav2vec2 CTC
没有可用英文字幕        → Whisper生成正文 → wav2vec2 CTC（有权威文本时）
明确选择“只使用Whisper” → 忽略字幕并执行Whisper
```

字幕至少需要解析出3个有效英文字幕块，否则自动回退Whisper。跳过Whisper时会在任务步骤和质量数据中记录`whisperSkipped=true`，并清除旧的`whisper-dtw`归档。

### YouTube对齐链

```text
YouTube URL
  ↓
yt-dlp解析标题、频道、时长、字幕
  ↓
优先人工英文字幕
  ↓
自动英文字幕后备
  ↓
无字幕时Whisper
  ↓
进入MP4视频导入流程
```

## 7. SQLite数据库

数据库：

```text
.local/library.sqlite3
```

主要表：

### `books`

保存：

- 图书/视频/YouTube ID
- 中文和英文标题
- 所属系列或标签
- `source_type`: `book`、`video`、`youtube`
- 原始路径、视频URL、音频URL、页面路径
- 字幕类型
- 最近阅读时间
- 对齐方式
- 正文、句子和单词时间轴JSON

### `book_artifacts`

保存：

- OCR原始结果
- Whisper/DTW原始结果
- CTC对齐报告
- 字幕内容

### `vocabulary`

保存：

- 生词
- 所在书、句子和词位置
- 中文释义、音标、上下文
- 个人备注
- 复习评级、间隔和到期日期

### `word_annotations`

保存：

- OCR原词
- 订正词
- 单词备注

### `learning_daily`

保存按日统计：

- 阅读秒数
- 句子数
- 查词数
- 复习数
- 跟读次数
- 学习会话数

### `app_settings`

保存：

- 快捷键
- 书架视图和当前系列
- 护眼模式
- 热力图范围
- 单词工具条停留时间
- 生词每页数量
- 听写朗读次数和停顿
- `highlightLeadMs`
- `sentenceAutoPause`

## 8. 当前前端功能

### 书架

- 按系列筛选。
- 最近阅读优先，未读新书排在已读书籍之后。
- 平铺和列表视图。
- PDF/视频关键帧封面。
- 点击切换系列后自动回到书架。

### 阅读

- 精读、泛听、跟读。
- 句子点读和自动滚动。
- 单词逐帧高亮。
- 句子页码自动切换。
- 视频书支持“关键帧/视频”切换。
- `A`上一句、`S`复读、`D`下一句、空格播放/暂停。
- `Q`切换句末自动暂停，默认关闭。
- 鼠标悬浮单词暂停，离开恢复。
- 顶部护眼开关。

### 单词

- Dioco中文词典。
- Dioco独立单词TTS。
- Dioco上下文用法。
- 生词本下划线。
- 注解词波浪下划线。
- 浮动工具条加入生词本、订正OCR、备注。
- 工具条默认2秒停留，可配置。

### 生词复习

- 昨日、当日、明日、所有。
- 普通复习：点击单词显示答案和评级，右栏展示完整信息。
- 听写：点击开始后每词重复朗读指定次数，词间停顿指定秒数。
- 听写支持暂停、继续、上一个、下一个、重新开始。
- 已播词可重听并在右栏显示完整释义。
- `A`上一页、`D`下一页、`E`尾页、`F`首页。
- 每页数量可在系统设置中修改，默认10。

## 9. 导入功能

### 目录书籍

页面：`导入内容 → 目录书籍`

选择系列、多选书籍，后台严格串行：

```text
PDF/MP3
→ OCR
→ 正文页识别
→ Whisper DTW
→ CTC强制对齐
→ 词典
→ SQLite
```

### 本地视频

页面：`导入内容 → 视频文件`

支持：

- MP4
- MOV
- M4V
- 外部SRT/VTT
- MP4内嵌字幕
- 无字幕Whisper

### YouTube

页面：`导入内容 → YouTube 地址`

步骤：

1. 粘贴地址并解析。
2. 显示标题、频道、时长、缩略图和字幕状态。
3. 确认中文标题、英文标题和标签。
4. yt-dlp下载最高720p视频。
5. 优先人工英文字幕，自动字幕后备。
6. 进入视频导入、DTW和CTC流程。

当前YouTube失败任务要查看：

```text
.local/youtube-<job_id>.log
.local/youtube-import-<job_id>.log
```

## 10. 重要API

### 书架和书籍

```text
GET /api/library
GET /api/books/<id>
GET /api/local-dictionary
```

### 导入

```text
GET  /api/import/catalog
GET  /api/import/jobs/<id>
POST /api/import
POST /api/import/batch
POST /api/import/video/init
POST /api/import/video/upload/<id>?kind=video|subtitle
POST /api/import/video/complete/<id>
POST /api/import/youtube/info
POST /api/import/youtube
```

### 学习

```text
GET  /api/vocabulary
POST /api/vocabulary
POST /api/vocabulary/<id>
POST /api/word-annotation
POST /api/activity
GET  /api/learning/days
```

### Dioco代理

```text
GET  /api/word-dictionary?word=...
GET  /api/word-tts?word=...
POST /api/word-context
```

### 设置

```text
GET  /api/settings
POST /api/settings
POST /api/preferences
```

## 11. 打包和部署

### 当前开发部署

```bash
./start-reader.sh
```

### macOS launchd

建议创建：

```text
~/Library/LaunchAgents/local.shiyue.reader.plist
```

示例：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.shiyue.reader</string>
  <key>ProgramArguments</key><array>
    <string>/Users/x/Documents/english/start-reader.sh</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/x/Documents/english</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/x/Documents/english/.local/reader.log</string>
  <key>StandardErrorPath</key><string>/Users/x/Documents/english/.local/reader-error.log</string>
</dict></plist>
```

加载：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.shiyue.reader.plist
```

卸载：

```bash
launchctl bootout gui/$(id -u)/local.shiyue.reader
```

### 未来Tauri

长期可将当前前端封装为Tauri桌面应用：

- 前端继续使用当前HTML/CSS/JavaScript。
- Python服务作为sidecar，或迁移成Rust本地API。
- FFmpeg、Whisper、CTC和SQLite由桌面应用管理。
- 适合输出macOS `.app` / `.dmg`。

当前还没有完成Tauri打包，不要把Python HTTP服务直接暴露到公网。

## 12. 安全与隐私

- 服务监听`0.0.0.0`是为了家庭局域网测试。
- `.dioco.local.json`权限应为`600`，不提交Git。
- 设置API只返回Dioco令牌掩码。
- Dioco令牌只由后端向上游转发。
- YouTube不会绕过登录、付费、DRM或访问控制。
- 当前局域网服务没有用户认证，不适合不可信网络。
- `.local/`、`.cache/`和生成媒体不应提交Git。

## 13. 新会话接手步骤

```bash
cd /Users/x/Documents/english
cat PROJECT_CONTEXT.md
./start-reader.sh
```

然后检查：

```bash
sqlite3 .local/library.sqlite3 'pragma integrity_check;'
curl http://127.0.0.1:8765/api/library
curl http://127.0.0.1:8765/api/settings
```

修改前端后：

1. 修改`reader/app.js`或`reader/styles.css`。
2. 提高`reader/index.html`里的CSS/JS缓存版本。
3. 运行`node --check reader/app.js`。
4. 重启服务或刷新浏览器。
5. 访问本机和局域网地址验证。

修改导入器后不要直接重跑整个10GB书库，先使用短音频或短MP4验证。

## 14. 已知事项

- CTC强制对齐速度明显慢于DTW，导入任务必须串行。
- CTC覆盖失败的句子保留DTW时间戳。
- OCR漫画气泡、词汇表和页眉顺序可能需要人工订正。
- 无字幕视频的正文质量取决于Whisper断句和音频质量。
- YouTube受登录、年龄、地区或Cookie限制时可能失败。
- `.local/import_jobs`保留历史失败/取消任务，是审计记录，不代表书籍当前不可用。
- 任务ID 5（《苏格兰玛丽女王》）在SQLite中仍显示历史状态 `running / 63%`，但当前没有对应导入进程；后续可标记失败或重新导入，不要误认为它仍在后台运行。
- 旧静态JSON和测试媒体可能位于系统临时目录或旧 `.reader/`目录，不是当前阅读器数据源；当前数据源是SQLite。

## 远程一键部署与成品同步

系统设置使用Tab布局，分为“通用设置”和“打包部署”。通用设置管理账户、快捷键与阅读体验；打包部署管理远程发布、资源同步、回滚、实时日志和最近任务。部署接口仅允许通过本机`127.0.0.1`或`localhost`操作，局域网访问会返回403。

用户只需要配置：

```text
SSH地址
SSH端口（默认22）
账号（默认root）
密码
远程目录（默认/srv/shiyue）
服务端口（默认8765）
是否安装远程录音Whisper
```

密码不写入SQLite或日志。macOS优先保存到钥匙串；首次连接后自动生成并安装拾页专用Ed25519部署密钥，后续操作优先使用密钥。

主要操作：

```text
测试连接
一键完整部署
升级程序
同步数据
版本回滚
```

三个发布操作边界：

- `一键完整部署`：面向新Linux服务器，检查或安装Docker，上传离线运行镜像、代码、模型和证书，并自动同步全部当前点读内容。
- `升级程序`：只上传当前前后端代码快照并切换版本，不上传运行镜像、Whisper模型、书籍媒体或内容数据库。代码包通常只有约0.1MiB，每次保留完整快照以支持可靠回滚。
- `同步数据`：只比较和同步书籍正文、内容数据库包以及新增、修改、删除的音频、页面图片和视频，不升级程序代码。

版本管理分为两条独立链：

- `回滚代码`：切换`/srv/shiyue/releases/code-*`，只回滚页面和后端程序，书籍内容与学习数据不变。
- `回滚内容`：恢复所选`content-*`的书籍正文、时间轴、字典缓存和媒体文件；保留远程生词、备注、学习记录与系统设置。回滚前自动创建操作级恢复点，回滚后健康检查失败会自动恢复。
- `清理过期版本`：默认保留30天，可在页面修改天数。删除截止日期之前的非当前代码版本、内容快照、资源差异备份和数据库备份；当前代码版本与当前内容版本永不删除。

从支持内容回滚的版本开始，每次同步都会在远程保留：

```text
/srv/shiyue/manifests/history/content-*.json
/srv/shiyue/manifests/history/content-*.json.gz
/srv/shiyue/backups/resources/content-*/
/srv/shiyue/backups/databases/content-*.sqlite3
```

所有操作均创建后台任务，并实时写入：

```text
.local/deployment/logs/<job-id>.log
```

页面每秒增量读取日志，刷新后可以继续跟踪。

远程代码采用版本目录：

```text
/srv/shiyue/releases/code-*/
/srv/shiyue/current -> releases/<active>
```

远程运行采用Docker，服务容器名为`shiyue-reader`。Docker允许在远程通过官方安装脚本或系统包管理器安装；Docker之外的拾页运行镜像、代码、whisper.cpp可执行环境、录音模型、HTTPS证书和点读资源都由本机准备后上传。远程不从GitHub、Hugging Face或Python软件源下载项目依赖，也不执行拾页镜像构建。

“一键完整部署”按以下顺序执行：

```text
检测Linux CPU架构
检查或远程安装Docker
上传本机缓存的完整运行镜像
上传并激活版本化代码
上传Whisper模型和本机生成的HTTPS证书
启动容器并健康检查
自动执行一次成品资源增量同步
再次健康检查
```

首次升级会把当前已验证的运行镜像缓存到本机：

```text
.local/deployment/runtime/shiyue-reader-runtime-amd64-20260930-1.tar.gz
```

当前缓存支持常见的x86_64/amd64 Linux。更换新的同架构Linux服务器后，只需配置SSH地址、root账号和密码，点击“一键完整部署”即可完成程序、模型、证书和当前全部点读资源部署。健康检查失败会恢复上一个代码版本。

资源同步只根据SQLite中`ready`书籍的实际URL生成成品清单：

```text
合并后的.reader/audio.mp3
页面/关键帧.reader/pages/page-*.jpg
本地MP4/YouTube source.mp4
```

不上传原始PDF、章节MP3、DOC/DOCX、TXT、CHM、Whisper分章文件、CTC环境或macOS编译产物。2026年9月30日验收时共19本成品、1241个媒体文件、约1.275GiB。

资源同步由本机比较当前与远程成品清单，只把新增或修改的文件打成离线增量包并通过SCP上传，同时同步删除记录。远程被替换或删除的文件先进入`backups/resources/<content-revision>/`。这种方式不会受SSH登录横幅影响，也不要求远程下载任何同步工具或代码。内容数据库包只合并`books`、`book_artifacts`和`dictionary_entries`，保留远程学习记录、生词、备注和设置。

远程实例运行：

```text
SHIYUE_RUNTIME_MODE=reader
```

该模式隐藏导入入口并拒绝导入API。

如果启用远程录音，离线运行镜像已包含Linux版FFmpeg和whisper.cpp；`ggml-base.en.bin`由本机校验后上传。HTTPS CA和服务器证书也在本机生成后上传，并将根证书保存在：

```text
.local/deployment/certificates/<host>-rootCA.pem
```

其他电脑或手机需要安装一次该根证书，才能在远程HTTPS页面授权麦克风。

部署实现文件：

```text
tools/deployment/manager.py
tools/deployment/remote_apply.py
tools/deployment/ssh_expect.exp
deployment/systemd/shiyue-reader.service
deployment/docker/Dockerfile
```
