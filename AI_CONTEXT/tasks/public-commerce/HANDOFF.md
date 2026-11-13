# 国际商业入口与国内隔离

更新时间：2026-11-13（Asia/Shanghai）

## 原价与实际售价调整

- 本轮分支 `feat/commerce-price-edit` 基于已上线完整基线 `122d444`，属国际商业扩展；国内商业入口/产物继续隔离。用户确认“原价＋实际售价”，例49/19显示3.9折，并授权京东云发布。
- 国际运营后台→套餐管理→套餐菜单→调整价格：以元输入两位小数价格，自动显示一位小数折扣，二次确认后调用 `POST /api/admin/commerce/products/{id}/price`，原管理员/登录/CSRF/可信国际站门禁保持。新建版本表单同步改为两价输入。
- API以整数分保存真实售价，服务端派生折扣，不用折扣反算金额；兼容旧版仅原价＋折扣的草稿创建请求。拒绝非法金额/售价高于原价/付费售价0；免费版只能0/0。0047仅放宽展示折扣范围至0..100（支持极低正价四舍五入0.0折），不改写存量商品或交易。
- 调价锁定商品并校验 `expectedVersionId`，事务复制当前已发布商品和完整plan配额/权益/期限/支付链接后发布新版本；历史版本退售，订单、订阅、兑换码原快照保留。同价无新版本；并发过期编辑409。云猫为外部商品，此处调价只控制本站新订单金额，云猫售价需在其平台另行同步。
- 关键文件：`sites/intl/components/CommerceAdmin.jsx`、`CommerceWorkspace.jsx`、`pages/PublicSite.jsx`、`utils/pricing.mjs`，`tools/saas_commerce.py`、`reader_server.py`、迁移0047。
- 已验证：价格/HTTP权限25项、商业/支付PG集成23项（专用 `shiyue_commerce_price_test`）、双站真实Chrome隔离fixture（CN26/国际84次API，含非法价、确认前不写入、失败返回修改重试、角分列表及新建版本）；双前端/博客构建与隔离、modern/UI/JS、部署120项＋博客部署6项、Python编译、diff检查均通过。两个价格表单使用独立name避免输入框ID冲突；确认与编辑用同一受控弹窗。
- 京东云 **#28 complete**：源码 `7750427d60a14a3d40cbcf9f53410bfac7f84706`（clean），`current=/srv/shiyue/releases/code-20261113-175831-0b004ac5`，0047已应用。国内/国际/博客/共享后端同步保数据升级，候选及正式健康检查通过；数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261113-175831-0b004ac5.dump`（0600），配置备份同目录 `settings-code-20261113-175831-0b004ac5/`。
- 公网22项HTTP检查、严格HTTPS/308、国内商业404及新调价接口国际未登录401、0/1/5GB、两支付渠道及云猫链接、当前HTML引用的版本化JS/CSS哈希通过；Chrome实际博客/国内登录/国际折扣及免费升级提示通过，无页面异常。国际裸 `/assets/index.js` 有Cloudflare旧缓存，实际HTML使用 `?v=` 构建指纹；验收必须跟随HTML的真实资源URL，源站与版本化公网字节一致。
- 切换后首轮数据核对用户/书城/内容/订单/订阅/兑换码/商品版本为1/2/2/3/0/0/12，与发布前一致；支付开关、支付凭据指纹不变。随后18:01:48（北京时间）线上后台出现1条标准调价审计：进阶版本 `advanced-30-v4`，原价1900分/售价100分，公开显示0.5折；本次部署及验收脚本未发起该生产调价，保留该新设置，未回退。未真实付款或模拟开通，真实支付宝回调闭环仍按支付交接待后续验收。

- 2026-11-13分支 `feat/site-import-entitlements` 增加0046，已发布京东云 **#27 complete**（源码 `46649cb`，`code-20261113-154904-ef012c6b`）：现售免费/进阶/Pro复制新商品版本，私人空间分别0/1/5GB，免费说明明确需升级才可导入；保留价格、折扣、云猫链接及历史销售快照。国际升级提示通过真实资源API判断；国内不引入升级模块。公网实际商品与Chrome套餐页通过，支付宝/云猫及交易数据数量保持，未付款；验证详情见 [导入交接](../import-media/HANDOFF.md)。

- 2026-11-13用户提供云猫链接后，已为国际进阶/Pro两个在售套餐都补齐 `https://catfk.com/item/d2nhyc`，公开API均恢复cloudcat方式。仅线上配置，无代码发布；国内商业API仍404。备份/审计与验收见 [支付交接](../payments/HANDOFF.md)。

## 2026-11-13 国内产物线上复核

- 对#24当前国内博客1个JS与阅读应用14个JS逐一从公网严格HTTPS下载，与线上发布文件SHA-256一致。全量扫描均无 `/api/commerce/`、`/api/membership/`、`/api/payments/`、会员中心、支付宝、云猫、`/pricing`、`/purchase/` 标记；国际产物包含这些模块。国内按 `@site` 构建隔离，非单纯隐藏按钮。
- 国内两域商业API与支付宝素材实际均404。扫描报告 `/private/tmp/domestic-commercial-assets-audit.json`；源码/构建隔离检查见 `frontend/vite.config.js`、`sites/cn/index.jsx`、`tools/test_dual_entry_build.py`。浏览器networkidle等待超时，因此未以该轮浏览器作为成功证据，采用全部JS公网字节核对与HTTP实测。
- 国际购买方式缺失已确认是线上渠道参数/套餐链接为空，代码仍在；详情见 [支付交接](../payments/HANDOFF.md)。本轮只读核查，未发布业务。

- 用户确认国际恢复原首页、会员、订单和支付；架构、验证及真实发布状态见 [双入口交接](../dual-entry-commerce/HANDOFF.md)。
- `frontend/src/sites/intl/` 包含RynEnglish首页、定价、购买、会员中心、商业运营和支付配置；素材在 `frontend/public-intl/`。共同阅读/账号业务保留当前版本。
- 国内 `sites/cn` 引用纸间微光邀请制页面；无商业模块或国际素材。国内商业路径前后端均拒绝，博客不代理API。
- 两站都要求有效邀请码、验证码与邮箱验证，Cookie分别登录同一账号库。
- 页面使用真实API及渠道就绪状态；错误、重试与空状态不伪造数据。浏览器自动化fixtures仅验证隔离展示和流程。
- 共享权益及支付门禁见 [支付交接](../payments/HANDOFF.md)。新增商业能力从国际站点模块接入，避免进入国内产物。

