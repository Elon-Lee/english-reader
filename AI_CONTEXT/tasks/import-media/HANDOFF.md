# 导入与媒体交接

## 2026-11-07 原文件泛读索引（已发布京东云）

- 新 EPUB 在现有独立导入分支调用 `read_epub(...,source_index=...)`，保留原返回接口；为原文件登记 `readingDocument.source={version:1,assetId,layout,spine:[{href,section,layout}]}`。解析全局与每个 itemref 的 fixed/reflow 版式，空/图片章节仍保留 spine 位置，文本章节 ID 与原 spine 索引一致。
- 泛读读取鉴权原 EPUB 的 XHTML/CSS/字体/插图；导入索引负责原文定位和学习地址映射。既有 `blocks` 与分句仍服务普通学习、查词及原音对齐，不以重新排版的分句代替新书原文。PDF 继续按原页直接加载，OCR 只服务学习索引。
- `reader_document()` 仅为完整授权阅读透传源索引；试读移除 source，继续按获准句裁剪段落。旧书不回填，TXT/Markdown/独立音视频/YouTube 不进入新 EPUB 策略，配套音频完整性与分段补传保持独立。
- 原文页/章与文本偏移由现有进度接口校验后保存在每用户的 `workspace_settings`，无 schema 迁移；删除书籍同时清理位置。前端新依赖随构建产物打包，安装/升级现有 `code_files()` 覆盖新增 `tools/*.py` 与 reader 静态资源，远端 Linux 不需新增 Node/Python 运行依赖。
- 验证：Linux 隔离 PostgreSQL/单元 61 项通过，最终位置删除清理 2 项复验通过，专用测试库 `source_reader_20261107_test` 已删除；EPUB/文档/位置单元 15 项、Node 22 项、构建/modern smoke/UI/JS/Python 编译/diff 检查通过。Chrome 原版 EPUB、既有泛读/PDF 和配套音频补传回归通过；验收脚本与产品边界见 reader 首节。当前 EPUB 整包下载、有界解压；加密 EPUB 不支持，流式 EPUB 无固定屏幕页数。
- 已按用户授权发布，入口 `abd3103b9d5f`，备份 `/srv/shiyue/backups/saas/source-reader-20261107/`、清单 `/srv/shiyue/manifests/history/source-reader-20261107.json`。在当前生产基线上定向替换 reader import 和进度参数，保留 RynEnglish/验证码/分段补传。实际发布候选后端在 Linux 隔离库重新运行 61 项通过，候选与生产静态文件 Chrome 回归通过，未写真实账号或旧书；发布专用测试库 `source_reader_publish_20261107_test` 已删除。完整部署前仍须合并线上较新品牌源码。

## 2026-11-07 再次停在 15%：配套音频分段补传（已发布）

- 新任务 `8bfb4be97a97498e9ba8d0525615c17c` 的 EPUB 已上传；08:32:30 UTC 配套音频请求被上传完整性校验拒绝（400），随后响应断连。后端未收到音频、没有处理子进程。不是对齐模型卡住；具体是哪层连接中断仍无证据。原界面把等待音频显示为 queued / 15%，且不能原任务补传，造成再次卡住的观感。
- 配套 MP3 改为独立 `tools/import_audio_upload.py` 策略：256 KiB 分段、每段 SHA-256/长度及合并后总长度校验、已接收分段持久化、幂等确认与完成凭据。刷新后选择同一完整文件，只发送缺失分段；最多三次自动重试。不同内容/长度拒绝混传，残缺音频不登记、不启动处理。取消清理本任务暂存；按账号锁定并检查存储额度。
- 新增私人及官方同构接口 `GET .../{id}/audio-upload`、`POST .../{id}/upload-audio-chunk`、`POST .../{id}/complete-audio-upload`，保留登录、CSRF、所有者/管理员与官方范围检查。最后一个接口在完整校验后提交后台任务，仍轮询进度。普通文档、独立 MP3、视频等资源处理及原上传策略保持独立。
- 私人导入列表和官方导入列表显示等待完整配套音频及“补传完整音频”，不再对未传完音频显示“继续处理”。`ResumeAudioUpload.jsx` 与 `companionAudioUpload.mjs` 共用新传输策略。代理补充安全的数字长度诊断，已知短读的断连响应不再抛 BrokenPipe 堆栈。
- 已定向发布入口 `206bdef9aa05`，备份 `backups/saas/import15-20261107/`、清单 `manifests/history/import15-20261107.json`。新任务通过新分段服务接收 32 段完整原音（8,159,161 字节，SHA-256 `e065fd63be99e495af3f1010672b6d49fdbd11a53966e1fe6e6b124993275a98`），当前 EPUB 已重新声学对齐并完成入库：`private-8bfb4be97a97498e9ba8d0525615c17c`、206 句、89 个原文块、1,011.947378 秒、词覆盖率 98.81%。所有者阅读接口、完整音频媒体服务和原文件哈希通过；旧书不恢复、不重处理。结果 `shared/.local/import15-20261107/recovery-result.json`。首次恢复脚本在导入成功后的校验误从 reader 响应读取未公开的 audioAlignment 字段，修正为从鉴权所属书籍 data_json 只读校验，通过后未重新处理任务。
- 验证：Linux Python 3.11 + 独立 PostgreSQL 共 26 项通过，覆盖分段、持久化补传、损坏/丢失分段、幂等、取消、所有者隔离、真实 HTTP 鉴权/CSRF、EPUB/PDF/独立 MP3/视频原路径；客户端单测 4 项通过。正式构建、modern smoke、UI 22 项、JS、Python 编译与 diff 检查通过；候选生产静态文件 Chrome 验收覆盖中断/刷新补传/确认丢失/不完整不启动、私人/官方补传及既有泛读，零页面异常。真实生产经 SSH 隧道验证新入口、RynEnglish 登录页、私人/官方 API 未登录 401、零页面异常；源站严格 HTTPS、SaaS/Redis 健康。专用测试库 `companion_upload_20261107_test` 已删除。

