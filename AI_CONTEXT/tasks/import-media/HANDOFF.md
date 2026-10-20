# 导入与媒体交接

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
- 可恢复分片上传、断点续传和失败分片重试。
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
