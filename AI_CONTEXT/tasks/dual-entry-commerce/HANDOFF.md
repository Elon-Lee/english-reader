# 国内与国际入口并行

更新时间：2026-11-12（Asia/Shanghai）

## 目标与授权

- 2026-11-12用户确认国内主页及10ye.cc流程验收通过，要求合并并推送至现有默认主线 `main`（已明确无需新建master）。后续不分叉两套核心业务，先声明共享核心/国内扩展/国际扩展；规则已写入根 `AGENTS.md` 与 `docs/DEPLOYMENT_SITES.md`。
- 每次程序发布必须同一提交同时交付两前端、博客及共享后端。已核实发布器的构建/候选/切换/回退整体覆盖两站；`package.json` 的 `deploy:jdcloud` 默认由完整部署 `--saas` 改为保数据 `--upgrade`。本轮仅修改入口命令和文档，不重新发布已验收的线上#19。
- 本轮主线合并验证：双React构建/产物隔离、博客构建/41页15文章审计、前端站点测试（5 Python+6 Node）、modern/UI/JS检查、120项部署回归、6项博客部署、发布相关Python编译和diff-check均通过。通过npm的 `--help` 无副作用确认默认命令实际传入 `--upgrade`；本轮生成的已跟踪React产物恢复后再提交，不把产物混入合并。

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

- 2026-11-13已按用户要求补装国内两域Let’s Encrypt HTTPS/80→443跳转，`https_deferred:false`；不发布业务代码，current仍#23，国内5174/国际5173/API8790拓扑保持。严格公网TLS、双域HTTP308、Chrome真实验证码生成、国际健康验证通过；43项入口/双入口部署回归通过。续期定时器已active/enabled；详情及续期验收见 [博客分站交接](../blog-domains/HANDOFF.md)。

- 最新为国内博客页脚布局发布 **#23 complete**，`current=code-20261113-103129-858fe5ab`、源码 `ce05402`；两前端/博客/后端同步升级，备案居中/版权靠右/移除页脚导航已公网验证，国际健康正常。详情见博客交接。

- 最新为备案号展示发布 **#22 complete**：`current=code-20261113-102413-ab033c51`、源码 `6d892f4`（clean），同步升级两前端/博客/后端；国内博客页脚真实备案号及工信部链接已公网Chrome验证，国际健康正常。仅国内博客配置变化，详情见 [博客交接](../blog-domains/HANDOFF.md)。

- 最新国内博客扩展发布为2026-11-13 **#21 complete**：`current=code-20261113-095135-d559ce0c`、源码 `f55dbe9`，两前端/博客/后端同步保数据升级。博客调整为AI英语工具主题、19篇文章；50个正常公网页面匹配本地，国际HTTPS健康正常，数据1/2/2/0/0与sites配置保持。实现分支 `feat/blog-ai-english-tools` 尚未合并；发布详情和#20配置读取失败处理见 [博客交接](../blog-domains/HANDOFF.md)。下方#19及更早为历史记录。

- 最新为博客改版发布 **#19 complete**，`current=code-20261112-180050-05f3c3a1`、源码 `e8b1ccd`（clean）。仅改博客展示与内容，双入口配置/端口保持；国际公网健康正常、数据仍1用户/2书目/2内容书/0支付订单/0订阅。四个AI栏目、12篇新文、40个正常公网页面验收见 [博客交接](../blog-domains/HANDOFF.md)。下方#17/#18为业务恢复和端口开放时验证记录。

