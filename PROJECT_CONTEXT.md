# 拾页（Shiyue）英语点读系统项目上下文

> 给后续开发会话使用的接手文档。最后更新：2026-10-02。
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
stanza       1.15.0
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

安装英文句式与语法分析模型：

```bash
./tools/install_grammar_model.sh
```

Stanza复用Python 3.11和现有PyTorch环境，模型保存在`.local/grammar/stanza`。模型只安装在本地内容生产端；远程Reader节点只读取已经同步到SQLite的语法结果，不安装Stanza或PyTorch。

2026年10月3日当前SQLite中有39本读物、16,109句，语法数据覆盖16,109句，缺失0。YouTube内容重置后只保留重新导入的`How to THINK in English`；本次变更未同步远程。

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
外部字幕 → 内嵌字幕 → 无字幕时Whisper
  ↓
字幕时间或Whisper词时间
  ↓
wav2vec2 CTC强制对齐
  ↓
SQLite
```

字幕视频的导入策略：

```text
本地上传SRT/VTT         → 跳过Whisper → 字幕时间 → wav2vec2 CTC
视频内嵌英文字幕        → 跳过Whisper → 字幕时间 → wav2vec2 CTC
YouTube人工/自动英文字幕 → 跳过Whisper → 保留原始cue断句 → wav2vec2 CTC
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
优先人工原生英文字幕（包括频道自定义的en-*轨道）
  ↓
原生自动英文字幕后备（优先en-orig，拒绝tlang=en翻译轨道）
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

### `sentence_grammar`

逐句保存原句哈希、句型、主谓宾或补语、从句、时态语态、词级句法角色、依存关系和成分句法树。正文变化后旧结果会自动失效。结构由本地Stanza生成；本地规则讲解和按需生成的Lexa中文讲解也保存在该表中。

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
- 视频书默认并固定使用视频画面，右上角只提供“高清/流畅”切换；关键帧仅作为加载、缓冲和失败时的背景兜底，不提供手动切换。
- `A`上一句、`S`复读、`D`下一句、空格播放/暂停。
- `Q`切换句末自动暂停，默认关闭。
- 鼠标悬浮单词暂停，离开恢复。
- 普通模式、专注模式以及精读、泛听、跟读都支持悬浮单词简释。
- 三种阅读方式点击单词都会在右栏展示完整释义和上下文用法；专注模式点击后临时展开右栏。
- 每个句子末尾提供“句法”，右栏可在“单词释义 / 句子语法”之间切换。
- 顶部护眼开关。

句子语法使用本地Stanza的`tokenize → POS → lemma → dependency parse → constituency parse`组合管线。Stanza负责结构事实，本地规则生成稳定中文摘要；用户点击句子时可再调用Lexa结合结构生成自然中文讲解并写回SQLite。Lexa失败不影响本地结构展示。

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

正文源匹配使用硬优先级，不能让中英对照版去除后缀后与同名原书竞争：

```text
中文书名完全一致 PDF
→ 英文书名完全一致 PDF
→ 中文/英文书名完全一致 DOC/DOCX
→ 完全一致 CHM/TXT
→ 书名相关 PDF（中英对照、编号英文版、一字译名差异）
→ 书名相关 DOC/DOCX
→ 书名相关 CHM/TXT
→ 正文规模与音频时长兜底
```

完全一致层保留“中英文对照版、英文版”等版本标签，因此`弗兰肯斯坦.pdf`属于完全一致，而`3A_01.弗兰肯斯坦中英对照.pdf`只属于次级相关候选。每本书的`.reader/import-plan.json`保存`matchPolicy`、`exactMatches`和`selectionReason`，方便排查选源。

2026年10月1日对`牛津书虫全系列7级（3）`的21本书完成选源审计，报告位于：

```text
.local/source-match-audit-level3-20261001.json
```

结果：18本选择完全一致PDF；《铁道少年》按一字译名差异选择`铁路少年.pdf`；《牙齿和爪子》和《星际动物园》没有同名PDF，分别选择同名DOC。若同名PDF可以渲染页面但OCR正文不足200词，自动保留PDF页面并依次回退同名DOC/DOCX、CHM/TXT及其他书名相关正文。

