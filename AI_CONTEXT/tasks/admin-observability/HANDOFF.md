# 媒体资产与服务器观测

更新时间：2026-11-14（Asia/Shanghai）；本地完成，用户已授权合并main并发布京东云，发布验证中。

## 目标与现状

- 属于共享后台核心：国内、国际均由 `AdminPage → MediaAssetsAdmin / ServerMetricsAdmin → /api/admin/*` 调用同一 Python 实现；仅管理员可读，页面按当前标签加载。无迁移，无新写接口。
- 原媒体明细的 `content_type LIKE 'video/%'` 过滤遗漏 EPUB/PDF/MP3；已改为所有有效资产。用户汇总含资产数/含音频数/视频数；展开源文件可查看 MP3 等变体的格式、大小、时长和存储路径。生成 MP3 仍登记为文档的 audio 变体。
- 媒体资产增加总占用、源文件/衍生文件、私人/官方占用及按天/月/年的新增登记空间/资产数图表，支持日期筛选。总量仅统计数据库有效资产，不等于全盘用量。
- 增长按北京时间及源文件/变体各自创建时间统计，含软删除记录；不重复计入 generated_bytes，不代表磁盘净增长。默认30天/12个月/5年，最大366天/120个月/20年，空日期补零，拒绝无效/未来/过长范围。
- 新“服务器观测”展示当前 API 环境 CPU、内存、系统/媒体文件系统磁盘、负载、交换空间、后端RSS、运行时间和网络速率；容器可见指标与cgroup限制明确区分。依赖 `requirements-saas.txt` 中 `psutil>=7.0,<8`，本地已安装并重载后台。
- 仅标签打开且页面可见时每10秒轮询，支持暂停/手动刷新；服务端缓存5秒，内存保留120次采样，重启清空。部分采集失败显示未知/错误；依赖缺失返回503。没有后台持续采集、跨服务器SSH或持久历史。
- 保留列表/统计/详情/观测的加载、失败重试、空状态；观测失败保留上次成功数据及时间。

## 接口与关键文件

- `GET /api/admin/media-assets`：用户汇总；`ownerId` 明细返回 `assets`（替代旧 `videos`），保留分页 `total`。
- `GET /api/admin/media-assets/statistics?period=day|month|year&start=YYYY-MM-DD&end=YYYY-MM-DD`：summary/history及统计时区、范围。
- `GET /api/admin/server-metrics`：当前采样与近期history。两接口在既有 `admin_get/admin_required` 之后执行。
- 后端：`tools/saas_media.py`、`saas_media_analytics.py`、`saas_server_metrics.py`、`reader_server.py`。
- 前端：`frontend/src/components/{MediaAssetsAdmin,AdminTelemetryChart,ServerMetricsAdmin}.jsx`、`pages/AdminPage.jsx`、`styles.css`。后台可直达 `/app?screen=admin&adminTab=media|server`。

## 验证

- `PYTHONPATH=tools .local/saas-venv/bin/python -m unittest tools/test_admin_observability.py`：7项通过，覆盖日期边界、真实采样、缓存、依赖缺失、部分失败、容器限制及管理员门禁。
- 专用 `127.0.0.1:55432/kokoro_import_20261114_test` 下运行 `test_saas_phase8_integration`：29项通过，含真实EPUB/PDF/Kokoro、MP3明细、分页、时区、零填充、删除历史、统计不重复及两站HTTP未登录401/普通用户403/管理员200。不得在真实用户库运行夹具。
- `npm run build:sites`、`test:modern`、`test:ui`、`test:sites`、`test:sites:built`、`check:js` 通过。构建产物不提交。
- 使用已安装 Playwright：`PLAYWRIGHT_MODULE=/Users/elonlee/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core node tools/test_admin_observability_browser.cjs`；双站资源/周期/MP3/失败重试/空状态及离页停止轮询通过，截图 `/private/tmp/admin-observability-browser/`。
- 同环境运行 `node tools/test_kokoro_browser.cjs` 与 `npm run test:sites:browser` 通过；阅读器无“AI 合成朗读”提示、逐句播放回归通过。
- 本地实际管理员会话/API与独立浏览器验收通过：有效资产2个、总73,308,190字节，MP3明细5,398,124字节；统计和服务器指标均返回200。实际已导入官方书籍MP3元数据时长674.675秒、浏览器解码/播放通过。截图 `/private/tmp/admin-observability-live-{media,server}.png`，日志 `/private/tmp/admin-observability-live.log`。未重新生成/删除真实媒体。
- Python编译、`git diff --check`通过；本轮构建与测试生成文件恢复，不提交产物。

## 未完成与后续

- 首次发布任务341已切换，但补充验收发现原升级流程复用旧后端镜像，psutil缺失。正在修复为升级先构建后端镜像、候选实际采集观测指标，再统一重新发布；未以容器内临时pip安装代替修复发布流程。国际CDN静态资源缓存需带版本参数核对。

- 用户已授权提交、合并main与远程发布。按仓库要求统一保数据升级两站、博客及共享后端；psutil随镜像依赖安装，同时为Kokoro准备独立Linux CPU持久环境并实测。发布完成后补充实际版本与验收结果。
- 如需全天候监控或跨重启长期历史，单独设计采集/存储/告警，当前模块仅提供按需实时观测。
