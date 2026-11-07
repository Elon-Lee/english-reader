# PC 阅读器交接

更新时间：2026-11-07（Asia/Shanghai）

## 阅读界面细节调整（2026-11-07）

- 翻页时长由 460ms 调整为 900ms，并放缓缓动；保留 reduced-motion 和动画清理。EPUB/PDF 各自原文件策略不变。
- 原 EPUB 书页外框与 iframe 使用当前原文 body/root 的实际底色，透明时回退白色；PDF 外框白底，翻页纸色同步，消除阅读框内的背景断层，不覆盖原文段落样式。
- 页脚紧凑显示 `当前页 1/7页`，输入框按位数适配且仍能跳页；保存状态统一为“进度已保存/正在保存进度/重试保存进度”，与上方当前页采用等宽两侧列居中对齐。
- PC 精读原始图片铺满媒体列宽、保持源比例；长图在列内滚动，消除容器黑边，不裁剪或拉伸图片。
- 本地标题、favicon、认证/工作区/官网品牌已同步生产 RynEnglish 官方资源；原因是旧本地源码未合入线上品牌变更。具体文件见 brand-assets 交接。
- 本地构建、modern smoke、UI 22 项、阅读器 Node 7 项/Python 15 项、JS/Python 编译/diff 检查通过；Chrome 在本地与生产基线候选检查真实原书两章、EPUB 2/3/目录兜底、900ms 动画、纸色/页码/对齐、图片横竖/左右上下布局，另检查真实三入口验证码。候选的 PDF 原页/空白页/查词/恢复及音频补传回归通过；测试在隔离浏览器拦截业务 API，不写真实用户数据。
- 已定向发布入口 `7b99f4600df6`、阅读器 `source-reader-72d99f5ab867.js`，新增 5 个版本化资产 + HTML，248 个既有文件哈希保持；无后台更新、数据库迁移或重启。备份 `backups/saas/reader-polish-20261107/`，清单 `manifests/history/reader-polish-20261107.json`。发布前后哈希和源站 HTTPS/SaaS/Redis 健康通过；实际生产静态文件经 Chrome 复验 EPUB 2/3/兜底/真实两章、背景/页码/状态对齐/900ms 动画、原图两布局、PDF 原页/空白页/查词/恢复，以及真实品牌登录/验证码开关/401/新资产 200，均通过，无页面异常。日志和截图在 `/private/tmp/english-reader-polish/deploy/`。
- 关键文件：`useBookPageTurn.jsx`、`EpubSourceReader.jsx`、`ExtensiveReader.jsx`、`extensive-reader.css`；浏览器回归 `tools/test_reader_polish_browser.cjs`、`tools/test_reader_interactions_browser.cjs`。

## 阅读交互修复（2026-11-07）

- 阅读器切换按钮、提示和系统设置将“普通模式”统一改为“精读模式”；持久化仍使用既有 `focusMode`，不迁移数据。
- 原文件 EPUB 的目录优先读取 EPUB 3 nav / EPUB 2 NCX 的真实标题与片段锚点；缺失或只声明封面 Start 时，使用已存正文标题和真实句地址。最新《The Stars》两个章节都在 `index.xhtml`，原 NCX 只有 Start；不再把封面/正文两个 spine 文件误当成两章，同一 XHTML 内反复点击目录可定位标题。无需重导入或回填旧书。
- `EpubSourceReader.jsx` 统一处理目录和原文链接的章节/锚点/句地址跳转，目录显示当前章节，页脚区分章节数量与当前正文文件的屏幕页。PDF 保持独立原页策略。
- `sourceWordHover.mjs` 为 EPUB DOM Range / PDF.js 文字层提供真实可查词范围的背景、下划线和手形指针；保留原段落和 CSS 结构，点击仍走既有查词 API。精读正文补充悬停背景。
- `useBookPageTurn.jsx` 在按钮、方向键与页码跳转时显示 460ms 纸页转动及阴影，兼容 EPUB / PDF / 既有段落泛读，动效限制在纸面内；遵循 reduced-motion。Vite 将复用 hook 单独打包为 `bookPageTurn`，避免 EPUB 懒加载反向依赖主入口。
- 已完成本地 Vite 4173 + Python 8790 调试；远程 PostgreSQL / Redis / 验证码使用 SSH 回环隧道，媒体经 Vite 转发远端鉴权接口。启动和日志见 platform-operations；后续先在此环境验证，再发布。
- 验证：独立目录构建、modern smoke、UI 22 项、Node 7 项 / Python 文档与位置 15 项、JS 检查、Python 编译及 diff 检查通过。Chrome 在本地源码和生产基线组装候选上检查原 EPUB/PDF、查词背景/手形、空白页、目录反复跳转/刷新恢复、翻页与 reduced-motion、上传断点重试；新增 `tools/test_reader_interactions_browser.cjs` 覆盖 EPUB 2/3、目录缺失和最新真实原文件。隔离浏览器拦截账号与写 API，不写真实用户学习数据。
- 已定向发布入口 `596c367b06f6`（模块 `source-reader-093be4088218.js`），7 个新增资产 + HTML，241 个既有静态文件哈希保持；无后台修改、数据库迁移或服务重启。备份 `backups/saas/reader-interactions-20261107/`，清单 `manifests/history/reader-interactions-20261107.json`。发布后真实静态文件的 EPUB 2/3/目录缺失/最新原书、PDF 原页/查词/空白页、设置模式名称均经 Chrome 复验通过，无页面异常；真实登录页/验证码开关/401 保护、源站 HTTPS/Redis 健康通过。