## 线上 PDF / EPUB 原文结构基线（2026-11-07 已发布京东云）

- 按用户要求只先启用 PDF / EPUB 泛读，旧书不回填、不重处理。`_document_text()` 的各资源分支独立提取；只有 PDF / EPUB 有 `documentBlocks` 时才执行 `build_reading_document()`。TXT/Markdown 保留 `_sentences()`，MP3/本地视频/YouTube 仍走原有转写和时间轴策略，未修改上传完整性、原音对齐或部署校验。
- EPUB：`read_epub(...,structured=True)` 在读取 spine 顺序时提取纯文本段落、标题、引用、显式 br、章节与 EPUB pagebreak 标签；过滤 head/script/style，不将上传 HTML 直接插入页面。部分导出器的独立 CHAPTER/PART/BOOK 标签识别为标题。原 `(text,cover)` 调用保持兼容；结构模式多返回 blocks。
- PDF：OCR/文本提取结果保留实际页索引（含空白页导致的不连续），作为学习分句与页的对应关系；原页排版和实际页数由阅读器直接渲染鉴权原 PDF，独立于 OCR 行分组。
- 新书 `data_json.readingDocument` 含 version、format、pagination、blocks；每块保留完整标点/换行及词的 Unicode code point 位置、句 ID、词索引，分句只服务学习与原音，不重排原文块。文档配套原音对齐仍保留此结构，无数据库 schema 迁移。
- 私有/官方 reader 接口完成原访问控制后返回结构；试读按允许句集合裁剪原文和词，避免整段/后续章节泄漏。无结构的旧 EPUB 禁止切泛读；PDF 有原件即可阅读原页，均不写回旧书。
- 回归：`PYTHONPATH=tools python3 -m unittest tools/test_reading_document.py tools/test_epub_document.py` 12 项通过；Linux Python 3.11 的隔离 PostgreSQL 与单元检查共 18 项通过，包含新 EPUB 完整导入落库/段落及词地址/所有者隔离/幂等、真实 `/opt/shiyue/pdf_ocr` 处理三页含空白页 PDF（学习句页码 1/3）、TXT、MP3 与本地视频原流程。PDF 单元、官方试读裁剪及旧书只读均通过。新增实际 EPUB 持久化和 TXT/PDF 断言在 `tools/test_saas_phase8_integration.py`。本轮没有重新运行整本 EPUB 配套原音声学推理，原完整音频校验与对齐文件保持不变。
- 已定向发布至基线 `code-20261106-113458-43116bfb`，前端版本 `73a8f1652388`，标准 HTTPS 源站与 SaaS/Redis 健康。备份 `/srv/shiyue/backups/saas/extensive-reader-20261107/`、发布清单 `/srv/shiyue/manifests/history/extensive-reader-20261107.json`。4 个后端基线先逐字节核对再应用本轮变更，现有上传校验、媒体对齐、前台代理及品牌/验证码保持原文件哈希；无 schema 迁移、旧书不回填。前端合入方式见 reader 与 platform-operations 交接。

## 2026-11-07 远程上传截断修复与完整原音恢复

