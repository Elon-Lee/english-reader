# 导入与媒体交接

## 已完成

- 支持 TXT、Markdown、PDF、MP3、本地视频和 YouTube。
- 上传不再使用浏览器 `arrayBuffer()`，直接发送 File 并显示上传进度。
- 上传完成后弹窗立即关闭，后台执行 `/complete`，书架每 3 秒轮询任务。
- 轮询覆盖 `queued`、`uploading`、`running`、`processing`、`awaiting_processor`。
- 任务支持取消、失败展示、重新导入入口和完整历史。
- 私人媒体通过鉴权 API 和 Range 请求访问。
- 2026-10-16 起音视频导入不按月次数扣减；导入完成前按私人空间字节额度校验并在最终事务检查公版收藏+私人学习空间合计的音频/视频数量上限。取消、失败或删除不占收藏名额。
- 2026-10-18 并发保护：同任务上传使用 PostgreSQL advisory lock，相同文件重试返回原资产，不重复写文件或占空间；新上传使用独立路径，取消后的上传不能恢复任务并释放新资产。`running` 任务重复 complete 只返回状态，不重复启动处理器；任务锁先锁用户再锁任务，最终入库与官方收藏共用数量锁。新增并发测试覆盖相同任务、取消竞争和最后音频名额竞争；尚未发布生产。
- YouTube 未填写自定义标题时保留任务标题为空，由后端在下载元数据后使用 yt-dlp 返回的真实视频标题；不再写入固定的“YouTube 学习视频”占位标题。

## 未完成

- 可恢复分片上传、断点续传和失败分片重试。
- 重复文件/URL 的前端确认流程。
- YouTube 导入前的信息预览。
- 批量导入 UI。
- 当前 `/complete` 仍由请求线程执行长任务；前端不等待，但服务端后续可演进为独立持久任务 worker。

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
