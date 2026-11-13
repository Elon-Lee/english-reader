# 国际支付与国内关闭边界

更新时间：2026-11-13（Asia/Shanghai）

- 后续双站导入/空间调整已统一发布京东云 **#27 complete**（源码 `46649cb`、`code-20261113-154904-ef012c6b`）。0046发布新销售版本，进阶/Pro容量改为1/5GB；原价/折扣/两条云猫链接/支付宝page_pay及支付开关保持。公网商品仍提供alipay/cloudcat，发布前后订单3/订阅0，未进行真实付款或回调测试；详情见 [导入交接](../import-media/HANDOFF.md)。下方#26为支付宝接入首次发布记录。

## 电脑网站支付接入（本轮）

- 用户授权配置并调试正式支付宝应用，后续明确授权操作已打开的控制台。从已上线源码 `53bb4a7` 新建 `feat/alipay-page-pay`；国际支付扩展，国内支付门禁保持。控制台确认应用已上线、电脑网站支付及page.pay/query/refund权限已开通；应用网址修改显示审核中。
- 本地已有应用私钥/支付宝公钥，与控制台当前公钥逐一匹配（RSA2048），复用现有密钥，不更换控制台凭据。已准备忽略目录内0600环境文件；密钥不进入源码、日志、文档或前端。先前SM4/appKey不用于支付宝RSA2接入。
- 新增 `ALIPAY_PAYMENT_PRODUCT=page_pay`，电脑收银台RSA2签名链接使用可信订单金额、标题、原始15分钟绝对过期时间；通知固定国际HTTPS支付notify、同步回跳国际会员页（不按回跳参数开通）。原face_to_face兼容；订单快照区分产品，不新增数据库结构。
- 修正真实网关响应原文JSON节点验签（原实现误用通知参数排序规则），保留异步通知参数验签。已签名TRADE_NOT_EXIST映射待支付；过期且支付宝确认不存在的本地订单关闭，允许新请求重试；成功查单严格匹配原订单号，支持TRADE_FINISHED。前端新增收银台链接/恢复/过期/关闭提示，原二维码模式保留。
- 本地双前端/博客构建及商业隔离、modern/UI/JS检查、双站浏览器fixture通过；单元12项含JSON原文/篡改/重复节点/签名/可信回调/过期；专用 `127.0.0.1:55432/shiyue_alipay_page_test` 验证下单幂等、用户归属、恢复、确认、退款及过期重试。测试与真实付款分开，未收费。
- 京东云正式网关只读查询不存在的探针订单，签名请求与RSA2响应验签通过，返回预期不存在/待支付。现已持久化服务端0600配置并完成统一保数据发布 **#26 complete**：源码 `d2409ed`（clean），`current=code-20261113-141503-c5f09bd8`；两前端、博客及共享后端同步切换，未使用defer-https。数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261113-141503-c5f09bd8.dump`；原环境备份 `/srv/shiyue/backups/saas/alipay-before-20261113-configuration.env`，开关备份 `/srv/shiyue/backups/saas/alipay-payment-methods-before-20261113.json`（0600）。密钥只在受限配置中，不写入交接或Git。
- 新服务正式page_pay就绪且testMode=false。使用现有唯一active、邮箱已验证的admin作为审计actor，调用既有 `AlipayService.update_config` 启用支付宝，保留cloudcat/redemption=true，新增1条payment_methods_updated审计；未创建管理员或登录会话。公开商品API确认进阶¥19、Pro¥49均返回alipay/cloudcat，两条云猫链接保留。国内支付API404、learn robots/noindex、博客备案与国内HTTPS/308及两站健康复核通过；国际缺签名notify返回401。
- 真实Chrome已到正式支付宝收银台，显示“进阶会员月卡”¥19.00、收款方“瑞恩英语在线学习”，页面提示付款人与收款人不能相同。调试产生1笔待支付订单、0订阅，未付款、退款或模拟开通。用户随后明确“暂时先不测试”，停止实际付款测试；未来需由用户使用其他付款账号完成一次付款，核实真实异步回调、自动权益和返回页面闭环。收银台可达不代表该闭环已验收。

## 2026-11-13 云猫购买恢复（线上配置）

