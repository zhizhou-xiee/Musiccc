# MSS/0.2 Curve-first PoC

这一版把 MSS 从“音乐摘要”改为“客观事件 + 多变量时间序列 + 显式未知项”。核心层不包含情绪标签、比喻或听后感，避免提前替接收模型解释音乐。

## 生成

```bash
python3 scripts/build_mss_curve_poc.py --audio /absolute/path/to/借月MMM.mp3
```

脚本先核对母带 SHA-256，然后完全离线地生成：

- 500ms RMS 响度曲线；
- 500ms 频谱质心曲线；
- 500ms 频谱变化量曲线；
- 由 20ms 能量帧计算的正向能量变化曲线；
- 每条曲线的 0–63 分位量化值和自适应稀疏关键点；
- 原有 32 条人工听音乐器事件，稳定 ID 不变；
- 曲线客观题与自由解释实验题。

`melody_contour` 明确为 `unknown`：混合母带没有可靠的主旋律分离或人工核验音符，频谱质心不能冒充旋律。

## 输出

- `outputs/mss.curves.json`：完整曲线、事实、来源与未知项。
- `outputs/mss_curve_800.txt`：面向约 800-token 实验预算的稀疏关键点版。
- `outputs/natural_curve_800.txt`：使用相同曲线证据的客观文字基线。
- `outputs/natural_hybrid_800.txt`：使用与 MSS/0.2 压缩版相同曲线、乐器和动作证据的客观自然语言对照。
- `outputs/natural_event_baseline_800.txt`：MSS/0.1 的自然语言事件基线。
- `evaluation-rubric.json`：客观曲线题与开放解释题。
- `metrics.json`：实测预处理时间、代理 Token 区间及事件完整性。

所有 Token 数仍是 UTF-8 字节数换算的代理区间，不是供应商 tokenizer 或账单数值。尚未调用任何模型。