## 当前原文件泛读（2026-11-07 已发布京东云）

- 目标：泛读直接展示鉴权原文件；PDF 保留实际页、尺寸、图文与空白页，EPUB 保留原始 XHTML 的段落、CSS、插图和嵌入字体。学习分句与原音继续使用独立原流程，旧书不回填。
- `EpubSourceReader.jsx` 仅对含 `readingDocument.source.version=1` 的新 EPUB 启用；旧结构化 EPUB 保留既有阅读方式，试读使用裁剪段落，不加载完整原件。固定版式按原 viewport 等比显示，一项 spine 对应一页；普通流式 EPUB 按窗口分页，原字号/段距/缩进不覆盖，Aa 明示页数随窗口变化。
- `epubSource.mjs` 按需获取鉴权原 EPUB，浏览器有界解压后只挂载当前章节；当前仍整包下载，不是网络逐章流式读取。DOMPurify 清理主动内容，CSS-tree 解析原 CSS 和嵌套导入，将本地图片/字体换为受控 Blob URL，禁止外部网络；无脚本的同源 sandbox iframe + CSP 隔离章节，退出释放 Blob。加密 EPUB 明确报不支持。
- `sourceTextRanges.mjs` 通过原 DOM Range 与学习词地址建立索引，不插入 span 破坏原 CSS；EPUB 与 PDF.js 文字层共享。只有匹配真实正文的词才接现有查词 API；扫描 PDF 无可匹配文本时保留原图，不生成伪词地址。节点查询二分定位，避免长章逐词全表扫描。
- 阅读位置沿用鉴权/CSRF `/api/workspace/progress`，附 `readingLocation`：PDF `{format:'pdf',page}`（包含空白页），EPUB `{format:'epub',chapter,offset}`。后端校验源格式与范围，在现有 `workspace_settings` 以 `source-position:<源书ID>` 按账号保存，与学习句进度同事务；不修改 schema，普通学习写入不清空原文位置。私人所有权、官方当前书架权限、试读隔离仍有效，永久删除清理对应位置。
- 翻页、目录、原文内部链接、刷新/窗口变化锚点恢复、模式往返位置保留、学习工具“定位原句”、位置保存失败重试均已接入；显式 `sentence` 学习链接优先于历史源位置。切章只在新章节完成排版后报告位置，避免旧章词索引导致跳回。泛读继续暂停且不跟随原音。
- 关键文件：`frontend/src/components/{EpubSourceReader,ExtensiveReader,PdfReadingPage}.jsx`、`frontend/src/utils/{epubSource,sourceTextRanges}.mjs`、`ReaderPage.jsx`、`tools/{epub_document,reading_document,source_reading,saas_workspace,saas_catalog,saas_imports,reader_server}.py`。新增依赖 fflate / DOMPurify / CSS-tree 已锁定并独立懒加载为 epub chunk；现有安装/升级会打包构建产物与全部 `tools/*.py`，Linux 无新增运行依赖。
- 验证：生产构建（独立目录 `/private/tmp/english-reader-source-build`）、modern smoke、UI 22 项/JS 检查、Node 22 项、Python 文档/位置 15 项、Python 编译及 diff 检查通过。Linux 隔离 PostgreSQL 与单元共 61 项通过，删除清理另复验 2 项，含 EPUB 实际导入/所有者隔离、官方书架/试读权限、真实 PDF 空白页、MP3/视频与完整上传回归；未触碰生产业务数据，专用测试库 `source_reader_20261107_test` 已删除。
- Chrome 脚本：`tools/test_epub_source_browser.cjs`（原 DOM/CSS/嵌套样式/图片/字体、查词/定位、隔离、精确位置/刷新/窗口变化/切章、固定画布、失败重试）；`tools/test_extensive_reader_browser.cjs`（既有 EPUB、资源入口限制、原音暂停、PDF 原页查词/空白页及恢复）；`tools/test_companion_audio_browser.cjs`（分段上传回归）。均使用独立浏览器上下文与拦截 API，不写真实账号。
- 已按用户授权定向发布，入口 `/assets/index-source-abd3103b9d5f.js?v=abd3103b9d5f`，阅读器模块 `source-reader-095d7575ec22.js`，复用生产 React / Ant Design（43 个导出实现经 AST 校验），只替换原入口的阅读器 import。新增 7 个静态文件并保留 237 个既有文件哈希，原品牌/CSS/验证码/音频补传保持。后端 6 个源文档文件 + `reader_server` 进度参数的单行补丁；仅重启 SaaS，无 schema 迁移或旧书处理。本地常驻后端未重启。
- 生产备份 `/srv/shiyue/backups/saas/source-reader-20261107/` 含通过 `pg_restore --list` 的数据库备份与旧代码；清单 `/srv/shiyue/manifests/history/source-reader-20261107.json`。基线 release 指针仍为 `code-20261106-113458-43116bfb`。候选后端 Linux 隔离库 61 项、原版/既有泛读/音频补传的候选与真实生产静态文件 Chrome 回归、真实登录/验证码/401/HTTPS 健康与发布哈希校验通过；业务 API 交互只在隔离上下文模拟，未写生产用户数据。专用 `source_reader_publish_20261107_test` 已删除。
- 发布候选及脚本 `/private/tmp/english-reader-source-deploy/`，远程执行记录 `shared/.local/source-reader-publish-20261107/`。首次解包遇到测试夹具 reader 符号链接指向容器路径，未进入发布；将夹具重命名后解包/校验/备份/发布成功。该品牌源码缺口现已通过完整同步提交 `7b65f78` 补齐，见 brand-assets 交接。