- 用户明确授权进阶与Pro都使用 `https://catfk.com/item/d2nhyc`（两链接相同，按原值配置）。已通过线上 `CommerceService.update_draft_purchase_url` 为当前在售 `advanced-30-v2`、`pro-30-v2` 补齐空的purchase_url，两版本仍published，增加2条标准 `commerce_purchase_link_updated` 审计。配置即时生效，业务版本仍#24，无代码发布/重建容器。
- 修改前备份 `/srv/shiyue/backups/saas/cloudcat-links-before-20261113-033714.json`（0600）；前后订单、订阅与兑换码数量不变。使用现有唯一active且已验证邮箱的admin身份记录审计，未创建登录会话、订单或收费。
- 线上国际公开商品API已返回两个付费套餐 `paymentMethods:["cloudcat"]` 及用户指定链接；云猫目标HTTP200。国内learn商业API仍404，支付宝仍未配置/未启用。购买必须先登录核对权益，兑换码仍由云猫商品交付；未做真实付款或兑换验收。
- 真实Chrome验证国际套餐页不再显示“暂未开放新购”，两付费套餐公开API均有cloudcat及指定URL，两条购买路由均可打开并要求登录核对方案；未借用真实用户会话验证登录后的按钮点击。截图 `/private/tmp/cloudcat-restored-production.png`，API快照 `/private/tmp/cloudcat-restored-catalog.json`。此前下节的空链接是恢复前排查状态。
- 后续#25国内备案页脚/抓取策略同步发布后，国际商品API复核上述两链接与cloudcat仍保留；匿名Chrome购买弹窗仍要求登录，未创建订单或收费。

## 2026-11-13 线上购买方式排查（只读）

- 当前#24公开商品API正常返回3个商品，但每个 `paymentMethods:[]`、`purchaseUrl:""`；兑换开通仍启用。支付宝应用ID、私钥、公钥、回调、获批产品与批准开关全部未配置，`commerce.payment_methods` 没有保存记录（默认支付宝关闭、云猫与兑换开启）。全部9个历史/现售套餐版本的云猫链接均为空。
- 购买界面仍有支付宝扫码下单与云猫跳转实现（`sites/intl/pages/PublicSite.jsx`）；`saas_commerce.py:174` 按套餐链接过滤云猫，无链接时不会返回该方式；支付宝由 `saas_payments.py` 就绪检查及开关控制。全球payment.methods含cloudcat/configured=true仅表示渠道开关，不代表具体套餐已可购买。
- 历史源码证据：2026-11-09 `810f19a` 私域改造在升级配置中清理 `ALIPAY_/PADDLE_/MBDPAY_/MBD_/CLOUDCAT_` 环境变量；2026-11-12 `3c404e1` 恢复国际代码，双站升级不再清理支付配置，但缺失配置无法从Git恢复。不能由此证明清理前真实参数一定齐全。现存2026-11-11至13日10份发布配置备份均无支付宝参数；未找到可直接恢复的凭据。退役MBDPay仍未恢复。
- 本轮未更改线上配置、链接、订单或支付开关，未创建订单/收费。恢复云猫购买需提供进阶/Pro实际商品链接；恢复支付宝需已有获批应用参数和RSA2密钥，回调固定国际HTTPS `/api/payments/alipay/notify`，并显式启用渠道。不得用测试模式伪装正式支付。

- 用户确认国际恢复会员、订单和支付；总体架构及实际发布状态以 [双入口交接](../dual-entry-commerce/HANDOFF.md) 为准。国内商业页面/API继续404。
- `saas_payments.py` 恢复支付宝、`saas_billing.py` 恢复Paddle、`saas_redemptions.py` 恢复兑换；保留可信国际入口、登录/验证邮箱、CSRF及管理员权限。旧MBDPay等退役渠道仍停用。
- 订单、订阅与资源账本共用；原私人账号保留非存储资源底线，私人存储按0046发布后的免费0/进阶1GiB/Pro5GiB有效上限执行。兼容增量迁移，不清历史交易或覆盖正式数据。
- 保持验签、订单/金额/币种校验和幂等。双入口支付宝notify必须精确匹配国际可信HTTPS地址。远程模式禁用simulate-paid；缺配置或配置不符不得下单。
- cryptography已加入运行依赖；远端已有支付配置仅保留，不输出、不自动启用。浏览器不能读取完整平台密钥。
- 隔离PG与浏览器fixture不代表正式收款联调。渠道批准、真实回调及支付联调仍依赖外部条件，不得用模拟成功声称正式可收款。
- 已随京东云#17部署，真实商品3个但商品paymentMethods与purchaseUrl均为空；未启用真实支付宝收款，未测试正式扣费。配置/批准渠道和国际回调联调为待办。