- 京东云基线实际为 `code-20261106-113458-43116bfb`，本轮按用户授权发布定向热修复，未重新初始化数据。备份 `/srv/shiyue/backups/saas/import-recovery-20261107/` 含可读取的 PostgreSQL dump 与原文件。保留线上 RynEnglish 品牌、验证码和其他功能。
- 私人任务 `22070acdf05345d99acdaf9d4fc27010`（`The_Stars-Alphonse_Daudet.epub`）排查时为 `queued` / 15%。北京时间 2026-11-07 12:38:11 文档上传返回 200，12:40:17 配套音频上传返回 200；排查时没有该任务的 `/complete` 请求，也没有转写/对齐子进程。
- 前台代理在音频上传响应 `self.wfile.write(data)` 时发生 `BrokenPipeError`，说明下游连接已断开。前一次同名任务也有音频上传响应断连，随后被取消。具体是浏览器离开/网络/外层代理超时，现有日志不足以区分，不能直接归因于某个固定超时。
- 最终根因核实：本机 Downloads 的同名 MP3 为 **8,159,161 字节 / 1,011.947378 秒（16 分 52 秒）**，SHA-256 `e065fd63be99e495af3f1010672b6d49fdbd11a53966e1fe6e6b124993275a98`；远端 3,843,761 字节 / 472.522378 秒文件与本地文件的同长度前缀逐字节相同，确为传输截断。前台 `_proxy()` 未验证 `rfile.read(Content-Length)` 的实际长度，并由 HTTPConnection 按残片长度重新生成 Content-Length，后端又未校验短读，因此残片被登记成功。具体是哪层客户端/代理先中断，现有日志不能确定。不能再将其描述成用户本来只提供半本原音。
- 修复：最后一次上传携带 `X-Import-Start-Processing: 1`，已鉴权的上传接口在响应前提交后台处理并返回 202；旧客户端无该头保持原行为。创建配套文档以 `metadata.awaitingAudioUpload` 阻止音频到齐前启动。断连/网关错误保留任务和源文件，私人导入记录新增“继续处理”及真实 step，沿用原所有者/CSRF/幂等检查。
- 上传完整性：ImportModal 携带 `X-Upload-Size`；前台代理检查实际长度与 Content-Length/原文件大小一致才转发，后端文档与配套音频上传再次检查，短读/大小不符返回 `400 incomplete_upload`、关闭连接，不登记残片、不启动任务。旧客户端仍检查 Content-Length；认证、CSRF、所有者/管理员检查保留。
- 按用户“音频不完整不能导入”，**已撤回接受部分音频方案**。正文声学覆盖至少 80%，并检查首尾缺失（只容许最多 2% 且不超过 50 词的未朗读标题/出版页脚）；错误音频、长缺头/缺尾拒绝，不编造缺词时间。完整本地原音实测 2,073/2,098 词（98.81%）、198 个计时句，故事末句完整匹配；未朗读的 THE END/网站宣传语与零星识别遗漏仍无时间。
- 远程持久化 `/app/.local/forced-aligner/` 使用 numpy 1.26.4、torch/torchaudio 2.2.2+cpu 与 WAV2VEC2_ASR_BASE_960H，模型 SHA-256 `488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d`。首次安装、重装、升级已自动准备依赖/模型并在候选上线前做真实推理检查，详见 `../platform-operations/HANDOFF.md`，不再要求部署后手工补装。
- 前端定向发布只替换生产 bundle 的 ImportModal/LibraryPage 两组件（按 AST 绑定映射），其余线上源码字节保留。最终入口版本 **`c03008a13c69`**，CSS、RynEnglish 品牌与验证码保持线上版本；后端 reader_server 也从线上原文件定向补丁，避免覆盖 11 月 6 日源码。后续完整升级应从包含线上最新变更的完整源码构建，避免品牌回退。
- 验证：构建、modern smoke/UI 22 项/JS、Python 编译及 diff 通过；Linux Python 3.11 下 **79 项部署 + 34 项上传/对齐/隔离 PostgreSQL 导入回归通过**，两个隔离测试库均已删除。真实 HTTP 短读与大小不符在文档、配套 MP3、前台代理均拒绝且不登记资产；完整上传后仅丢响应仍启动处理。Chrome 三场景通过，新增检查客户端发送原文件大小。Linux 独立目录禁网全新安装、真实 CPU 推理和部署 helper 复用检查通过；旧 import-source-plan 测试缺本机夹具，未列入通过项。
- 原任务及读物 ID 保持不变：`22070acdf05345d99acdaf9d4fc27010` / `private-22070acdf05345d99acdaf9d4fc27010`。完整源文件和独立对齐结果保留在远程 `shared/.local/import-recovery-20261107/complete-audio-*`；修复原读物时仅替换音频变体与实测时间/时长，保留正文 ID、翻译、学习记录；同步修正媒体占用差额，旧残片留作故障证据。不得恢复此前部分原音成功结果。
- 最终完整音源与时间轴已原位修复；真实所有者阅读/媒体服务校验通过，线上前台模拟截断请求为 `400 incomplete_upload`，后台、前台、Redis 健康。Chrome 通过 SSH 隧道访问实际生产 TLS 前台，RynEnglish 页面与健康 API 正常、无浏览器异常（使用 DOM 就绪判断，任务轮询页面不等待 networkidle）。修复前备份 `/srv/shiyue/backups/saas/upload-integrity-20261107/`，清单 `/srv/shiyue/manifests/history/upload-integrity-20261107.json`；详细结果 `shared/.local/import-recovery-20261107/complete-audio-result.json`。

