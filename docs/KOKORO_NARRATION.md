# EPUB/PDF 的 Kokoro 朗读试用

2026-11-14已随京东云#342统一发布国内/国际/博客/共享后端，源码 `e0b4dbc`。服务器 `shared/.local/kokoro` 的Linux CPU独立环境已完成禁网实际合成，正式服务可用；整本长书音质与吞吐仍待验收。

## 使用范围

- 国内管理员的官方内容导入、国际有导入权益用户的私人导入，共用一份实现。
- 选择英文 EPUB/PDF 且没有本次配套 MP3、没有匹配的已上传 MP3 时，可选“AI 生成朗读”；默认仍为仅导入正文。
- 四种英文音色：`af_heart`、`am_michael`、`bf_emma`、`bm_george`。生成语速可选 0.85/1/1.15；服务端允许 0.75–1.25。
- 新生成的 MP3 作为源文档的 `audio` 变体登记，走既有鉴权、Range、存储计费、书籍删除、官方审核与试读裁剪。已有书籍不重处理。
- 阅读器不显示“AI 合成朗读”提示或标题标签，后端仍保留生成元数据供时间轴判断；逐句时间来自每句生成音频的样本长度。单词时间来自模型预测并标记 `estimated:true`；无法完整映射的句子只保留句级时间，不均分单词时间。

## 安装

模型不加入 SaaS 必需依赖，也不在用户导入时联网下载。由管理员在实际运行服务的环境中安装：

```sh
sh tools/install_kokoro.sh
```

默认使用现有 `.local/saas-venv/bin/python` 创建独立 `.local/kokoro/venv`，要求 Python 3.11。可显式指定解释器与持久目录：

```sh
PYTHON311=/usr/bin/python3.11 SHIYUE_KOKORO_HOME=/persistent/kokoro sh tools/install_kokoro.sh
```

服务进程使用同一 `SHIYUE_KOKORO_HOME`；需要时可指定 `SHIYUE_KOKORO_PYTHON`。默认目录无需额外配置。模型环境需 FFmpeg（含 libmp3lame）及 FFprobe，PDF 沿用已有 OCR 安装。本地生成支持项目既有 `.local/local-dev/tools/ffmpeg/bin` 回退。

安装器固定 `hexgrad/Kokoro-82M` revision `f3ff3571791e39611d31c381e3a41a3af07b4987`，保存原始模型卡、音色说明和 Apache-2.0 许可副本；安装 spaCy 英文模型后执行离线合成。只有成功才写 `ready.json`，导入选项接口才报告可用。大模型、虚拟环境、合成样本均在 Git 忽略的 `.local/` 中。

云端需要在容器内安装 Linux 对应的虚拟环境；不能拷贝 macOS venv。发布包包含安装器、依赖声明和Python运行代码，模型与虚拟环境独立保存于 `shared/.local/kokoro`，通过既有 `/app/.local` 持久挂载供候选/正式容器共用。默认目录无需新增环境变量；自定义位置须配置 `SHIYUE_KOKORO_HOME`。普通发布不自动联网安装模型，首次上线必须先完成Linux CPU实际合成预检，再执行统一保数据升级。

## 处理与接口

- `GET /api/workspace/imports/speech-options`：有私人导入权益的登录用户；国内私人 API 继续 404。
- `GET /api/admin/content-imports/speech-options`：登录管理员。
- 创建任务仍使用现有 POST，metadata 可带：

```json
{"speechSynthesis":{"engine":"kokoro","voice":"af_heart","speed":1}}
```

- 不新增写路由。创建、上传、处理、最终入库沿用 CSRF、所有者/官方范围和资源检查；创建与补传均拒绝同时配置原音和 AI 朗读。
- 后台子进程逐句生成 24kHz PCM，然后转为 64kbps MP3。进度、成功、失败、取消、重试继续由现有任务列表轮询展示。
- 同一后端进程最多一个 Kokoro 生成任务，其他任务等待；每约两秒复查取消与权限，结束时复查实际容量。生成音频登记和读物发布在同一事务提交，失败或取消清理本次未登记文件。
- 试用上限为 500,000 字符、12 小时音频、4 小时处理时间；WAV 暂存最多 2GiB，生成预算按当前可用存储限制。长书建议分册。
- 线上通过共享数据库队列串行处理；排队任务在服务恢复后自动继续，中断的运行任务沿用80分钟无进度恢复规则（从头处理，不是句级断点续跑）。本地默认保持原处理方式。整本书的音质、漏读率、吞吐和目标服务器峰值内存尚无验收结论。

## 线上导入资源限额

