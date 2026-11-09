# 纸间微光 · 阅读与资料空间

当前页面使用 React + Ant Design，构建源在 `frontend/`，产物输出到 `reader/site/`。
Python 服务入口为 `tools/reader_server.py`；账号及学习数据使用 PostgreSQL，媒体按账号权限访问。

## 本地开发

在仓库根目录执行 `./start-reader.sh --saas-local`。完整安装、启停、登录与排错见
[`docs/LOCAL_DEVELOPMENT.md`](../docs/LOCAL_DEVELOPMENT.md)。

## 访问与数据

- 注册必须提供有效邀请码，管理员负责邀请码创建与管理。
- 保留原音阅读、资料导入、生词复习、个人学习记录和账号设置。
- 私人资料默认只允许所属账号访问；其他阅读资料需经过权限与内容审核。
- 所有账号采用统一资源规则，不按会员等级区分访问能力。
- 不提供站内商品销售、支付、购买兑换或订阅功能。

## 历史文件

`reader/index.html`、`reader/app.js` 和相关样式保留为旧界面的兼容资料；当前服务入口继续使用 React，
不要把新功能重新接入旧 UI。已执行的 SQL 迁移保留升级链，历史数据库记录不因删除功能而自动清除。

## 验证

在仓库根目录运行 `npm run build:modern`、`npm run test:modern`、`npm run test:ui`、
`npm run check:js` 和 `git diff --check`。涉及账号或资料权限的修改还需运行专用测试数据库上的相关回归。