## 2026-10-22 文档与配套原音对齐（等待用户自行验收）

- `book_audio_alignment.py` 使用本机 wav2vec2 CTC 模型分窗口读取 16kHz 原音，通过全书单调文本匹配建立声学锚点，再对识别差异执行局部 forced alignment；保留 EPUB 句子 ID、正文和单词索引。没有匹配到的词保留无时间状态，不按长度分摊时间；静音/错误文本拒绝。
- 文档附带音频时，完成接口返回 HTTP 202 并启动任务，前端沿用任务轮询；进度持续刷新、取消时停止子进程、入库前重查状态与额度。缺少本机对齐模型会明确失败。完成任务展示实际词覆盖率。纯文本导入仍即时完成。
- 私人和官方阅读 API 透传 `timingPolicy=acoustic-only`；阅读器对这类正文不估算缺失词时间。用户短文实测后修复显示层的 end 清空逻辑，词/句停顿保持当前词到下个真实 start；无需重导入或修改声学时间，详见 reader 交接。
- 已验证真实原音前 32 秒通过鉴权 HTTP 上传文本+MP3、202（0.047 秒）、轮询至完成和阅读 API，词覆盖 96.4%（未朗读标题不填时间）。前段约 74 分钟/908 句缓存检查覆盖 99.43%。全书处理在声学进度 55/85 时随用户中断停止，未回写测试书。用户随后要求只重启服务并自行重新导入验证，不再继续自动验证或重做该书。
- 证据：`.local/debug/epub-pair-20261022/real-http-alignment.json`、`half-diagnostic.json`、`alignment.log`。调试缓存和定向修复脚本保留，但修复脚本未执行，`private-256de11c81a94b749b2e1779248ce3e3` 仍为原导入状态。
- 已通过：19 项 phase8、13 项 phase7、3 项对齐映射单测、10 项 readerTiming、构建、modern/UI/JS、Python 编译、diff、29 项完整 HTTP smoke（修正已停用 `highlightLeadMs` 的旧断言并补齐隔离库商品/账号夹具）。随后增加短文本匹配和旧时间别名清理，尚未重跑；完整书籍和浏览器验收由用户自行进行。8790 已按用户要求重启加载，未发布生产。

## 2026-10-22 EPUB、音频匹配与等级元数据

