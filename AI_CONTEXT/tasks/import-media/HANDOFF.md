# 导入与媒体交接

## 已完成

- 支持 TXT、Markdown、PDF、MP3、本地视频和 YouTube。
- 上传不再使用浏览器 `arrayBuffer()`，直接发送 File 并显示上传进度。
- 上传完成后弹窗立即关闭，后台执行 `/complete`，书架每 3 秒轮询任务。
- 轮询覆盖 `queued`、`uploading`、`running`、`processing`、`awaiting_processor`。
- 任务支持取消、失败展示、重新导入入口和完整历史。
- 私人媒体通过鉴权 API 和 Range 请求访问。

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
