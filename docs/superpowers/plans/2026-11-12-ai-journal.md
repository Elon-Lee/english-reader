# AI手记博客实施计划

**目标：** 四个AI一级栏目、12篇原创文章和具有个人特色的纸色博客首页。
**架构：** 现有Astro静态集合，集中categories配置，独立分类/归档路由，复用正文与Feed。现有React及API不变。

- [ ] 在 `blog/src/categories.ts` 定义4分类，schema category枚举；为原文分类。新增 `categories/[category].astro` 与 `archives.astro`。
- [ ] 新增12个Markdown，按每类3篇组织；技术事实参考已核实论文、NIST与Anthropic，保持原创练习主体。
- [ ] 修改Layout/Header/Navbar/Footer/Button布局，增加PostCard与本地书页SVG；首页加入hero、栏目入口、最新文章、个人侧栏。
- [ ] `verify-output.mjs` 检查至少15篇、4分类每类>=3、分类归属、归档/Feed数量、首页组件与现有隔离；仅允许文章参考资料的精确官方URL，资源保持本地。
- [ ] Node24执行 `npm --prefix blog run build && npm --prefix blog run verify`，浏览器桌面检查首页/分类/归档/正文/明暗切换，无pageerror或断链；检查小屏基础可用，不做独立移动端视觉优化。
- [ ] 更新交接并提交源码，保数据发布；公网IP博客检查及国际健康验证，恢复本轮生成的已跟踪React产物，不提交产物。
