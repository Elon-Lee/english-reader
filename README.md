# 纸间微光

个人阅读空间，仅通过有效邀请码注册。站内保留阅读、原音听读、私人资料导入和学习记录；不提供商品购买、支付或会员订阅。

React + Ant Design 前端，Python SaaS 后端，PostgreSQL 16、Redis 7 和本地 Java 旋转验证码服务。

**安装、启动、停止、登录、环境迁移和排错统一以 [本地开发指南](docs/LOCAL_DEVELOPMENT.md) 为准。** 本地调试使用独立数据，不连接远程数据库、缓存、验证码或媒体。

已安装依赖的项目，在项目根目录执行：

```sh
./start-reader.sh --saas-local
```

浏览器打开 `http://127.0.0.1:4173`。默认 `./start-reader.sh` 同样启动这套本地环境。

AI 开发前按 [AGENTS.md](AGENTS.md) 和 [任务索引](AI_CONTEXT/README.md) 读取对应交接文档。