《弗兰肯斯坦》旧计划误选`3A_01.弗兰肯斯坦中英对照.pdf`，CTC覆盖率仅66.29%（448句失败）；修复后使用`弗兰肯斯坦.pdf`页面和`弗兰肯斯坦.docx`正文，CTC覆盖率97.13%（26句失败），共906句、9635词。

选择系列、多选书籍，后台严格串行：

```text
PDF/MP3
→ OCR
→ 正文页识别
→ Whisper DTW
→ CTC强制对齐
→ 词典
→ Stanza逐句语法分析
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

所有目录书籍、本地视频/音频和YouTube导入在CTC完成后都会运行逐句语法分析。语法失败只记录到`.local/grammar-<book-id>.log`，不会让已经完成的音频、正文和时间轴导入失败。

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
POST /api/sentence-grammar
```

`POST /api/sentence-grammar`参数为`bookId`、`sentenceId`和可选`enhance=true`。本机缺少缓存时会按需运行Stanza；远程Reader节点只读取已同步缓存。`enhance=true`会在配置了Dioco令牌时生成并缓存受Stanza结构约束的中文讲解。

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

## YouTube字幕断句与时间轴

YouTube自动字幕不能把SRT块直接视为句子。滚动字幕通常大量重叠，并且会重复前一块的单词。当前导入链路改为：

```text
YouTube人工字幕或原生自动字幕
→ 同时下载英文和中文字幕
→ 每个英文原始cue直接作为一条阅读句子
→ 不去重、不运行SaT、不按停顿或标点重新断句
→ wav2vec2 CTC只校准cue内部的英文单词边界
→ 按时间重叠把原始中文字幕挂到英文cue
→ 语法栏展示该句原始中文字幕
```

YouTube不再使用项目的动态断句参数；阅读句子数量必须等于有效英文字幕cue数量。句子保留`originalCueIndex`、`cueStart`和`cueEnd`，CTC只调整实际朗读词的开始和结束时间。

提交数据库前必须满足：

```text
相邻句子时间重叠 = 0
句内0.8秒以上停顿 = 0
CTC覆盖率 >= 75%
已有生词与备注全部迁移到新句子ID
```

重建工具：

```bash
PYTHONPATH=tools python3 tools/repair_youtube_subtitles.py
```

工具会从每个视频的`source.info.json`重新选择严格的原生英文轨道，先生成所有候选结果，全部通过后才开启SQLite事务；执行前使用SQLite Backup API保存完整数据库。它同时迁移生词和备注、删除旧`whisper-dtw`归档及遗留Whisper文件，并把字幕轨道写入SQLite和`.video-import.json`。2026年10月2日修复现有7个YouTube视频后的指标：

```text
TEDx Stanford（人工en）：235句，短句7，CTC 99.02%
Friends（人工en-6Pw-d3P9U40）：522句，短句22，CTC 98.57%
Vocabulary（人工en-rfcqDbLL02Q）：138句，短句2，CTC 97.44%
TEDx天文（原生自动en-orig）：251句，短句38，CTC 89.96%
Top 10（人工en-6Pw-d3P9U40）：217句，短句11，CTC 98.99%
Think in English（人工en-6Pw-d3P9U40）：162句，短句7，CTC 100%
Grit（人工en）：86句，CTC 98.65%
全部视频：句子重叠0，无法解释的句内0.8秒以上停顿0，Whisper未使用
```

### 视频画面与声音同步

阅读页面使用独立的主音频和静音视频画面。原始方案允许两者偏差达到250ms后才直接跳转视频，容易出现口型提前及周期性回跳。当前方案：

```text
requestVideoFrameCallback读取实际显示帧时间
基础倍速始终与主音频一致
偏差小于40ms：保持正常速度
偏差40～180ms：临时微调视频速度，最大约±4%
偏差超过180ms：硬校准到主音频时间
播放、暂停、拖动、切句和切换画面模式时立即校准
```

对源视频音轨与提取MP3进行90秒波形互相关，相关度99.9646%，实际内容偏移为0ms，因此不使用固定音频补偿。

### 阅读页视频画布布局

视频书的画面区域使用无边框、真实宽高比驱动的媒体画布，不再使用固定高卡片和`object-fit`黑边。浏览器读取视频`videoWidth/videoHeight`或关键帧`naturalWidth/naturalHeight`，按当前栏宽和可用视口高度计算画布：

