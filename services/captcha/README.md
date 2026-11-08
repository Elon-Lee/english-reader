# 拾页 Tianai 验证码内部服务

使用官方 `cloud.tianai.captcha:tianai-captcha-springboot-starter:1.5.6`，只生成和校验 `ROTATE`。Spring Boot 2.7.18，Java 17 字节码，部署使用 JRE 21。浏览器 SDK 及来源记录位于 `frontend/public/tianai/`。

## 构建和启动

```sh
./services/captcha/build.sh
# 在受限配置文件/环境中设置至少 32 字符的 SHIYUE_CAPTCHA_SECRET，不要放到命令参数、Git 或日志。
java -Xms32m -Xmx192m -Djava.awt.headless=true -jar services/captcha/target/shiyue-captcha-1.0.0.jar
```

`build.sh` 先检查 Java 与 javac（JDK 17 或以上），再运行 `clean verify`；`build.sh --check` 仅检查 JDK，不下载 Maven或构建。JDK 优先使用显式 `JAVA_HOME`，其次项目忽略目录 `.local/captcha-tools/jdk`，然后 macOS 已安装的 JDK 21/17 或 PATH。项目内目录应直接包含 `bin/java` 和 `bin/javac`，macOS 解压包可将此路径链接到 `Contents/Home`。缺失时在部署任务中给出明确错误，并在前端构建、上传和远程切换前停止。

Maven 优先使用 `MAVEN_BIN` 或现有 Maven；否则下载并校验固定 Maven 3.9.9 到 `.local/captcha-tools/`。产物为 `services/captcha/target/shiyue-captcha-1.0.0.jar`，不提交构建产物。

Docker 使用预先从源码构建的 JAR：

```sh
docker build -t shiyue-captcha:local services/captcha
# 通过部署环境文件传入密钥；Python 和 Java 使用同一密钥。
docker run --network host --env-file /path/to/restricted/captcha.env --memory 384m --pids-limit 64 shiyue-captcha:local
```

Docker 默认最大堆 192 MiB、2 个逻辑 CPU、Tomcat 最多 8 个工作线程；Java 强制绑定 `127.0.0.1`，默认端口 18080。不要发布此服务到公网。无 Redis 或外部图片服务依赖。未启用 actuator、CORS 或原生二次验证接口。

## 内部协议

- `GET /health`：无需密钥，返回 `{"status":"ok"}`，不含配置或挑战数据。
- `GET /gen?type=ROTATE`：必须 `X-Captcha-Secret`；返回原生 TAC JSON（`code/msg/data/success`），`data` 包含 `id/type/backgroundImage/templateImage` 等。图片为本地依赖包资源生成的 data URL；拒绝其他类型。
- `POST /check`：必须 `X-Captcha-Secret`，JSON `{"id":"ROTATE_…","data":<SDK轨迹对象>}`；成功严格返回 `code:200, success:true, data:{id:…}`。失败 `success:false`，过期/错误轨迹通常 HTTP 200 但业务码不为 200；畸形请求 HTTP 400、超出 64 KiB HTTP 413、无效密钥 HTTP 401、服务异常 HTTP 503。

挑战有效期 120 秒，一次检查即原子消费，成功/失败均不能重放。使用自有受限内存 `CacheStore`（最多 10000 条，满时淘汰最早条目）修复官方本地缓存 remove 操作在过期清理前仍可读取的问题；轨迹校验继续使用官方 `SimpleImageCaptchaValidator`、`ParamCheckCaptchaInterceptor` 和 `BasicTrackCaptchaInterceptor`。进程重启使未完成挑战失效；Python 负责场景/邮箱绑定、限流和一次性业务票据。

官方 SDK 的轨迹为页面绝对坐标，适配层在校验有限值后将坐标相对 pointer-down 归一化，再交给官方校验器；不修改角度容差或跳过轨迹检查。背景按用户反馈恢复为随 JAR 部署的 `captcha/animal-default.jpg`（原 Tianai 动物图），来源见该目录 README。

## 验证

`./services/captcha/build.sh` 的 8 项测试覆盖真实离线旋转图像生成、零起点及带页面偏移的正确轨迹、错误轨迹、过期、重放、内部鉴权、类型限制、畸形请求和请求体上限。无需数据库。Docker 镜像需在有 Docker 的环境构建验收；本次京东云已有实际 Docker 发布验证。
