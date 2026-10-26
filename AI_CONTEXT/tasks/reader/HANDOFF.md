# PC 阅读器交接

更新时间：2026-10-24（Asia/Shanghai）

## 现状

- 面向 PC 的 React 阅读器已经覆盖普通、护眼、专注三种呈现状态，使用 SaaS API 和鉴权后的原始音视频。当前只在本机验证，尚未发布生产。
- 本地前端开发入口由 `npm run dev:modern` 运行在 `127.0.0.1:5173`；`./start-reader.sh --saas-local` 单独启动 SaaS 后端 `8790` 和调试 SMTP `1025`。后端健康检查为 `/api/health`。调试 SMTP 仍用于在 `.local/smtp-outbox` 捕获注册验证和找回密码邮件，不能作为无用逻辑删除。
- 如果启动时报端口已占用，先检查现有服务是否健康，不要直接再起一份。健康时复用该实例；确认是残留或无响应进程后，使用 `./start-reader.sh --stop-saas-local` 清理，再执行 `./start-reader.sh --saas-local`。
- 2026-10-24 已清理一个无响应的残留 `8790` 进程并重启，健康接口和两个监听端口均已验证。本次操作未修改业务代码。
- 2026-10-24 新增阅读推进方式：默认“当前行轮播”保持原逐句跟随；可选择“整屏阅读”，当前句自然向下推进，到达可见区域底部后才把下一条未读句移到正文顶部。选项同时位于 Aa 阅读设置和系统设置，原有账号未保存该字段时按当前行轮播处理。两处共用 `ReaderFlowControl.jsx`，底层 `SettingsRadioGroup.jsx` 也用于默认学习空间、正文布局和界面密度，统一轻量 Radio 单选、浅色选中背景和细边框；圆点、背景、边框及文字通过 Ant Design 主题 Token 跟随松林绿/雾蓝/鸢尾紫，弹窗不依赖 Layout 的 CSS 变量继承。行为说明实时变化，阅读设置保持紧凑间距。
- 2026-10-24 护眼模式补齐整页背景覆盖：阅读器外层 Layout、工作区、正文、工具栏、播放器、词卡和浮层统一使用护眼纸面/画布变量，避免页面边缘或滚动区域出现白色断层。
- 阅读推进功能已完成构建、modern smoke、UI 22 项、34 项阅读器单测、phase7 PostgreSQL 13 项和 Python 编译；真实 906 句读物验证轮播逐句定位，整屏模式连续 7 句不滚动、第 8 句越界后翻页到顶部。
- Radio 控件已在浏览器验证 Aa 弹窗与系统设置：切换即时更新说明，方向键可切换；松林绿/雾蓝/鸢尾紫均同步圆点、浅底色和边框。选中底色由主题主色按 8% 混合容器底色，避免深种子色生成过重底色；仅键盘聚焦显示额外轮廓。测试后已恢复原鸢尾紫主题，未保存阅读偏好变更。截图：`.local/debug/reader-flow-radio-20261024/aa-iris.png`。
- PC 视频左右布局缩窄视频列：宽屏展开工具时、PC 收起工具时采用 `clamp(260px,22vw,360px)` 视频列，正文承接剩余宽度，消除原比例分配中视频两侧的空白占位。只针对视频，不改变文档/图片、上方布局、专注模式或窄 PC 的既有上下排列。1863px 浏览器验证为视频 360px / 正文 946px / 工具 350px；收起工具后正文 1308px，均无横向溢出。设置四组单选的互斥切换已验证，未提交测试改动。截图同目录 `settings-unified.png`、`reader-side-wider-story.png`。
- 左右布局媒体底部新增上下拖动手柄，支持鼠标拖动、方向键微调和 Home/End 顶部/底部定位。`ReaderMediaPosition.jsx` 在可用列高内约束位置，通过 `ResizeObserver` 适配窗口/媒体尺寸；使用既有鉴权偏好 API 保存账号级 `readerMediaPosition`（0～1），刷新及换读物后恢复。不重建原媒体，不改变播放状态；上方、专注和窄 PC 已上下堆叠的布局不应用偏移。浏览器已验证拖动 252px、刷新恢复、键盘边界，测试后恢复顶部。截图 `media-position-restored.png`。
- 底部倍速菜单不再继承 54px 按钮宽度，改为独立 112px、右侧对齐并向上弹出；六个选项禁用虚拟列表且可完整显示。浏览器已验证普通护眼和专注模式无文字省略，选择 1.5× 后真实视频 `playbackRate` 正确更新，验收后恢复 1.25× 与普通模式。构建、modern smoke、UI 22 项、JS 语法和 Python 编译通过；截图 `.local/debug/reader-speed-20261024/menu-fixed.png`、`focus.png`。
- 修复播放结束仍为 99%：完整原视频/音频的 `ended` 事件立即通过 `/api/workspace/progress` 发送 `completed:true` 和最后一句，原防抖位置保存不作为完成依据。后端验证当前访问权限、布尔字段和最后一句，再幂等写现有 `completed_at`，重读或活动保存保留完成状态；不增加时长、奖励或学习事件，试读不标完成。前端有保存中、成功和失败重试提示。35 项阅读器单测、进度 4 项、phase7 隔离 PostgreSQL 15 项、HTTP smoke 29 项通过；另以隔离账号播放完整 4 秒真实 MP4，书架与工作区均显示 100%。截图 `completion-100.png`。
- 用户明确反馈已播完的私人视频 `private-e60701ec03fe49078b53df94b6af5350` 已单独补记完成；仅更新其所有者现有进度行 `completed_at`，保留当前复习句、学习时长及更新时间。修复前行备份保存在 `.local/debug/reader-flow-radio-20261024/reported-completion-before.json`，未批量推断其他 99% 记录。
- 本地 8790 已重启加载以上后端改动并通过健康检查；本次浏览器隔离验收误用同一 `127.0.0.1` 主机导致登录 Cookie 被测试账号覆盖，已告知用户需要重新登录，未删除真实服务器会话。以后浏览器隔离测试须使用不同主机名或浏览器隔离上下文，端口不能隔离 Cookie。临时测试服务与数据库已清理，当前未发布生产。
- 2026-10-24 等级标准改为 CEFR（欧洲共同语言参考标准）六级：A1（入门）、A2（初级）、B1（中级）、B2（中高级）、C1（高级）、C2（精通）。前端导入、书城筛选和内容管理均使用 `frontend/src/utils/levels.mjs` 定义；后端无硬编码校验，只传递字符串。新增数据库迁移 `tools/saas_migrations/0043_cefr_levels.sql` 将现有 starter/elementary/intermediate 等旧值转换为对应 CEFR 级别，尚未应用到数据库。

