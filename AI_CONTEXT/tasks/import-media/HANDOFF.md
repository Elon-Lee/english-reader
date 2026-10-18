# 导入与媒体交接

## 已完成

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

- 可恢复分片上传、断点续传和失败分片重试。
- 重复文件/URL 的前端确认流程。
- YouTube 导入前的信息预览。
- 批量导入 UI。
- 当前 `/complete` 仍由请求线程执行长任务；前端不等待。阶段进度和 80 分钟 stale recovery 可处理已中断任务，但独立持久任务 worker 仍未实现。

## 关键文件

- `frontend/src/main.jsx` 中 `ImportModal`
- `frontend/src/pages/LibraryPage.jsx`
- `tools/saas_imports.py`
- `tools/import_*_worker.py`
- `tools/reader_server.py`

## 验收重点

- 上传后立即回到书架并看到任务。
- 不刷新页面也能看到状态变化。
- 取消和失败状态释放额度与临时媒体。
- 大文件上传期间浏览器内存不能出现整文件双份复制。
