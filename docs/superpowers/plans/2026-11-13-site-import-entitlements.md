# 双站导入权限实施计划

> 执行方式：本会话内顺序实施，使用 executing-plans；不派生代理。

**Goal:** 国内关闭私人导入、保留管理员官方导入；国际免费提示升级并强制进阶1GB/Pro5GB。

**Architecture:** `ResourceService`统一计算私人导入权限/容量；可信入口过滤国内导入API，国际写入口与服务执行前再次校验；`@site`隔离升级引导。增量迁移保留历史销售快照并发布新版本。

**Tech Stack:** Python、PostgreSQL、React、Ant Design、Vite。

- [x] 在`tools/test_private_resources.py`、`tools/test_saas_sites.py`补容量/导入策略失败测试；执行 `PYTHONPATH=tools .local/saas-venv/bin/python -m unittest tools.test_private_resources tools.test_saas_sites`确认缺失行为。
- [x] 实现`saas_resources.py`导入能力、`saas_sites.py`国内路径边界、`reader_server.py`上传前门禁与`saas_imports.py`服务层检查；保持取消/清理与官方管理员规则。
- [x] 新增`0046_private_import_entitlements.sql`，从当前现售商品复制新不可变版本、容量及文案，迁移在独立_test库验证前后链接与快照。
- [x] 在`@site`增加导入能力/升级处理，`main.jsx`统一按需校验及加载状态，工作台/书架按站点显示导入、管理员后台官方导入保留。国际套餐卡片免费显示“不支持”，清除免费可导入文案。
- [x] 扩展真实HTTP/PG和双站浏览器fixture验证：伪造头不可绕过、免费点击引导、付费打开、国内无按钮及无导入请求。
- [x] 运行两前端/博客构建与隔离、modern/UI/JS、相关Python测试及编译、diff检查，恢复本轮构建产物。
- [x] 更新对应HANDOFF与全局索引，记录实际验证及未发布状态。
