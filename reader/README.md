# 拾页 · 本地英语点读

## 启动

在项目根目录运行：

```bash
./start-reader.sh
```

浏览器打开 `http://localhost:8765`。不要直接双击 `index.html`，浏览器会阻止读取本地 JSON。

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
- 书架支持平铺和紧凑列表视图，并保存上次视图选择
- 左下角书系选择器可在多个已导入书系之间切换

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
