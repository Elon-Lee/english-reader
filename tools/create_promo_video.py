#!/usr/bin/env python3
"""Build the first vertical product promo from checked-in product screenshots."""

from pathlib import Path
import subprocess
import json


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".local/promo/20261018-shiye-first-video"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
VOICE = OUT / "voice.aiff"
VOICE_WAV = OUT / "voice.wav"


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def make_scene(source: Path, title: str, subtitle: str, scene: Path, duration: int) -> None:
    image = scene.with_suffix(".png")
    run("swift", str(ROOT / "tools/render_promo_frame.swift"), str(source), title, subtitle, str(image))
    run(
        "ffmpeg", "-y", "-loop", "1", "-i", str(image), "-t", str(duration),
        "-vf", "scale=1080:1920", "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(scene),
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assets = {
        "reader": ROOT / "reader/site/product/reader-overview.jpg",
        "word": ROOT / "reader/site/product/reader-word-panel.jpg",
        "workspace": ROOT / "reader/site/product/workspace-overview.png",
        "insights": ROOT / "reader/site/product/learning-insights.png",
    }

    scenes = [
        (assets["reader"], "看懂英文，不必来回切页面", "原文、原音、字幕，放在同一个阅读空间", "01-hook.mp4", 5),
        (assets["reader"], "听一句，读一句，跟着原音走", "逐句播放 · 自动定位 · 保留真实音视频", "02-reader.mp4", 6),
        (assets["word"], "遇到生词，点一下就知道", "释义、语境、例句，在当前句子里理解", "03-word.mp4", 6),
        (assets["insights"], "每天读一点，进步看得见", "学习记录帮你把阅读变成持续习惯", "04-cta.mp4", 10),
    ]
    for source, title, subtitle, name, duration in scenes:
        make_scene(source, title, subtitle, OUT / name, duration)

    concat = OUT / "concat.txt"
    concat.write_text("\n".join(f"file '{(OUT / name).as_posix()}'" for *_, name, _ in scenes) + "\n", encoding="utf-8")
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(OUT / "video-silent.mp4"))

    script = (
        "还在看英文的时候，\n"
        "一会儿查词，一会儿切字幕，一会儿又找不到刚才听到的那句？\n"
        "拾页，把原文、原音和逐句字幕放在同一个阅读空间。\n"
        "听一句，读一句，点一下单词，就能看到它在当前语境里的意思。\n"
        "每天读一点，学习记录会留下你的真实进步。\n"
        "这是拾页，给想把英文真正读进去的人。"
    )
    (OUT / "voice-script.txt").write_text(script, encoding="utf-8")
    run("say", "-v", "Tingting", "-r", "178", "-o", str(VOICE), script)
    run("ffmpeg", "-y", "-i", str(VOICE), "-ar", "48000", "-ac", "2", str(VOICE_WAV))
    run(
        "ffmpeg", "-y", "-i", str(OUT / "video-silent.mp4"), "-i", str(VOICE_WAV),
        "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(OUT / "shiye-first-promo.mp4"),
    )

    srt = """1\n00:00:00,000 --> 00:00:03,800\n还在看英文的时候，\n一会儿查词，一会儿切字幕？\n\n2\n00:00:03,800 --> 00:00:08,200\n拾页，把原文、原音和逐句字幕\n放在同一个阅读空间。\n\n3\n00:00:08,200 --> 00:00:13,000\n听一句，读一句。\n跟着真实音视频，把句子读进去。\n\n4\n00:00:13,000 --> 00:00:18,200\n遇到生词，点一下。\n释义、语境、例句，一起看懂。\n\n5\n00:00:18,200 --> 00:00:23,000\n每天读一点，\n学习记录留下你的真实进步。\n\n6\n00:00:23,000 --> 00:00:27,500\n拾页 English Workspace\n给想把英文真正读进去的人。\n"""
    (OUT / "captions.srt").write_text(srt, encoding="utf-8")

    notes = """# 剪映剪辑表：拾页首条产品推广视频

- 画布：1080 x 1920，9:16，30 fps，约 27.5 秒
- 主素材：`shiye-first-promo.mp4`
- 可拆分素材：`01-hook.mp4`、`02-reader.mp4`、`03-word.mp4`、`04-cta.mp4`
- 配音：`voice.wav`，中文女声；剪映中可替换为真人录音
- 字幕：`captions.srt`，建议使用白字、深绿半透明底，底部安全区内显示

## 镜头

| 时间 | 画面 | 口播/字幕 |
|---|---|---|
| 0-5s | 阅读器总览 | 还在看英文时一会儿查词、一会儿切字幕？ |
| 5-11s | 原音、逐句字幕、播放器 | 原文、原音和逐句字幕放在同一个阅读空间 |
| 11-17s | 点词后的词典与语境面板 | 点一下单词，就能看到当前语境里的意思 |
| 17-23s | 学习记录 | 每天读一点，留下真实进步 |
| 23-27.5s | 品牌收尾 | 拾页，给想把英文真正读进去的人 |

发布建议：标题用“把英文阅读，变成每天都能坚持的事”，正文写“原文 + 原音 + 逐句字幕 + 点词释义，第一次把这些放在一起。评论区放产品入口。”
"""
    (OUT / "jianying-edit-sheet.md").write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