```text
画布宽度 = min(布局栏宽, 最大可用高度 × 媒体宽高比)
画布高度 = 画布宽度 ÷ 媒体宽高比
```

- 上下布局：媒体与正文处于同一主列并水平居中，最大高度约为视口44%，去除边框、标题栏和内边距后将空间直接提供给画面。
- 上下布局媒体画布使用15px圆角和轻量阴影；浮动工具条最右侧提供关闭按钮，点击直接返回左右布局。
- 左右布局以正文为主：桌面媒体列约占可用宽度29%，中等窗口约27%，中间正文获得最大剩余空间；画面在媒体栏内部按真实比例取最大尺寸并垂直居中，不显示固定容器产生的上下空白或黑边。左右布局的实际视频/关键帧使用15px圆角，但不增加边框、背景卡片或阴影。
- “高清 / 流畅 / 关闭上下布局”悬浮在媒体内部右上角，顺序固定，关闭按钮位于最右侧且只在上下布局显示。视频书不再展示“关键帧/视频”切换。
- 普通PDF/图片书籍继续使用原有“标题、原书页、页码”布局，不受视频画布规则影响。

### 不同导入场景的模型组合

三条导入路径互相隔离，避免YouTube自动字幕优化影响目录书籍：

```text
目录书籍
PDF/DOC/DOCX/TXT/CHM/OCR权威正文
→ 标点与章节规则断句
→ Whisper只提供时间参考
→ wav2vec2 CTC词级对齐
→ 不加载SaT

目录书籍纯音频特例（没有PDF/DOC/DOCX/TXT/CHM）
→ 合并章节音频
→ Whisper生成正文和初始词时间
→ speech-asr SaT + 停顿融合
→ wav2vec2 CTC

本地视频 / 本地音频
人工外挂或内嵌字幕优先
→ 标点充足时以字幕标点+停顿+CTC为主，跳过SaT
→ 标点稀疏时加载SaT
无字幕时：Whisper → SaT → 停顿融合 → CTC

YouTube
人工或自动英文字幕：保留原始cue → CTC词级对齐（跳过Whisper与SaT）
中文字幕：人工中文 → 原生自动中文 → 英文自动翻译中文
自动翻译英文字幕（URL含tlang=en）：拒绝，不作为英文原稿
无英文字幕：Whisper → SaT → 停顿融合 → CTC
```

YouTube字幕轨道必须按`人工原生英文 → 原生自动英文 → Whisper`选择。不能只请求精确`en`：人工轨道可能是`en-6Pw-d3P9U40`、`en-rfcqDbLL02Q`等频道自定义代码；自动字幕优先`en-orig`。任何URL带`tlang=en`且原始`lang`不是英文的轨道都是自动翻译结果，必须拒绝。相关选择逻辑集中在`tools/youtube_subtitles.py`，不能在其他导入器中另写宽松判断。

中文字幕必须与英文字幕同时下载，优先人工简体中文，其次原生自动中文，最后才使用由英文自动翻译的简体中文。2026年10月3日已删除旧的7本YouTube内容及生成资源，只重新导入`How to THINK in English | No More Translating in Your Head!`：人工英文轨道`en-6Pw-d3P9U40`、人工中文轨道`zh-CN`、160个英文原始cue、CTC 160/160、相邻句时间重叠0、中文原始字幕覆盖155/160。未提供中文的5个发音示范cue在语法栏明确显示“原始中文字幕未提供该段译文”。此次未同步远程。

YouTube导入不提供手动书系选择，书系由频道自动确定并由后端强制写入，避免表单残留上一次标签。频道规范化规则包括：`TED`复用`Ted`书系，任何`TEDx...`频道归入`TEDx Talks`，其他频道保留频道名称并按大小写复用已有书系。前端解析后只读展示“自动归入书系”。历史误分类的Grit视频已从`Rachel's English`修正为`Ted`，物理资源目录不移动，避免改变媒体URL。

SaT使用独立本机环境与模型缓存：

```text
.local/sentence-segmenter/venv
.local/sentence-segmenter/huggingface
模型：sat-3l-sm，ONNX CPU
```

该环境不上传到远程Reader节点。普通的PDF/DOC/CHM/OCR目录书籍不会加载SaT；只有完全没有正文来源的目录纯音频书会使用`speech-asr`配置。SaT只提供词间边界概率，最终边界由全局动态规划融合SaT、Whisper标点、音频停顿、句长、句尾功能词、条件从句开头和固定搭配决定。