## 线上泛读基线（2026-11-07 已发布京东云）

- 用户限定：专注模式改名为泛读模式；泛读不跟随、不恢复原音；只先支持 PDF / EPUB；旧书不回填或重跑，其他资源处理策略保持原流程。偏好仍使用 `focusMode` 布尔键兼容已有账号，无数据库迁移。
- 泛读能力由 `canReadExtensively()` 统一判定：阅读 API 提供可访问 PDF 原件，或 `readingDocument.version=1 / format=epub` 且有原文块。音频、视频、YouTube、TXT、无结构的旧 EPUB 禁用入口并说明原因；默认泛读偏好也不能绕过能力判断。PDF 试读无全文媒体时不允许进入。
- PC 泛读独立于逐句工作台：居中纸页、章节目录、左右按钮/方向键/PageUp/PageDown/空格翻页、跳页、进度条、字号/行距/宽度、护眼纸色。EPUB 保留新导入的段落、标点、显式换行、标题/章节和可用原书页码标签；阅读页数随窗口/字号调整，调整后按当前词锚点定位。
- PDF 使用独立惰性加载的 `PdfReadingPage` / PDF.js 5.4.624，渲染鉴权原文件的实际页面、文字选择层、真实总页数、空白页、整页适配与缩放；不把 OCR 分句排版冒充原书页面。PDF 字号不重排，Aa 中仅提供适用设置。字体/CMap/WASM 本地随构建打包，资源路径带版本，worker URL 带版本，适配远程 Linux 静态前台与缓存。
- 进入泛读暂停原始媒体和单词发音，播放事件/时钟同步/普通播放快捷键均有模式守卫；自动单词发音关闭，手动查词与显式词发音仍走现有真实 API。隐藏播放器、跟读入口和跟读标签；普通模式的媒体实例与工作台恢复保留。
- EPUB 点击词继续使用真实句 ID / 单词索引查词和收藏，默认轻量词卡、按需展开学习工具。阅读位置仍沿用现有鉴权 `/api/workspace/progress` 的句级位置，新增保存中、成功、失败重试状态；试读不写进度。PDF 空白页及 EPUB 跨页长句的刷新恢复精度仍受现有句级进度模型限制。
- 新文档模型仅在导入时建立，私有与官方阅读 API 都在原鉴权之后透传。官方试读按实际获准句集合裁剪段落和词地址，不返回后续段落/标题；旧书读取不写入数据。
- 新增关键文件：`frontend/src/components/{ExtensiveReader.jsx,PdfReadingPage.jsx,extensive-reader.css}`、`frontend/src/utils/extensiveReading{.mjs,.test.mjs}`、`tools/reading_document.py`；PDF 资源打包见 `frontend/vite.config.js`；独立资源提取见 import-media 交接。
- 已验证：生产构建与 modern smoke、UI 22 项、39 项阅读器 Node 回归、12 项 EPUB/文档/API 单元回归、静态前台路由 2 项、Python 编译及 diff 检查；Linux Python 3.11 的隔离 PostgreSQL 与单元回归共 18 项通过，包含 EPUB 实际导入/段落与词地址持久化/所有者隔离、真实 Linux PDF 处理（保留第 1/3 页及中间空白页）、TXT、MP3 和视频原路径。测试仅使用专用 `_test` 库及临时媒体，没有修改生产账号或书目。新增持久化回归见 `tools/test_saas_phase8_integration.py`。
- 京东云基线仍为 `code-20261106-113458-43116bfb`，定向发布前端 `73a8f1652388`：独立阅读器模块 `extensive-reader-1345b43bb194.js`、作用域 CSS、PDF.js/字体资源，入口使用 `index-extensive-73a8f1652388.js`；旧入口及 CSS/其他线上模块字节保持不变。保留现有 React / Ant Design 实例和主题上下文，远端阅读器页脚使用 RynEnglish。后端 4 个既有文件与本地 HEAD 基线逐字节一致后才合入本轮补丁，新增 `reading_document.py`。未重处理旧书、未迁移 schema。
- 备份 `/srv/shiyue/backups/saas/extensive-reader-20261107/` 含经 `pg_restore --list` 校验的数据库及原代码；清单 `/srv/shiyue/manifests/history/extensive-reader-20261107.json`。品牌源码现已通过完整同步提交 `7b65f78` 补齐。
- 浏览器脚本：`PLAYWRIGHT_MODULE=<playwright-core路径> READER_TEST_BASE=<前台URL> node tools/test_extensive_reader_browser.cjs`；可设 `READER_TEST_BOOK` 为隔离书籍 JSON。构建目录 `/private/tmp/english-reader-extensive-build`；发布候选及远端截图 `/private/tmp/english-reader-extensive-deploy/`。Chrome 已检查原段落、翻页/重排定位/目录/真实查词请求地址、无音频同步、试读与资源限制、PDF 原页/空白页和加载/保存失败重试；业务 API 由测试上下文拦截，生产登录页另用真实未登录 API 检查 RynEnglish、验证码开启及 401 访问保护，无页面异常。
- 源站标准 HTTPS 首页/API 200、SaaS/Redis 健康、发布与保留文件哈希一致。开发机公网访问 `rynenglish.com:443` 仍有既有 TLS 超时，SSH 隧道可正常访问真实生产前台，公网外部访问需用户所处网络确认。

