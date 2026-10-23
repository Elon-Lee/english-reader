# PC 阅读器交接

更新时间：2026-10-24（Asia/Shanghai）

## 现状

- 面向 PC 的 React 阅读器已经覆盖普通、护眼、专注三种呈现状态，使用 SaaS API 和鉴权后的原始音视频。当前只在本机验证，尚未发布生产。
- 本地前端开发入口由 `npm run dev:modern` 运行在 `127.0.0.1:5173`；`./start-reader.sh --saas-local` 单独启动 SaaS 后端 `8790` 和调试 SMTP `1025`。后端健康检查为 `/api/health`。调试 SMTP 仍用于在 `.local/smtp-outbox` 捕获注册验证和找回密码邮件，不能作为无用逻辑删除。
- 如果启动时报端口已占用，先检查现有服务是否健康，不要直接再起一份。健康时复用该实例；确认是残留或无响应进程后，使用 `./start-reader.sh --stop-saas-local` 清理，再执行 `./start-reader.sh --saas-local`。
- 2026-10-24 已清理一个无响应的残留 `8790` 进程并重启，健康接口和两个监听端口均已验证。本次操作未修改业务代码。

## 功能基线

### 页面与模式

- 正文、原媒体和学习工具组成单视口工作台；字幕列独立滚动，页面外层不随播放滚动。
- 普通模式显示完整阅读工作台；专注模式使用连续纸面与紧凑播放器，隐藏媒体和侧栏但保留快捷键。两种模式共用同一个媒体实例、字号、笔记和活动草稿，退出后恢复普通模式此前的工具与媒体位置。
- 护眼模式覆盖头部、正文、工具、播放器、浮层、翻译块和媒体区域。纸面与工具样式使用现有语义变量，不使用移动端布局替代 PC 页面。
- 阅读器与系统设置不再使用“阅读 / 精读 / 影子模式”；前端忽略旧 `readerMode` 数据，不新增相关迁移。
- Aa 设置管理字号、行距、正文宽度、护眼、固定侧栏和媒体位置；偏好通过现有鉴权 preferences API 校验并持久化。进入专注时临时收起侧栏，退出时恢复普通模式快照。

### 媒体与播放

- 只通过鉴权 `/api/media/*` 读取原媒体。播放、逐句复读、时间同步和跟读均使用原始音视频，不用浏览器 TTS 代替原音。
- 视频支持左侧/上方布局和“高清 / 流畅”切换。切换画质或布局时保留播放时间、播放状态、倍速、音量和静音；缺失流畅变体时明确报错，不回退到未授权源。
- 流畅视频必须保留音轨。新导入和补齐脚本使用 FFmpeg 生成带 AAC 音轨的 360p H.264 变体；阅读器只把非 `generated` 的规范视频资产作为清晰度选项。
- 原始媒体时间驱动当前句和单词高亮。`readerTiming.mjs` 预建句/词索引并二分查询；播放期间只更新受影响的句子，暂停后停止动画帧循环。播放条进度最多每 100ms 更新一次。
- `timingPolicy=acoustic-only` 的文档原音只使用真实词时间，缺失词不估算。高亮保持在最后一个已开始词直到下一个真实词或句开始；首词开始前无高亮，词间停顿不闪断。
- 上一句、复读、下一句、播放/暂停、句末暂停、时间轴和倍速共用播放器。点击句子会定位到该句并播放；Q 关闭句末暂停时从未播放的句末继续。默认 A/S/D/空格，快捷键在输入框和编辑区域中不拦截。
- 中文 SRT 匹配后作为句译文返回。阅读 API 只为鉴权通过且有对应字幕的句子附加 `translation`，不修改正文或重跑转写；前端只在译文非空时显示翻译入口。

### 查词与学习工具

- 点击正文单词按侧栏当前可见性分流：侧栏收起时显示轻量词卡，展开时切到“单词”并更新内容。词卡的“查看更多用法”会展开侧栏；侧栏手动收起后恢复词卡。普通与专注模式遵循相同规则。
- 悬浮查词使用 `/api/word-hover`，有 300ms 意图延时、缓存及加载、空、失败状态。悬停按偏好暂停原音；连续跨词时共享暂停意图，真正离开后延迟恢复，手动暂停的媒体不会被误播。
- 点击查词分别请求完整词典与语境，任一服务失败时保留另一部分结果。旧请求不能覆盖当前词；完整词典可合并本地 ECDICT 音标。
- 单词面板优先展示来源原句和本句含义，再展示通用词典、例句、私人释义与备注。认识程度为“不认识 / 困难 / 记得 / 简单”，仅收藏后可记录；私人释义和备注默认折叠并合并保存。
- 发音使用鉴权 `/api/word-tts`。`wordPronunciation.mjs` 在点击前按意图预加载，最多缓存 12 个近期音频，并在从 0 秒播放前等待缓冲。PC 共用惰性创建的 Web Audio 输出通道；换词、停止、离开或较旧请求晚到时会取消旧播放。
- 句法、跟读和词典独立加载、独立重试。跟读流程为听原句、录一句、回放对比、练下一句；录音权限申请或录制期间禁止切句、切布局、收起工具和离开。无原音或无时间标记时禁用相关操作，录音只保留在当前页，不上传。
- “加入生词本”和“已加入”是独立状态；学习目标句与用户播放/阅读位置独立显示。工具内操作不触发正文快捷键。

### 学习记录与访问控制