本地“视频 / 音频”入口支持：

```text
视频：MP4、MOV、M4V
音频：MP3、M4A、WAV、FLAC、AAC、OGG、OPUS
字幕：可选SRT、VTT
```

纯音频不会生成关键帧或视频资源，会自动生成正文、自然段落、句子和词级时间轴，并以`sourceType=audio`作为无画面读物进入书架。

## 远程一键部署与成品同步

系统设置使用Tab布局，分为“通用设置”和“打包部署”。通用设置管理账户、快捷键与阅读体验；打包部署管理远程发布、资源同步、回滚、实时日志和最近任务。部署接口仅允许通过本机`127.0.0.1`或`localhost`操作，局域网访问会返回403。

远程部署支持多个独立节点。系统设置的“打包部署”页先展示节点列表，每个节点独立保存SSH、远程目录、服务端口、录音模型开关、部署密钥、任务历史和版本链。原有单节点配置会自动迁移为节点ID 1，不丢失钥匙串密码或部署密钥。

每个节点需要配置：

```text
SSH地址
SSH端口（默认22）
账号（默认root）
密码
远程目录（默认/srv/shiyue）
服务端口（默认8765）
访问协议（HTTP或HTTPS）
是否安装远程录音Whisper
```

访问协议与录音模型相互独立：HTTP模式不会生成、上传或挂载TLS证书，容器健康检查使用`http://`；HTTPS模式挂载节点证书并使用`https://`检查。已有节点迁移后默认保持HTTPS。远程HTTP页面受浏览器安全上下文限制，通常不能申请麦克风，即使服务器已安装录音Whisper。只修改协议或服务端口时，保存节点后执行“升级程序”即可重新创建容器并应用配置，不需要同步内容。

密码不写入SQLite或日志。macOS优先保存到钥匙串；首次连接后自动生成并安装拾页专用Ed25519部署密钥，后续操作优先使用密钥。

主要操作：

```text
测试连接
一键完整部署
升级程序
同步数据
版本回滚
一键卸载
```

- 节点列表可以直接选择、一键部署或一键卸载。
- 节点管理页面使用紧凑双栏布局：节点列表与连接配置并排，部署操作与版本管理并排；节点卡片只负责选择，不重复放部署或卸载按钮。窄屏自动恢复单列。
- `一键卸载`要求输入节点名称二次确认，会停止并删除`shiyue-reader`容器、旧systemd服务、拾页专用Docker镜像，以及该节点配置的远程目录中的代码、内容、模型、证书和版本备份；不会卸载服务器上的Docker引擎，也不会删除本地书库。
- `删除配置`只删除本机保存的节点、部署密钥、钥匙串密码引用、任务历史和版本记录，不连接或修改远程服务器。
- 所有部署、同步、回滚、清理和卸载请求必须携带明确的`targetId`，避免多节点之间串用配置。

三个发布操作边界：

- `一键完整部署`：面向新Linux服务器，检查或安装Docker，上传离线运行镜像、代码、模型和证书，并自动同步全部当前点读内容。CentOS/RHEL的yum分支只使用阿里云Docker CE仓库，避免官方仓库覆盖镜像地址；安装`docker-ce`、`docker-ce-cli`、`containerd.io`时最多重试3次，每次失败会清理下载缓存并重建仓库缓存。安装后启用Docker开机自启并验证daemon；已运行的Docker直接复用。
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

同步清单必须保留数据库URL对应的逻辑路径。单文件音频书的`.reader/audio.mp3`通常是指向原始章节MP3的符号链接：传输时只解引用文件内容，清单和远程目标仍使用`.reader/audio.mp3`。不能对路径先调用`resolve()`再生成相对路径，否则会误传成原始MP3路径并导致阅读端404。该行为由`tools/test_deployment_content_paths.py`覆盖。

2026年10月2日修复了25本0级单文件音频书的历史错误：增量同步新增25个正确`.reader/audio.mp3`、删除25个误传原始MP3，并逐一验证远程Range请求均返回`206 Partial Content`。

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

## 低带宽远程节点优化（2026-10-05）

不使用CDN时，当前远程Reader采用分层优化：

