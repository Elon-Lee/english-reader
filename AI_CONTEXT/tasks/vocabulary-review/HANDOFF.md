# 生词复习学习闭环交接

更新时间：2026-10-23（Asia/Shanghai）

## 2026-10-23 主题背景补齐（本地，未发布）

- `frontend/src/styles.css` 接入根布局当前调色板的 `--study-primary` / `--study-tint` / `--study-tint-soft`：今日复习主卡、导航/词数控件、状态标签、方法说明带、原句提示和复习结算背景随松林绿/雾蓝/鸢尾紫切换；配套文字、图标和分隔线同步适配。评分按钮保留原有语义色，未修改复习业务或 API。
- 已重建 `reader/site/`。构建、modern smoke、UI 22 项、JS 检查、Python 编译（reader_server/saas_auth/saas_review）及 `git diff --check` 通过；本轮未做浏览器实测，未发布生产。

## 目标与现状

PC 第一版已本地实现：阅读收藏 → 今日计划 → 主动回忆 → 薄弱词巩固 → 本轮结算 → 下次复习/回原文。沿用 React + Ant Design 深绿暖白风格，真实 API，无静态业务演示数据。未发布生产。

## 已完成

- 2026-10-20 首页接复习汇总、active 恢复与 latest 回顾，完成主操作返回学习空间查看成果。URL 支持 `review=resume|summary`、`size=5|10|20`、`scope=all` 及 `words=词条ID列表`；阅读结算进入本次新词范围，零到期可提前巩固。
- start API 新增 `scope=selected,vocabularyIds=[正整数]`，1–100 个 ID，仅从当前用户可访问词条取交集；选词写入会话 options，同幂等键异选词拒绝。现有 active 会话优先恢复，不能覆盖未完成队列。隔离 PostgreSQL `test_saas_review.py` 目前 32 项通过（含 phase7 8 项），新增计划/汇总/新词日期/签到分离/选词归属/奖励有效性/官方下架测试。Chrome 已走通阅读新词 → 指定新词复习 → 首页成果。

- 今日复习与生词本双入口；5/10/20 词、到期/薄弱/全部范围；真实今日去重词数、近 7 天复习天数、来源/状态/文本筛选和分页。
- 先隐藏答案，原句可选提示，揭示释义后四档自评。忘记/模糊本轮末尾仅重练一次，跳过不计成果；提示与巩固不计独立回忆。暂停、刷新和重新进入恢复服务端进度。
- 结算区分实际练习、首次独立自评记得、巩固后记得、仍需巩固及跳过；不声称客观正确率或长期掌握。下一轮安排、返回书架、定位原文句子形成复访闭环。
- 新增 saas_review.py 与 migration 0039。GET /api/workspace/review，POST /api/workspace/review/start、/api/workspace/review/answer；要求验证邮箱，写接口保留 CSRF。私人归属及官方发布/授权/当前收藏均校验。
- 服务端队列按词条 ID 固定，作答回执、排程、学习事件和每日计数同事务；账号/会话行锁、稳定请求键保证并发与重试不重复计数，同键异参和过期题号返回冲突。失去来源访问或缺释义只能跳过。
- 忘记 10 分钟、模糊/提示/巩固后记得 1 天；独立记得/轻松按已有间隔延长，上限 90 天。原阅读器新收藏立即到期、编辑已有词保留排程；移除旧 TTS 复习入口。
- 本地正式库已备份并迁移 0039，8790 已重启加载；5173 可查看。备份：.local/saas-backups/vocabulary-review-20261020/150432-database.dump。

## 验证

- npm run build:modern、test:modern、22 项 test:ui、check:js，相关 Python 编译及 git diff --check 通过。构建保留既有大分包提示。
- 隔离 PostgreSQL tools/test_saas_review.py 共 24 项通过（含复用 phase7 的 8 项）；覆盖 HTTP 鉴权/CSRF、用户隔离、并发/幂等、原子回滚、提示/巩固/跳过、来源失效、官方访问及排程边界。新建隔离库 HTTP smoke 通过。
- Chrome 实测正式账号只读首页；全部练习写入隔离库测试账号。走通完整 5 词 7 题、暂停刷新恢复、结算及原文定位；搜索空态、薄弱/来源筛选通过；1280×900 PC 首页与答案区无横向溢出。
- 截图和 HTTP 日志：.local/debug/product-design/vocabulary-20261020/。测试数据仅存在隔离库，不能作为正式账号成绩。

## 未完成与边界

- 未发布生产；首页联动发布需包含迁移 0039/0040。移动端视觉仍未进入优化阶段。
- 原声听写、输入判分、跨轮长期掌握模型、提醒通知及复习转化专属报表尚未实现。
- 商业承接沿用回阅读后的既有真实权益触限/购买恢复流程，本轮不新增收费限制或付费能力。
- 复习会话尚未单独加入账号数据导出；注销仍沿用现有账号生命周期规则。

## 关键文件与验证命令

- frontend/src/pages/VocabularyPage.jsx、frontend/src/styles.css、frontend/src/main.jsx
- frontend/src/pages/ReaderPage.jsx（sentence 路由定位、新词排程）
- tools/saas_review.py、tools/reader_server.py、tools/saas_migrations/0039_vocabulary_review.sql
- tools/test_saas_review.py；测试库必须以 _test 结尾，禁止指向正式库。

验证：npm run build:modern；npm run test:modern；npm run test:ui；npm run check:js；Python 编译上述 3 个 Python 文件；隔离库执行 tools/test_saas_review.py；./start-reader.sh --saas-smoke 8795；git diff --check。