## 功能基线

### 页面与模式

- 正文、原媒体和学习工具组成单视口工作台；字幕列独立滚动，页面外层不随播放滚动。
- 普通模式显示完整阅读工作台；专注模式使用连续纸面与紧凑播放器，隐藏媒体和侧栏但保留快捷键。两种模式共用同一个媒体实例、字号、笔记和活动草稿，退出后恢复普通模式此前的工具与媒体位置。
- 护眼模式覆盖头部、正文、工具、播放器、浮层、翻译块和媒体区域。纸面与工具样式使用现有语义变量，不使用移动端布局替代 PC 页面。
- 阅读器与系统设置不再使用“阅读 / 精读 / 影子模式”；前端忽略旧 `readerMode` 数据，不新增相关迁移。
- Aa 设置管理字号、行距、正文宽度、护眼、固定侧栏和媒体位置；偏好通过现有鉴权 preferences API 校验并持久化。进入专注时临时收起侧栏，退出时恢复普通模式快照。
- 阅读推进方式使用现有 preferences JSON 的 `readerFlowMode` 字段，值为 `line` 或 `screen`，无需数据库迁移。整屏阅读不会逐句调用滚动，只在当前句不能完整停留在可见区域时按正文顶部对齐，并保留当前句高亮、原音同步、手动切句和进度恢复。

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

- 最近阅读句通过鉴权 `/api/workspace/progress` 防抖保存，私人读物和已解锁官方读物都映射到当前账号的 `workspace_progress`，刷新后恢复句子的真实起始时间；完整原媒体播放结束另以 `completed:true` 幂等记录完成，书架达到 100%。
- “保存本次学习”调用鉴权 `/api/workspace/activity`。时长按页面可见、聚焦、原媒体播放或最近 60 秒有交互估算，句子与生词按真实结果去重；这是活动时间近似值，不代表掌握程度。
- 保存失败时冻结载荷与幂等键，重试不会重复计时。保存成功后显示“本次已保存”；继续阅读时开始新片段。结算可回到学习空间、继续阅读或复习本次新增词。
- 活动草稿按账号、材料和类型隔离，保存在 sessionStorage，最长 7 天，只用于同标签页刷新恢复。未提交的笔记正文不在活动草稿中；强制关闭后的笔记恢复不能承诺。
- 私人读物校验所有权；官方读物校验发布状态、账号书架与套餐权益。后端保持认证、租户隔离、CSRF、幂等和管理员权限约束。
- 官方试读保留原媒体布局：媒体最多播放前 10%，纯文本最多前 10% 句数，PDF 不返回全文。播放结束、拖动越界或下一句越界时暂停并展示加入提示；加入成功后从当前时间继续。收藏上限、词汇语境或句法额度触限时接现有会员购买/兑换，原操作可继续。

## 关键 API 与文件

- 页面与状态：`frontend/src/pages/ReaderPage.jsx`、`frontend/src/hooks/useReaderSession.js`
- 句子、侧栏与媒体位置：`frontend/src/components/ReaderSentence.jsx`、`ReaderWordPanel.jsx`、`ReaderHoverCard.jsx`、`ReaderMediaPosition.jsx`
- 纯逻辑及回归：`frontend/src/utils/readerLearning.mjs`、`readerPresentation.mjs`、`readerTiming.mjs`、`wordPronunciation.mjs` 及对应 `.test.mjs`
- 偏好与样式：`frontend/src/config/preferences.js`、`frontend/src/components/ReaderFlowControl.jsx`、`frontend/src/components/SettingsRadioGroup.jsx`、`frontend/src/styles.css`
- 页面相关 API：`/api/word-hover`、`/api/word-dictionary`、`/api/word-context`、`/api/sentence-grammar`、`/api/word-tts`、`/api/workspace/progress`、`/api/workspace/activity`
- 后端实现：`tools/reader_server.py`、`tools/saas_auth.py`、`tools/saas_workspace.py`、`tools/saas_catalog.py`、`tools/saas_ai.py`、`tools/saas_imports.py`
- 视频变体与测试：`tools/backfill_saas_video_variants.py`、`tools/test_saas_phase7_integration.py`
- 旧行为参考：`reader/app.js`。SaaS 阅读器不得跳转旧 `reader/index.html` 或 `reader/app.js`。

## 未完成与待验证

- 2026-10-25 桌面阅读器左侧图片沿用视频媒体列宽（`clamp(260px,22vw,360px)`），避免图片独占过宽；仅改普通模式的左侧布局，构建待验证。

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
