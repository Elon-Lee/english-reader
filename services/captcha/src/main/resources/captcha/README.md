# 验证码背景图片

`animal-default.jpg` 是用户要求恢复的原 Tianai 动物示例图（猫咪），按原文件复制，不裁剪或重新编码。图片随 JAR 部署，运行时不请求外部图片服务。

- 来源：Tianai 1.5.6 `META-INF/cut-image/resource/1.jpg`。
- 上游：https://github.com/dromara/tianai-captcha，项目许可 MulanPSL-2.0，见 `frontend/public/tianai/LICENSE`。
- 尺寸：600×360。2026-11-05 恢复，替代用户反馈难以识别的书籍图片。

该照片不是项目原创。验证码模板与随机旋转继续使用 Tianai；不能在公开接口返回正确角度或服务端缓存答案。单层居中弹窗和页面坐标归一化修复继续保留。
