# 纸间微光博客

独立的 Astro 静态博客。源码在 `blog/`，构建输出到 `reader/blog/`，部署时该目录是主域名的站点根目录。博客没有后端、账号、统计、评论或在线编辑器，所有访问者收到同一份静态页面。

## 主题来源

基于真实 Retypeset 上游源码：`https://github.com/radishzzz/astro-theme-retypeset`，固定参考版本为 commit `a636b6d393be714cab52d3fc4baddd3f3905f701`。保留上游 MIT 许可证于 [LICENSE](LICENSE)。

保留上游正文排版、标签页、目录、明暗切换、页面过渡和 Markdown 插件；站点布局改为横向导航、纸色首屏、书页插画、四个一级栏目、精选与文章卡片、个人侧栏和完整归档。只保留简体中文，没有导入上游演示文章、作者账户、统计及验证配置。去掉不需要的评论、远程截图、媒体嵌入、音效、Mermaid、KaTeX、第三方字体与远程图片依赖。订阅生成沿用上游 Feed 机制，移除不需要的图片处理和认证字段。

## 本地命令

使用 Node.js >=22.23.4；已验证 Node 24.14.0。上游主题所用 Astro 6.1.5 的审计存在安全告警，本地独立包选用已修复的 Astro 7.4.10、Markdown-it 14.3.3 与 sanitize-html 2.18.1；主题来源版本保持不变。依赖与根项目分开管理，根项目依赖无需变更。

```sh
npm --prefix blog ci
npm --prefix blog run dev -- --host 127.0.0.1 --port 4321
npm --prefix blog run build
npm --prefix blog run verify
npm --prefix blog run preview -- --host 127.0.0.1 --port 4321
```

`build` 先执行 `astro check` 类型检查，再生成静态文件。`verify` 检查文章、标签、关于、RSS、sitemap、404，以及输出中的本地资源和站点隔离边界。`dev` 会展示草稿；`preview` 展示最近一次生产构建。

如果系统 Node 版本较旧，可在命令前设置已安装的 Node 24 路径：

```sh
PATH=/Users/elonlee/.nvm/versions/node/v24.14.0/bin:$PATH npm --prefix blog run build
```

## 写文章

在 `src/content/posts/` 创建一个 `.md` 文件。文件名采用小写英文与连字符；每篇文章设置稳定且唯一的 `abbrlink`。内容必须是有权发布的原创或已获授权文本。

```md
---
title: 一篇文章的标题
published: 2026-11-11
category: ai-reading
description: 一两句话说明文章内容，用于列表、订阅与页面描述。
tags: [阅读笔记, 写作]
lang: zh
abbrlink: a-stable-post-address
draft: true
toc: true
---

文章正文，使用 Markdown。

## 一个小标题

从具体的观察开始。
```

- 必填：`title`、`published`、`category`。日期用 `YYYY-MM-DD`。
- 一级栏目集中定义在 `src/categories.ts`：`ai-basics`（AI 入门）、`prompt-notes`（提示词手记）、`ai-reading`（AI 与阅读）、`practice`（实践与思考）。文章必须属于其中一类，标签可多个。栏目页为 `/categories/<slug>/`，全量归档为 `/archives/`，包括置顶文章。
- 常用可选字段：`description`、`tags`、`updated`、`abbrlink`、`draft`、`toc`。
- `draft: true` 只在开发预览显示，生产构建和订阅不会发布。准备好后改为 `false` 或删除该项。
- `pin` 可取 0–99，默认 0；数值越大，置顶顺序越靠前。
- `lang` 使用 `zh`，也可留空表示默认语言。
- 导航使用站内路径；文章的原始资料参考链接须逐条加入 `scripts/verify-output.mjs` 的精确 URL 白名单。图片请放到 `public/images/` 并使用 `/images/文件名`，不要引入远程脚本、字体、图片或媒体。
- 一篇文章的地址是 `/posts/<abbrlink>/`；不设置时使用文件名。

关于页编辑 `src/content/about/about-zh.md`。站点名称、描述、色彩配置在 `src/config.ts`。`icpRecord` 默认为空，不显示备案链接；仅在取得真实备案号后填写。没有备案号时禁止编造或使用占位号码。

## 输出与部署边界

`reader/blog/` 是生成目录，不直接编辑，不手动写入源码。发布前执行 `build` 和 `verify`，仅将输出目录作为静态网站提供。服务端须用真实 HTTP 404 状态提供 `404.html`，不要把未知地址回退为首页 200。站点不依据 User-Agent 或爬虫身份差异化响应。

当前静态站共15篇：2026-11-12新增12篇AI手记，每个栏目3篇；2026-11-11的3篇阅读随笔保留原地址并归入“AI 与阅读”，该栏目合计6篇。示例不冒充真实经历或测试结果，技术介绍附原始参考资料。系统字体随访问设备略有差异；页面不加载外部字体或图片。首次安装依赖需要访问 npm 软件仓库，页面浏览无需第三方服务。
