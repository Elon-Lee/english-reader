# 拾页 · 本地英语点读

## 启动

在项目根目录运行：

```bash
./start-reader.sh
```

浏览器打开 `http://localhost:8765`。不要直接双击 `index.html`，浏览器会阻止读取本地 JSON。

## 已实现

- 本地书架和阅读进度保存
- 原版 MP3 自动朗读、进度拖动、0.75–1.5 倍速
- 句子级高亮、点击句子跳转、上一句/下一句、单句循环
- 鼠标悬浮单词时自动暂停，移开继续
- 精读、泛听、跟读三种学习模式
- 跟读停顿、麦克风录音、录音回放；受支持的浏览器可显示语音文本匹配度
- 40 个互动故事段落和 `Go to …` 剧情跳转
- 点击单词查看中文释义、上下文用法并单独发音
- 点击正文单词会直接调用 Dioco TTS 接口播放独立单词发音，不再截取原书 MP3，因此不会串读相邻单词
- “认识 / 模糊 / 不认识”评级和间隔复习
- 本地学习记录：进度、听读时间、剧情选择、模式使用次数
- 原书扫描页和重排点读版双视图
- 导入质量报告：OCR 置信度、空白页、缺失段落、无效跳转和异常时间片

本地释义来自项目内的 ECDICT 英汉离线词典；当前《生存游戏》正文中的 237 种英文词形已全部建立词典索引。导入新书时，导入器会重新生成合并后的本地词典。
变形词会继承原形音标；词典中的多条释义会按真正的换行显示，不再显示字面量 `\\n`。

## Dioco 单词接口

阅读器现在通过本地后端分别代理三个接口：

- `/api/word-dictionary`：查询中文释义和例句。
- `/api/word-tts`：获取单词 MP3 发音；点击正文单词和右侧喇叭都使用该发音。
- `/api/word-context`：结合当前句和前后句生成中文语境解释。

在左侧“接口设置”填写账号邮箱和令牌。浏览器只提交给本机后端；后端仅在调用 Dioco 上下文接口时转发。完整令牌保存于项目根目录 `.dioco.local.json`，文件权限为 `600`，并已加入 `.gitignore`；浏览器读取设置时只能看到掩码。词典、TTS和语境结果会缓存在本机 `.cache/dioco`。接口失败时自动回退到ECDICT和本地语境规则。

《生存游戏》当前已经使用 Whisper 词级时间戳，不再使用最初的正文长度估算时间轴。导入器仍保留静音辅助估算作为未运行 Whisper 时的后备方案。

本项目已经在 `tools/vendor/whisper.cpp` 安装本地 `whisper.cpp`，并下载 `base.en` 英语模型。Whisper 只在本机运行，不上传书籍或录音。

Whisper 增强包括：

- 原书单词随 MP3 逐词变色
- 点击词典面板中的“听原书中的发音”播放该词的真实书籍录音
- Whisper 转写与原书正文强制对齐，正文仍以原书 OCR 校对文本为准
- 跟读录音发送到本机 `/api/transcribe`，由本地 Whisper 识别后计算文本匹配度

## 导入更多书籍

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
