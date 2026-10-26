# 官网首页截图与互动演示

更新时间：2026-10-26（Asia/Shanghai）

## 目标与当前状态

- 首页使用当前 PC 产品截图，互动演示与真实阅读器查词体验一致。仅本地完成，未发布生产。
- 用户提供的首批第 1/2/3 张截图分别替换首页第 2/1/4 图；首页第 3 图 `workspace-current.jpg` 保留。生词复习最终采用用户后补的绿色主题截图。
- 三张新图采用 Lanczos 缩放、轻度锐化与 WebP 质量 91，保留原始界面和学习数据；移除查词截图右上角残留浮层、遮住复习截图中的个人邮箱。
- 第四图文案同步改为生词复习。生产图片 URL 按文件内容哈希刷新缓存，构建同时更新 `reader/site/`。

## 互动演示

- 原句：Don't stop to correct yourself. / Just keep going and let the language flow.
- correct 与 language 的简义、来源原句和语境释义取自用户截图。悬停/聚焦显示简义，点击复用当前 `ReaderWordPanel` compact 卡，展示音标、核心含义和操作栏。
- 支持词条切换、关闭按钮、Escape、外部点击、Enter/Space 激活和定位原句；查词卡边界样式独立于 PC 页面媒体查询。
- 公开演示明确标注示例预览；收藏和练习进入真实学习入口，要求用户选择原文，不伪造业务保存或学习成果。“查看更多用法”展开简义并提供真实阅读器入口。
- 已登录单词发音调用现有 `GET /api/word-tts?word=...`；未登录显示登录入口，加载与播放失败有反馈，关闭或换词停止音频。
- 本轮未改业务 API、数据库或真实阅读器。原音播放规则保持不变。

## 新资产

目录：`frontend/public/product/`，生产副本由构建生成至 `reader/site/product/`。

| 文件 | 尺寸 | 用途 |
|---|---|---|
| `reader-lookup-20261026.webp` | 2560×1338 | 首页首图：原声视频与 confident 本句查词浮窗 |
| `reader-tools-20261026.webp` | 2560×1337 | 首页第二图：三栏阅读与固定阅读工具 |
| `vocabulary-review-20261026.webp` | 2560×1403 | 首页第四图：绿色主题生词复习 |

单张约 130–190 KB。旧图片仍保留，不再用于已替换的位置。

## 关键文件

- `frontend/src/pages/PublicSite.jsx`：图片顺序、尺寸与第四图配套文案。
- `frontend/src/components/InteractiveDemo.jsx`：公开示例与交互。
- `frontend/src/components/ReaderWordPanel.jsx`：复用的当前查词卡，未修改。
- `frontend/src/styles.css`：演示与查词浮层样式。
- `frontend/vite.config.js`、`tools/test_modern_frontend.py`：截图内容哈希名单。
- 首页原有定价和 `TrustSection.jsx` 的公开统计继续走真实 API。

## 验证与未完成

- `npm run build:modern`、`npm run test:modern`、`npm run test:ui`（22 项）、`npm run check:js`。
- `python3 -m py_compile tools/reader_server.py tools/test_modern_frontend.py`；`git diff --check`。
- Chrome 1440/1280 桌面检查图片顺序、成功加载与词卡主要交互；未登录发音提示、展开、关闭和键盘激活已检查。
- 768/390 仅检查新增词卡的基本边界和关闭操作；未开展移动端视觉优化。
- 验收截图：`.local/debug/*20261026.png`。
- 未完成：生产发布、已登录真实发音的人工验收、移动端正式优化。