- `ImportModal` 可同时选择一个 EPUB/PDF/TXT/Markdown 与同名 MP3，自动匹配并显示“将一起上传”；仅选文档时查询当前账号、当前官方/私人范围已登记的同名 MP3。浏览器不能读取未选中的同目录文件；未匹配/查询失败有明确提示，匹配期间禁止提交。失败上传取消任务释放资产，文件直接以 File 上传并汇总进度。
- 新增 `POST /api/workspace/imports/{id}/upload-audio`（官方对应 admin 路径），复用登录、CSRF、任务所有者与官方范围检查；仅 queued 文档可上传同名 MP3，探测真实时长，存为文档资产的 `audio` 变体；相同音频重试幂等，不同音频拒绝。与 complete 共用任务锁，完成时按 audio 检查收藏容量。匹配已有资产时服务端重新验证所有者、范围、名称并复制为本读物变体，计入存储，不改变原资产所属书籍；删除和官方发布跟随本读物。
- 撤回此前不安全的阅读器全库文件名/ID 查询方案；阅读器继续只返回本读物实际关联资产。仅保存文件名的历史书籍不会自动变成有声书，旧书籍与学习数据未回填。
- `tools/epub_document.py` 使用 XML 解析容器、OPF manifest 与 spine，按阅读顺序提取正文、跳过 head/script/style/nav；兼容 EPUB2 cover metadata 与 EPUB3 cover-image，不依赖属性顺序，识别 JPEG/PNG 原格式并登记 `cover` 变体；限制包内文件数量、解压大小与路径。普通文档沿用共享分句规则，系列/等级保存至 content_books 与 data_json。
- 实测桌面 `When_Summer_Comes-Helen_Naylor.epub` + 同名完整 MP3：通过当前 Chrome 私人导入窗口联合上传，任务 `256de11c81a94b749b2e1779248ce3e3` complete，生成 `private-256de11c81a94b749b2e1779248ce3e3`。正文 1,790 句，MP3 134,790,348 字节/8,422.799813 秒，封面 JPEG 25,177 字节。书架和阅读器均显示原封面，媒体返回 206，浏览器 readyState=4、播放时间推进至 49.28 秒后暂停。证据 `.local/debug/epub-pair-20261022/{reader-playing.jpg,playback.json}`；该新读物保留在当前用户书架。
- 验证：16 项隔离 PostgreSQL phase8 回归（含同名配套音频、幂等、跨租户拒绝、删除清理）、2 项 EPUB 解析回归、前端文件配对检查、构建、modern smoke、UI 22 项、JS、Python 编译和 diff 检查通过。独立库 `shiyue_epub_20261022_test` 的完整 HTTP smoke 在商品目录步骤因缺商品种子返回空 products 阻断；不属于导入失败。测试库验证后删除。本地 8790 已重启加载并通过真实浏览器导入，未发布生产。
- 此节最初验收仅覆盖完整原音播放；后续声学对齐进度见上节。此前四次无音频导入不自动覆盖。

## 2026-10-21 导入时间与中文字幕接入

- 官方内容管理导入表增加“导入时间”列，私人导入任务/历史明确标注同字段，均使用 API `createdAt`，不使用随进度变化的 `updatedAt`。
- 已确认最新官方 YouTube《English Words – The Top 10》中文字幕文件实际存在、下载标记为 true，但导入后 0 句 translation：SaaS 只登记字幕变体，没有执行按时间匹配。新导入在入库前调用 `attach_chinese`，中文 SRT 使用 `require_english=False`；记录匹配数量。
- 私人/官方阅读 API 在完成读物鉴权后，用当前书籍关联的有效 `subtitles-zh-CN` 资产为缺译文句子补充响应，不写回历史书籍、不重转写；沿用 MEDIA_ROOT 安全路径检查。无文件/无匹配时保持空译文。阅读器只给非空译文句子显示翻译按钮，删除误导性占位文案。
- 验证：14 项隔离 PostgreSQL phase8 通过，增加纯中文字幕入库、历史读物读时补充且无写回、字幕文件缺失、官方试读和原租户隔离回归；临时库已删除。构建、modern/UI/JS、Python 编译、diff 检查通过。确认无活动任务后已重启 8790。Chrome 实机核对官方/私人导入时间；当前官方视频可展开实际中文译文，无字幕的《100 English Sentences…》1,093 句显示 0 个翻译按钮。未发布生产。

## 2026-10-21 仅人工英文字幕的新导入路径

