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

关键版本：

```text
yt-dlp       2026.08.19
whisper.cpp  1.9.4-dev
torch        2.2.2
torchaudio   2.2.2
Python       3.11.16
```

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
