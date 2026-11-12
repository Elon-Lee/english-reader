# 国内与国际入口并行

更新时间：2026-11-12（Asia/Shanghai）

## 目标与授权

- 用户已确认实施并保数据发布京东云；工作分支 `feat/dual-entry-commerce`，基线 `7a0d16e`。设计和计划位于 `docs/superpowers/{specs,plans}/2026-11-12-dual-entry-commerce*.md`。
- 国内主域保留Astro博客，learn提供阅读；国际10ye.cc恢复原首页、会员、订单与支付。两站都要求邀请码，不开放自由注册。
- 单仓库同一业务主线，不维护长期国内/国际业务分支；不重装、不删数据、不做真实收费测试。

## 实现与关键文件

- `frontend/src/sites/cn|intl` 通过Vite `@site` 独立构建，共用阅读器、账号和内容管理。国内 `reader/site/` 不含商业依赖或国际素材，国际 `reader/site-intl/` 恢复商业模块。会员入口 `/app?screen=membership`。
- 国际回环HTTP5173，国内回环HTTP5174，共享API8790、PG、Redis、媒体与验证码。Cloudflare沿用5173回源，国内Nginx转5174。端口及后续升级见 `docs/DEPLOYMENT_SITES.md`。
- `saas_sites.py` 校验回环来源、独立本站凭据及可信原始Host；前端覆写客户端内部头。国内前端和API均拒绝商业路径，未知Host421。邮件、验证码、支付返回使用可信站点地址；Cookie各域分别登录。
- `0045_shared_account_entitlements.sql` 增加账号资源策略：原私人账号容量不降低，新国际受邀账号使用商业免费资源；有效权益与统一资源账本跨入口一致，不随来访域名切换额度。登录设备限制也用相同资源模型。
- 定向迁回会员/商品/兑换/支付宝/Paddle模块，保留鉴权、CSRF、管理员权限、租户隔离、验签、金额/币种校验及幂等。生产模拟付款关闭，已退役渠道停用，缺配置不能标记可收款。
- 发布同时包含两份React、博客和同一后端；候选15173/15174/18790整体检查，失败恢复current、站点配置、令牌、Nginx及旧单站拓扑。数据库仅兼容增量迁移。

## 验证与发布状态

- 前端双构建、源码/产物隔离、UI/modern/JS检查通过；隔离Chrome fixtures覆盖首页素材、失败重试、购买深链、会员空订单、下单轮询和邀请码必填，无页面异常。fixtures不是正式收款验收。
- 真实隔离PG/HTTP覆盖两站同账号、偏好一致、统一用量、国内商业404、国际鉴权、伪造内部头拒绝与两站无邀请码400。
- 独立审查发现支付宝notify国际地址门禁、journey购买恢复缺失，已修正并复核通过；同步更新旧国内journey测试的404预期。
- 主代理最终复验：71项站点/网关/路由/支付/资源单元、5项Paddle/权益单元、34项商业真实PG、15项phase7工作台、3项真实双入口HTTP、119项部署及6项博客部署均通过。前端源码/产物、Chrome、modern、UI和JS检查通过；Python编译通过。
- 本轮尚未发布。线上基线 `code-20261111-152232-21f52fbd`，迁移0044，只读计数1用户/2书目/0支付订单/0订阅。发布后核对保留数据。

## 接续与外部条件

- 完成最终验证与源码提交后，执行保数据 `--target 1 --upgrade --app-domain learn.rynenglish.com --blog-domain rynenglish.com --intl-domain 10ye.cc --defer-https --identity-file <已授权私钥路径>`；不能用中间dirty包或完整重装。
- 实际验收Host/API、国内Nginx、Cloudflare严格TLS、容器/配置权限/版本与迁移；不输出凭据。
- 国内DNS、云商放行及直连HTTPS待实际核实；Cloudflare仍回源京东云，不能视为境外部署或备案结论。真实支付还依赖批准渠道配置与联调。
- 节点2GiB，临时1GiB swap `/var/lib/shiyue/paper-glow-deploy-20261111.swap` 未写fstab，重启需恢复。

## 验证命令

```sh
npm run build:sites
npm run test:sites && npm run test:sites:built
npm run test:sites:browser
npm run test:modern && npm run test:ui && npm run check:js
npm --prefix blog run build && npm --prefix blog run verify
PYTHONPATH=tools .local/saas-venv/bin/python -m unittest discover -s tools -p 'test_deployment*.py'
PYTHONPATH=tools .local/saas-venv/bin/python -m unittest tools.test_saas_sites tools.test_saas_gateway tools.test_saas_commercial_http
git diff --check
```

PG集成仅用明确的 `_test` 库；本机使用有可用scrypt的 `.local/saas-venv/bin/python`。

本机浏览器测试需设置 `PLAYWRIGHT_MODULE=/Users/elonlee/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core`，使用已安装Google Chrome，不新增项目依赖。
