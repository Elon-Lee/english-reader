# PC 商业化界面改版

更新时间：2026-10-20（Asia/Shanghai）

## 目标

按用户授权实施首页、套餐、学习空间、会员与书城的商业化体验改进。保留真实价格、会员规则和数据；先完成 PC，不提前优化移动端。

## 当前状态

- 第二轮已按用户授权实施并在本地加载。套餐统一展示 7 行关键权益、公共能力只说明一次、完整权益可展开；修正公开存储单位和 AI 权益口径，官网、会员与触限弹窗共用数据表达，不改价格或权益。
- 首次学习指引依据真实书架、正时长学习记录和已保存生词；支持账号级跳过/恢复。书城及 React 阅读器承接指引，阅读器明确“保存本次学习 / 本次已保存”，失败重试保留同一活动载荷及幂等键。打开页面或保存位置不算完成听读。
- 购买选择及前往云猫动作写入真实账号接口，提醒保留 7 天、可移除、可跨页面/设备恢复；兑换后自动隐藏，再选同款可开始下一次续费。停售深链接仍可进入通用兑换；客服入口保留方案上下文。注册后保留验证提示及返回登录入口。
- 运营“转化分析”按需加载 7/30/90 天真实人数、首次学习漏斗和次日留存。自迁移开始采集，历史不补记；次日完整结束后才计留存分母。购买报表仅是账号选择→前往云猫→之后兑换，不能推断云猫支付成功率、金额或精确订单归因。
- 本地正式库已备份并应用 `0038_product_journey.sql`，8790 已重启且健康。备份：`.local/saas-backups/commercial-round2-20261020/20261019T232256Z/database.dump`。临时测试库及验收服务已清理；未使用正式兑换码或真实付款。
- 已实施并在本地加载，未发布生产。保留深绿与暖白品牌，修正首页断行、层级、间距与产品图片；新增真实学习空间裁剪截图，排除账号邮箱、管理员导航和私人书架列表。未使用生成图片冒充产品界面。
- 套餐仅一个付费推荐；权益说明明确收藏范围。邀请注册、邮件验证、付款后兑换、不自动续费、到期容量规则提前说明。购买前接服务端预览，区分开通、续费、升级、不可降级和失败重试。兑换保留防重复提交及幂等键，成功后刷新状态。
- 学习空间同时接私人和官方书架，按最近保存的位置继续阅读；优先展示继续学习、真实待复习数量、本周实际分钟及参考目标。累计时间不再作为完成进度，未完成读物最高显示 99%。
- 会员先方案、日期、AI 权益和容量，再分页订单及变更；存储显示 MB/GB，历史订单使用商品/权益版本名称，隐藏内部版本编号。
- 书城改善长标题、重复说明、资源类型、按钮对齐；列表/详情具备失败重试，筛选无结果可恢复。
- 补齐 React 政策页面及生产前端 /purchase/*、五种政策路径。复用既有政策文本，仅修正账号在兑换成功时绑定的业务描述；未更改退款条件。政策页面是 React + Ant Design，不回跳旧阅读器。
- 第一轮只读接口新增官方/私人 readingProgress 的位置、百分比和更新时间；订单新增 planName。租户过滤保留，无正式订阅或兑换码测试写入；第二轮迁移见上。
- 原始审查见 REPORT.md，它描述改版前问题。用户引用聊天此前 read_thread 返回找不到任务，未以其内容作依据；本机 ui-ux-pro-max 技能已使用。

## 验证

- 第二轮：前端构建、modern smoke、22 项 UI、JS 检查、9 项展示逻辑、Python 编译和 diff 检查通过。独立 PostgreSQL commerce 12、phase7 8、phase2 10、phase4 6，共 36 项通过；35 项 HTTP smoke 通过。续费再次选择边界修复后 phase7 8 项已重跑。
- Chrome 验收真实套餐对比/完整权益、续费预览、跨页恢复和移除提醒、运营周期切换及空状态；隔离新账号验证首次引导跳过/恢复、进入 React 阅读器、真实保存成功状态。截图：`.local/debug/product-design/commercial-round2-20261020/`。正式账号仅产生一次方案选择遥测，验收提醒已移除；订阅未改变。
- 构建、modern smoke、22 项 UI 回归、JS 检查、Python 编译、diff 检查通过。构建保留已有大分包提示。
- 新增 7 项展示逻辑、4 项阅读位置、2 项前端 HTTP 路由测试通过（覆盖 8 个公开路径与缺失资源 404）。
- 独立临时 PostgreSQL：commerce 12、phase7 4、phase2 10，共 26 项通过。35 项 HTTP smoke 通过，临时库均已删除。
- HTTP smoke 过时首页 HTML 和媒体资产数组断言已改为实际 API-only 边界及用户用量汇总契约。
- Chrome 验证真实 Pro 账号续费预计日期、禁用低档、空码拦截，会员用量/订单名称、学习空间句子位置、书城详情、搜索无结果与恢复；1280 宽首页和书城、1839 宽主要页面已截图检查。访客使用独立 IPv6 回环域的构建产物验证登录门槛和退款公开页面，不注销用户会话。
- 截图：.local/debug/product-design/commercial-implementation-20261019/；审查前图在 commercial-audit-20261019/。截图为本机附件，不保证进入 Git。

## 未完成 / 外部条件

- 尚未发布生产；真实资金付款、发码及正式兑换需商户本人验收。未改变价格、权益额度、正式订阅或销售卡密。
- 移动端、完整键盘/读屏验收、转化率实验未进行；不承诺转化或留存提升幅度。
- 保留现有政策的业务承诺，运营应在发布前自行确认其执行条件。

## 关键文件与命令

- 第二轮：`components/{LearningJourney,JourneyReport}.jsx`、`api/journey.js`、`hooks/useJourney.js`、`tools/saas_journey.py`、`tools/saas_migrations/0038_product_journey.sql`、`tools/test_saas_phase7_integration.py`。
- frontend/src/pages/{PublicSite,WorkspacePage,MembershipPage,CatalogPage,LegalPage}.jsx
- frontend/src/{main.jsx,styles.css}、hooks/usePurchasePreviews.js、utils/presentation.mjs
- frontend/public/product/workspace-current.jpg
- tools/saas_{progress,workspace,catalog,membership,frontend_server,http_smoke}.py
- node --test tools/test_commercial_presentation.mjs
- .local/saas-venv/bin/python tools/test_saas_progress.py
- python3 tools/test_saas_frontend_routes.py
- 集成测试必须指定新建、名称以 _test 结尾的隔离库；HTTP smoke 需要迁移并创建已验证的 ai-owner@local.test 夹具。禁止使用正式库或销售卡密。