- 按用户限定，只为后续 YouTube 新导入接入已下载的原语言人工英文字幕；自动字幕、翻译英文字幕、无字幕、本地文件继续原有流程。已有书籍与学习数据未重处理、未覆盖。
- `tools/manual_caption_alignment.py` 独立子进程复用本地 `WAV2VEC2_ASR_BASE_960H`，逐字幕段与原音 CTC 对齐，保留人工文本与标点。数字等显示文本通过 `ctc_forced_align.word_char_ranges` 仅作发音映射，不调用旧 SQLite CLI。字幕区间仅作搜索窗口，不均分词时长；结果记录 `manual-caption-ctc`、置信度、非估算标记和绝对媒体时间。
- 声学贪心解码一致性、词置信度/时长及服务端时间单调/边界校验必须通过；重叠滚动字幕不走此路径。通过词数不足字幕词数的 65%、运行环境缺失或对齐异常时全量回退原 Whisper；其余只采用失败段的 ASR 正文。失败窗口超过 8 个或覆盖超过全片 25% 时只跑一次全量 Whisper，再提取失败段，避免重复启动模型。书籍 `subtitleAlignment` 保存采用状态、回退原因/范围，导入进度保持单调。
- 不自动下载模型。默认运行环境 `.local/forced-aligner/venv/bin/python`（torch/torchaudio 2.2.2、numpy<2）与 `.local/forced-aligner/models/hub/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth`，可用 `SHIYUE_CTC_PYTHON`、`SHIYUE_CTC_MODEL_HOME` 覆盖；`SHIYUE_CTC_THREADS` 默认 2、上限 3。本地已具备依赖；生产尚未发布，须配置同等环境，否则安全回退 Whisper。现有安装入口 `tools/install_forced_aligner.sh` 需要可用 Python 3.11。
- 验证：864.316 秒真实原音/306 段人工字幕，275 段（1,615/1,830 词）通过 CTC，31 段拒绝；与先前保存的真实全片 Whisper 输出组合后 1,826 词，时间无重叠、负时长和越界。此前第 11 句 CTC 为 44.472–49.468 秒；真实 15 秒视频副本经完整 FFmpeg/CTC/分句路径得到 16 词，跳过 Whisper，用时 5.96 秒。真实错字幕、静音均被拒绝。证据 `.local/debug/manual-captions-20261021/{aligned.json,acoustic-negative-check.json,combined-check.json,end-to-end/result.json}`，均未写入业务书籍。
- 自动化：人工字幕单测、词时间/分句/字幕选择回归、14 项独立 PostgreSQL phase8 测试通过（含人工字幕结果入库/不调用 Whisper、缺环境回退、自动字幕维持旧路径、租户隔离与真实 FFmpeg）；临时数据库已删除。构建、modern/UI/JS、Python 编译和 diff 检查通过。
- 用户确认导入完成后，2026-10-21 已查询无活动导入，重启本地 8790 加载人工字幕路径；8790 与 5173 `/api/health` 均返回 200。再执行 15 项隔离 PostgreSQL 集成测试通过，新增真实 15 秒原音副本 + 人工字幕 + FFmpeg + 实际 CTC 子进程 + 入库验证，16 词对齐、跳过 Whisper、进度单调，总用时 6.15 秒；下载使用测试夹具，未重新执行 YouTube 网络下载。证据 `.local/debug/manual-captions-20261021/end-to-end/postgres-real-import-check.json`；测试库已删除，原有书籍未更改。9 项人工字幕、14 项词时间、9 项字幕选择回归及 Python 编译、diff 检查再次通过。尚未发布生产。
- 这轮验证确认接入和时间合法性，不等于逐词人工标注精度基准或全片提速承诺；此样本拒绝段较分散，仍需一次全量 Whisper，端到端可能增加耗时。

## 2026-10-20 新导入词级时间轴修复

- 已确认：旧解析器丢弃 token/DTW 时间，在片段内均分词时长；当前 Whisper 默认 Flash Attention 会禁用 DTW；`-p 2` 合并只偏移 segment，不偏移 token；时间归一化强制每词至少 30ms，会推迟密集词；所有结果却统一标记 DTW。
- 新音频、本地视频及 YouTube 的 SaaS 转写统一 `-p 1 -nfa`，保留 CPU 线程数配置，DTW preset 跟随模型文件名；未知模型使用 token 时间并如实记录来源。读取 DTW 百分之一秒时间与 token 毫秒边界，合并缩写/子词，保留标点边界；重复/失效 DTW 点回退 token，缺失时间才估算。每词记录 `timingSource/estimated`，书籍记录 `timingVersion=3`、方法和来源数量。
- 最新导入 `private-cbbd129e4ec54431844944f547ac2fd9` 的第 11 行暴露 v2 回归：以 segment 时间 ±2 秒判断 DTW 有效性，但 segment/token 粗时间本身被片尾静音拉长；正确 DTW 被拒绝后，`on … video 1` 从 46.08–49.88 秒变成 48.14–55.58 秒，整句也被拆成两行。已删除该相距判断，保留时间有效性/单调检查。共享标点 DTW 点先寻找下一有效词边界，避免把整句递归回退到漂移的 token 时间；真实重复词点仍保留回退。复测完整句恢复 44.56–49.88 秒。
- 归一化保留有效起点、截断重叠，不再累计强制 30ms 或按字长截短有效测量词；超媒体结尾词删除，末词终点限于媒体时长。`music` 正常正文不再被删除，只过滤明确声音标签。共用构建/旧脚本同步参数，分册合并同时偏移 token 毫秒与 DTW 百分之一秒，避免共用解析器回归；SaaS 仍不调用 SQLite worker。
- **用户明确要求已有书籍不再处理。** 本轮只修改后续导入程序，未回填、重转写或覆盖已有书籍及学习数据。
- 验证：14 项词时间回归（含该第 11 行、共享标点真实输出）、现有分句/策略 9 项及隔离 PostgreSQL phase8 导入 12 项通过；临时测试库已删除。第 11 行旧判断能重放已保存的 12 个词错误时间，真实回归在旧判断下失败。除先前 18 秒音视频/65 秒跨窗口音频外，现已对最新视频完整 864.316 秒重转写到调试目录：1,884 词，无重叠、负时长或越界；与人工字幕匹配的 1,742 词，起点超出所属字幕区间 0.8 秒的情况从 12 降为 0（字幕区间检查不是逐词人工标注精度验收）。新来源 DTW 1,876 词、token 回退 8 词。证据 `.local/debug/import-sentence11-20261020/{full.json,full-comparison.json,full-corrected-book.json,sentence11-comparison.json}`；这些是调试产物，未写回业务书籍。构建、modern/UI/JS、Python 编译、diff 检查通过。
- 本地 8790 已在确认无运行导入任务后重启加载 v3；尚未发布生产。真实对齐仍有模型误差，退化来源可追查；未重新执行真实 YouTube 网络下载。生产发布需带入本轮 Python 及支持 `-nfa` 的配套 Whisper CLI。