- 首页只加载`/api/library`和轻量设置；完整词典、生词、学习记录、导入目录、部署配置均按页面进入时加载，不再自动打开书架第一本书。
- 书架前8张封面优先加载，其余使用`loading=lazy`与`decoding=async`。导入时从原书第一页生成`.reader/cover-320.jpg`；现有36张封面从约4.9MiB降到约0.40MiB，平均约11.2KiB。
- 大型书籍使用`/api/books/<id>/manifest`和`/api/books/<id>/chunks/<n>`。manifest保留全书轻量句子索引，词级时间轴每80句一个分块；浏览器初始加载当前位置前后分块并在播放接近边界时预取。
- Python API与静态文本支持gzip；GET响应支持ETag和304。书架元数据、书籍manifest、时间轴分块、图片和媒体使用分级Cache-Control。
- 视频导入生成`.reader/video-muted.mp4`：移除重复音轨并写入faststart索引；独立MP3继续作为点读主音频。
- 保持现有离线运行镜像兼容，不增加Nginx依赖。Python Reader直接使用`socket.sendfile`发送静态大文件，并提供Range、gzip、ETag、304和分级缓存；客户端中断媒体请求时不再输出异常堆栈。
- 这些服务端优化只涉及代码，保存节点配置后执行“升级程序”即可生效，不需要重新上传运行镜像或同步内容。

本机实测：

```text
首页HTML gzip                  8.0 KiB
app.js gzip                   41.4 KiB
styles.css gzip               18.7 KiB
/api/library gzip              2.5 KiB
《简·爱》manifest gzip       118.0 KiB
《简·爱》每80句分块 gzip      17.2 KiB
```

首屏不再请求约2.17MiB完整词典、约4MiB第一本书JSON、导入目录或部署配置。当前策略不生成低码率音频副本，因为重新编码可能引入编码器延迟并破坏已校准的词级时间轴；如后续需要低码率音频，应在CTC之前生成并以该文件完成最终对齐。

## 远程Reader文案模式（2026-10-05）
+
+前端根据`/api/settings.runtimeMode`区分本机完整模式与远程Reader节点。HTML初始使用中性文案，避免远程首屏闪现`LOCAL`：
+
+- 本机`full`模式显示`LOCAL READER`、`LOCAL BOOK`、本地数据库、词典与制作环境相关说明。
+- 远程`reader`模式显示`WEB READER`、`READING`、`READER SETTINGS`、内置词典、语境规则和句法模型等中性文案。
+- 远程模式隐藏导入入口、打包部署Tab及其本地运维说明；学习记录与账户设置不再显示“只保存在这台设备”或“本机服务”等文字。
+- API返回的来源名称如果包含“本地词典、本地语境规则、本地模型”，远程页面展示时会转换为“内置词典、语境规则、句法模型”，不修改底层数据来源。

## 视频双清晰度与低带宽降级（2026-10-05）

视频导入现在生成两个静音画面版本，独立MP3、字幕、CTC与语法数据不变：

```text
高清：.reader/video-muted.mp4
流畅：.reader/video-low.mp4（最大640×360、H.264、CRF 27、maxrate 380k、无音轨、faststart）
```

`book.data_json`保存`videoDefaultQuality=high`和`videoVariants.high/low`，包含URL、codec、宽高、码率、字节数、时长和状态。新视频导入时自动生成流畅版；生成失败不会让整本导入失败，会保留高清版本并在质量报告中记录失败。`同步数据`会同时包含两个版本。

播放器只展示“高清 / 流畅”两个选项，默认高清。切换时独立MP3继续播放，视频按主音频`currentTime`重新同步。视频未就绪时保留当前关键帧作为背景，并显示加载或缓冲状态：

- 高清连续缓冲约1.8秒或加载失败时自动切换流畅版；不会自动再次升级，用户可手动重试高清。
- 流畅版最多重试2次，仍失败则保留在视频界面并显示当前关键帧背景与“重试”按钮；音频、正文滚动和单词高亮不停止。关键帧不是可手动选择的模式。
- 视频第一帧可播放后淡入，切换过程中不显示纯黑屏。

现有两个视频已补齐流畅版，不重新执行Whisper、字幕、CTC或语法分析：

```text
How to THINK：高清36.1MiB，流畅16.4MiB
Critical Words：高清50.0MiB，流畅16.9MiB
新增存储合计约33.3MiB
```