- 最近阅读句通过鉴权 `/api/workspace/progress` 防抖保存，私人读物和已解锁官方读物都映射到当前账号的 `workspace_progress`，刷新后恢复句子的真实起始时间。
- “保存本次学习”调用鉴权 `/api/workspace/activity`。时长按页面可见、聚焦、原媒体播放或最近 60 秒有交互估算，句子与生词按真实结果去重；这是活动时间近似值，不代表掌握程度。
- 保存失败时冻结载荷与幂等键，重试不会重复计时。保存成功后显示“本次已保存”；继续阅读时开始新片段。结算可回到学习空间、继续阅读或复习本次新增词。
- 活动草稿按账号、材料和类型隔离，保存在 sessionStorage，最长 7 天，只用于同标签页刷新恢复。未提交的笔记正文不在活动草稿中；强制关闭后的笔记恢复不能承诺。
- 私人读物校验所有权；官方读物校验发布状态、账号书架与套餐权益。后端保持认证、租户隔离、CSRF、幂等和管理员权限约束。
- 官方试读保留原媒体布局：媒体最多播放前 10%，纯文本最多前 10% 句数，PDF 不返回全文。播放结束、拖动越界或下一句越界时暂停并展示加入提示；加入成功后从当前时间继续。收藏上限、词汇语境或句法额度触限时接现有会员购买/兑换，原操作可继续。

## 关键 API 与文件

- 页面与状态：`frontend/src/pages/ReaderPage.jsx`、`frontend/src/hooks/useReaderSession.js`
- 句子与侧栏：`frontend/src/components/ReaderSentence.jsx`、`ReaderWordPanel.jsx`、`ReaderHoverCard.jsx`
- 纯逻辑及回归：`frontend/src/utils/readerLearning.mjs`、`readerPresentation.mjs`、`readerTiming.mjs`、`wordPronunciation.mjs` 及对应 `.test.mjs`
- 偏好与样式：`frontend/src/config/preferences.js`、`frontend/src/styles.css`
- 页面相关 API：`/api/word-hover`、`/api/word-dictionary`、`/api/word-context`、`/api/sentence-grammar`、`/api/word-tts`、`/api/workspace/progress`、`/api/workspace/activity`
- 后端实现：`tools/reader_server.py`、`tools/saas_auth.py`、`tools/saas_workspace.py`、`tools/saas_catalog.py`、`tools/saas_ai.py`、`tools/saas_imports.py`
- 视频变体与测试：`tools/backfill_saas_video_variants.py`、`tools/test_saas_phase7_integration.py`
- 旧行为参考：`reader/app.js`。SaaS 阅读器不得跳转旧 `reader/index.html` 或 `reader/app.js`。

## 未完成与待验证

- 用户曾反馈页面刷新后首次点击单词的首音节可能不完整。缓冲和 Web Audio 输出启动已修复并通过事件采样，但仍需在真实扬声器或有线耳机上人工听辨确认。
- 麦克风完整录制、回放与设备切换尚未实机验收；这次待验证的范围不同于“原句播放正常”。
- 隔离账号尚未配置可用的 AI，词汇语境和句法成功响应路径需要在可用账号中复验。
- 独立纯音频材料、官方试读裁剪边界、超长正文首次挂载和内存压测仍需补验。
- 超长读物尚未迁移旧版的完整窗口化虚拟滚动；当前只完成句级渲染和时间索引优化。
- 视频缓冲自动降级、重试次数和关键帧降级尚未完全达到旧版能力。
- Dioco `base_dict_getFullDict_8` 已接入单词详情，但缓存刷新和上游错误监控仍需评估。
- 完整键盘与辅助技术验收尚未完成。最近一次播放条主题色调整已构建并通过自动检查，但未做浏览器复测。
- 既有 Vite 大包提示和 Ant Design Modal 弃用警告仍在；当前版本未发布生产。

## 验证

常规前端与阅读器回归：

```bash
npm run build:modern
npm run test:modern
npm run test:ui
npm run check:js
node --test frontend/src/utils/readerLearning.test.mjs frontend/src/utils/readerPresentation.test.mjs frontend/src/utils/readerTiming.test.mjs frontend/src/utils/wordPronunciation.test.mjs
python3 -m py_compile tools/reader_server.py tools/saas_auth.py tools/test_saas_phase7_integration.py
git diff --check
```

页面改动后需要重建 `reader/site/`。涉及认证、租户数据或写 API 时，使用名称以 `_test` 结尾的隔离 PostgreSQL 库运行 phase7/review 回归和 HTTP smoke；禁止用正式库运行测试夹具。设置 `SHIYUE_SAAS_TEST_DATABASE_URL` 后运行 `tools/test_saas_phase7_integration.py`、`tools/test_saas_review.py`。原有全站 smoke 命令为：

```bash
SHIYUE_SAAS_TEST_DATABASE_NAME=shiyue_reader_http_test ./start-reader.sh --saas-smoke 8795
```

浏览器验收至少覆盖真实视频、纯音频、普通/护眼/专注、媒体左右/上方、画质切换、逐句定位、Q 句末暂停、查词词卡/侧栏、原句跟读、刷新恢复和保存结算。历史改前证据见同目录的 `READER_AUDIT_20261020.md`、`READER_LAYOUT_REVIEW_20261020.md`、`READER_MODES_REVIEW_20261020.md`；近期截图位于 `.local/debug/reader-lookup-20261022/`、`.local/debug/reader-hover-20261022/` 和 `.local/debug/reader-sync-20261020/`。
