# 国际支付与国内关闭边界

更新时间：2026-11-13（Asia/Shanghai）

## 2026-11-13 云猫购买恢复（线上配置）

- 用户明确授权进阶与Pro都使用 `https://catfk.com/item/d2nhyc`（两链接相同，按原值配置）。已通过线上 `CommerceService.update_draft_purchase_url` 为当前在售 `advanced-30-v2`、`pro-30-v2` 补齐空的purchase_url，两版本仍published，增加2条标准 `commerce_purchase_link_updated` 审计。配置即时生效，业务版本仍#24，无代码发布/重建容器。
- 修改前备份 `/srv/shiyue/backups/saas/cloudcat-links-before-20261113-033714.json`（0600）；前后订单、订阅与兑换码数量不变。使用现有唯一active且已验证邮箱的admin身份记录审计，未创建登录会话、订单或收费。
- 线上国际公开商品API已返回两个付费套餐 `paymentMethods:["cloudcat"]` 及用户指定链接；云猫目标HTTP200。国内learn商业API仍404，支付宝仍未配置/未启用。购买必须先登录核对权益，兑换码仍由云猫商品交付；未做真实付款或兑换验收。
- 真实Chrome验证国际套餐页不再显示“暂未开放新购”，两付费套餐公开API均有cloudcat及指定URL，两条购买路由均可打开并要求登录核对方案；未借用真实用户会话验证登录后的按钮点击。截图 `/private/tmp/cloudcat-restored-production.png`，API快照 `/private/tmp/cloudcat-restored-catalog.json`。此前下节的空链接是恢复前排查状态。

## 2026-11-13 线上购买方式排查（只读）

- 当前#24公开商品API正常返回3个商品，但每个 `paymentMethods:[]`、`purchaseUrl:""`；兑换开通仍启用。支付宝应用ID、私钥、公钥、回调、获批产品与批准开关全部未配置，`commerce.payment_methods` 没有保存记录（默认支付宝关闭、云猫与兑换开启）。全部9个历史/现售套餐版本的云猫链接均为空。
- 购买界面仍有支付宝扫码下单与云猫跳转实现（`sites/intl/pages/PublicSite.jsx`）；`saas_commerce.py:174` 按套餐链接过滤云猫，无链接时不会返回该方式；支付宝由 `saas_payments.py` 就绪检查及开关控制。全球payment.methods含cloudcat/configured=true仅表示渠道开关，不代表具体套餐已可购买。
- 历史源码证据：2026-11-09 `810f19a` 私域改造在升级配置中清理 `ALIPAY_/PADDLE_/MBDPAY_/MBD_/CLOUDCAT_` 环境变量；2026-11-12 `3c404e1` 恢复国际代码，双站升级不再清理支付配置，但缺失配置无法从Git恢复。不能由此证明清理前真实参数一定齐全。现存2026-11-11至13日10份发布配置备份均无支付宝参数；未找到可直接恢复的凭据。退役MBDPay仍未恢复。
- 本轮未更改线上配置、链接、订单或支付开关，未创建订单/收费。恢复云猫购买需提供进阶/Pro实际商品链接；恢复支付宝需已有获批应用参数和RSA2密钥，回调固定国际HTTPS `/api/payments/alipay/notify`，并显式启用渠道。不得用测试模式伪装正式支付。

- 用户确认国际恢复会员、订单和支付；总体架构及实际发布状态以 [双入口交接](../dual-entry-commerce/HANDOFF.md) 为准。国内商业页面/API继续404。
- `saas_payments.py` 恢复支付宝、`saas_billing.py` 恢复Paddle、`saas_redemptions.py` 恢复兑换；保留可信国际入口、登录/验证邮箱、CSRF及管理员权限。旧MBDPay等退役渠道仍停用。
- 订单、订阅与资源账本共用；原私人账号容量不降低。0045兼容增量迁移，不清历史交易或覆盖正式数据。
- 保持验签、订单/金额/币种校验和幂等。双入口支付宝notify必须精确匹配国际可信HTTPS地址。远程模式禁用simulate-paid；缺配置或配置不符不得下单。
- cryptography已加入运行依赖；远端已有支付配置仅保留，不输出、不自动启用。浏览器不能读取完整平台密钥。
- 隔离PG与浏览器fixture不代表正式收款联调。渠道批准、真实回调及支付联调仍依赖外部条件，不得用模拟成功声称正式可收款。
- 已随京东云#17部署，真实商品3个但商品paymentMethods与purchaseUrl均为空；未启用真实支付宝收款，未测试正式扣费。配置/批准渠道和国际回调联调为待办。
