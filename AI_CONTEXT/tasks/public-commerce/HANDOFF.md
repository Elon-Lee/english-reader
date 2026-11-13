# 国际商业入口与国内隔离

更新时间：2026-11-12（Asia/Shanghai）

- 2026-11-13本地分支 `feat/site-import-entitlements` 增加0046：现售免费/进阶/Pro复制新商品版本，私人空间分别0/1/5GB，免费说明明确需升级才可导入；保留价格、折扣、云猫链接及历史销售快照。国际升级提示通过真实资源API判断；国内不引入升级模块。尚未发布或应用正式数据库，验证详情见 [导入交接](../import-media/HANDOFF.md)。

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

