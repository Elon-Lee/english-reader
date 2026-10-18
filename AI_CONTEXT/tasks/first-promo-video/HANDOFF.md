# 首条产品推广视频交接

## 目标

为拾页制作第一条短视频平台推广素材，优先适配剪映继续编辑。

## 当前完成

- 2026-10-18 已用真实产品截图制作 9:16 竖屏成片，约 27.5 秒。
- 成片包含阅读器总览、原音与逐句字幕、点词释义/语境、学习记录和品牌收尾。
- 已拆出无旁白分镜视频、中文配音 WAV、SRT 字幕和剪映时间轴说明。

## 关键文件

- `.local/promo/20261018-shiye-first-video/shiye-first-promo.mp4`
- `.local/promo/20261018-shiye-first-video/video-silent.mp4`
- `.local/promo/20261018-shiye-first-video/voice.wav`
- `.local/promo/20261018-shiye-first-video/captions.srt`
- `.local/promo/20261018-shiye-first-video/jianying-edit-sheet.md`
- `tools/create_promo_video.py`

## 未完成/外部条件

- 尚未在剪映桌面端打开工程；当前输出是可导入剪映的素材包，不是剪映专有草稿格式。
- 尚未执行短视频平台真实发布；发布文案和封面可在剪映检查后按平台再微调。

## 验证

- 已使用 FFmpeg 生成并合并四段 1080x1920、30fps 片段。
- 需继续检查：MP4 播放、音视频时长、SRT 编码和关键帧画面。
