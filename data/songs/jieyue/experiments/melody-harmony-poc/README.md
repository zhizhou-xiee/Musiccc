# 《借月》旋律 / 和声 PoC 0.1

本实验尝试补上 MSS 的旋律走向，并验证和弦候选是否足够可靠。自动候选本身不直接进入生产；只有负责人实际试听通过、明确标记 `publish_to_mcp` 且适合单线表示的歌词行，才会由 `build_mcp_data.py` 压缩后发布。调性、和弦和多人声单线候选仍只保留在后台实验数据中。

## 输入与隐私边界

- 输入母带：负责人提供的 48 kHz、24-bit、双声道 WAV。
- 人声 / 伴奏：本机使用 Demucs `htdemucs` 二分轨生成。
- WAV、MP3 和分轨均保留在 Git 仓库之外。
- 仓库只保存可复现实验脚本、自动候选 JSON 和不含音频的校对工具。

## 生成

先在本机分轨：

```bash
python -m demucs.separate -n htdemucs --two-stems vocals -o /private/tmp/musiccc-wav-stems /path/to/master.wav
```

再生成候选：

```bash
python scripts/analyze_melody_harmony_poc.py \
  --master /path/to/master.wav \
  --vocals /path/to/vocals.wav \
  --accompaniment /path/to/no_vocals.wav
```

Python 依赖见 `scripts/requirements-melody-poc.txt`。输出为 `outputs/candidates.json`。

## 输出内容

- 72 句歌词各 16 个稀疏旋律候选点，包含休止 / 低置信度空值。
- 两遍副歌 11 对对应歌词的相对旋律轮廓相关与中位音高差。
- 全曲调性前五候选。
- 自动速度候选；本实验不推断拍号。
- 每四个跟踪拍形成的大小三和弦模板候选。第一、第二候选差距不足 0.08 时强制留空。

候选层保留自动状态、失败原因和人工观察，供后台审计。人工流程见 `tools/melody-review/README.md`。

负责人第一轮抽听观察保存在 `data/songs/jieyue/source/manual-melody-review-observations.json`。生成脚本只对其中明确记录的分析窗口、概率门槛和采样格数应用局部覆盖；双主唱 / 多主唱片段标为单旋律表示不适用，不会用一条主导音高曲线冒充完整声部。