## 现状

- 面向 PC 的 React 阅读器提供普通学习、护眼配色及受资源能力限制的泛读模式，使用 SaaS API 和鉴权后的原始音视频。当前线上原文件泛读见首节；EPUB 需新导入才建立新索引，旧书按用户要求保持原样。
- 本地前端开发入口由 `npm run dev:modern` 运行在 `127.0.0.1:4173`；`./start-reader.sh --saas-local` 单独启动 SaaS 后端 `8790` 和调试 SMTP `1025`。后端健康检查为 `/api/health`。调试 SMTP 仍用于在 `.local/smtp-outbox` 捕获注册验证和找回密码邮件，不能作为无用逻辑删除。
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
- 普通模式显示完整阅读工作台；泛读模式使用独立原文书页与翻页导航，暂停并隐藏原音及跟读工具。两种模式共享字号、笔记和活动草稿，退出后恢复普通工作台的工具与媒体位置。
- 护眼模式覆盖头部、正文、工具、播放器、浮层、翻译块和媒体区域。纸面与工具样式使用现有语义变量，不使用移动端布局替代 PC 页面。
- 阅读器与系统设置不再使用“阅读 / 精读 / 影子模式”；前端忽略旧 `readerMode` 数据，不新增相关迁移。
- Aa 设置管理字号、行距、正文宽度及护眼，PDF 泛读只显示适用设置；固定侧栏和媒体位置仍在普通工作台管理。偏好通过现有鉴权 preferences API 持久化。进入泛读临时收起侧栏，退出恢复普通模式快照。
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