2026-11-14实际导入曾触发2GiB服务器全局OOM，连带数据库认证超时。新增共享导入进程隔离；启用后，文档提取、OCR、朗读、转写、FFmpeg及下载处理都在独立进程树中执行，HTTP服务与数据库留在限额外。两站共用同一个预算与文件锁，受限任务串行处理，等待/处理状态继续通过任务轮询显示。

线上持久配置位于权限0600的 `shared/config/saas.env`：

```dotenv
SHIYUE_IMPORT_MEMORY_MB=1024
SHIYUE_IMPORT_SWAP_MB=512
SHIYUE_IMPORT_THREADS=1
```

- 单位为MiB；`MEMORY_MB`是物理内存上限，`SWAP_MB`是额外允许的Swap，合计默认1536MiB。物理内存至少128MiB，Swap允许0；线程1–32。实际Swap可用量仍取决于主机配置。
- 限额模式下Kokoro默认按约40字符的小段推理，在原句内拼接音频与时间轴，避免整条长句的激活峰值；不切断单词，并关闭oneDNN缓存加速、回收临时分配以降低内存。可通过 `SHIYUE_KOKORO_CHUNK_CHARACTERS` 调整（0保留模型原分段），本地默认保持原分段。小段可能改变句内韵律，需试听验收。
- 日常升级只补缺失的配置，保留管理员已设值。修改配置后通过统一升级重建服务生效，国内/国际/博客/共享后端按同一版本发布。不要只给整个API容器加内存上限，否则无法单独保护HTTP服务。
- 本地不设置这些变量时默认 `MEMORY_MB=0`，不启用隔离、不限制原处理流程。线上显式设置0也可关闭内存限额，但不关闭全站串行队列及每用户限制。
- Linux使用cgroup限制整个处理进程树；部署只挂载专用 `shiyue-imports` 子组，不挂载Docker socket或整个宿主控制树。候选发布执行真实子进程入组检查；控制器/Swap限额不可用时拒绝启动受限处理，不悄悄改成无限制。
- 内存压力可能通过回收和有限Swap换取更慢的处理；如果模型的必要内存仍超过预算，任务会明确提示“达到内存上限”，保留源文件供调整限额后重试。限额保护主站，不保证任意大小的模型都能完成。被杀进程的子进程及未登记朗读暂存会清理；已有音频和书籍不重新生成。
- 线上（`SHIYUE_DEPLOYMENT_MODE=remote`）每个用户只允许一个上传、等待配套音频、排队或运行中的任务；官方/私人范围合并计数。完成、失败、取消后才能创建下一任务；幂等重发返回原任务。失败重试也检查该限制。
- 完整源文件/配套音频提交处理后分配数据库队列顺序，所有用户、两站、所有类型共用FIFO；未传完的任务不阻塞其他用户处理。一个数据库会话锁覆盖整段处理和子进程清理，已有文件锁继续保护共享内存cgroup。排队时不启动模型/处理进程；原列表轮询显示等待状态，可取消。
- 生产后端启动后恢复队列调度；发布候选禁止调度真实任务，正式切换后才启用。排队任务持久保留；运行中断沿用80分钟无进度恢复规则，不保存模型中间结果。不改变租户、管理员、CSRF、权益或最终入库检查。
- Kokoro模型与正文分词不同（如 `Stranger-man`）时，按实际模型时间保留词组范围，不把词组平均分配成假词时间。已有缺少词时间的朗读句以真实整句时间显示整句高亮，既有音频不重新生成。

## 验证

常规：

```sh
PYTHONPATH=tools .local/saas-venv/bin/python -m unittest tools.test_kokoro_speech
node --test frontend/src/utils/readerTiming.test.mjs
npm run build:sites
npm run test:sites
npm run test:sites:built
```

导入集成只设置 `SHIYUE_SAAS_TEST_DATABASE_URL` 到名称以 `_test` 结尾的专用 PostgreSQL 数据库，禁止正式库。`SHIYUE_RUN_KOKORO_TEST=1` 启用真实模型；`SHIYUE_KOKORO_TEST_PDF_OCR` 可指向真实 PDF OCR 可执行文件，否则 PDF 提取使用已有测试夹具。

```sh
PYTHONPATH=tools SHIYUE_RUN_KOKORO_TEST=1 .local/saas-venv/bin/python -m unittest tools.test_saas_phase8_integration
./start-reader.sh --saas-smoke 8795
```

浏览器：构建两站后运行 `node tools/test_kokoro_browser.cjs`，通过 `PLAYWRIGHT_MODULE` 指向已安装的 playwright-core。使用隔离 API 夹具和 `.local/kokoro/preflight.wav`，覆盖可用性/失败重试、两站导入参数、原音优先和阅读器音频解码；不写真实用户数据。