- 前端双构建、源码/产物隔离、UI/modern/JS检查通过；隔离Chrome fixtures覆盖首页素材、失败重试、购买深链、会员空订单、下单轮询和邀请码必填，无页面异常。fixtures不是正式收款验收。
- 真实隔离PG/HTTP覆盖两站同账号、偏好一致、统一用量、国内商业404、国际鉴权、伪造内部头拒绝与两站无邀请码400。
- 独立审查发现支付宝notify国际地址门禁、journey购买恢复缺失，已修正并复核通过；同步更新旧国内journey测试的404预期。
- 主代理最终复验：71项站点/网关/路由/支付/资源单元、5项Paddle/权益单元、34项商业真实PG、15项phase7工作台、3项真实双入口HTTP、119项部署及6项博客部署均通过。前端源码/产物、Chrome、modern、UI和JS检查通过；Python编译通过。
- 京东云任务 **#17 complete**，正式版本 `code-20261112-113233-fafb1495`，源码 `3c404e1`，sourceDirty=false，发布包SHA-256 `980f979fb17d5b8e3d46adad019795d220828970649d3caedc435d26b20f6a48`。已完成候选双前端、迁移完整性、真实原音CPU检查和正式切换。
- 发布前后均为1用户/2书目/2内容书/0支付订单/0订阅，原用户仍private；迁移0045。数据库备份 `/srv/shiyue/backups/saas/pre-upgrade-code-20261112-113233-fafb1495.dump`（0600），配置备份同目录 `settings-code-20261112-113233-fafb1495/`。七容器运行，API/双前端均回环监听，cryptography46.0.7可导入。
- 正式源站两入口首页/登录/静态资源200；未登录认证与资源401，国际会员401/定价200/真实商品3个，国内商业404。主域文章/关于/RSS200、API/登录404，未知或跨站Host421；直连API无网关凭据403。两站真实验证码启用，前端独立令牌文件0600且仅含本站令牌，sites.json v2端口正确。
- `https://10ye.cc` 已严格TLS验证：首页/定价/7个入口资源/健康/验证码配置/商品200，未登录认证401。Cloudflare保持active/enabled、4连接，未更换隧道配置或凭据。
- 真实公网Chrome已渲染国际首页和定价，无API fixtures或付款操作；定价页显示真实免费/进阶/Pro额度与“暂未开放新购，可使用已有兑换码”。截图 `/private/tmp/english-reader-dual-entry-check/intl-production-{home,pricing}.png`。初次networkidle等待超时，改用DOM及真实方案标题等待完成验收，不把该超时记为页面成功。
- 国内Nginx源站80主域/learn正确，主域构建无learn链接；服务器侧主域HTTP200，本机固定真实IP公网HTTP仍为JDTP403。learn在服务器解析未得到A；443无监听，国内公网HTTPS未完成。不能将源站可用写成公网已放行。
- 国际恢复真实3个商品，但当前每个商品paymentMethods为空、purchaseUrl为空，支付宝未就绪；已部署流程不代表已能真实收款。未开启渠道、未执行收费或模拟生产付款。

## 接续与外部条件

- 用户要求5174监听所有IPv4供测试，已增加 `cn_public_preview` 显式配置与固定IP博客预览。开启时国内正式进程0.0.0.0:5174，IP仅映射静态博客，域名分站/国际回环/候选回环不变。实现见 `saas_frontend_server.py`、`deployment/manager.py`，运维说明见部署文档。
- **端口开放发布#18 complete**：`current=code-20261112-143047-2b622ca0`，源码 `0e0ea91`（clean），包SHA-256 `cd6517ff8b78aa160b9e75723cc940d889c630a720e0e9c4db401636c32656ab`。持久化sites.json已开启 `cn_public_preview:true`；修改前配置备份 `shared/config/sites-before-public-preview-20261112.json`。
- 本轮34项入口/部署相关测试、120项完整部署回归、Python编译、diff-check、发布双构建/博客隔离及候选检查通过。公网 `http://117.72.209.44:5174/` 和3个入口资源均200，Chrome实际打开无页面异常；IP API404、learn登录200、国际200与公网健康正常。实际监听0.0.0.0:5174，5173/8790仍127.0.0.1，数据仍1用户/2书目/2内容书。浏览器截图 `/private/tmp/cn-public-preview-20261112.png`。
- 后续普通保数据升级自动读取sites.json v2；不要完整重装。源码与两份前端使用同一提交，共同阅读业务只改一次。
- 国内两域A解析至117.72.209.44、HTTPS与80跳443已于2026-11-13验收；后续升级继续读取已保存的5174端口与 `https_deferred:false`，不要重新延后HTTPS。
- Cloudflare仍回源京东云，不能视为境外部署或备案结论。真实支付还需获批渠道配置、国际回调地址及实际联调，保留待办。
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
