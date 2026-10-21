# 支付方式与运营订单交接

更新时间：2026-10-21（Asia/Shanghai）

## 目标与现状

- 运营后台可动态启用/停用云猫购买、支付宝和兑换码开通；公开套餐页只展示当前可用方式。
- 新增支付宝当面付扫码链路：服务端预下单、异步通知验签后主动查单、核对应用与金额后幂等开通会员。前端仅在当前浏览器会话保存待支付订单号，恢复时通过当前登录用户的订单接口取回二维码和状态。
- 运营后台新增支付宝订单筛选、详情、全额退款及退款状态查询；退款成功且金额完全匹配后才撤销首次开通权益。续费、升级或已有后续会员变更的订单拒绝自动退款，转人工核对。
- 运营后台新增拾页兑换记录列表，支持状态、订单号/批次/兑换码前缀/账号/套餐搜索。此列表仅覆盖拾页兑换码与核销，不包含未同步的云猫订单。
- 用户已创建支付宝个人开发者应用，尚未开通支付产品。真实支付宝当面付仍需产品批准和服务端参数；当前本地服务另启用了隔离的模拟模式，可测试订单/开通/退款，不连接支付宝网关、不产生真实资金交易。
- 购买弹窗权益预览改为紧凑文本行：续费/开通天数和预计到期日并列显示，升级额外显示剩余权益折算；取消普通权益预览的大面积 Alert，加载及错误状态仍保留。Chrome 实测续费预览约 21px（原约 96px），构建、modern smoke、UI 回归、JS 检查、Python 编译及 diff 检查通过。
- 购买弹窗打开时默认选中云猫；若云猫未开放则回退到当前首个可用支付方式。待支付支付宝订单仍会恢复到弹窗状态，但不会覆盖云猫默认选中；点击支付宝入口可查看恢复的订单。
- 兑换码或支付宝开通成功提示提供主按钮“前往会员中心”，直达 `/app?screen=membership`。
- 成功提示位于渠道内容区之外，支付宝支付与兑换码开通成功后均可见，避免支付宝选中态隐藏兑换结果引导。
- 支付或兑换开通确认后清除服务端购买恢复提醒；清除失败不回滚成功结果，并提供重试按钮。

## 关键文件

- `tools/saas_payments.py`：支付宝协议、动态设置、支付与退款订单服务。
- `tools/saas_migrations/0041_alipay_commerce_operations.sql`：支付渠道/退款状态、订单快照与管理查询字段。
- `tools/reader_server.py`：登录用户和管理员支付 API、通知入口。
- `tools/saas_commerce.py`、`tools/saas_redemptions.py`：公开支付方式与兑换记录查询。
- `frontend/src/pages/PublicSite.jsx`：动态购买方式、支付宝二维码、订单状态和恢复。
- `reader/site/assets/payment-alipay.svg`、`payment-cloudcat.svg`：购买弹窗的独立支付方式图示。
- `frontend/src/components/PaymentOperations.jsx`、`frontend/src/pages/AdminPage.jsx`：后台支付设置、支付宝订单与兑换记录。
- `tools/test_saas_payments.py`：RSA2、审批启用门槛与退款结果判定单测。

## 配置与外部条件

- 服务端 `.env` 使用 `ALIPAY_APP_ID`、`ALIPAY_PRIVATE_KEY`、`ALIPAY_PUBLIC_KEY`、`ALIPAY_NOTIFY_URL`、`ALIPAY_PAYMENT_PRODUCT`、`ALIPAY_PAYMENT_PRODUCT_APPROVED`；只在部署环境配置真实值，密钥不得写入仓库、日志或交接文档。
- 仅本地模拟使用 `ALIPAY_TEST_MODE=1` 且 `SHIYUE_DEPLOYMENT_MODE=local`；当前 8790 由 `ALIPAY_TEST_MODE=1 ./start-reader.sh --saas-local 8790` 启动。远端模式即使设置该变量也无法通过 ready 检查；本地模拟订单没有二维码，前端提供明确的“模拟付款成功”动作，网关请求会被服务端拒绝。
- 正式启用前需要在支付宝开放平台完成个人开发者应用对应支付产品申请与审核、回调域名/HTTPS 配置、应用签名配置及真实小额支付/退款联调。个人开发者主体当前尚无支付产品审批，不能真实联调。
- 正式本地库应用 `0041` 前先完成并校验备份 `.local/saas-backups/payments-20261021/20261021T072124Z`；迁移已应用。隔离库 payment 集成 3 项、commerce 回归 13 项和 HTTP smoke 全部通过。不得使用真实销售兑换码做测试。
- 云猫交易/退款查询依赖云猫侧 API 或 webhook；当前没有该接口，因此后台只呈现拾页的兑换码库存与核销流水。

## 验证

- 已通过：`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、相关 Python 编译、支付宝 RSA2/审批/退款状态单测及 `git diff --check`。
- 已通过：支付 PostgreSQL 集成 4 项（动态开关/未批准拦截、本地模拟支付和远端保护、待付二维码恢复、付款幂等开通、后台查询与退款、兑换记录筛选）、commerce PostgreSQL 13 项、完整 HTTP smoke、支付 RSA2/审批/退款单测及前端构建/测试检查。
- 购买弹窗将云猫与支付宝呈现为独立图示入口；所选渠道只显示自身付款信息。支付宝显示订单摘要、真实扫码或不可支付的本地模拟二维码与状态；云猫入口选中后新标签购买，返回时聚焦兑换码框，格式简提示在占位符、获取说明用输入框 Tooltip。云猫外跳提醒已移除。2026-10-21 Chrome 已实测本地模拟创建与开通成功及渠道内容切换；真实支付宝扫码及云猫资金交易仍不属于本地模拟范围。
- 2026-10-21 Chrome 验收：模拟支付宝已支付订单可在会员中心订单列表查看，会员中心未显示待处理购买提醒。直接打开带 `?purchase=pro-30` 的新购买链接会按设计重新记录方案选择并显示一条新提醒；移除该提醒后返回会员中心确认已消失。支付成功和兑换成功处理都调用 `clear_purchase`，状态事件同步更新当前页提醒组件。
- 支付数据库集成脚本：`PYTHONPATH=tools SHIYUE_SAAS_TEST_DATABASE_URL=<专用_test数据库> .local/saas-venv/bin/python tools/test_saas_payments_integration.py`。支付宝真实支付、通知、退款与个人开发者审核仍待外部条件满足。