## 2026-10-19 内容管理调整

- 验证：隔离临时 PostgreSQL 的 phase3/6（排除旧页面断言）/7/8、权益并发与视频画质共 45 项通过；含真实 FFmpeg、管理员导入 HTTP 登录/CSRF/角色隔离及文件清理。构建、modern/UI/JS、Python 编译、diff 检查通过。旧 phase6 的 `/terms` 页面断言和完整 HTTP smoke 的后台 `/` 首页断言均仍因 API-only 架构返回 404，不属于本轮接口失败；未执行真实 YouTube 网络下载或浏览器人工验收。临时测试库均已删除。
- 本地已备份 `.local/backups/pre-content-management-20261019-083247.dump`，应用 `0037_private_import_ownership.sql`：3 本历史个人导入恢复私人，删除官方登记及收藏关联，保留所有者正文/媒体/学习数据；迁移可重复执行，官方导入不受影响。本地 8790 已重启、5173 API 代理健康；未发布生产。
- 2026-10-19 私人与官方导入分流：我的数据/书架使用 `/api/workspace/imports`，服务端固定 `officialImport=false`；运营内容管理使用管理员专属 `/api/admin/content-imports`，固定 true。两组任务互不可读写，客户端 metadata 不能改变归属。官方导入完成登记官方媒体及未审核 catalog，不进入私人书架、不占私人空间及收藏名额，审核发布后才进入书城；私人导入不在内容管理展示且审核 API 拒绝发布。
- 新 SaaS YouTube 下载格式上限由 720p 改为 480p，流畅变体由 360p 改为最高 240p（不放大小于该尺寸的源视频）；旧视频保持原文件，不批量重新编码。本地文件高清仍使用用户上传原文件。共用导入弹窗已移至 `frontend/src/components/ImportModal.jsx`。


## 已完成

- 2026-10-25 修复书架“导入记录 → 删除无效任务”404：`LibraryPage` 曾调用旧 `DELETE /api/workspace/imports/invalid`，改为后端已实现的 `POST /api/workspace/imports/delete-invalid`，并在 modern frontend smoke 中加入路由契约断言。前端构建（独立临时目录）、modern smoke、JS 检查、Python 编译和 diff 检查通过；phase8 集成测试因未配置专用 `_test` 数据库未运行。仅本地，未发布生产。
- 2026-10-19 导入历史操作改为“删除无效任务”，范围为当前账号 `failed` + `cancelled` 记录；前端按 `invalidCount` 启用按钮，确认与成功提示同步更新。POST 改为 `/api/workspace/imports/delete-invalid`，保留登录/CSRF/用户隔离与重复删除安全；有效任务和源媒体不删除。构建、modern/UI/JS、Python 编译、diff 检查与 phase8 的 11 项隔离库集成测试通过（含仅取消记录、混合状态、重复删除及 HTTP 鉴权）。本地后台已重启加载，未发布生产。

- 2026-10-18 YouTube 新导入系列默认取 `data.youtube.channel`，无频道信息时才回退“私人导入”；`0036_youtube_channel_series.sql` 回填旧默认系列并同步书城默认分组，保留手工系列。迁移已在隔离库验证，尚未应用本地正式库和生产。任务历史 GET 支持 `page/limit` 并返回 `total/failedCount/invalidCount/page/pageSize`；新增 POST `/api/workspace/imports/delete-invalid`，沿用登录、用户隔离、CSRF 与用户锁，仅删除当前用户失败和已取消任务记录，不清理源媒体。phase3/7/8 共 23 项隔离库回归及追加 phase8 11 项回归通过；本轮尚未发布生产。

