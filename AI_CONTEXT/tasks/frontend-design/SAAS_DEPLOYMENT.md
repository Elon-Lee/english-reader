# RynEnglish 启动说明入口

原文档中的旧端口、环境变量、SQLite 调试和手动启动流程已经撤销，不再作为操作依据。

本地开发唯一有效说明：[docs/LOCAL_DEVELOPMENT.md](../../../docs/LOCAL_DEVELOPMENT.md)。该文档包含新电脑首次安装、当前机器直接启动、本地管理员登录、停止/重启、数据目录、检查标准和故障排查。

已有依赖时，在项目根目录执行：

```sh
./start-reader.sh --saas-local
```

前端固定 `http://127.0.0.1:4173`，后台固定 `127.0.0.1:8790`，数据库/Redis/验证码全部在本机。

服务器安装/升级使用管理员“平台与部署”，见 [平台部署交接](../platform-operations/HANDOFF.md)。它与本地调试启动是两个独立操作。

