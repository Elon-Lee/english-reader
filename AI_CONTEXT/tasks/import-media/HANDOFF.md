# 导入与媒体交接

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