- 2026-10-18 导入创建、XHR 上传和 complete 返回的套餐额度/空间/收藏容量错误统一接入会员升级弹窗，保留错误 code；前台导入受限关闭表单，升级后返回原表单。已上传后的异步 complete 受限返回重新导入入口，不自动重传文件；未改变现有导入任务与鉴权接口。仅本地，尚未发布生产。
- 支持 TXT、Markdown、PDF、MP3、本地视频和 YouTube。
- 上传不再使用浏览器 `arrayBuffer()`，直接发送 File 并显示上传进度。
- 上传完成后弹窗立即关闭，后台执行 `/complete`，书架每 3 秒轮询任务。
- 轮询覆盖 `queued`、`uploading`、`running`、`processing`、`awaiting_processor`。
- 任务支持取消、失败展示、重新导入入口和完整历史。
- 私人媒体通过鉴权 API 和 Range 请求访问。
- 2026-10-16 起音视频导入不按月次数扣减；导入完成前按私人空间字节额度校验并在最终事务检查公版收藏+私人学习空间合计的音频/视频数量上限。取消、失败或删除不占收藏名额。
- 2026-10-18 并发保护：同任务上传使用 PostgreSQL advisory lock，相同文件重试返回原资产，不重复写文件或占空间；新上传使用独立路径，取消后的上传不能恢复任务并释放新资产。`running` 任务重复 complete 只返回状态，不重复启动处理器；任务锁先锁用户再锁任务，最终入库与官方收藏共用数量锁。新增并发测试覆盖相同任务、取消竞争和最后音频名额竞争；尚未发布生产。
- YouTube 未填写自定义标题时保留任务标题为空，由后端在下载元数据后使用 yt-dlp 返回的真实视频标题；不再写入固定的“YouTube 学习视频”占位标题。
- 2026-10-18 修复 YouTube 长转写看似卡在 45%：45% 是下载结束标记，后续 FFmpeg/Whisper 原先不回报进度；Whisper 命令带 `-np` 且 stderr 丢弃，实际 CPU 转写时 UI 长时间不动。现在开启 `-pp` 并流式解析 Whisper stderr，进度映射到任务 60–85%，无新输出时每 30 秒更新时间戳；其他媒体阶段也更新任务。complete 用 PostgreSQL advisory lock 防重复执行，并在无心跳超过 80 分钟后恢复遗留任务。2026-10-18 原任务 `995fb99dc2ea4c1b92735bf66f2da431` 已恢复并完成，尚未发布生产。
- 2026-10-18 已检查京东云视频环境并热修复生产：`shiyue-saas` 内 FFmpeg 5.1.9、Node 18.20.4、yt-dlp 2026.08.19、Whisper CLI/动态库、`ggml-base.en.bin`（147,964,211 bytes）均可用；2 核/约 2 GiB 内存、磁盘剩余约 30 GiB，无 swap，3 秒视频完整 FFmpeg+Whisper 探测通过。生产后台原先仍是旧 `saas_imports.py`，已替换为当前修复版并重启，健康检查和前台 200 通过；原文件备份在 `/srv/shiyue/backups/saas/saas_imports.py.20261018-210557.bak`。该热修复需在下一次正式 SaaS 升级时纳入发布包，避免被旧 release 覆盖。

## 未完成

- 用户本轮仅授权人工字幕；无字幕/自动字幕的 VAD + ASR + CTC、新识别引擎、FFmpeg 阶段并行、持久 worker、阶段缓存/版本化原始结果和断点恢复均未实施。后续比较引擎需实测目标服务器端到端耗时、峰值内存、正文错误及人工逐词标注边界误差（P50/P95、多秒异常率）；不将其他硬件加速宣传当作本站承诺。用户原有“不改已有书籍”要求继续有效。
- 普通文档与独立音视频的可恢复分片上传（配套 MP3 已完成，见首部已发布节）。
- 重复文件/URL 的前端确认流程。
- YouTube 导入前的信息预览。
- 批量导入 UI。
- 当前 `/complete` 仍由请求线程执行长任务；前端不等待。阶段进度和 80 分钟 stale recovery 可处理已中断任务，但独立持久任务 worker 仍未实现。

## 关键文件

- `frontend/src/components/ImportModal.jsx`
- `frontend/src/pages/LibraryPage.jsx`
- `tools/saas_imports.py`
- `tools/import_*_worker.py`
- `tools/reader_server.py`

## 验收重点

- 上传后立即回到书架并看到任务。
- 不刷新页面也能看到状态变化。
- 取消和失败状态释放额度与临时媒体。
- 大文件上传期间浏览器内存不能出现整文件双份复制。
